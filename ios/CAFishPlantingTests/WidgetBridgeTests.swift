import Foundation
import XCTest
@testable import CAFishPlanting
@testable import PlantingCore

/// The app hands the widget the snapshot's week at the current favorites,
/// through the App Group container, and only when something changed.
@MainActor
final class WidgetBridgeTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        // Same isolation as AppEnvironmentTests: favorites live on disk.
        let layout = try AppStorageLayout.applicationSupport(bundleIdentifier: Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting")
        try? FileManager.default.removeItem(at: layout.directory)
        tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("widget-bridge-\(UUID().uuidString)")
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    /// The widget is part of full access (DECISIONS 0015). Before the
    /// purchase its digest is locked and carries nobody's favorites. A
    /// purchase or a restore unlocks it at once, and a refund locks it
    /// again. Both purchase and restore end in `setEntitled`, which is what
    /// this drives: StoreKit itself can't run on the iOS 26.5 simulator.
    func testTheWidgetUnlocksOnPurchaseOrRestoreAndLocksOnRefund() throws {
        var reloads = 0
        let store = WidgetDigestStore(directory: tempDir)
        let bridge = WidgetBridge(store: store, reload: { reloads += 1 })
        let env = AppEnvironment(widgetBridge: bridge)
        XCTAssertFalse(env.purchases.isEntitled, "sanity check: a fresh install hasn't bought anything")

        let initial = try XCTUnwrap(store.load(), "launch writes a digest, so the widget has the week even before a purchase")
        XCTAssertTrue(initial.locked)
        XCTAssertEqual(initial.week, env.snapshot?.sourceWeek)
        XCTAssertTrue(initial.favorites.isEmpty)
        XCTAssertEqual(reloads, 1)

        let snapshot = try XCTUnwrap(env.snapshot)
        let listedID = try XCTUnwrap(snapshot.thisWeek.first?.waterID, "the bundled snapshot must list a water this week")
        let listed = try XCTUnwrap(snapshot.water(id: listedID))
        env.toggleFavorite(listed)
        env.dismissNotificationExplainer()
        XCTAssertEqual(store.load()?.favorites, [], "a locked widget shows nobody's favorites")
        XCTAssertEqual(reloads, 1, "so favoriting doesn't redraw it")

        // A purchase, or a restore on a new device.
        env.purchases.setEntitled(true)
        let unlocked = try XCTUnwrap(store.load())
        XCTAssertFalse(unlocked.locked)
        XCTAssertEqual(unlocked.favorites.map(\.id), [listedID])
        XCTAssertTrue(unlocked.favorites[0].isListedThisWeek)
        XCTAssertEqual(reloads, 2, "the widget redraws straight away, not at the next refresh")

        env.publishWidgetDigest()
        XCTAssertEqual(reloads, 2, "an unchanged digest doesn't spend the widget's reload budget")

        env.toggleFavorite(listed)
        XCTAssertEqual(store.load()?.favorites, [])
        XCTAssertEqual(reloads, 3)

        // A refund.
        env.toggleFavorite(listed)
        env.purchases.setEntitled(false)
        let relocked = try XCTUnwrap(store.load())
        XCTAssertTrue(relocked.locked)
        XCTAssertEqual(relocked.favorites, [])
    }

    /// Both targets must declare the one group the code reads, or the
    /// widget silently says "open the app" forever.
    func testBothEntitlementsDeclareTheAppGroupTheCodeReads() throws {
        let ios = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        for path in ["CAFishPlanting/CAFishPlanting.entitlements", "CAFishPlantingWidgets/CAFishPlantingWidgets.entitlements"] {
            let data = try Data(contentsOf: ios.appendingPathComponent(path))
            let plist = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any]
            XCTAssertEqual(plist?["com.apple.security.application-groups"] as? [String], [WidgetDigestStore.appGroupIdentifier], path)
            XCTAssertEqual(plist?.count, 1, "\(path): the widget adds the App Group and nothing else")
        }
    }

    /// The simulator build carries the entitlement, so the real container is
    /// reachable. On a device this also needs the group registered for the
    /// team (see ios/README.md).
    func testTheAppCanReachTheAppGroupContainer() {
        XCTAssertNotNil(WidgetDigestStore.appGroup(), "no App Group container: the entitlement didn't reach the build")
    }

    func testTheWidgetKindMatchesTheExtension() throws {
        let ios = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let source = try String(contentsOf: ios.appendingPathComponent("CAFishPlantingWidgets/FavoriteWatersWidget.swift"), encoding: .utf8)
        XCTAssertTrue(source.contains("static let kind = \"\(WidgetBridge.widgetKind)\""), "the app reloads a widget kind the extension must declare")
    }
}
