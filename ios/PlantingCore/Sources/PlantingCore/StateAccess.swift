import Foundation

/// Which in-app purchase unlocks alerts and the widget in which state
/// (docs/adr/0021). Pure, so `swift test` checks the rule that matters most:
/// California is the original Full Access product, unchanged, so nobody who
/// bought it loses anything.
///
/// Apple's guideline 4.3(a) asks for one app with in-app purchases instead
/// of an app per place, so each state is its own non-consumable product in
/// this one app. Browsing, history and favorites stay free everywhere.
public enum StateAccess {
    /// The product that has existed since 1.0. It is California's, and it
    /// stays exactly what its buyers paid for (alerts and the widget for
    /// California). Never renamed, never repointed.
    public static let californiaProductID = "com.chelseakr.cafishplanting.fullaccess"

    /// Placeholder ids until the owner creates the products in App Store
    /// Connect (docs/app-store/OWNER-STEPS.md).
    public static let productIDsByState: [String: String] = [
        "CA": californiaProductID,
        "TN": "com.chelseakr.cafishplanting.state.tn",
        "MA": "com.chelseakr.cafishplanting.state.ma",
        "MI": "com.chelseakr.cafishplanting.state.mi",
    ]

    public static var allProductIDs: Set<String> { Set(productIDsByState.values) }

    public static func productID(forState code: String) -> String? { productIDsByState[code] }

    public static func state(forProductID id: String) -> String? {
        productIDsByState.first { $0.value == id }?.key
    }

    /// The states a set of owned products unlocks. Unknown ids unlock nothing.
    public static func entitledStates(fromProductIDs ids: Set<String>) -> Set<String> {
        Set(ids.compactMap(state(forProductID:)))
    }
}
