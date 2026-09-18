import XCTest
@testable import PlantingCore

private func utc(_ iso: String) -> Date {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.date(from: iso)!
}

// MARK: - Throttle

final class RefreshThrottleTests: XCTestCase {
    private let throttle = RefreshThrottle.foreground
    private let t0 = utc("2026-09-18T15:00:00Z")

    private func meta(attemptedAt: Date?, failed: Bool) -> SnapshotMeta {
        SnapshotMeta(lastAttemptAt: attemptedAt, lastOutcome: attemptedAt == nil ? nil : (failed ? "failed" : "updated"))
    }

    func testTheShippedThrottleIsSixHoursOrThirtyMinutesAfterAFailure() {
        XCTAssertEqual(throttle.afterSuccess, 6 * 60 * 60)
        XCTAssertEqual(throttle.afterFailure, 30 * 60)
    }

    func testNeverCheckedIsDue() {
        XCTAssertTrue(throttle.isDue(meta: SnapshotMeta(), now: t0), "a fresh install must check on first open")
    }

    func testASuccessfulCheckHoldsOffForSixHours() {
        let m = meta(attemptedAt: t0, failed: false)
        XCTAssertFalse(throttle.isDue(meta: m, now: t0.addingTimeInterval(60)))
        XCTAssertFalse(throttle.isDue(meta: m, now: t0.addingTimeInterval(6 * 60 * 60 - 1)))
        XCTAssertTrue(throttle.isDue(meta: m, now: t0.addingTimeInterval(6 * 60 * 60)))
    }

    func testAFailedCheckRetriesAfterThirtyMinutesNotSixHours() {
        let m = meta(attemptedAt: t0, failed: true)
        XCTAssertFalse(throttle.isDue(meta: m, now: t0.addingTimeInterval(29 * 60)))
        XCTAssertTrue(throttle.isDue(meta: m, now: t0.addingTimeInterval(30 * 60)))
    }

    func testAClockSetBackwardsDoesNotStrandTheApp() {
        let m = meta(attemptedAt: t0, failed: false)
        XCTAssertTrue(throttle.isDue(meta: m, now: t0.addingTimeInterval(-24 * 60 * 60)),
                      "a last attempt in the future means the clock moved; waiting for it would strand old data")
    }

    /// The throttle reads the same meta the store writes, so a background
    /// refresh counts against it and a failure is recognised as one.
    func testTheThrottleReadsWhatTheStoreRecords() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-throttle-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: dir) }
        let bundled = dir.appendingPathComponent("bundled.json")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Fixture.data(Fixture.minimalValid).write(to: bundled)
        let store = try SnapshotStore(layout: AppStorageLayout(directory: dir), bundledSnapshotURL: bundled)

        store.recordFailure("offline", now: t0)
        XCTAssertTrue(store.meta.lastAttemptFailed)
        XCTAssertFalse(throttle.isDue(meta: store.meta, now: t0.addingTimeInterval(60)))
        XCTAssertTrue(throttle.isDue(meta: store.meta, now: t0.addingTimeInterval(30 * 60)))

        store.recordNotModified(now: t0)
        XCTAssertFalse(store.meta.lastAttemptFailed)
        XCTAssertFalse(throttle.isDue(meta: store.meta, now: t0.addingTimeInterval(30 * 60)),
                       "after a success the long interval applies")
    }
}

// MARK: - What the app says about the schedule it shows

final class SnapshotFreshnessTests: XCTestCase {
    /// Fixture week: week of 2026-09-13 (Sun) to 2026-09-19 (Sat), one water listed.
    private func snapshot() throws -> Snapshot { try SnapshotDecoder().decode(Fixture.data(Fixture.minimalValid)) }

    private let midWeek = utc("2026-09-16T18:00:00Z")
    private let weekLater = utc("2026-09-24T18:00:00Z")

    func testACurrentWeekAfterASuccessfulCheck() throws {
        let f = SnapshotFreshness(snapshot: try snapshot(), origin: .stored,
                                  meta: SnapshotMeta(lastAttemptAt: midWeek, lastSuccessAt: midWeek, lastOutcome: "updated"),
                                  isChecking: false, now: midWeek)
        XCTAssertFalse(f.isStale)
        XCTAssertFalse(f.needsAttention)
        XCTAssertEqual(f.check, .succeeded(at: midWeek))
        XCTAssertEqual(f.headline, "Schedule for the week of 2026-09-13")
        XCTAssertEqual(f.summary, "1 water is listed for that week.")
        XCTAssertEqual(f.detail, "This is the newest published schedule.")
        XCTAssertEqual(f.listedBadge, "This week")
        XCTAssertEqual(f.lastSuccessfulCheck, midWeek)
    }

