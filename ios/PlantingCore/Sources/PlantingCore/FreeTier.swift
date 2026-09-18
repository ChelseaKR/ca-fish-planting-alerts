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
    /// purchase. **Not decided yet (owner question):** until it is, widgets
    /// are free for everyone, like favoriting and browsing. Flip this one
    /// flag to make them part of full access; the widget then says to
    /// unlock full access instead of listing favorites
    /// (`WidgetDigest.locked`). Nothing else changes.
    public static let widgetsRequireFullAccess = false

    /// Whether the widget may show favorites, given whether the one-time
    /// purchase is owned. Read in one place: where the app builds the
    /// widget's digest (`AppEnvironment.publishWidgetDigest()`).
    public static func widgetsAllowed(isEntitled: Bool) -> Bool {
        !widgetsRequireFullAccess || isEntitled
    }
}
