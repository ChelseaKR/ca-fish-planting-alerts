import Foundation
import XCTest
import UserNotifications
@testable import CAFishPlanting
@testable import PlantingCore

@MainActor
final class AppEnvironmentTests: XCTestCase {
    /// `AppEnvironment` persists to the app's real Application Support
    /// directory (by design — that's what makes it offline-first). Without
    /// this, test methods leak favourites/alert-state across each other
    /// through that shared, real, on-disk directory (found by running on
    /// the simulator: `testUnfavouritingDoesNotReTriggerExplainer` failed
    /// only when run after another test had already favourited something).
    override func setUpWithError() throws {
        let layout = try AppStorageLayout.applicationSupport(bundleIdentifier: Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting")
        try? FileManager.default.removeItem(at: layout.directory)
    }

    func testInitLoadsTheBundledSnapshotWithoutError() {
        let env = AppEnvironment()
        XCTAssertNil(env.loadError)
        XCTAssertNotNil(env.snapshot)
        XCTAssertGreaterThan(env.snapshot?.waters.count ?? 0, 0)
        XCTAssertEqual(env.snapshotOrigin, .bundled, "a freshly-installed app has only the bundled snapshot")
    }

    func testNotificationExplainerShownOnlyOnFirstEverFavourite() throws {
        let env = AppEnvironment()
        let waters = try XCTUnwrap(env.snapshot?.waters)
        let first = try XCTUnwrap(waters.first)
        let second = try XCTUnwrap(waters.dropFirst().first)

        XCTAssertNil(env.pendingNotificationExplainer)
        env.toggleFavourite(first)
        XCTAssertEqual(env.pendingNotificationExplainer?.water.id, first.id, "the first-ever favourite must trigger the explainer")

        env.dismissNotificationExplainer()
        XCTAssertNil(env.pendingNotificationExplainer)

        env.toggleFavourite(second)
        XCTAssertNil(env.pendingNotificationExplainer, "a second favourite must never re-trigger the explainer")
    }

    func testUnfavouritingDoesNotReTriggerExplainer() throws {
        let env = AppEnvironment()
        let water = try XCTUnwrap(env.snapshot?.waters.first)

        env.toggleFavourite(water) // favourite: triggers
        env.dismissNotificationExplainer()
        env.toggleFavourite(water) // unfavourite
        XCTAssertFalse(env.isFavourite(water.id))
        XCTAssertNil(env.pendingNotificationExplainer)

        env.toggleFavourite(water) // favourite again: still not the "first ever" moment... 
        // ...but this app instance has no persisted memory of "already asked" beyond
        // favourites.isEmpty, so re-favouriting after removing every favourite is
        // indistinguishable from a first favourite. That is intentional: the app
        // only ever asks once *per empty->non-empty transition*, and there is no
        // system API to ask "have I already shown my own explainer sheet before"
        // separate from "is notifications permission already decided" — which
        // requestAuthorization() itself is a no-op for once already decided.
        XCTAssertEqual(env.pendingNotificationExplainer?.water.id, water.id)
    }

    /// Favouriting is never gated (see `FreeTier`, PlantingCore, and the
    /// DECISIONS entry that resolves 0007's "owner follow-up"): a default
    /// `AppEnvironment()` has made no purchase, so this exercises the real
    /// default non-purchaser path, not an injected fake.
    func testNonPurchaserFavouritesAreUnconstrained() throws {
        let env = AppEnvironment()
        XCTAssertFalse(env.purchases.isEntitled, "sanity check: a fresh environment must not already be entitled")
        let waters = try XCTUnwrap(env.snapshot?.waters)
        // Well past the old placeholder cap of 3, to prove there is no limit at all.
        XCTAssertGreaterThan(waters.count, 10, "fixture needs enough waters for this test to mean anything")

        for water in waters.prefix(10) {
            env.toggleFavourite(water)
        }
        XCTAssertEqual(env.favourites.count, 10, "a non-purchaser must be able to favourite as many waters as a purchaser")

        // Unfavouriting still works normally.
        let firstFavourite = waters[0]
        env.toggleFavourite(firstFavourite)
        XCTAssertEqual(env.favourites.count, 9)
    }

    func testBackgroundTaskIdentifierMatchesInfoPlistDeclaration() throws {
        let infoPlistURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // CAFishPlantingTests
            .deletingLastPathComponent() // ios
            .appendingPathComponent("CAFishPlanting/Resources/Info.plist")
        let data = try Data(contentsOf: infoPlistURL)
        let plist = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any]
        let declared = plist?["BGTaskSchedulerPermittedIdentifiers"] as? [String] ?? []
        XCTAssertEqual(declared, [BackgroundRefresh.taskIdentifier], "Info.plist must permit exactly the identifier the code registers")
    }

    // MARK: - Notification gating (DECISIONS: local notifications are the paid unlock, not favouriting)

