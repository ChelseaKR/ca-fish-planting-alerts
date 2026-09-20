import Foundation
import StoreKit
import Observation
import PlantingCore

/// The app's one purchase: a single non-consumable "unlock full access".
/// StoreKit 2 only (no `SKPaymentQueue`/transaction-observer code) — see
/// `docs/APP-STORE.md` for what has to exist in App Store Connect to match
/// this identifier, and `docs/DECISIONS.md` 0007 for why this replaced the
/// original "no StoreKit, paid-app-price" plan in 0003.
///
/// `Transaction.currentEntitlements` is always asked and is always the
/// truth this settles on; the on-disk `EntitlementStore` cache only avoids
/// a locked-looking flash before that async answer comes back.
@MainActor
@Observable
final class PurchaseManager {
    /// Must match exactly the product Chelsea creates in App Store
    /// Connect — see docs/APP-STORE.md.
    static let productID = "com.chelseakr.cafishplanting.fullaccess"

    enum UIState: Equatable {
        case idle
        case purchasing
        case restoring
        case failed(String)
    }

    private(set) var isEntitled: Bool
    private(set) var product: Product?
    private(set) var productLoadError: String?
    private(set) var uiState: UIState = .idle

    /// Called on the main actor every time the entitlement is set: at
    /// launch, after a purchase, a restore, a purchase from another device,
    /// or a refund. `AppEnvironment` uses it to redraw the widget, which is
    /// part of full access, so it unlocks (or locks) without waiting for
    /// the next refresh.
    var onEntitlementChange: (@MainActor (Bool) -> Void)?

    private let entitlementStore: EntitlementStore?
    // `deinit` on a `@MainActor` class is itself non-isolated (it may run
    // on any thread), so it cannot touch a main-actor-isolated stored
    // property directly. This is written once, in `init`, and read once,
    // in `deinit`, to cancel the listener — never concurrently.
    nonisolated(unsafe) private var transactionListener: Task<Void, Never>?

    init(entitlementStore: EntitlementStore?) {
        self.entitlementStore = entitlementStore
        // Cached answer first, so a returning purchaser never sees a
        // paywall flash before StoreKit responds.
        self.isEntitled = entitlementStore?.load().isPurchased ?? false

        transactionListener = Task { [weak self] in
            await self?.observeTransactionUpdates()
        }
        Task { [weak self] in await self?.loadProduct() }
        Task { [weak self] in await self?.refreshEntitlement() }
    }

    deinit {
        transactionListener?.cancel()
    }

    /// Fetches the product's live price/title from the App Store (or the
    /// local `.storekit` configuration in development — see
    /// `ios/CAFishPlanting/Configuration.storekit`).
    func loadProduct() async {
        do {
            let products = try await Product.products(for: [Self.productID])
            product = products.first
            productLoadError = products.first == nil
                ? "Product \(Self.productID) is not configured yet."
                : nil
        } catch {
            productLoadError = String(describing: error)
        }
    }

    /// The launch-time entitlement check: walks every currently-valid
    /// transaction StoreKit knows about for this Apple ID/device and looks
    /// for this app's product. This — not the disk cache — is what decides
    /// whether the purchase is real.
    func refreshEntitlement() async {
        var entitled = false
        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result, transaction.productID == Self.productID else { continue }
            entitled = true
        }
        setEntitled(entitled)
    }

    /// Buys the one product this app sells. Safe to call repeatedly; a
    /// purchase already in flight is a no-op rather than a second sheet.
    func purchase() async {
        guard uiState != .purchasing else { return }
        uiState = .purchasing

        do {
            let product = try await resolvedProduct()
            let result = try await product.purchase()
            switch result {
            case .success(.verified(let transaction)):
                setEntitled(true)
                await transaction.finish()
                uiState = .idle
            case .success(.unverified(_, let error)):
                // StoreKit itself could not verify the transaction (e.g. a
                // JWS signature it doesn't trust) — never unlock on this.
                uiState = .failed("Purchase could not be verified: \(error.localizedDescription)")
            default:
                uiState = Self.nextUIState(forNonSuccess: result) ?? .idle
            }
        } catch {
            uiState = .failed(String(describing: error))
        }
    }

    /// Required by Apple for non-consumable IAP: re-derives entitlement
    /// from the Apple ID's purchase history, for a reinstall or a new
    /// device where the on-disk cache is empty.
    func restorePurchases() async {
        uiState = .restoring
        do {
            try await AppStore.sync()
        } catch {
            uiState = .failed("Restore failed: \(String(describing: error))")
            return
        }
        await refreshEntitlement()
        if uiState == .restoring { uiState = .idle }
    }

    /// Pure mapping for the two non-error, non-success outcomes — factored
    /// out of `purchase()` so it is directly unit-testable: `.userCancelled`
    /// and `.pending` carry no payload, so a test can construct them
    /// without a live product or a real purchase sheet and assert neither
    /// one is treated as a failure.
    static func nextUIState(forNonSuccess result: Product.PurchaseResult) -> UIState? {
        switch result {
        case .userCancelled:
            // Not an error: the person chose not to buy. No alert.
            return .idle
        case .pending:
            // Ask to Buy / family approval etc. Transaction.updates will
            // deliver the entitlement later if it is approved.
            return .idle
        default:
            return nil
        }
    }

    // MARK: -

    private func resolvedProduct() async throws -> Product {
        if let product { return product }
        await loadProduct()
        guard let product else { throw PurchaseManagerError.productUnavailable }
        return product
    }

    /// Catches entitlements granted outside an in-process `purchase()`
    /// call — a renewal-style delivery, a purchase completed after a
    /// `.pending` result, or a purchase made on another device that
    /// StoreKit syncs in.
    private func observeTransactionUpdates() async {
        for await update in Transaction.updates {
            guard case .verified(let transaction) = update else { continue }
            if transaction.productID == Self.productID {
                setEntitled(true)
            }
            await transaction.finish()
        }
    }

    /// Internal, not private, so hosted tests can stand in for StoreKit,
    /// which can't run on the iOS 26.5 simulator (`ios/README.md`).
    func setEntitled(_ value: Bool) {
        isEntitled = value
        try? entitlementStore?.save(PurchaseEntitlement(isPurchased: value))
        onEntitlementChange?(value)
    }
}

enum PurchaseManagerError: LocalizedError {
    case productUnavailable
    var errorDescription: String? { "The full-access product isn't available right now." }
}