    /// Staleness is judged on the schedule's own calendar
    /// (America/Los_Angeles), not UTC: 06:00Z on Sunday the 20th is still
    /// Saturday the 19th in California, the last day of the week.
    func testStalenessUsesTheScheduleTimeZone() throws {
        let s = try snapshot()
        let saturdayNightInCalifornia = utc("2026-09-20T06:00:00Z") // 23:00 PDT, Sat 19th
        let sundayInCalifornia = utc("2026-09-20T08:00:00Z")        // 01:00 PDT, Sun 20th
        XCTAssertEqual(SnapshotFreshness.scheduleDate(of: saturdayNightInCalifornia), PlainDate(isoDate: "2026-09-19"))
        XCTAssertFalse(SnapshotFreshness(snapshot: s, origin: .stored, meta: SnapshotMeta(), isChecking: false, now: saturdayNightInCalifornia).isStale)
        XCTAssertTrue(SnapshotFreshness(snapshot: s, origin: .stored, meta: SnapshotMeta(), isChecking: false, now: sundayInCalifornia).isStale)
    }

    /// A week that has ended is never called "this week", and is said to be
    /// out of date, even when the check worked (the site had nothing newer).
    func testAnEndedWeekIsLabelledWithItsWeekAndCalledOutOfDate() throws {
        let f = SnapshotFreshness(snapshot: try snapshot(), origin: .stored,
                                  meta: SnapshotMeta(lastAttemptAt: weekLater, lastSuccessAt: weekLater, lastOutcome: "not modified"),
                                  isChecking: false, now: weekLater)
        XCTAssertTrue(f.isStale)
        XCTAssertTrue(f.needsAttention)
        XCTAssertEqual(f.listedBadge, "week of 2026-09-13")
        XCTAssertEqual(f.listedPhrase, "scheduled for the week of 2026-09-13")
        XCTAssertEqual(f.detail, "This is the newest schedule published so far. That week has ended, so this schedule is out of date.")
        for text in [f.headline, f.summary, f.detail, f.listedBadge, f.listedPhrase] {
            XCTAssertFalse(text.localizedCaseInsensitiveContains("this week"), "an ended week called \"this week\": \(text)")
        }
    }

    func testAFreshInstallThatHasNotCheckedYetSaysItIsTheBundledSchedule() throws {
        let f = SnapshotFreshness(snapshot: try snapshot(), origin: .bundled, meta: SnapshotMeta(), isChecking: false, now: weekLater)
        XCTAssertEqual(f.check, .never)
        XCTAssertNil(f.lastSuccessfulCheck)
        XCTAssertEqual(f.detail, "This is the schedule that came with the app. It hasn't been checked for a newer one yet. That week has ended, so this schedule is out of date.")
    }

    func testAFailedCheckIsSaidPlainlyAndKeepsTheLastSuccessTime() throws {
        let lastGood = utc("2026-09-14T12:00:00Z")
        let f = SnapshotFreshness(snapshot: try snapshot(), origin: .stored,
                                  meta: SnapshotMeta(lastAttemptAt: midWeek, lastSuccessAt: lastGood, lastOutcome: "failed", lastError: "offline"),
                                  isChecking: false, now: midWeek)
        XCTAssertTrue(f.checkFailed)
        XCTAssertTrue(f.needsAttention)
        XCTAssertEqual(f.lastSuccessfulCheck, lastGood)
        XCTAssertEqual(f.detail, "Couldn't check for a newer schedule, so this is the last one downloaded.")
        XCTAssertEqual(f.summary, "1 water is listed for that week.")
    }

    func testACheckInProgressIsShownAsChecking() throws {
        let f = SnapshotFreshness(snapshot: try snapshot(), origin: .bundled, meta: SnapshotMeta(), isChecking: true, now: midWeek)
        XCTAssertTrue(f.isChecking)
        XCTAssertEqual(f.detail, "Checking for a newer schedule…")
    }
}

// MARK: - Absence is never rendered as a value

/// Serves the snapshot GET from a canned reply, and counts requests.
final class StubSnapshotProtocol: URLProtocol {
    enum Reply { case offline, http(Int, Data) }
    nonisolated(unsafe) static var reply: Reply = .offline
    nonisolated(unsafe) static var requests = 0

    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == SnapshotEndpoint.host }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        Self.requests += 1
        switch Self.reply {
        case .offline:
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
        case .http(let status, let body):
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        }
    }
}

/// Phrases that report an empty schedule. Each is allowed only when a
/// published snapshot really lists nothing for its week.
func absenceClaims(in text: String) -> [String] {
    ["no waters", "no plantings", "no plants", "nothing", "none", "0 waters"]
        .filter { text.localizedCaseInsensitiveContains($0) }
}

final class FailedFetchNeverRendersAbsenceTests: XCTestCase {
    private var dirs: [URL] = []
    private let now = utc("2026-09-16T18:00:00Z")

    override func tearDown() {
        for dir in dirs { try? FileManager.default.removeItem(at: dir) }
        StubSnapshotProtocol.reply = .offline
    }

    /// A store holding the fixture's week (one water listed), as if it came with the app.
    private func makeStore() throws -> SnapshotStore {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-absence-\(UUID().uuidString)")
        dirs.append(dir)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let bundled = dir.appendingPathComponent("bundled.json")
        try Fixture.data(Fixture.minimalValid).write(to: bundled)
        return try SnapshotStore(layout: AppStorageLayout(directory: dir.appendingPathComponent("support")), bundledSnapshotURL: bundled)
    }

