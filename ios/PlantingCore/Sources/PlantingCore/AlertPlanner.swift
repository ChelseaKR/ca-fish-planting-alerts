import Foundation

/// One (week, species) a favorited water had listed, as of the last time
/// the alert planner evaluated a snapshot. This is a baseline, not a
/// cumulative "ever notified" set: a plant that goes `removed` then
/// `listed` again is newsworthy again, exactly as `schema/README.md`
/// specifies ("a `(water_id, week, species)` with `status == \"listed\"`
/// appears in a refreshed snapshot that was not in the previous one").
public struct PlantKey: Hashable, Sendable, Codable {
    public let weekStart: PlainDate
    public let species: String
    public init(weekStart: PlainDate, species: String) { self.weekStart = weekStart; self.species = species }
    public init(_ plant: Plant) { self.weekStart = plant.week.start; self.species = plant.species }
}

/// Per favorited water, the listed-plant baseline as of the last
/// evaluation. Persisted so a cold app launch does not re-diff against
/// nothing (which would treat everything on screen as "new").
public struct AlertState: Codable, Equatable, Sendable {
    public var lastListed: [Water.ID: Set<PlantKey>]
    public init(lastListed: [Water.ID: Set<PlantKey>] = [:]) { self.lastListed = lastListed }
}

public struct PlannedNotification: Equatable, Sendable, Identifiable {
    /// Deterministic: `plant.<water id>.<newest new week>`. UNUserNotificationCenter
    /// replaces a pending request with the same identifier, so a double
    /// `schedule()` call for the same evaluation still collapses to one.
    public let id: String
    public let waterID: Water.ID
    public let waterName: String
    /// Ascending. Usually one; more when a refresh reveals several new weeks at once.
    public let newKeys: [PlantKey]

    public init(waterID: Water.ID, waterName: String, newKeys: [PlantKey]) {
        precondition(!newKeys.isEmpty)
        let sorted = newKeys.sorted { $0.weekStart == $1.weekStart ? $0.species < $1.species : $0.weekStart < $1.weekStart }
        self.newKeys = sorted
        self.id = "plant.\(waterID).\(sorted.last!.weekStart.isoDate)"
        self.waterID = waterID
        self.waterName = waterName
    }

    public var title: String { "\(waterName) is on the stocking schedule" }

    /// Week-of only, and "scheduled" rather than "stocked" — per
    /// `schema/README.md`: "all fish plants are subject to change... Never
    /// say 'stocked'."
    public func body() -> String {
        let byWeek = Dictionary(grouping: newKeys, by: \.weekStart)
        let weeks = byWeek.keys.sorted()
        let when: String
        if weeks.count == 1 {
            when = "Scheduled for the week of \(weeks[0].isoDate)"
        } else {
            when = "Scheduled for the weeks of " + weeks.map(\.isoDate).joined(separator: " and ")
        }
        let species = newKeys.map(\.species).reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        let what = species.isEmpty ? "species not stated" : species.joined(separator: ", ")
        return "\(when) (\(what)). Plans can change; CDFW gives the week, not the day."
    }
}

public struct AlertPlan: Equatable, Sendable {
    public let notifications: [PlannedNotification]
    public let state: AlertState
    public init(notifications: [PlannedNotification], state: AlertState) {
        self.notifications = notifications
        self.state = state
    }
}

/// A record of a notification that was sent, for display in notification history.
public struct NotificationRecord: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let waterID: Water.ID
    public let waterName: String
    public let species: String
    public let sentAt: Date
    public init(id: String, waterID: Water.ID, waterName: String, species: String, sentAt: Date) {
        self.id = id
        self.waterID = waterID
        self.waterName = waterName
        self.species = species
        self.sentAt = sentAt
    }
}

/// A log of sent notifications, limited to the last 30 days.
public struct NotificationHistory: Codable, Equatable, Sendable {
    public var records: [NotificationRecord]
    public init(records: [NotificationRecord] = []) { self.records = records }

    /// Adds a new record and prunes entries older than 30 days.
    public mutating func record(_ notification: PlannedNotification) {
        let record = NotificationRecord(
            id: notification.id,
            waterID: notification.waterID,
            waterName: notification.waterName,
            species: notification.species.joined(separator: ", "),
            sentAt: Date()
        )
        records.append(record)
        let cutoff = Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date()
        records.removeAll { $0.sentAt < cutoff }
    }
}

/// Pure. No clock, no I/O, no notification center — this is the function
/// `docs/APP-STORE.md` and the deliverable list call out to test without the
/// simulator. Implements the diff rule from `schema/README.md` exactly:
///
/// * For each favorited water, take its listed plants at or after
///   `snapshot.sourceWeek` (current and future weeks — never past ones).
/// * Any `(week, species)` in that set that is **not** in the water's stored
///   baseline is new → one notification per water, naming every new
///   (week, species) found in this evaluation.
/// * The baseline is then replaced (not accumulated) with the current
///   listed set, so the next evaluation diffs against *this* one — a
///   `removed` week silently drops out of the baseline, and if CDFW relists
///   it later that is new again, matching the pipeline's own semantics for
///   "subject to change".
/// * "Same week, evaluated twice" (an unchanged or re-fetched-but-identical
///   snapshot) yields zero notifications, because the diff is empty.
/// * A water with no plants at or after `sourceWeek` gets an empty baseline
///   and no notification — correct, not an error.
public enum AlertPlanner {
    public static func plan(snapshot: Snapshot, favorites: [Water.ID], state: AlertState) -> AlertPlan {
        var nextBaseline: [Water.ID: Set<PlantKey>] = [:]
        var notifications: [PlannedNotification] = []

        for id in favorites {
            guard let water = snapshot.water(id: id) else {
                // The water dropped out of the snapshot entirely: carry the
                // last known baseline through untouched rather than losing it.
                if let previous = state.lastListed[id] { nextBaseline[id] = previous }
                continue
            }
            let currentListed = Set(water.listedPlants(onOrAfter: snapshot.sourceWeek).map(PlantKey.init))
            let previous = state.lastListed[id] ?? []
            let newKeys = currentListed.subtracting(previous)
            if !newKeys.isEmpty {
                notifications.append(PlannedNotification(waterID: id, waterName: water.name, newKeys: Array(newKeys)))
            }
            nextBaseline[id] = currentListed
        }
        return AlertPlan(notifications: notifications, state: AlertState(lastListed: nextBaseline))
    }

    /// Call when a water is favorited: seed its baseline at what is
    /// currently visible so the plants already on screen are not announced.
    public static func seeding(_ state: AlertState, favoriting id: Water.ID, snapshot: Snapshot) -> AlertState {
        guard let water = snapshot.water(id: id) else { return state }
        var next = state
        next.lastListed[id] = Set(water.listedPlants(onOrAfter: snapshot.sourceWeek).map(PlantKey.init))
        return next
    }

    public static func pruning(_ state: AlertState, unfavoriting id: Water.ID) -> AlertState {
        var next = state
        next.lastListed.removeValue(forKey: id)
        return next
    }
}
