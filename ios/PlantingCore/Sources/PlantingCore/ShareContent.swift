import Foundation

/// The text a person sends when they share a water from `WaterDetailView`'s
/// share button. Pure and `SwiftUI`-free (no `import SwiftUI`, no
/// `Bundle.main`) so it can be exercised with plain `swift test` — see
/// `ShareContentTests` — the same reason `AlertPlanner` lives here rather
/// than in the app target.
///
/// Every word is grounded in the real `Water`/`Snapshot` the share was
/// invoked from:
/// - the status line only names a scheduled week when `water.lastListedWeek` is
///   non-`nil`, and only names species `water.lastListedSpecies` actually
///   lists for that week (never `speciesSeen`, which can include other
///   weeks or `removed` plants);
/// - a water with no observed history gets the same honest sentence
///   `WaterDetailView` already shows in that case, never a fabricated one;
/// - the link is `SnapshotEndpoint.siteWaterURL(slug:)` — the site's real,
///   stable per-water URL — and is simply omitted (not replaced with a
///   placeholder) if that can't be formed.
///
/// The status line is `ScheduleWording`'s, the same words `WaterDetailView`
/// shows: "scheduled", never "planted" or "stocked", and a week, never a
/// day. CDFW publishes scheduled plants, which are subject to change, so
/// even a past week is only ever "scheduled" (`schema/README.md`).
public enum ShareContent {
    /// The product name the message is signed with (DECISIONS 0010). Same
    /// string as the app's `CFBundleDisplayName` in `Info.plist`; repeated
    /// here because this type never reads `Bundle.main`.
    public static let productName = "Trout Truck"

    /// The full share-sheet message: water name, real status, real link.
    public static func message(for water: Water, siteURL: URL?, sourceWeek: Week) -> String {
        var parts = ["\(water.name) — \(productName), CA fish planting alerts.", statusLine(for: water, sourceWeek: sourceWeek)]
        if let siteURL {
            parts.append("Schedule history: \(siteURL.absoluteString)")
        }
        return parts.joined(separator: " ")
    }

    /// The one sentence stating which week, if any, this water's real history
    /// says it was most recently scheduled for. Exposed separately so it's easy to test
    /// in isolation from message framing/links.
    public static func statusLine(for water: Water, sourceWeek: Week) -> String {
        let line = ScheduleWording.lastScheduledLine(for: water, sourceWeek: sourceWeek)
        let species = water.lastListedSpecies
        guard water.lastListedWeek != nil, !species.isEmpty else {
            // No listed week, or (defensive only: lastListedWeek is derived
            // from a listed plant, so this shouldn't occur) a week with no
            // species. Never invent a species name.
            return "\(line)."
        }
        return "\(line): \(species.joined(separator: ", "))."
    }

    /// Legacy entry point for callers without a source week.
    public static func message(for water: Water, siteURL: URL?) -> String {
        var parts = ["\(water.name) — \(productName), CA fish planting alerts.", statusLine(for: water)]
        if let siteURL {
            parts.append("Schedule history: \(siteURL.absoluteString)")
        }
        return parts.joined(separator: " ")
    }

    /// Legacy status line for callers without a source week.
    public static func statusLine(for water: Water) -> String {
        let line = ScheduleWording.lastScheduledLine(for: water)
        let species = water.lastListedSpecies
        guard water.lastListedWeek != nil, !species.isEmpty else {
            return "\(line)."
        }
        return "\(line): \(species.joined(separator: ", "))."
    }
}
