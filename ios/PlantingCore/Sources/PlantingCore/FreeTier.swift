import Foundation

/// The app's free/paid gate.
///
/// `docs/DECISIONS.md` 0007 shipped the StoreKit *mechanism* — entitlement
/// check, purchase, restore — without deciding what it unlocks, and left a
/// placeholder (a cap on favourited waters) so the mechanism could be real
/// without inventing product scope that was Chelsea's call. That call is
/// now made (see the DECISIONS entry that resolves 0007's "owner
/// follow-up"):
///
/// * **Favouriting and browsing are free and unconstrained for everyone.**
///   The app's own free tier must never be worse than the free website
///   (`docs/DECISIONS.md` 0001) already gives anyone, so favouriting is
///   never gated here or anywhere else in the app.
/// * **Local notifications are the paid unlock.** A website cannot push a
///   native notification to a phone — that's the one piece of value this
///   app has that the free site structurally cannot replicate, so it's the
///   coherent thing to gate instead of a capability the free site already
///   gives away. Non-purchasers can favourite freely; no local notification
///   is ever scheduled for any favourited water without the one-time
///   purchase (`com.chelseakr.cafishplanting.fullaccess`, see
///   `PurchaseManager`).
public enum FreeTier {
    /// Whether local notifications may be scheduled for a favourited
    /// water's schedule changes, given whether the one-time purchase is
    /// owned. Call this immediately before
    /// `NotificationScheduler.schedule(_:)` — never anywhere on the
    /// favouriting path, which this gate does not touch.
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

    /// What full access unlocks, in the words the purchase screen lists.
    /// One place, so the screen, About and the App Store copy can't drift
    /// apart (`FullAccessCopyTests` checks the App Store side).
    public static let fullAccessFeatures = [
        "An alert on this device when a favorite is newly on CDFW's weekly schedule",
        "The Favorite waters widget for your Home Screen and Lock Screen",
    ]
}
