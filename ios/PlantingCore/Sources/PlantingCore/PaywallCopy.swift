import Foundation

/// The purchase sheet's plain-language lines, kept here so `swift test` can
/// hold them to the rules below. The sheet for any state shows, in this
/// order: what the purchase adds (`FreeTier.stateFeatures`), what it costs
/// and how (`terms`), and how current that state's data is (`freshness`),
/// before the buy button.
///
/// Rules (DECISIONS 0025, and the listing rules in `docs/APP-STORE-LISTING.md`):
/// - No urgency or scarcity: no countdown, sale, "limited", "today", "last
///   chance".
/// - No promise the data can't keep. Never "forever": a purchase keeps
///   working as long as the state's agency publishes and Trout Truck can read
///   it, and that is what the sheet says.
/// - When the newest check of a state's source failed, the sheet says so
///   before the buy button, not only on the Browse screen.
public enum PaywallCopy {
    /// Words the sheet never uses. `PaywallCopyTests` checks every line here
    /// against them, so a later edit can't slip one in.
    public static let bannedWords = [
        "forever", "lifetime", "limited", "hurry", "today only", "last chance",
        "sale", "discount", "% off", "only", "first", "best",
    ]

    /// What the purchase costs and how it works, under the feature list.
    public static func terms(stateName: String) -> String {
        "One payment for \(stateName). No subscription and no account. Each state is its own purchase, and Restore purchases brings it back on a new device."
    }

    /// How current the state's data is, from the snapshot the app already
    /// has. Uses the last good fetch's civil date (`StateInfo.asOf`).
    public static func freshness(_ state: StateInfo, locale: Locale = .current) -> String {
        let date = state.asOf.formatted(locale: locale)
        if state.lastAttemptOK {
            return "Latest update read from \(state.agencyShortName): \(date). Alerts follow \(state.agencyShortName)'s own page and are never more current than it is."
        }
        return "Trout Truck's newest check of \(state.agencyShortName) failed, so what you see is still the update read on \(date). Alerts for \(state.name) resume when \(state.agencyShortName)'s page can be read again."
    }
}
