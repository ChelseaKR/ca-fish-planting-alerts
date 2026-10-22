import XCTest
@testable import PlantingCore

/// A clock a test moves by hand.
private final class TestClock: @unchecked Sendable {
    private let lock = NSLock()
    private var current: Date
    init(_ start: Date) { current = start }
    var now: Date { lock.withLock { current } }
    func advance(days: Double) { lock.withLock { current = current.addingTimeInterval(days * 24 * 60 * 60) } }
    func set(_ date: Date) { lock.withLock { current = date } }
}

final class ReviewPromptTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_790_000_000) // 2026-09-21

    private func prompter(launches: Int = 0, askedAt: [Date] = [], askedVersions: [String] = [],
                          clock: TestClock) -> ReviewPrompter {
        var p = ReviewPrompter(state: ReviewPromptState(askedAt: askedAt, askedVersions: askedVersions),
                               now: { clock.now })
        for _ in 0..<launches { p.recordLaunch() }
        return p
    }

    // MARK: Never at first launch

    func testTheFirstLaunchNeverAsksWhateverTheMoment() {
        let clock = TestClock(start)
        var p = prompter(launches: 1, clock: clock)
        XCTAssertFalse(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
        XCTAssertFalse(p.considerAsking(.finishedWithWater, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
        XCTAssertTrue(p.state.askedAt.isEmpty)
    }

    // MARK: The third launch with a favorite

    func testFinishingWithAWaterAsksFromTheThirdLaunchAndOnlyWithAFavorite() {
        let clock = TestClock(start)
        var p = prompter(launches: 2, clock: clock)
        XCTAssertFalse(p.considerAsking(.finishedWithWater, hasFavorites: true, appVersion: "1.1.0", isBusy: false),
                       "second launch")
        p.recordLaunch()
        XCTAssertFalse(p.considerAsking(.finishedWithWater, hasFavorites: false, appVersion: "1.1.0", isBusy: false),
                       "third launch, no favorite")
        XCTAssertTrue(p.considerAsking(.finishedWithWater, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
        XCTAssertEqual(p.state.askedAt, [start])
        XCTAssertEqual(p.state.askedVersions, ["1.1.0"])
    }

    // MARK: After opening a planting alert

    func testReadingAPlantingAlertAsksFromTheSecondLaunch() {
        let clock = TestClock(start)
        var p = prompter(launches: 2, clock: clock)
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
    }

    // MARK: Never mid-task

    func testNothingElseOnScreenOrUnderWay() {
        let clock = TestClock(start)
        var p = prompter(launches: 5, clock: clock)
        XCTAssertFalse(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: true))
        XCTAssertFalse(p.considerAsking(.finishedWithWater, hasFavorites: true, appVersion: "1.1.0", isBusy: true))
        XCTAssertTrue(p.state.askedAt.isEmpty)
    }

    // MARK: Spacing, versions and the yearly cap

    func testOncePerAppVersion() {
        let clock = TestClock(start)
        var p = prompter(launches: 5, clock: clock)
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
        clock.advance(days: 200)
        XCTAssertFalse(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: false),
                       "same version, long after")
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.2.0", isBusy: false))
    }

    func testNotAgainFor120DaysEvenInANewVersion() {
        let clock = TestClock(start)
        var p = prompter(launches: 5, clock: clock)
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
        clock.advance(days: 119.9)
        XCTAssertFalse(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.2.0", isBusy: false))
        clock.advance(days: 0.2)
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.2.0", isBusy: false))
    }

    /// 120-day spacing alone would allow a fourth ask on day 360. The app's
    /// own cap matches iOS's: three in any 365 days.
    func testAtMostThreeInAnyYear() {
        let clock = TestClock(start)
        var p = prompter(launches: 5, clock: clock)
        for (i, version) in ["1.1", "1.2", "1.3"].enumerated() {
            XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: version, isBusy: false),
                          "ask \(i + 1)")
            clock.advance(days: 120)
        }
        XCTAssertEqual(clock.now, start.addingTimeInterval(360 * 86_400))
        XCTAssertFalse(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.4", isBusy: false),
                       "fourth ask inside a year")
        clock.advance(days: 5.1) // the first ask is now more than 365 days old
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.4", isBusy: false))
        XCTAssertEqual(p.state.askedAt.count, 3, "asks older than a year are dropped")
    }

    func testAClockSetBackTreatsTheLastAskAsRecent() {
        let clock = TestClock(start)
        var p = prompter(launches: 5, clock: clock)
        XCTAssertTrue(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.1.0", isBusy: false))
        clock.set(start.addingTimeInterval(-400 * 86_400))
        XCTAssertFalse(p.considerAsking(.readPlantingAlert, hasFavorites: true, appVersion: "1.2.0", isBusy: false))
    }

    /// Negative control: the policy is not a constant `false`. With every
    /// rule satisfied it asks, and each rule alone turns it off.
    func testEachRuleAloneTurnsItOff() {
        let policy = ReviewPromptPolicy.standard
        let ok = ReviewPromptState(launchCount: 3)
        let now = start
        XCTAssertTrue(policy.shouldAsk(.finishedWithWater, state: ok, hasFavorites: true, appVersion: "1", isBusy: false, now: now))
        XCTAssertFalse(policy.shouldAsk(.finishedWithWater, state: ReviewPromptState(launchCount: 1), hasFavorites: true,
                                        appVersion: "1", isBusy: false, now: now))
        XCTAssertFalse(policy.shouldAsk(.finishedWithWater, state: ok, hasFavorites: false, appVersion: "1", isBusy: false, now: now))
        XCTAssertFalse(policy.shouldAsk(.finishedWithWater, state: ok, hasFavorites: true, appVersion: "1", isBusy: true, now: now))
        XCTAssertFalse(policy.shouldAsk(.finishedWithWater, state: ReviewPromptState(launchCount: 3, askedVersions: ["1"]),
                                        hasFavorites: true, appVersion: "1", isBusy: false, now: now))
        XCTAssertFalse(policy.shouldAsk(.finishedWithWater,
                                        state: ReviewPromptState(launchCount: 3, askedAt: [now.addingTimeInterval(-86_400)]),
                                        hasFavorites: true, appVersion: "1", isBusy: false, now: now))
    }

    // MARK: Storage

    func testStateRoundTripsAndACorruptFileReadsAsFresh() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-review-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let layout = AppStorageLayout(directory: dir)
        let store = ReviewPromptStore(layout: layout)
        XCTAssertEqual(store.load(), ReviewPromptState())
        let saved = ReviewPromptState(launchCount: 4, askedAt: [start], askedVersions: ["1.1.0"])
        try store.save(saved)
        XCTAssertEqual(store.load(), saved)
        try Data("{".utf8).write(to: layout.reviewPromptFile)
        XCTAssertEqual(store.load(), ReviewPromptState())
    }

    // MARK: The About row

    func testTheWriteReviewLinkIsThisAppsAppStorePage() {
        let url = AppStoreReviewLink.writeReviewURL
        XCTAssertEqual(url.scheme, "https")
        XCTAssertEqual(url.host, AppStoreReviewLink.host)
        XCTAssertEqual(url.path, "/app/id\(AppStoreReviewLink.appID)")
        XCTAssertEqual(url.query, "action=write-review")
    }

    /// Guideline 5.6.1: no reward, and nothing that sorts people by whether
    /// they like the app before sending them to the App Store.
    func testTheRowOffersNothingAndAsksNoQuestion() {
        let text = (AppStoreReviewLink.rowTitle + " " + AppStoreReviewLink.rowFootnote).lowercased()
        for banned in ["free", "unlock", "reward", "enjoy", "like", "love", "happy", "5 star", "five star", "?"] {
            XCTAssertFalse(text.contains(banned), banned)
        }
    }
}
