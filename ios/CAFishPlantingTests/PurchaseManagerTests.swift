import XCTest
import StoreKit
import StoreKitTest
@testable import CAFishPlanting
import PlantingCore

/// Drives real StoreKit 2 purchases against the local `.storekit`
/// configuration (`ios/CAFishPlanting/Configuration.storekit`) through
/// `SKTestSession` — StoreKit's own supported way to run purchases
/// deterministically in XCTest, with no App Store Connect product and no
/// UI automation required. See `docs/APP-STORE.md` for what Chelsea still
/// has to create in App Store Connect for the real product to exist.
@MainActor
final class PurchaseManagerTests: XCTestCase {
    private var session: SKTestSession!
    private var tempDir: URL!

    override func setUpWithError() throws {
        session = try SKTestSession(contentsOf: try Self.configurationURL())
        session.resetToDefaultState()
        session.disableDialogs = true
        session.clearTransactions()

        tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-purchase-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        session.clearTransactions()
        try? FileManager.default.removeItem(at: tempDir)
    }

    // MARK: - Purchase success

    func testPurchaseSuccessGrantsEntitlementAndPersistsIt() async throws {
        let store = EntitlementStore(layout: AppStorageLayout(directory: tempDir))
        let manager = PurchaseManager(entitlementStore: store)
        try await waitForProductToLoad(manager)
        XCTAssertFalse(manager.isEntitled)

        await manager.purchase()

        XCTAssertTrue(manager.isEntitled, "a successful purchase must grant entitlement immediately")
        XCTAssertEqual(manager.uiState, .idle)
        XCTAssertTrue(store.load().isPurchased, "a successful purchase must be cached to disk")
    }

    // MARK: - Purchase failure

    func testPurchaseFailureLeavesEntitlementFalseAndSurfacesAnError() async throws {
        let store = EntitlementStore(layout: AppStorageLayout(directory: tempDir))
        let manager = PurchaseManager(entitlementStore: store)
        try await waitForProductToLoad(manager)

        session.failTransactionsEnabled = true
        session.failureError = .unknown

        await manager.purchase()

        XCTAssertFalse(manager.isEntitled, "a failed purchase must never grant entitlement")
        guard case .failed = manager.uiState else {
            XCTFail("expected .failed, got \(manager.uiState)")
            return
        }
        XCTAssertFalse(store.load().isPurchased)
    }

    // MARK: - Cancellation / pending
    // `.userCancelled` and `.pending` carry no payload, so these are
    // constructed directly — no live product or purchase sheet needed —
    // to pin down that neither is ever treated as an error.

    func testUserCancelledIsNotTreatedAsAnError() {
        XCTAssertEqual(PurchaseManager.nextUIState(forNonSuccess: .userCancelled), .idle)
    }

    func testPendingApprovalIsNotTreatedAsAnErrorEither() {
        XCTAssertEqual(PurchaseManager.nextUIState(forNonSuccess: .pending), .idle)
    }

    // MARK: - Restore purchases

    func testRestorePurchasesRecoversEntitlementOnAFreshInstall() async throws {
        // "Buy" once, as if on a previous device/install under this account.
        let firstManager = PurchaseManager(entitlementStore: EntitlementStore(layout: AppStorageLayout(directory: tempDir.appendingPathComponent("first-install"))))
        try await waitForProductToLoad(firstManager)
        await firstManager.purchase()
        XCTAssertTrue(firstManager.isEntitled)

        // A fresh install: its own empty entitlement cache, same simulated
        // StoreKit account (same SKTestSession, same process).
        let secondLayout = AppStorageLayout(directory: tempDir.appendingPathComponent("second-install"))
        let secondStore = EntitlementStore(layout: secondLayout)
        let secondManager = PurchaseManager(entitlementStore: secondStore)
        try await waitForProductToLoad(secondManager)
        XCTAssertFalse(secondManager.isEntitled, "a fresh install must start locked, never assume entitlement")

        await secondManager.restorePurchases()

        XCTAssertTrue(secondManager.isEntitled, "restore must recover a purchase made under the same account")
        XCTAssertTrue(secondStore.load().isPurchased)
    }

    // MARK: - Entitlement check on launch

    func testFreshLaunchWithNoPriorPurchaseChecksAndStaysLocked() async throws {
        let manager = PurchaseManager(entitlementStore: EntitlementStore(layout: AppStorageLayout(directory: tempDir)))
        // init() itself kicks off the launch-time refreshEntitlement().
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertFalse(manager.isEntitled)
    }

    func testLaunchAfterAPurchaseUnlocksEvenWithNoLocalCache() async throws {
        let purchasingManager = PurchaseManager(entitlementStore: EntitlementStore(layout: AppStorageLayout(directory: tempDir.appendingPathComponent("purchasing-device"))))
        try await waitForProductToLoad(purchasingManager)
        await purchasingManager.purchase()
        XCTAssertTrue(purchasingManager.isEntitled)

        // A brand-new launch on the same account with no cache file at
        // all — PurchaseManager.init() must discover the entitlement via
        // Transaction.currentEntitlements, not merely via the disk cache.
        let freshManager = PurchaseManager(entitlementStore: EntitlementStore(layout: AppStorageLayout(directory: tempDir.appendingPathComponent("fresh-launch"))))
        XCTAssertFalse(freshManager.isEntitled, "must start locked before the async check lands")
        try await Task.sleep(for: .milliseconds(500))
        XCTAssertTrue(freshManager.isEntitled, "init's own entitlement check must find the existing purchase")
    }

    // MARK: - Free tier, unlocked

    /// The mirror of `AppEnvironmentTests.testFreeTierCapsNonPurchaserAtMaxFavouritesAndShowsPaywall`:
    /// an actual purchaser (a real purchase through this SKTestSession, not
    /// a stubbed flag) must have no favourites cap at all.
    func testPurchaserHasNoFavouriteCap() async throws {
        let layout = try AppStorageLayout.applicationSupport(bundleIdentifier: Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting")
        try? FileManager.default.removeItem(at: layout.directory)

        let manager = PurchaseManager(entitlementStore: EntitlementStore(layout: layout))
        try await waitForProductToLoad(manager)
        await manager.purchase()
        XCTAssertTrue(manager.isEntitled)

        let env = AppEnvironment(purchases: manager)
        let waters = try XCTUnwrap(env.snapshot?.waters)
        XCTAssertGreaterThan(waters.count, FreeTier.maxFavourites, "fixture needs more waters than the cap for this test to mean anything")

        for water in waters.prefix(FreeTier.maxFavourites + 2) {
            env.toggleFavourite(water)
        }

        XCTAssertEqual(env.favourites.count, FreeTier.maxFavourites + 2, "an entitled purchaser must have no favourites cap")
        XCTAssertNil(env.pendingPaywall)
    }

    // MARK: -

    private func waitForProductToLoad(_ manager: PurchaseManager, timeout: TimeInterval = 8) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while manager.product == nil && Date() < deadline {
            try await Task.sleep(for: .milliseconds(50))
        }
        XCTAssertNotNil(manager.product, "the local .storekit configuration should have loaded \(PurchaseManager.productID)")
    }

    private static func configurationURL() throws -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // CAFishPlantingTests
            .deletingLastPathComponent() // ios
            .appendingPathComponent("CAFishPlanting/Configuration.storekit")
    }
}
