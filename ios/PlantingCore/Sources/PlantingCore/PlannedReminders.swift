import Foundation

/// A reminder that a favorite's planned stocking period is beginning
/// (New York, DECISIONS 0034). New York publishes a spring plan once a year,
/// in its own words ("April - third week"), so there is nothing new to alert
/// on week by week. What the app can honestly do is remind: on the first day
/// of a planned period, it says the period, in DEC's words, and that it is a
/// plan, not a date or a confirmed stocking.
public struct PlannedReminder: Equatable, Sendable, Identifiable {
    /// Deterministic, so a replan replaces rather than duplicates.
    public let id: String
    public let waterID: Water.ID
    public let waterName: String
    /// The period's first day: when the reminder shows.
    public let fireOn: PlainDate
    public let periodLabel: String
    public let species: [String]
    public let agencyShortName: String

    public static let idPrefix = "remind."

    public var title: String { "\(waterName): planned stocking period" }

    public var body: String {
        let what = species.isEmpty ? "" : " (\(species.joined(separator: ", ")))"
        return "\(agencyShortName) plans to stock \(waterName) in \(periodLabel)\(what). A plan in \(agencyShortName)'s own words, not a date and not a confirmed stocking."
    }
}

/// Pure: which reminders a set of favorites should have.
public enum ReminderPlanner {
    /// A period longer than this ("Spring", "March - April") is too loose to
    /// remind about honestly, so it gets none.
    public static let maxSpanDays = 31

    public static func reminders(snapshot: Snapshot, favorites: [Water.ID], entitledStates: Set<String>, muted: Set<Water.ID>, today: PlainDate) -> [PlannedReminder] {
        var out: [PlannedReminder] = []
        for id in favorites where !muted.contains(id) {
            guard let water = snapshot.water(id: id), water.semantics == .plan,
                  entitledStates.contains(water.state) else { continue }
            let upcoming = water.plants.filter {
                $0.status == .listed && $0.week.start > today && $0.week.spanDays <= maxSpanDays
            }
            let byPeriod = Dictionary(grouping: upcoming, by: \.week)
            for (period, plants) in byPeriod {
                var species: [String] = []
                for plant in plants where !species.contains(plant.species) { species.append(plant.species) }
                out.append(PlannedReminder(id: "\(PlannedReminder.idPrefix)\(id).\(period.start.isoDate)",
                                           waterID: id, waterName: water.name, fireOn: period.start,
                                           periodLabel: period.label, species: species,
                                           agencyShortName: water.agencyShortName))
            }
        }
        return out.sorted { ($0.fireOn, $0.id) < ($1.fireOn, $1.id) }
    }
}
