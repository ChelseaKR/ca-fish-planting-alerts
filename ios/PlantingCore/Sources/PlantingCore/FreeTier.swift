import Foundation

/// The app's free/paid gate.
///
/// `docs/DECISIONS.md` 0007 shipped the StoreKit *mechanism* — entitlement
/// check, purchase, restore — without deciding what it unlocks, and left a
/// placeholder (a cap on favorited waters) so the mechanism could be real
/// without inventing product scope that was Chelsea's call. That call is
/// now made (see the DECISIONS entry that resolves 0007's "owner
/// follow-up"):
///
/// * **Favoriting and browsing are free and unconstrained for everyone.**
///   The app's own free tier must never be worse than the free website
///   (`docs/DECISIONS.md` 0001) already gives anyone, so favoriting is
///   never gated here or anywhere else in the app.
/// * **Local notifications are the paid unlock.** A website cannot push a
///   native notification to a phone — that's the one piece of value this
///   app has that the free site structurally cannot replicate, so it's the
///   coherent thing to gate instead of a capability the free site already
///   gives away. Non-purchasers can favorite freely; no local notification
///   is ever scheduled for any favorited water without the one-time
///   purchase (`com.chelseakr.cafishplanting.fullaccess`, see
///   `PurchaseManager`).
public enum FreeTier {
    /// Whether local notifications may be scheduled for a favorited
    /// water's schedule changes, given whether the one-time purchase is
    /// owned. Call this immediately before
    /// `NotificationScheduler.schedule(_:)` — never anywhere on the
    /// favoriting path, which this gate does not touch.
    public static func notificationsAllowed(isEntitled: Bool) -> Bool {
        isEntitled
    }

    /// Whether the Home Screen and Lock Screen widget needs the one-time
    /// purchase. It does: the owner decided on 2026-09-18 that the widget is
    /// part of full access, like alerts (`docs/DECISIONS.md` 0015). Before
    /// the purchase the widget says it is part of full access, and a tap
    /// opens the purchase screen (`WidgetDigest.locked`,
    /// `UnlockLink`). It never shows made-up or partial favorites.
    public static let widgetsRequireFullAccess = true

    /// Whether the widget may show favorites, given whether the one-time
    /// purchase is owned. Read in one place: where the app builds the
    /// widget's digest (`AppEnvironment.publishWidgetDigest()`).
    public static func widgetsAllowed(isEntitled: Bool) -> Bool {
        !widgetsRequireFullAccess || isEntitled
    }

    /// Whether Trout Truck on Apple Watch (the watch app and its
    /// complications) needs the one-time purchase. It does: the owner asked
    /// on 2026-10-12 for watch extras as more reasons to buy the same
    /// purchase (`docs/DECISIONS.md` 0027). The watch never checks a
    /// purchase itself. It shows only the digest the phone sends
    /// (`WatchSync`), and the phone builds that digest locked, with no
    /// favorites in it, unless this allows it.
    public static let watchRequiresFullAccess = true

    /// Whether the watch may show favorites at all, given the states this
    /// device owns. The same rule as the widget (DECISIONS 0025): any
    /// state's purchase unlocks it, and the digest then lists only the
    /// favorites in owned states. Read in one place: where the phone builds
    /// the watch's digest (`AppEnvironment.publishWidgetDigest()`).
    public static func watchAllowed(entitledStates: Set<String>) -> Bool {
        !watchRequiresFullAccess || !entitledStates.isEmpty
    }

    /// What full access unlocks, in the words the purchase screen lists.
    /// One place, so the screen, About and the App Store copy can't drift
    /// apart (`FullAccessCopyTests` checks the App Store side).
    public static let fullAccessFeatures = [
        "An alert on this device when a favorite is newly on CDFW's weekly schedule",
        "The Favorite waters widget for your Home Screen and Lock Screen",
        "Your favorite waters on Apple Watch, with a complication",
    ]

    // MARK: Per state (DECISIONS 0025)

    /// Alerts for a water need its state's purchase. California's is the
    /// original Full Access (`StateAccess.californiaProductID`).
    public static func notificationsAllowed(forState code: String, entitledStates: Set<String>) -> Bool {
        entitledStates.contains(code)
    }

    /// The widget unlocks with any state's purchase, and then lists only the
    /// favorites in states this device owns.
    public static func widgetsAllowed(entitledStates: Set<String>) -> Bool {
        !widgetsRequireFullAccess || !entitledStates.isEmpty
    }

    /// What a state's purchase unlocks, in the purchase screen's words. A
    /// report state's alert says "stocked", a schedule state's "scheduled".
    public static func stateFeatures(stateName: String, agencyShortName: String, semantics: StateSemantics) -> [String] {
        let alert: String
        switch semantics {
        case .schedule:
            alert = "An alert on this device when a \(stateName) favorite is newly on \(agencyShortName)'s schedule"
        case .report:
            alert = ReportWording.alertFeature(stateName: stateName, agencyShortName: agencyShortName)
        case .plan:
            alert = "A reminder on this device when a \(stateName) favorite's planned stocking period begins, in \(agencyShortName)'s own words"
        }
        return [alert, "\(stateName) favorites in the Favorite waters widget", "\(stateName) favorites on Apple Watch"]
    }
}
