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
        "\(Self.scheduledPhrase(weeks: weeks)) (\(Self.speciesPhrase(species))). Plans can change; CDFW gives the week, not the day."
    }

    /// The distinct weeks, ascending.
    public var weeks: [PlainDate] { Set(newKeys.map(\.weekStart)).sorted() }

    /// The distinct species, in `newKeys` order.
    public var species: [String] {
        newKeys.map(\.species).reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
    }

    /// "Scheduled for the week of …": week-of only, never a day.
    static func scheduledPhrase(weeks: [PlainDate]) -> String {
        if weeks.count == 1 { return "Scheduled for the week of \(weeks[0].isoDate)" }
        return "Scheduled for the weeks of " + weeks.map(\.isoDate).joined(separator: " and ")
    }

    /// An empty list is said, never left blank.
    static func speciesPhrase(_ species: [String]) -> String {
        species.isEmpty ? "species not stated" : species.joined(separator: ", ")
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

/// One alert the app planned, kept for the in-app history. It records the
/// schedule's own granularity, the week(s), never a day: `foundAt` is when
/// this device found the new week(s), not when fish are planted.
public struct NotificationRecord: Codable, Equatable, Sendable, Identifiable {
    /// Unique per record. `PlannedNotification.id` alone is not: a week that
    /// is removed and later relisted produces the same identifier again.
    public let id: String
    public let waterID: Water.ID
    public let waterName: String
    /// Ascending week starts, as in the alert.
    public let weeks: [PlainDate]
    public let species: [String]
    public let foundAt: Date

    public init(id: String, waterID: Water.ID, waterName: String, weeks: [PlainDate], species: [String], foundAt: Date) {
        self.id = id
        self.waterID = waterID
        self.waterName = waterName
        self.weeks = weeks
        self.species = species
        self.foundAt = foundAt
    }

    public init(_ notification: PlannedNotification, foundAt: Date) {
        self.init(id: "\(notification.id).\(Int(foundAt.timeIntervalSince1970))",
                  waterID: notification.waterID,
                  waterName: notification.waterName,
                  weeks: notification.weeks,
                  species: notification.species,
                  foundAt: foundAt)
    }

    /// "Scheduled for the week of 2026-09-20 (Rainbow trout)": the same
    /// wording as the alert itself.
    public var summary: String {
        "\(PlannedNotification.scheduledPhrase(weeks: weeks)) (\(PlannedNotification.speciesPhrase(species)))"
    }
}

/// The alerts of the last 30 days, newest first. Pure: the caller passes
/// the clock.
public struct NotificationHistory: Codable, Equatable, Sendable {
    public static let retentionDays = 30
    public private(set) var records: [NotificationRecord]
    public init(records: [NotificationRecord] = []) { self.records = records }

    /// Adds the alerts found at `now`, then drops records older than
    /// `retentionDays`.
    public mutating func record(_ notifications: [PlannedNotification], at now: Date) {
        records.append(contentsOf: notifications.map { NotificationRecord($0, foundAt: now) })
        records.sort { $0.foundAt > $1.foundAt }
        prune(now: now)
    }

    /// Drops records older than `retentionDays` before `now`.
    public mutating func prune(now: Date) {
        let cutoff = now.addingTimeInterval(-Double(Self.retentionDays) * 24 * 60 * 60)
        records.removeAll { $0.foundAt < cutoff }
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
