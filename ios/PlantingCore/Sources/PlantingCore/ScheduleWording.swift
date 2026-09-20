import Foundation

/// The words for a water's most recent scheduled week. The water screen and
/// the share sheet both use them, so the two can't drift apart.
///
/// CDFW publishes the week a plant is *scheduled*, never the day, and says
/// "all fish plants are subject to change". `schema/README.md`: "Never say
/// 'stocked'", "never say 'planted on'", and "Say 'scheduled' / 'listed for
/// the week of …'". So nothing here says "planted" or "stocked", which would
/// claim a plant happened, and every line names a week, never a day. The
/// site says the same thing ("most recently scheduled for planting the week
/// of …", `pipeline/src/cfpa/templates/water.html.jinja`).
public enum ScheduleWording {
    /// For a water with no listed week at all.
    public static let noScheduledWeekYet = "Not on the schedule for any week so far in this app's history"

    /// "Next scheduled for the week of 2026-09-20", or nil if no upcoming week.
    public static func nextScheduledLine(for water: Water, sourceWeek: Week) -> String? {
        let upcoming = water.listedPlants(onOrAfter: sourceWeek)
        guard let nextWeek = upcoming.first?.week else { return nil }
        return "Next scheduled: the \(nextWeek.label)"
    }

    /// "Last scheduled for the week of 2026-09-06", or `noScheduledWeekYet`,
    /// or a next-scheduled line when only future weeks exist.
    public static func lastScheduledLine(for water: Water, sourceWeek: Week) -> String {
        if let week = water.lastListedWeek {
            return "Last scheduled for the \(week.label)"
        }
        if let next = nextScheduledLine(for: water, sourceWeek: sourceWeek) {
            return next
        }
        return noScheduledWeekYet
    }

    /// Legacy entry point for callers without a source week.
    public static func lastScheduledLine(for water: Water) -> String {
        guard let week = water.lastListedWeek else { return noScheduledWeekYet }
        return "Last scheduled for the \(week.label)"
    }
}
