import Foundation
import XCTest
@testable import CAFishPlanting
@testable import PlantingCore

/// Apple Watch gets the phone's digest, gated by the phone: locked, with
/// nobody's favorites, until full access is owned (`FreeTier.watchAllowed`).
/// A mute tapped on the watch lands in the phone's mute list.
@MainActor
final class WatchBridgeTests: XCTestCase {
    override func setUpWithError() throws {
        let layout = try AppStorageLayout.applicationSupport(bundleIdentifier: Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting")
        try? FileManager.default.removeItem(at: layout.directory)
    }

    private func environment(_ watch: WatchBridge) -> AppEnvironment {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("watch-bridge-\(UUID().uuidString)")
        return AppEnvironment(widgetBridge: WidgetBridge(store: WidgetDigestStore(directory: dir), reload: {}), watchBridge: watch)
    }

    func testTheWatchIsLockedUntilFullAccessAndUnlocksWithThePhone() throws {
        let watch = WatchBridge(session: nil)
        let env = environment(watch)
        XCTAssertFalse(env.purchases.isEntitled)

        let snapshot = try XCTUnwrap(env.snapshot)
        let listedID = try XCTUnwrap(snapshot.thisWeek.first?.waterID)
        env.toggleFavorite(try XCTUnwrap(snapshot.water(id: listedID)))
        env.dismissNotificationExplainer()

        let locked = try XCTUnwrap(watch.latest, "the watch gets the week even before a purchase")
        XCTAssertTrue(locked.locked)
        XCTAssertEqual(locked.favorites, [], "a locked watch is sent nobody's favorites")

        env.purchases.setEntitled(true)
        let unlocked = try XCTUnwrap(watch.latest)
        XCTAssertFalse(unlocked.locked)
        XCTAssertEqual(unlocked.favorites.map(\.id), [listedID])
        XCTAssertEqual(unlocked.nextFavorite?.id, listedID)

        env.purchases.setEntitled(false)
        XCTAssertEqual(watch.latest?.favorites, [], "a refund locks the watch again")
        XCTAssertEqual(watch.latest?.locked, true)
    }

    /// Per state (DECISIONS 0025): another state's purchase unlocks the watch
    /// but not this California favorite, which is counted, never shown.
    func testAnotherStatesPurchaseDoesNotShowThisStatesFavorites() throws {
        let watch = WatchBridge(session: nil)
        let env = environment(watch)
        let snapshot = try XCTUnwrap(env.snapshot)
        let water = try XCTUnwrap(snapshot.waters.first { $0.state == "CA" })
        env.toggleFavorite(water)
        env.dismissNotificationExplainer()

        env.purchases.setEntitled(states: ["TN"])
        let tn = try XCTUnwrap(watch.latest)
        XCTAssertFalse(tn.locked)
        XCTAssertEqual(tn.favorites, [])
        XCTAssertEqual(tn.favoritesInOtherStates, 1)

        env.purchases.setEntitled(states: ["CA", "TN"])
        XCTAssertEqual(watch.latest?.favorites.map(\.id), [water.id])
    }

    func testAMuteFromTheWatchMutesThatWaterOnThePhone() throws {
        let watch = WatchBridge(session: nil)
        let env = environment(watch)
        let snapshot = try XCTUnwrap(env.snapshot)
        let water = try XCTUnwrap(snapshot.water(id: try XCTUnwrap(snapshot.thisWeek.first?.waterID)))
        env.toggleFavorite(water)
        env.dismissNotificationExplainer()

        watch.received(WatchSync.muteRequest(for: water.id))
        XCTAssertTrue(env.mutedWaters.contains(water.id))
        XCTAssertTrue(env.isFavorite(water.id), "muting keeps the favorite")

        watch.received([:])
        XCTAssertTrue(env.mutedWaters.contains(water.id), "anything else is ignored")
    }

    /// The watch app and its complication share one App Group container on
    /// the watch, under the identifier the code reads.
    func testTheWatchEntitlementsDeclareTheAppGroupTheCodeReads() throws {
        let ios = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        for path in ["CAFishPlantingWatch/CAFishPlantingWatch.entitlements", "CAFishPlantingWatchWidgets/CAFishPlantingWatchWidgets.entitlements"] {
            let data = try Data(contentsOf: ios.appendingPathComponent(path))
            let plist = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any]
            XCTAssertEqual(plist?["com.apple.security.application-groups"] as? [String], [WidgetDigestStore.appGroupIdentifier], path)
            XCTAssertEqual(plist?.count, 1, "\(path): the App Group and nothing else")
        }
    }

    /// The watch app pairs with this app and nothing else, and doesn't run
    /// without it (it has no data of its own).
    func testTheWatchAppNamesThisAppAsItsCompanion() throws {
        let ios = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let data = try Data(contentsOf: ios.appendingPathComponent("CAFishPlantingWatch/Resources/Info.plist"))
        let plist = try XCTUnwrap(PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any])
        XCTAssertEqual(plist["WKCompanionAppBundleIdentifier"] as? String, Bundle.main.bundleIdentifier)
        XCTAssertEqual(plist["WKRunsIndependentlyOfCompanionApp"] as? Bool, false)
    }
}