    private func refresher() -> SnapshotRefresher {
        SnapshotRefresher(session: SnapshotRefresher.makeSession(protocolClasses: [StubSnapshotProtocol.self]))
    }

    /// The fixture, one day newer, listing nothing for its week.
    private func emptyWeek(generatedAt: String = "2026-09-14T06:12:44Z") -> String {
        Fixture.minimalValid
            .replacingOccurrences(of: "\"generated_at\": \"2026-09-13T06:12:44Z\"", with: "\"generated_at\": \"\(generatedAt)\"")
            .replacingOccurrences(of: "\"this_week\": [ { \"water_id\": \"cdfw-1001\", \"species\": \"Trout\" } ],", with: "\"this_week\": [],")
    }

    private func freshness(_ store: SnapshotStore) -> SnapshotFreshness {
        SnapshotFreshness(snapshot: store.snapshot, origin: store.origin, meta: store.meta, isChecking: false, now: now)
    }

    func testEveryKindOfFailedFetchKeepsTheLastGoodWeekAndSaysSo() async throws {
        let emptyButBroken = emptyWeek().replacingOccurrences(of: "\"schema_version\": 1", with: "\"schema_version\": 2")
        let cases: [(String, StubSnapshotProtocol.Reply)] = [
            ("offline", .offline),
            ("server error", .http(500, Data())),
            ("not found page", .http(404, Data("<html>Not Found</html>".utf8))),
            ("truncated download", .http(200, Data(Fixture.minimalValid.utf8.prefix(400)))),
            ("empty week in a snapshot this app can't read", .http(200, Data(emptyButBroken.utf8))),
        ]
        XCTAssertNotEqual(emptyButBroken, Fixture.minimalValid, "sanity check: the broken empty week must differ from the fixture")
        XCTAssertTrue(emptyButBroken.contains("\"this_week\": []"), "sanity check: the broken reply must really list nothing")

        for (name, reply) in cases {
            let store = try makeStore()
            let before = store.snapshot
            XCTAssertEqual(before.thisWeek.count, 1, "\(name): precondition, the last good week lists one water")

            StubSnapshotProtocol.reply = reply
            let outcome = await refresher().refresh(into: store, now: now)

            guard case .failed = outcome else { XCTFail("\(name): expected a failed refresh, got \(outcome)"); continue }
            XCTAssertEqual(store.snapshot, before, "\(name): a failed fetch must keep the last good snapshot")
            let f = freshness(store)
            XCTAssertTrue(f.checkFailed, "\(name): the failure must be reported, not hidden")
            XCTAssertEqual(f.watersListed, 1, "\(name): the count must come from the last good snapshot")
            XCTAssertTrue(f.detail.hasPrefix("Couldn't check for a newer schedule"), "\(name): \(f.detail)")
            XCTAssertEqual(f.headline, "Schedule for the week of 2026-09-13", "\(name): the data shown must be labelled with its week")
            let shown = [f.headline, f.summary, f.detail].joined(separator: " ")
            XCTAssertEqual(absenceClaims(in: shown), [], "\(name): a failed fetch rendered as an empty schedule: \(shown)")
        }
    }

    /// The control for the test above: the detector does fire on an empty
    /// week, and that sentence is reachable only from a snapshot the
    /// pipeline published and this app decoded.
    func testAnEmptyWeekIsSaidOnlyWhenAPublishedSnapshotSaysSo() async throws {
        let store = try makeStore()
        StubSnapshotProtocol.reply = .http(200, Data(emptyWeek().utf8))

        let outcome = await refresher().refresh(into: store, now: now)

        XCTAssertEqual(outcome, .updated)
        XCTAssertEqual(store.snapshot.thisWeek, [], "sanity check: the published week really lists nothing")
        let f = freshness(store)
        XCTAssertFalse(f.checkFailed)
        XCTAssertEqual(f.summary, "No waters are listed for that week.")
        XCTAssertEqual(f.headline, "Schedule for the week of 2026-09-13", "even an empty week is named")
        XCTAssertEqual(absenceClaims(in: f.summary), ["no waters"], "the detector must catch the empty-week sentence, or the test above proves nothing")
    }

    /// A newer snapshot that lists nothing but is broken elsewhere must not
    /// get through half-applied: all or nothing.
    func testABrokenNewerSnapshotChangesNothingOnDisk() async throws {
        let store = try makeStore()
        let broken = emptyWeek().replacingOccurrences(of: "\"id\": \"cdfw-1001\"", with: "\"id\": \"not-a-cdfw-id\"")
        XCTAssertNotEqual(broken, emptyWeek(), "sanity check: the corruption must apply")
        StubSnapshotProtocol.reply = .http(200, Data(broken.utf8))

        let outcome = await refresher().refresh(into: store, now: now)

        guard case .failed = outcome else { return XCTFail("expected failure, got \(outcome)") }
        XCTAssertEqual(store.snapshot.thisWeek.count, 1)
        XCTAssertEqual(store.origin, .bundled, "nothing was written, so the app still shows the bundled week")
        XCTAssertFalse(FileManager.default.fileExists(atPath: store.layout.snapshotFile.path))
    }
}
