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
    /// For a water with no listed week up to the snapshot's own week
    /// (`lastListedWeek == nil`: every plant is in the future or removed).
    public static let noScheduledWeekYet = "Not on the schedule for any week so far in this app's history"

    /// "Last scheduled for the week of 2026-09-06", or `noScheduledWeekYet`.
    public static func lastScheduledLine(for water: Water) -> String {
        guard let week = water.lastListedWeek else { return noScheduledWeekYet }
        return "Last scheduled for the \(week.label)"
    }
}
