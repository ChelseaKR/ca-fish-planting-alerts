import Foundation
import XCTest
import UserNotifications
@testable import CAFishPlanting
@testable import PlantingCore

/// A tapped alert or a `trouttruck://water/<id>` link opens that water's
/// screen, in the tab the person keeps it in, and never a blank screen.
@MainActor
final class AppRouterTests: XCTestCase {
    private func bundledSnapshot() throws -> Snapshot {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "snapshot", withExtension: "json"))
        return try SnapshotDecoder().decode(try Data(contentsOf: url))
    }

    func testAFavoriteOpensUnderFavorites() throws {
        let snapshot = try bundledSnapshot()
        let water = try XCTUnwrap(snapshot.waters.first)
        let router = AppRouter()
        router.browsePath = ["something-else"]

        router.request(waterID: water.id)
        XCTAssertTrue(router.openPending(in: snapshot, isFavorite: { $0 == water.id }))

        XCTAssertEqual(router.selectedTab, .favorites)
        XCTAssertEqual(router.favoritesPath, [water.id], "the water replaces whatever was open, so Back goes to the list")
        XCTAssertEqual(router.browsePath, ["something-else"], "the other tab is left alone")
        XCTAssertNil(router.pendingWaterID, "a request is opened once")
    }

    func testAnyOtherWaterOpensUnderBrowse() throws {
        let snapshot = try bundledSnapshot()
        let water = try XCTUnwrap(snapshot.waters.last)
        let router = AppRouter()
        router.selectedTab = .about

        XCTAssertTrue(router.handle(WaterLink.url(for: water.id)))
        XCTAssertTrue(router.openPending(in: snapshot, isFavorite: { _ in false }))

        XCTAssertEqual(router.selectedTab, .browse)
        XCTAssertEqual(router.browsePath, [water.id])
        XCTAssertTrue(router.favoritesPath.isEmpty)
    }

    /// A favorite that has dropped out of the snapshot: open Favorites, but
    /// never push a screen with nothing to show.
    func testAWaterTheSnapshotDoesNotHaveIsNeverPushed() throws {
        let snapshot = try bundledSnapshot()
        let router = AppRouter()

        router.request(waterID: "cdfw-does-not-exist")
        XCTAssertFalse(router.openPending(in: snapshot, isFavorite: { _ in true }))
        XCTAssertEqual(router.selectedTab, .favorites)
        XCTAssertTrue(router.favoritesPath.isEmpty)
        XCTAssertTrue(router.browsePath.isEmpty)

        router.request(waterID: "cdfw-does-not-exist")
        XCTAssertFalse(router.openPending(in: snapshot, isFavorite: { _ in false }))
        XCTAssertEqual(router.selectedTab, .favorites, "a non-favorite that doesn't exist leaves the app where it was")
        XCTAssertNil(router.pendingWaterID)
    }

    /// The locked widget's link opens the purchase screen over About.
    func testTheUnlockLinkOpensThePurchaseScreen() {
        let router = AppRouter()
        XCTAssertFalse(router.showingPurchase)
        XCTAssertTrue(router.handle(UnlockLink.url))
        XCTAssertTrue(router.showingPurchase)
        XCTAssertEqual(router.selectedTab, .about)
        XCTAssertNil(router.pendingWaterID, "it opens no water")
    }

    func testOtherLinksAreIgnored() throws {
        let router = AppRouter()
        let url = try XCTUnwrap(URL(string: "trouttruck://county/Modoc"))
        XCTAssertFalse(router.handle(url))
        XCTAssertNil(router.pendingWaterID)
        XCTAssertFalse(router.openPending(in: try bundledSnapshot(), isFavorite: { _ in true }))
        XCTAssertEqual(router.selectedTab, .browse)
    }

    /// The alert the scheduler builds carries the water it names, so the
    /// responder can open it.
    func testTheScheduledAlertCarriesItsWater() {
        let planned = PlannedNotification(waterID: "cdfw-3", waterName: "Test Lake",
                                          newKeys: [PlantKey(weekStart: PlainDate(year: 2026, month: 9, day: 13), species: "Trout")])
        let content = NotificationScheduler.content(for: planned)
        XCTAssertEqual(WaterLink.waterID(fromNotificationUserInfo: content.userInfo), "cdfw-3")
        XCTAssertEqual(content.threadIdentifier, "cdfw-3")
        XCTAssertEqual(content.title, planned.title)
        XCTAssertEqual(content.body, planned.body())
    }

    func testInfoPlistRegistersTheLinkScheme() throws {
        let infoPlistURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // CAFishPlantingTests
            .deletingLastPathComponent() // ios
            .appendingPathComponent("CAFishPlanting/Resources/Info.plist")
        let plist = try PropertyListSerialization.propertyList(from: try Data(contentsOf: infoPlistURL), format: nil) as? [String: Any]
        let types = plist?["CFBundleURLTypes"] as? [[String: Any]] ?? []
        let schemes = types.flatMap { $0["CFBundleURLSchemes"] as? [String] ?? [] }
        XCTAssertEqual(schemes, [WaterLink.scheme], "Info.plist must register exactly the scheme WaterLink builds")
    }

    func testTheResponderIsTheNotificationCenterDelegate() {
        XCTAssertTrue(UNUserNotificationCenter.current().delegate === NotificationResponder.shared,
                      "App.init() must install the responder, or a tapped alert opens nothing")
    }
}
