import Foundation

/// PLACEHOLDER product-scope gate.
///
/// `docs/DECISIONS.md` does not yet say what, specifically, the one-time
/// purchase unlocks — only that the app is "paid up front" (0003). Rather
/// than guess at scope that is Chelsea's to decide, this gates the
/// simplest possible capability (a cap on how many waters a non-purchaser
/// may favourite) so the StoreKit *mechanism* — entitlement check,
/// purchase, restore — is complete and real, and is trivial to repoint at
/// whatever the actual free/paid split turns out to be. Nothing else in
/// the app depends on this specific number or this specific capability.
public enum FreeTier {
    /// Non-purchasers may favourite at most this many waters. Purchasers
    /// (`isEntitled == true`) have no limit.
    public static let maxFavourites = 3

    /// Whether one more water may be favourited, given how many are
    /// already favourited and whether the one-time purchase is owned.
    public static func canAddFavourite(currentCount: Int, isEntitled: Bool) -> Bool {
        isEntitled || currentCount < maxFavourites
    }
}
