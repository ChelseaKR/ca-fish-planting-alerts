import Foundation

/// The spoken and written answer to "When is <water> scheduled next?" (the
/// Shortcuts and Siri action). Pure, so it is tested without the app.
///
/// The same rules as every screen: a week, never a day; "scheduled", never
/// "stocked" or "planted"; and the answer always names the schedule's week,
/// so an old schedule can't pass for a current one. A water with nothing
/// listed is "not on the schedule for the week of … or later", never "no
/// fish".
public enum ScheduleAnswer {
    public static func nextScheduled(for water: Water, in snapshot: Snapshot, now: Date) -> String {
        let week = snapshot.sourceWeek
        let stale = SnapshotFreshness.scheduleDate(of: now) > week.end
        let upcoming = water.listedPlants(onOrAfter: week)
        var sentences: [String] = []

        if let first = upcoming.first {
            let species = speciesList(upcoming.filter { $0.week == first.week })
            if first.week == week, !stale {
                sentences.append("\(water.name) is on the schedule this week, the \(week.label)\(species).")
            } else {
                sentences.append("\(water.name) is next scheduled for the \(first.week.label)\(species).")
            }
            let later = Array(Set(upcoming.map(\.week).filter { $0 > first.week })).sorted()
            if let next = later.first {
                sentences.append("After that, the \(next.label).")
            }
            sentences.append("CDFW gives the week, not the day, and plans can change.")
        } else {
            sentences.append("\(water.name) isn't on the schedule for the \(week.label) or later.")
            if let last = water.lastListedWeek {
                sentences.append("It was last scheduled for the \(last.label).")
            } else {
                sentences.append("It hasn't been on the schedule in this app's history.")
            }
        }

        if stale {
            sentences.append("This schedule is for the \(week.label), which has ended. Open Trout Truck to check for a newer one.")
        }
        return sentences.joined(separator: " ")
    }

    private static func speciesList(_ plants: [Plant]) -> String {
        var species: [String] = []
        for plant in plants where !species.contains(plant.species) { species.append(plant.species) }
        return species.isEmpty ? "" : " (\(species.joined(separator: ", ")))"
    }
}
