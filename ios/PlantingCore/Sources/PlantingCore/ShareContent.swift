import Foundation

/// The text a person sends when they share a water from `WaterDetailView`'s
/// share button. Pure and `SwiftUI`-free (no `import SwiftUI`, no
/// `Bundle.main`) so it can be exercised with plain `swift test` — see
/// `ShareContentTests` — the same reason `AlertPlanner` lives here rather
/// than in the app target.
///
/// Every word is grounded in the real `Water`/`Snapshot` the share was
/// invoked from:
/// - the status line only claims a planting when `water.lastListedWeek` is
///   non-`nil`, and only names species `water.lastListedSpecies` actually
///   lists for that week (never `speciesSeen`, which can include other
///   weeks or `removed` plants);
/// - a water with no observed history gets the same honest sentence
///   `WaterDetailView` already shows in that case, never a fabricated one;
/// - the link is `SnapshotEndpoint.siteWaterURL(slug:)` — the site's real,
///   stable per-water URL — and is simply omitted (not replaced with a
///   placeholder) if that can't be formed.
///
/// Per `schema/README.md` ("Never say 'stocked'.") this never uses the verb
/// "stocked". `lastListedWeek` is by construction not in the future, so
/// "planted" is the sanctioned term here (the same one `WaterDetailView`
/// already uses for this exact field) — as opposed to a future/current-week
/// plant, which the app calls "scheduled" and this type never describes.
public enum ShareContent {
    /// The product name the message is signed with (DECISIONS 0010). Same
    /// string as the app's `CFBundleDisplayName` in `Info.plist`; repeated
    /// here because this type never reads `Bundle.main`.
    public static let productName = "Trout Truck"

    /// The full share-sheet message: water name, real status, real link.
    public static func message(for water: Water, siteURL: URL?) -> String {
        var parts = ["\(water.name) — \(productName), CA fish planting alerts.", statusLine(for: water)]
        if let siteURL {
            parts.append("Stocking history and schedule: \(siteURL.absoluteString)")
        }
        return parts.joined(separator: " ")
    }

    /// The one sentence stating what, if anything, this water's real history
    /// says happened most recently. Exposed separately so it's easy to test
    /// in isolation from message framing/links.
    public static func statusLine(for water: Water) -> String {
        guard let lastListedWeek = water.lastListedWeek else {
            return "Not yet planted in the schedule this app has observed."
        }
        let species = water.lastListedSpecies
        guard !species.isEmpty else {
            // Defensive only: lastListedWeek is derived from a listed plant
            // in the real snapshot, so this shouldn't occur — but never
            // silently invent a species name if it somehow does.
            return "Last planted \(lastListedWeek.label)."
        }
        return "Last planted with \(species.joined(separator: ", ")), \(lastListedWeek.label)."
    }
}
