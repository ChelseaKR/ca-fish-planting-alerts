import XCTest
@testable import PlantingCore

/// What reaches Apple Watch: the phone's digest round-trips, a locked digest
/// carries no favorites to the watch, and the complication picks a water
/// only when one is actually listed.
final class WatchSyncTests: XCTestCase {
    private let midWeek = ISO8601DateFormatter().date(from: "2026-09-16T19:00:00Z")!
    private let sundayLA = ISO8601DateFormatter().date(from: "2026-09-20T07:30:00Z")!
    private let meta = SnapshotMeta(lastAttemptAt: Date(timeIntervalSince1970: 1), lastSuccessAt: Date(timeIntervalSince1970: 1), lastOutcome: "updated")

    private func snapshot() -> Snapshot {
        TS.snapshot(sourceWeek: "2026-09-13", waters: [
            TS.water(id: "cdfw-1", name: "Listed Lake", plants: [
                TS.plant("2026-08-30"),
                TS.plant("2026-09-13", species: "Rainbow Trout"),
            ]),
            TS.water(id: "cdfw-2", name: "Later Lake", plants: [
                TS.plant("2026-09-06"),
                TS.plant("2026-10-04"),
            ]),
            TS.water(id: "cdfw-3", name: "Sooner Lake", plants: [
                TS.plant("2026-09-27"),
            ]),
            TS.water(id: "cdfw-4", name: "Quiet Pond", plants: [
                TS.plant("2026-07-05"),
            ]),
        ])
    }

    private func digest(_ ids: [Water.ID], locked: Bool = false) -> WidgetDigest {
        WidgetDigest(snapshot: snapshot(), meta: meta, favorites: ids, locked: locked)
    }

    func testTheDigestRoundTripsThroughTheApplicationContext() throws {
        let original = digest(["cdfw-4", "cdfw-1", "cdfw-2"])
        let context = try WatchSync.applicationContext(for: original)
        XCTAssertEqual(WatchSync.digest(fromApplicationContext: context), original)
        let bytes = try XCTUnwrap(context[WatchSync.digestKey] as? Data).count
        XCTAssertLessThan(bytes, 4_096, "a digest, not the snapshot")
    }

    func testAMissingOrForeignContextIsNoDigestNeverAnEmptyOne() throws {
        XCTAssertNil(WatchSync.digest(fromApplicationContext: [:]))
        XCTAssertNil(WatchSync.digest(fromApplicationContext: [WatchSync.digestKey: Data("{}".utf8)]))
        XCTAssertNil(WatchSync.digest(fromApplicationContext: [WatchSync.digestKey: "not data"]))

        let d = digest(["cdfw-1"])
        let other = WidgetDigest(version: WidgetDigest.currentVersion + 1, week: d.week, snapshotGeneratedAt: d.snapshotGeneratedAt,
                                 lastCheckFailed: false, lastSuccessfulCheck: nil, watersListed: 1,
                                 favorites: d.favorites, missingFavorites: 0, locked: false)
        XCTAssertNil(WatchSync.digest(fromApplicationContext: try WatchSync.applicationContext(for: other)),
                     "a digest from a different app version is not read")
    }

    /// The watch shows only what the phone sends. Locked, the phone sends
    /// no favorites, so there is nothing on the wire for the watch to show.
    func testALockedDigestCarriesNoFavoritesToTheWatch() throws {
        let locked = digest(["cdfw-1", "cdfw-2"], locked: !FreeTier.watchAllowed(isEntitled: false))
        XCTAssertTrue(locked.locked)
        let received = try XCTUnwrap(WatchSync.digest(fromApplicationContext: try WatchSync.applicationContext(for: locked)))
        XCTAssertTrue(received.favorites.isEmpty)
        XCTAssertNil(received.nextFavorite)
        let bytes = try XCTUnwrap(WatchSync.applicationContext(for: locked)[WatchSync.digestKey] as? Data)
        XCTAssertFalse(String(decoding: bytes, as: UTF8.self).contains("Listed Lake"), "no favorite's name is sent while locked")
    }

    func testTheWatchIsPartOfFullAccess() {
        XCTAssertTrue(FreeTier.watchRequiresFullAccess)
        XCTAssertFalse(FreeTier.watchAllowed(isEntitled: false))
        XCTAssertTrue(FreeTier.watchAllowed(isEntitled: true))
        XCTAssertTrue(FreeTier.fullAccessFeatures.contains { $0.contains("Apple Watch") })
    }

    func testTheNextFavoriteIsListedThisWeekOrTheSoonestLater() {
        XCTAssertEqual(digest(["cdfw-2", "cdfw-1"]).nextFavorite?.id, "cdfw-1", "listed this week wins over add order")
        XCTAssertEqual(digest(["cdfw-2", "cdfw-3"]).nextFavorite?.id, "cdfw-3", "the sooner later week, not the first added")
        XCTAssertNil(digest(["cdfw-4"]).nextFavorite, "nothing listed this week or later: no water is named")
        XCTAssertNil(digest([]).nextFavorite)
    }

    func testShortWordsNameTheWeekAndNeverSayThisWeekAfterItEnds() throws {
        let d = digest(["cdfw-1", "cdfw-3", "cdfw-4"])
        let listed = try XCTUnwrap(d.favorites.first { $0.id == "cdfw-1" })
        let sooner = try XCTUnwrap(d.favorites.first { $0.id == "cdfw-3" })
        let quiet = try XCTUnwrap(d.favorites.first { $0.id == "cdfw-4" })
        XCTAssertEqual(d.shortStatus(of: listed, at: midWeek), "This week")
        XCTAssertEqual(d.shortStatus(of: listed, at: sundayLA), "Scheduled that week", "the headline names the ended week")
        XCTAssertEqual(d.shortStatus(of: sooner, at: midWeek), "Next: week of 2026-09-27")
        XCTAssertEqual(d.shortStatus(of: quiet, at: midWeek), "Not listed")

        XCTAssertEqual(d.nextScheduledLine(of: sooner), "Next scheduled: week of 2026-09-27")
        XCTAssertEqual(d.nextScheduledLine(of: quiet), "No later week listed yet")
        XCTAssertEqual(d.lastScheduledLine(of: quiet), "Last scheduled: week of 2026-07-05")
        XCTAssertEqual(d.lastScheduledLine(of: listed), "Last scheduled: week of 2026-09-13")
        XCTAssertNil(d.lastScheduledLine(of: sooner), "a last week after the digest's week is not called last")
        for line in [WidgetDigest.watchLockedMessage, WidgetDigest.watchNoDigestMessage] {
            for word in ["stocked", "planted", "no fish", "confirmed"] {
                XCTAssertFalse(line.localizedCaseInsensitiveContains(word), "\(line): schema/README.md wording rule")
            }
        }
    }

    func testAMuteRequestCarriesOnlyTheWaterID() {
        let request = WatchSync.muteRequest(for: "cdfw-125")
        XCTAssertEqual(request.count, 1)
        XCTAssertEqual(WatchSync.waterIDToMute(fromUserInfo: request), "cdfw-125")
        XCTAssertNil(WatchSync.waterIDToMute(fromUserInfo: [:]))
        XCTAssertNil(WatchSync.waterIDToMute(fromUserInfo: [WatchSync.muteWaterIDKey: ""]))
    }
}
