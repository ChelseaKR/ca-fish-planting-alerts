import Foundation

/// Every phrase that says "stocked", in one place (DECISIONS 0025).
///
/// California's rule stands: CDFW publishes a *schedule*, so nothing about
/// California may say "stocked" or "planted" (`ScheduleWordingTests` scans
/// the whole app for it). Massachusetts and Michigan are different: their
/// agencies *report* stockings that happened, and "scheduled" would
/// understate that. Those words live here, and only code that has already
/// checked `water.semantics == .report` calls them. The scan skips this file
/// and nothing else.
public enum ReportWording {
    public static let noStockingOnRecord = "No stocking on record in this app's history"

    /// "Last stocked on 2026-10-09".
    public static func lastStocked(_ week: Week) -> String {
        "Last stocked \(week.precision == .day ? "on " : "")\(week.phrase)"
    }

    public static func stockedThisWeek(_ species: [String]) -> String {
        "Stocked this week: \(species.joined(separator: ", "))"
    }

    public static let rowStatus = "Stocked"

    public static func alertTitle(_ waterName: String) -> String { "\(waterName) was stocked" }

    public static func alertBody(periods: [String], species: String, agencyShortName: String, lagging: Bool) -> String {
        let lag = lagging ? " Records can appear weeks after the stocking." : ""
        return "Stocked on \(periods.joined(separator: " and ")) (\(species)), per \(agencyShortName)'s report.\(lag)"
    }

    /// The Siri and Shortcuts answer for a report-state water.
    public static func answer(waterName: String, last: Week?, agencyShortName: String, lagging: Bool) -> String {
        var line = last.map {
            "\(waterName) was last stocked \($0.precision == .day ? "on " : "")\($0.phrase), per \(agencyShortName)'s report."
        } ?? "\(waterName) has no stocking on record in this app's history."
        if lagging { line += " \(agencyShortName)'s records can appear weeks after the stocking." }
        return line
    }

    /// What a state's purchase unlocks for a report state.
    public static func alertFeature(stateName: String, agencyShortName: String) -> String {
        "An alert on this device when \(agencyShortName) reports stocking a \(stateName) favorite"
    }
}
