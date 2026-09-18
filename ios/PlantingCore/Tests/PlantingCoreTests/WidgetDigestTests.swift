import XCTest
@testable import PlantingCore

/// The widget's words: every line names its week, an ended week is never
/// "this week", and nothing missing is shown as "nothing scheduled".
final class WidgetDigestTests: XCTestCase {
    // Source week 2026-09-13 (Sun) .. 2026-09-19 (Sat).
    private let midWeek = ISO8601DateFormatter().date(from: "2026-09-16T19:00:00Z")!      // Wed, LA
    private let saturdayNightLA = ISO8601DateFormatter().date(from: "2026-09-20T06:30:00Z")! // Sat 23:30 LA
    private let sundayLA = ISO8601DateFormatter().date(from: "2026-09-20T07:30:00Z")!        // Sun 00:30 LA

    private func snapshot() -> Snapshot {
        TS.snapshot(sourceWeek: "2026-09-13", waters: [
            TS.water(id: "cdfw-1", name: "Listed Lake", plants: [
                TS.plant("2026-08-30"),
                TS.plant("2026-09-13", species: "Rainbow Trout"),
                TS.plant("2026-09-13", species: "Brown Trout"),
            ]),
            TS.water(id: "cdfw-2", name: "Later Lake", plants: [
                TS.plant("2026-09-06"),
                TS.plant("2026-09-13", status: .removed),
                TS.plant("2026-09-27"),
                TS.plant("2026-10-04"),
            ]),
            TS.water(id: "cdfw-3", name: "Quiet Pond", plants: [
                TS.plant("2026-07-05"),
            ]),
            TS.water(id: "cdfw-4", name: "Never Pond", plants: []),
        ])
    }

    private func digest(favorites: [Water.ID], meta: SnapshotMeta = SnapshotMeta(lastAttemptAt: Date(timeIntervalSince1970: 1), lastSuccessAt: Date(timeIntervalSince1970: 1), lastOutcome: "updated"), locked: Bool = false) -> WidgetDigest {
        WidgetDigest(snapshot: snapshot(), meta: meta, favorites: favorites, locked: locked)
    }

    func testBuildsEachFavoriteFromTheSnapshotInTheOrderAdded() throws {
        let d = digest(favorites: ["cdfw-3", "cdfw-1", "cdfw-2"])
        XCTAssertEqual(d.favorites.map(\.id), ["cdfw-3", "cdfw-1", "cdfw-2"])
        XCTAssertEqual(d.week.label, "week of 2026-09-13")
        XCTAssertEqual(d.missingFavorites, 0)

        let listed = try XCTUnwrap(d.favorites.first { $0.id == "cdfw-1" })
        XCTAssertEqual(listed.speciesThisWeek, ["Rainbow Trout", "Brown Trout"])
        XCTAssertNil(listed.nextWeek)

        let later = try XCTUnwrap(d.favorites.first { $0.id == "cdfw-2" })
        XCTAssertEqual(later.speciesThisWeek, [], "a removed plant is not a listing")
        XCTAssertEqual(later.nextWeek?.label, "week of 2026-09-27", "the first listed week after this one")
        XCTAssertEqual(later.lastListedWeek?.label, "week of 2026-10-04", "last_listed_week comes from the snapshot model")
    }

    func testStatusLinesNameTheWeekAndSayScheduled() throws {
        let d = digest(favorites: ["cdfw-1", "cdfw-2", "cdfw-3", "cdfw-4"])
        let lines = Dictionary(uniqueKeysWithValues: d.favorites.map { ($0.id, d.statusLine(of: $0, at: midWeek)) })
        XCTAssertEqual(lines["cdfw-1"], "Scheduled this week: Rainbow Trout, Brown Trout")
        XCTAssertEqual(lines["cdfw-2"], "Next scheduled for the week of 2026-09-27")
        XCTAssertEqual(lines["cdfw-3"], "Not listed for the week of 2026-09-13. Last scheduled for the week of 2026-07-05")
        XCTAssertEqual(lines["cdfw-4"], "Not listed for the week of 2026-09-13")
        for line in lines.values {
            for word in ["stocked", "planted", "no fish", "confirmed"] {
                XCTAssertFalse(line.localizedCaseInsensitiveContains(word), "\(line): schema/README.md wording rule")
            }
        }
        XCTAssertEqual(d.headline(at: midWeek), "This week")
        XCTAssertEqual(d.subheadline(at: midWeek), "Schedule for the week of 2026-09-13")
        XCTAssertEqual(d.summary(at: midWeek), "1 favorite scheduled this week")
    }

    /// The week turns over at midnight Los Angeles time, not UTC and not
    /// the device's zone. After that, nothing says "this week".
    func testAnEndedWeekIsNeverThisWeek() throws {
        let d = digest(favorites: ["cdfw-1", "cdfw-2"])
        XCTAssertFalse(d.isStale(at: saturdayNightLA), "Saturday 23:30 in Los Angeles is still that week (already Sunday in UTC)")
        XCTAssertTrue(d.isStale(at: sundayLA))
        XCTAssertEqual(d.staleAt, ISO8601DateFormatter().date(from: "2026-09-20T07:00:00Z"), "midnight after Saturday, Los Angeles (PDT)")

        let listed = try XCTUnwrap(d.favorites.first)
        XCTAssertEqual(d.statusLine(of: listed, at: sundayLA), "Scheduled for the week of 2026-09-13: Rainbow Trout, Brown Trout")
        XCTAssertEqual(d.headline(at: sundayLA), "Schedule for the week of 2026-09-13")
        XCTAssertTrue(d.subheadline(at: sundayLA).hasPrefix("That week has ended."))
        XCTAssertEqual(d.summary(at: sundayLA), "1 favorite listed for the week of 2026-09-13")
        let all = [d.headline(at: sundayLA), d.subheadline(at: sundayLA), d.summary(at: sundayLA)] + d.favorites.map { d.statusLine(of: $0, at: sundayLA) }
        for line in all {
            XCTAssertFalse(line.localizedCaseInsensitiveContains("this week"), "\(line): the week has ended")
        }
    }

