import XCTest
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

    /// The free tier (`FreeTier`, PlantingCore — a placeholder gate pending
    /// a real free/paid decision) must actually hold for a non-purchaser: a
    /// default `AppEnvironment()` has made no purchase, so this exercises
    /// the real default path, not an injected fake.
    func testFreeTierCapsNonPurchaserAtMaxFavouritesAndShowsPaywall() throws {
        let env = AppEnvironment()
        XCTAssertFalse(env.purchases.isEntitled, "sanity check: a fresh environment must not already be entitled")
        let waters = try XCTUnwrap(env.snapshot?.waters)
        XCTAssertGreaterThan(waters.count, FreeTier.maxFavourites, "fixture needs more waters than the cap for this test to mean anything")

        for water in waters.prefix(FreeTier.maxFavourites) {
            env.toggleFavourite(water)
        }
        XCTAssertEqual(env.favourites.count, FreeTier.maxFavourites)
        XCTAssertNil(env.pendingPaywall, "must not show the paywall before the cap is reached")

        let overCap = waters[FreeTier.maxFavourites]
        env.toggleFavourite(overCap)

        XCTAssertEqual(env.favourites.count, FreeTier.maxFavourites, "a non-purchaser must never exceed the free-tier cap")
        XCTAssertFalse(env.isFavourite(overCap.id))
        XCTAssertEqual(env.pendingPaywall?.water.id, overCap.id)

        // Unfavouriting must still work at the cap, freeing a slot.
        let firstFavourite = waters[0]
        env.toggleFavourite(firstFavourite)
        XCTAssertEqual(env.favourites.count, FreeTier.maxFavourites - 1)
        env.dismissPaywall()
        XCTAssertNil(env.pendingPaywall)
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
}