    /// The other half of `PurchaseManagerTests.testPurchaserGetsAScheduledNotificationWhenAFavouritesScheduleChanges`:
    /// exercises the real `performBackgroundRefresh()` path (not just the
    /// pure `FreeTier.notificationsAllowed` predicate) via a mocked network
    /// response, and confirms a non-purchaser never gets a local
    /// notification scheduled even though the exact same schedule change
    /// would notify a purchaser.
    func testNonPurchaserGetsNoScheduledNotificationEvenWhenAFavouritesScheduleChanges() async throws {
        let env = AppEnvironment(refresher: makeMockedSnapshotRefresher())
        XCTAssertFalse(env.purchases.isEntitled, "sanity check: a fresh environment must not already be entitled")

        let snapshot = try XCTUnwrap(env.snapshot)
        let target = try XCTUnwrap(waterWithNoCurrentOrFutureListing(in: snapshot), "fixture needs a water with nothing listed at/after source_week yet")
        env.toggleFavourite(target)
        XCTAssertTrue(env.isFavourite(target.id))

        let (data, _) = try updatedSnapshotFixture(addingListingTo: target.id, after: snapshot.sourceWeek)
        MockSnapshotURLProtocol.responseData = data
        defer { MockSnapshotURLProtocol.responseData = nil }

        let outcome = await env.performBackgroundRefresh()
        XCTAssertEqual(outcome, .updated, "sanity check: the mocked refresh must actually land as an update")

        let center = UNUserNotificationCenter.current()
        let pending = await center.pendingNotificationRequests()
        XCTAssertTrue(pending.isEmpty, "a non-purchaser must never have a local notification scheduled")
        center.removeAllPendingNotificationRequests()
    }

    // MARK: - Refresh on open (launch and return to the foreground)

    private let opened = Date(timeIntervalSince1970: 1_790_000_000) // 2026-09-21

    /// Launch fetches once; a return to the foreground inside the throttle
    /// window doesn't fetch again; one after it does.
    func testOpeningTheAppFetchesOnceThenThrottles() async throws {
        let env = AppEnvironment(refresher: makeMockedSnapshotRefresher())
        MockSnapshotURLProtocol.responseData = try bundledSnapshotData()
        MockSnapshotURLProtocol.requestCount = 0
        defer { MockSnapshotURLProtocol.responseData = nil }

        let first = await env.refreshIfDue(now: opened)
        XCTAssertNotNil(first, "a fresh install must check on first open")
        XCTAssertEqual(MockSnapshotURLProtocol.requestCount, 1)
        XCTAssertEqual(env.snapshotOrigin, .stored, "the fetched snapshot must replace the bundled one")

        let soon = await env.refreshIfDue(now: opened.addingTimeInterval(60 * 60))
        XCTAssertNil(soon, "an hour later is inside the throttle window")
        XCTAssertEqual(MockSnapshotURLProtocol.requestCount, 1, "a throttled open must not touch the network")

        let later = await env.refreshIfDue(now: opened.addingTimeInterval(6 * 60 * 60))
        XCTAssertNotNil(later)
        XCTAssertEqual(MockSnapshotURLProtocol.requestCount, 2)
    }

    /// Launch fires both the root view's `.task` and the `.active` scene
    /// phase: two asks, one GET.
    func testTwoOpensAtOnceShareOneFetch() async throws {
        let env = AppEnvironment(refresher: makeMockedSnapshotRefresher())
        MockSnapshotURLProtocol.responseData = try bundledSnapshotData()
        MockSnapshotURLProtocol.requestCount = 0
        defer { MockSnapshotURLProtocol.responseData = nil }

        async let a = env.refreshIfDue(now: opened)
        async let b = env.refreshIfDue(now: opened)
        let outcomes = await [a, b]

        XCTAssertTrue(outcomes.contains { $0 != nil }, "one of the two opens must fetch: \(outcomes)")
        XCTAssertEqual(MockSnapshotURLProtocol.requestCount, 1, "two opens at once must cost one GET")
        XCTAssertFalse(env.isRefreshing)
    }

    /// Offline at launch: the app says it couldn't check and keeps the
    /// bundled week, labelled with that week. It never shows the week as
    /// empty.
    func testAFailedFetchOnOpenKeepsTheBundledWeekAndSaysSo() async throws {
        let env = AppEnvironment(refresher: makeMockedSnapshotRefresher())
        MockSnapshotURLProtocol.responseData = nil
        MockSnapshotURLProtocol.requestCount = 0
        let before = try XCTUnwrap(env.snapshot)
        XCTAssertFalse(before.thisWeek.isEmpty, "the bundled fixture must list waters for this test to mean anything")

        let outcome = await env.refreshIfDue(now: opened)

        guard case .failed = outcome else { return XCTFail("expected a failed refresh, got \(String(describing: outcome))") }
        XCTAssertEqual(MockSnapshotURLProtocol.requestCount, 1, "sanity check: the fetch really ran and failed")
        XCTAssertEqual(env.snapshot, before, "a failed fetch must keep the last good snapshot")
        XCTAssertEqual(env.snapshotOrigin, .bundled)
        let freshness = try XCTUnwrap(env.freshness(now: opened))
        XCTAssertTrue(freshness.checkFailed)
        XCTAssertEqual(freshness.watersListed, Set(before.thisWeek.map(\.waterID)).count)
        XCTAssertEqual(freshness.headline, "Schedule for the \(before.sourceWeek.label)")
        XCTAssertTrue(freshness.detail.hasPrefix("Couldn't check for a newer schedule, so this is the one that came with the app."), freshness.detail)
        XCTAssertFalse(freshness.summary.localizedCaseInsensitiveContains("no waters"))

        let retry = await env.refreshIfDue(now: opened.addingTimeInterval(10 * 60))
        XCTAssertNil(retry, "a failure is retried after the short interval, not on every open")
        XCTAssertEqual(MockSnapshotURLProtocol.requestCount, 1)
    }
}

