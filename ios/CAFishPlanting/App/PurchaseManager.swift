import Foundation
import StoreKit
import Observation
import PlantingCore

/// The app's purchases: one non-consumable product per state
/// (docs/adr/0021). California's is the original Full Access,
/// `com.chelseakr.cafishplanting.fullaccess`, unchanged, so everyone who
/// bought it keeps exactly what they bought. Tennessee, Massachusetts and
/// Michigan each have their own (`StateAccess.productIDsByState`). StoreKit 2
/// only; see `docs/APP-STORE.md` and `docs/app-store/OWNER-STEPS.md` for what
/// has to exist in App Store Connect.
///
/// `Transaction.currentEntitlements` is always asked and is always the truth
/// this settles on; the on-disk `EntitlementStore` cache only avoids a
/// locked-looking flash before that async answer comes back.
@MainActor
@Observable
final class PurchaseManager {
    /// California's product. Must match App Store Connect exactly.
    static let productID = StateAccess.californiaProductID

    enum UIState: Equatable {
        case idle
        case purchasing
        case restoring
        case failed(String)
    }

    /// Every product this device owns.
    private(set) var ownedProductIDs: Set<String>
    /// Loaded products by id. A state whose product isn't configured yet has
    /// none, and its purchase button says so.
    private(set) var products: [String: Product] = [:]
    private(set) var productLoadError: String?
    private(set) var uiState: UIState = .idle

    /// California's Full Access. The name every screen used before states.
    var isEntitled: Bool { ownedProductIDs.contains(Self.productID) }
    /// California's product, as before.
    var product: Product? { products[Self.productID] }

    var entitledStates: Set<String> { StateAccess.entitledStates(fromProductIDs: ownedProductIDs) }
    var hasAnyAccess: Bool { !entitledStates.isEmpty }
    func isEntitled(state code: String) -> Bool { entitledStates.contains(code) }
    func product(forState code: String) -> Product? {
        StateAccess.productID(forState: code).flatMap { products[$0] }
    }

    /// Called on the main actor every time the entitlements are set: at
    /// launch, after a purchase, a restore, a purchase from another device,
    /// or a refund. `AppEnvironment` redraws the widget with it.
    var onEntitlementChange: (@MainActor (Bool) -> Void)?

    private let entitlementStore: EntitlementStore?
    nonisolated(unsafe) private var transactionListener: Task<Void, Never>?

    init(entitlementStore: EntitlementStore?) {
        self.entitlementStore = entitlementStore
        // Cached answer first, so a returning purchaser never sees a paywall
        // flash before StoreKit responds. A 1.0 cache reads as California.
        self.ownedProductIDs = entitlementStore?.load().ownedProductIDs ?? []

        transactionListener = Task { [weak self] in
            await self?.observeTransactionUpdates()
        }
        Task { [weak self] in await self?.loadProducts() }
        Task { [weak self] in await self?.refreshEntitlement() }
    }

    deinit {
        transactionListener?.cancel()
    }

    /// Fetches every state's product (or the local `.storekit` configuration
    /// in development: `ios/CAFishPlanting/Configuration.storekit`).
    func loadProducts() async {
        do {
            let loaded = try await Product.products(for: StateAccess.allProductIDs)
            products = Dictionary(uniqueKeysWithValues: loaded.map { ($0.id, $0) })
            productLoadError = products[Self.productID] == nil
                ? "Product \(Self.productID) is not configured yet."
                : nil
        } catch {
            productLoadError = String(describing: error)
        }
    }

    /// Kept for callers from before states.
    func loadProduct() async { await loadProducts() }

    /// The launch-time check: every currently valid, verified transaction
    /// for one of this app's products. Revoked (refunded) ones are not in
    /// `currentEntitlements`, so a refund locks that state again.
    func refreshEntitlement() async {
        var owned: Set<String> = []
        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result,
                  StateAccess.allProductIDs.contains(transaction.productID) else { continue }
            owned.insert(transaction.productID)
        }
        setOwned(owned)
    }

    /// Buys California's Full Access, as before states.
    func purchase() async { await purchase(state: "CA") }

    /// Buys one state's product. A purchase already in flight is a no-op.
    func purchase(state code: String) async {
        guard uiState != .purchasing else { return }
        uiState = .purchasing
        do {
            let product = try await resolvedProduct(forState: code)
            let result = try await product.purchase()
            switch result {
            case .success(.verified(let transaction)):
                setOwned(ownedProductIDs.union([transaction.productID]))
                await transaction.finish()
                uiState = .idle
            case .success(.unverified(_, let error)):
                // Never unlock on a transaction StoreKit could not verify.
                uiState = .failed("Purchase could not be verified: \(error.localizedDescription)")
            default:
                uiState = Self.nextUIState(forNonSuccess: result) ?? .idle
            }
        } catch {
            uiState = .failed(String(describing: error))
        }
    }

    /// Required by Apple for non-consumables: re-derives every state's
    /// entitlement from the Apple ID's purchase history.
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

    /// `.userCancelled` and `.pending` are not failures.
    static func nextUIState(forNonSuccess result: Product.PurchaseResult) -> UIState? {
        switch result {
        case .userCancelled: return .idle
        case .pending: return .idle
        default: return nil
        }
    }

    // MARK: -

    private func resolvedProduct(forState code: String) async throws -> Product {
        if let product = product(forState: code) { return product }
        await loadProducts()
        guard let product = product(forState: code) else { throw PurchaseManagerError.productUnavailable }
        return product
    }

    /// Purchases finished outside `purchase(state:)`: after `.pending`, on
    /// another device, or a refund. Re-reads the whole set, so a revocation
    /// locks its state again.
    private func observeTransactionUpdates() async {
        for await update in Transaction.updates {
            guard case .verified(let transaction) = update else { continue }
            await transaction.finish()
            await refreshEntitlement()
        }
    }

    /// Internal, not private, so hosted tests can stand in for StoreKit,
    /// which can't run on the iOS 26.5 simulator (`ios/README.md`).
    /// `true` owns California's product; `false` owns nothing.
    func setEntitled(_ value: Bool) {
        setOwned(value ? [Self.productID] : [])
    }

    /// Hosted tests: own exactly these states' products.
    func setEntitled(states: Set<String>) {
        setOwned(Set(states.compactMap(StateAccess.productID(forState:))))
    }

    private func setOwned(_ ids: Set<String>) {
        ownedProductIDs = ids
        try? entitlementStore?.save(PurchaseEntitlement(isPurchased: ids.contains(Self.productID),
                                                        productIDs: ids.sorted()))
        onEntitlementChange?(!ids.isEmpty)
    }
}

enum PurchaseManagerError: LocalizedError {
    case productUnavailable
    var errorDescription: String? { "That purchase isn't available right now." }
}