    func testAFailedCheckIsSaidAndKeepsTheWeek() {
        let failed = SnapshotMeta(lastAttemptAt: Date(timeIntervalSince1970: 2), lastSuccessAt: Date(timeIntervalSince1970: 1), lastOutcome: SnapshotStore.failedOutcome, lastError: "offline")
        let d = digest(favorites: ["cdfw-1"], meta: failed)
        XCTAssertTrue(d.lastCheckFailed)
        XCTAssertEqual(d.lastSuccessfulCheck, Date(timeIntervalSince1970: 1))
        XCTAssertEqual(d.subheadline(at: midWeek), "Schedule for the week of 2026-09-13. Couldn't check for a newer one.")
        XCTAssertEqual(d.favorites.first?.speciesThisWeek, ["Rainbow Trout", "Brown Trout"], "a failed check keeps the last good week")
        XCTAssertEqual(d.subheadline(at: sundayLA), "That week has ended. Couldn't check for a newer schedule.")

        let never = digest(favorites: ["cdfw-1"], meta: SnapshotMeta())
        XCTAssertNil(never.lastSuccessfulCheck)
        XCTAssertFalse(never.lastCheckFailed)
    }

    /// A favorite CDFW dropped is counted, not silently lost, and a digest
    /// with only dropped favorites never reads as "no favorites".
    func testAFavoriteTheSnapshotDoesNotHaveIsCounted() {
        let d = digest(favorites: ["cdfw-gone", "cdfw-1"])
        XCTAssertEqual(d.favorites.map(\.id), ["cdfw-1"])
        XCTAssertEqual(d.missingFavorites, 1)

        let onlyGone = digest(favorites: ["cdfw-gone"])
        XCTAssertTrue(onlyGone.favorites.isEmpty)
        XCTAssertEqual(onlyGone.summary(at: midWeek), "Favorites not in this schedule")
        XCTAssertEqual(digest(favorites: []).summary(at: midWeek), "No favorite waters yet")
    }

    func testScheduledFavoritesComeFirstThenLaterThenTheRest() {
        let d = digest(favorites: ["cdfw-3", "cdfw-2", "cdfw-4", "cdfw-1"])
        XCTAssertEqual(d.favoritesByStatus.map(\.id), ["cdfw-1", "cdfw-2", "cdfw-3", "cdfw-4"])
        XCTAssertEqual(d.favoritesListedThisWeek, 1)
    }

    func testALockedDigestCarriesNoFavorites() {
        let d = digest(favorites: ["cdfw-1", "cdfw-gone"], locked: true)
        XCTAssertTrue(d.locked)
        XCTAssertTrue(d.favorites.isEmpty)
        XCTAssertEqual(d.missingFavorites, 0)
        XCTAssertEqual(d.summary(at: midWeek), "Unlock full access in Trout Truck")
    }

    // MARK: Store

    func testTheStoreRoundTripsAndReadsAnythingElseAsMissing() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("widget-digest-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: dir) }
        let store = WidgetDigestStore(directory: dir)
        XCTAssertNil(store.load(), "no file yet: the widget says to open the app")

        let d = digest(favorites: ["cdfw-1", "cdfw-2"])
        try store.save(d)
        XCTAssertEqual(store.load(), d)

        try Data("{not json".utf8).write(to: store.url)
        XCTAssertNil(store.load(), "an unreadable file is missing, never an empty schedule")

        let other = WidgetDigest(version: WidgetDigest.currentVersion + 1, week: d.week, snapshotGeneratedAt: d.snapshotGeneratedAt,
                                 lastCheckFailed: false, lastSuccessfulCheck: nil, watersListed: 1, favorites: [], missingFavorites: 0, locked: false)
        try store.save(other)
        XCTAssertNil(store.load(), "a digest from another app version is not misread")
    }

    /// DECISIONS 0015: the widget is part of full access.
    func testTheWidgetIsPartOfFullAccess() {
        XCTAssertTrue(FreeTier.widgetsRequireFullAccess)
        XCTAssertFalse(FreeTier.widgetsAllowed(isEntitled: false), "before the purchase the widget is locked")
        XCTAssertTrue(FreeTier.widgetsAllowed(isEntitled: true))
    }

    /// A locked digest still carries the published week (the widget says
    /// how many waters it lists), and nothing from anyone's favorites.
    func testALockedDigestKeepsTheWeekButNoFavorites() {
        let d = digest(favorites: ["cdfw-1", "cdfw-2"], locked: true)
        XCTAssertEqual(d.week.label, "week of 2026-09-13")
        XCTAssertEqual(d.watersListed, digest(favorites: [], locked: false).watersListed, "the published count, locked or not")
        XCTAssertEqual(d.favoritesListedThisWeek, 0)
        XCTAssertTrue(d.favoritesByStatus.isEmpty)
    }
}
