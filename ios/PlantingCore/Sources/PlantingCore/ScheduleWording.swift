import Foundation

/// The words for a water's most recent and next dates. The water screen and
/// the share sheet both use them, so the two can't drift apart.
///
/// California: CDFW publishes the week a plant is *scheduled*, never the
/// day, and says "all fish plants are subject to change". `schema/README.md`:
/// "Never say 'stocked'", "never say 'planted on'". So nothing here says
/// "planted" or "stocked" for a schedule state, and every line names a period
/// at the agency's own precision (`Week.phrase`): a week, a day, or a month.
/// A report state (Massachusetts, Michigan) reports stockings that happened,
/// so its lines say "stocked".
public enum ScheduleWording {
    /// For a water with no listed week at all.
    public static let noScheduledWeekYet = "Not on the schedule for any week so far in this app's history"

    /// For a report-state water with nothing on record.
    public static let noStockingOnRecord = ReportWording.noStockingOnRecord

    /// "Next scheduled: the week of 2026-09-20", or nil if nothing upcoming
    /// (and always nil for a report, which has no future).
    public static func nextScheduledLine(for water: Water, sourceWeek: Week) -> String? {
        guard water.semantics != .report else { return nil }
        guard let next = water.listedPlants(onOrAfter: sourceWeek).first?.week else { return nil }
        return water.semantics == .plan ? "Planned for \(next.phrase)" : "Next scheduled: \(next.phrase)"
    }

    /// "Last scheduled for the week of 2026-09-06", "Last stocked on
    /// 2026-10-09", or an honest line when there is none.
    public static func lastScheduledLine(for water: Water, sourceWeek: Week) -> String {
        if water.semantics == .report {
            return water.lastListedWeek.map(ReportWording.lastStocked) ?? noStockingOnRecord
        }
        if water.semantics == .plan {
            // A plan's future comes first: it is a reminder, not a record.
            if let next = nextScheduledLine(for: water, sourceWeek: sourceWeek) { return next }
            if let week = water.lastListedWeek { return "Last planned for \(week.phrase)" }
            return noScheduledWeekYet
        }
        if let week = water.lastListedWeek {
            return "Last scheduled for \(week.phrase)"
        }
        if let next = nextScheduledLine(for: water, sourceWeek: sourceWeek) {
            return next
        }
        if let note = water.monthsNote {
            return "Listed by month only (\(water.agencyShortName)'s letters): \(note)"
        }
        return noScheduledWeekYet
    }

    /// Legacy entry point for callers without a source week.
    public static func lastScheduledLine(for water: Water) -> String {
        if water.semantics == .report {
            return water.lastListedWeek.map(ReportWording.lastStocked) ?? noStockingOnRecord
        }
        guard let week = water.lastListedWeek else { return noScheduledWeekYet }
        return water.semantics == .plan ? "Last planned for \(week.phrase)" : "Last scheduled for \(week.phrase)"
    }
}