private func bundledSnapshotData() throws -> Data {
    guard let url = Bundle.main.url(forResource: "snapshot", withExtension: "json") else {
        throw NotificationGatingFixtureError.bundledSnapshotMissing
    }
    return try Data(contentsOf: url)
}

// MARK: - Notification-gating test support (shared with PurchaseManagerTests)
//
// `SnapshotRefresher.makeSession(protocolClasses:)` exists specifically so a
// test can intercept the snapshot GET without a live network call — see its
// doc comment in `SnapshotRefresher.swift`. These helpers build an "an
// update just landed" snapshot by mutating the real bundled fixture (not a
// hand-built one — see `ios/README.md`'s "real pipeline output" note),
// adding one new `listed` plant to a water chosen to have nothing listed at
// or after `source_week` already, so it is guaranteed "new" on the next
// refresh. File-scope (not nested in one test class) because both
// `AppEnvironmentTests` (non-purchaser: no notification) and
// `PurchaseManagerTests` (purchaser: one notification) need them to
// exercise the same real `performBackgroundRefresh()` integration point.

enum NotificationGatingFixtureError: Error { case bundledSnapshotMissing, waterNotFound }

final class MockSnapshotURLProtocol: URLProtocol {
    /// Set by a test immediately before calling `performBackgroundRefresh()`;
    /// reset to `nil` in a `defer` once that test is done with it. `nil`
    /// fails the request, like a device with no connection.
    static var responseData: Data?
    /// Snapshot GETs that reached this stub. Reset by the tests that count.
    static var requestCount = 0

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == SnapshotEndpoint.host
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requestCount += 1
        guard let url = request.url, let data = Self.responseData else {
            client?.urlProtocol(self, didFailWithError: URLError(.unknown))
            return
        }
        let response = HTTPURLResponse(
            url: url, statusCode: 200, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json", "ETag": "\"mock-update\""]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

func makeMockedSnapshotRefresher() -> SnapshotRefresher {
    SnapshotRefresher(session: SnapshotRefresher.makeSession(protocolClasses: [MockSnapshotURLProtocol.self]))
}

func waterWithNoCurrentOrFutureListing(in snapshot: Snapshot) -> Water? {
    snapshot.waters.first { $0.listedPlants(onOrAfter: snapshot.sourceWeek).isEmpty }
}

/// Returns the mutated snapshot's bytes and the new plant's week-start ISO
/// date, so a test can assert the exact deterministic notification
/// identifier `AlertPlanner`/`PlannedNotification` produces
/// (`plant.<water id>.<week start>`).
func updatedSnapshotFixture(addingListingTo waterID: Water.ID, after sourceWeek: Week) throws -> (data: Data, newWeekStartISO: String) {
    guard let bundledURL = Bundle.main.url(forResource: "snapshot", withExtension: "json") else {
        throw NotificationGatingFixtureError.bundledSnapshotMissing
    }
    guard var json = try JSONSerialization.jsonObject(with: try Data(contentsOf: bundledURL)) as? [String: Any],
          var waters = json["waters"] as? [[String: Any]],
          let index = waters.firstIndex(where: { ($0["id"] as? String) == waterID })
    else {
        throw NotificationGatingFixtureError.waterNotFound
    }

    var utcCalendar = Calendar(identifier: .gregorian)
    utcCalendar.timeZone = TimeZone(identifier: "UTC")!
    // 4 weeks after source_week.start: safely in the future relative to the
    // fixture's own current week, however this fixture is later refreshed.
    let newStart = utcCalendar.date(byAdding: .day, value: 28, to: sourceWeek.start.noonUTC)!
    let newEnd = utcCalendar.date(byAdding: .day, value: 6, to: newStart)!
    let formatter = DateFormatter()
    formatter.timeZone = TimeZone(identifier: "UTC")
    formatter.dateFormat = "yyyy-MM-dd"
    let startISO = formatter.string(from: newStart)
    let endISO = formatter.string(from: newEnd)

    var water = waters[index]
    var plants = (water["plants"] as? [[String: Any]]) ?? []
    plants.append([
        "week": ["start": startISO, "end": endISO, "label": "week of \(startISO)"],
        "species": "Trout",
        "status": "listed",
        "first_observed_at": "2026-09-21T00:00:00Z",
        "last_observed_at": "2026-09-21T00:00:00Z",
    ])
    water["plants"] = plants
    waters[index] = water
    json["waters"] = waters

    let data = try JSONSerialization.data(withJSONObject: json)
    return (data, startISO)
}
