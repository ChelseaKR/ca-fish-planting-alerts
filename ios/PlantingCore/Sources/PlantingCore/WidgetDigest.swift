import Foundation

/// What the Home Screen and Lock Screen widget shows: the schedule's week at
/// the person's favorite waters.
///
/// The app builds it from the snapshot it already has on this device and
/// writes it to the App Group container (`WidgetDigestStore`) whenever the
/// snapshot, a favorite, or the last check changes. The widget only reads
/// it. The widget makes no network request of its own, so the app's single
/// snapshot GET stays its only network call.
///
/// The same rule as the app: absence is never rendered as a value. Every
/// line names the week it is about. A week that has ended is never called
/// "this week", and a missing digest, a failed check, or a favorite the
/// snapshot doesn't have is said plainly, never shown as "nothing scheduled".
public struct WidgetDigest: Codable, Equatable, Sendable {
    /// Bumped when the shape changes, so a widget never misreads a digest
    /// written by a different version of the app.
    public static let currentVersion = 1

    public let version: Int
    /// The snapshot's week (`source_week`).
    public let week: Week
    /// When the pipeline built the snapshot.
    public let snapshotGeneratedAt: Date
    /// The last check for a newer schedule failed.
    public let lastCheckFailed: Bool
    /// When a check last worked on this device, if one has.
    public let lastSuccessfulCheck: Date?
    /// Distinct waters the snapshot lists for `week`.
    public let watersListed: Int
    /// The favorites the snapshot has, in the order they were added.
    public let favorites: [Favorite]
    /// Favorites the snapshot doesn't have (a water CDFW dropped). Counted,
    /// never silently left out.
    public let missingFavorites: Int
    /// The widget needs full access and this device doesn't have it
    /// (`FreeTier.widgetsAllowed`). Then `favorites` is empty.
    public let locked: Bool

    public struct Favorite: Codable, Equatable, Sendable, Identifiable {
        public let id: Water.ID
        public let name: String
        public let countyLabel: String
        /// Species listed for the digest's `week`, in the order first seen.
        /// Empty when the water isn't listed that week.
        public let speciesThisWeek: [String]
        /// The first week after the digest's `week` that the schedule
        /// already lists for this water, if any.
        public let nextWeek: Week?
        /// The newest listed week that isn't in the future (`last_listed_week`).
        public let lastListedWeek: Week?

        public init(id: Water.ID, name: String, countyLabel: String, speciesThisWeek: [String], nextWeek: Week?, lastListedWeek: Week?) {
            self.id = id; self.name = name; self.countyLabel = countyLabel
            self.speciesThisWeek = speciesThisWeek; self.nextWeek = nextWeek; self.lastListedWeek = lastListedWeek
        }

        public var isListedThisWeek: Bool { !speciesThisWeek.isEmpty }
    }

    public init(version: Int = WidgetDigest.currentVersion, week: Week, snapshotGeneratedAt: Date, lastCheckFailed: Bool, lastSuccessfulCheck: Date?, watersListed: Int, favorites: [Favorite], missingFavorites: Int, locked: Bool) {
        self.version = version; self.week = week; self.snapshotGeneratedAt = snapshotGeneratedAt
        self.lastCheckFailed = lastCheckFailed; self.lastSuccessfulCheck = lastSuccessfulCheck
        self.watersListed = watersListed; self.favorites = favorites
        self.missingFavorites = missingFavorites; self.locked = locked
    }

    /// Builds the digest from what the app holds. `favorites` in the order
    /// they were added.
    public init(snapshot: Snapshot, meta: SnapshotMeta, favorites ids: [Water.ID], locked: Bool) {
        var favorites: [Favorite] = []
        var missing = 0
        if !locked {
            for id in ids {
                guard let water = snapshot.water(id: id) else { missing += 1; continue }
                var species: [String] = []
                for plant in water.plants where plant.status == .listed && plant.week == snapshot.sourceWeek {
                    if !species.contains(plant.species) { species.append(plant.species) }
                }
                let next = water.plants.first { $0.status == .listed && $0.week > snapshot.sourceWeek }?.week
                favorites.append(Favorite(id: water.id, name: water.name, countyLabel: water.countyLabel,
                                          speciesThisWeek: species, nextWeek: next, lastListedWeek: water.lastListedWeek))
            }
        }
        self.init(week: snapshot.sourceWeek, snapshotGeneratedAt: snapshot.generatedAt,
                  lastCheckFailed: meta.lastAttemptFailed, lastSuccessfulCheck: meta.lastSuccessAt,
                  watersListed: Set(snapshot.thisWeek.map(\.waterID)).count,
                  favorites: favorites, missingFavorites: missing, locked: locked)
    }

    // MARK: What to say

    /// The week has ended by the schedule's own calendar
    /// (America/Los_Angeles), so it is no longer "this week".
    public func isStale(at now: Date) -> Bool {
        SnapshotFreshness.scheduleDate(of: now) > week.end
    }

    /// The moment the week ends: midnight after `week.end`, Los Angeles
    /// time. The widget's timeline changes its words then, without the app
    /// having to run.
    public var staleAt: Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = SnapshotFreshness.scheduleTimeZone
        let end = DateComponents(year: week.end.year, month: week.end.month, day: week.end.day)
        let endDay = calendar.date(from: end) ?? week.end.noonUTC
        return calendar.date(byAdding: .day, value: 1, to: endDay) ?? endDay
    }

    /// "This week", or the week itself once it has ended.
    public func headline(at now: Date) -> String {
        isStale(at: now) ? "Schedule for the \(week.label)" : "This week"
    }

    /// One line under the headline: which week, and how current it is.
    public func subheadline(at now: Date) -> String {
        if isStale(at: now) {
            return lastCheckFailed
                ? "That week has ended. Couldn't check for a newer schedule."
                : "That week has ended. Open Trout Truck to check for a newer schedule."
        }
        return lastCheckFailed
            ? "Schedule for the \(week.label). Couldn't check for a newer one."
            : "Schedule for the \(week.label)"
    }

    /// Where one favorite stands in the digest's week.
    public enum Status: Equatable, Sendable {
        /// Listed for the digest's week, and that week is current.
        case scheduledThisWeek(species: [String])
        /// Listed for the digest's week, which has ended.
        case scheduledForEndedWeek(Week, species: [String])
        /// Not listed for the digest's week, but a later week is listed.
        case scheduledLater(Week)
        /// Not listed for the digest's week, and no later week is listed.
        case notListed(Week, lastListed: Week?)
    }

    public func status(of favorite: Favorite, at now: Date) -> Status {
        if favorite.isListedThisWeek {
            return isStale(at: now)
                ? .scheduledForEndedWeek(week, species: favorite.speciesThisWeek)
                : .scheduledThisWeek(species: favorite.speciesThisWeek)
        }
        if let next = favorite.nextWeek {
            return .scheduledLater(next)
        }
        return .notListed(week, lastListed: favorite.lastListedWeek)
    }

    /// The short words for a favorite's status, for a widget row.
    public func statusLine(of favorite: Favorite, at now: Date) -> String {
        switch status(of: favorite, at: now) {
        case .scheduledThisWeek(let species):
            return "Scheduled this week: \(species.joined(separator: ", "))"
        case .scheduledForEndedWeek(let week, let species):
            return "Scheduled for the \(week.label): \(species.joined(separator: ", "))"
        case .scheduledLater(let week):
            return "Next scheduled for the \(week.label)"
        case .notListed(let week, let lastListed):
            let listed = "Not listed for the \(week.label)"
            guard let lastListed else { return listed }
            return "\(listed). Last scheduled for the \(lastListed.label)"
        }
    }

    /// Scheduled for the digest's week first, then a later week, then the
    /// rest. Within each, the order the favorites were added.
    public var favoritesByStatus: [Favorite] {
        func rank(_ favorite: Favorite) -> Int {
            if favorite.isListedThisWeek { return 0 }
            if favorite.nextWeek != nil { return 1 }
            return 2
        }
        return favorites.enumerated()
            .sorted { (rank($0.element), $0.offset) < (rank($1.element), $1.offset) }
            .map(\.element)
    }

    /// Favorites listed for the digest's week.
    public var favoritesListedThisWeek: Int { favorites.filter(\.isListedThisWeek).count }

    /// A one-line summary for small spaces (the Lock Screen's inline widget).
    public func summary(at now: Date) -> String {
        if locked { return "Unlock full access in Trout Truck" }
        if favorites.isEmpty {
            return missingFavorites > 0 ? "Favorites not in this schedule" : "No favorite waters yet"
        }
        let count = favoritesListedThisWeek
        let noun = count == 1 ? "favorite" : "favorites"
        if isStale(at: now) {
            return "\(count) \(noun) listed for the \(week.label)"
        }
        return "\(count) \(noun) scheduled this week"
    }
}

/// Reads and writes the digest in a directory both the app and the widget
/// can reach (the App Group container). A missing, unreadable, or
/// other-version file reads as `nil`, and the widget says to open the app,
/// never "nothing scheduled".
public struct WidgetDigestStore: Sendable {
    /// Declared in both targets' entitlements files.
    public static let appGroupIdentifier = "group.com.chelseakr.cafishplanting"
    public static let fileName = "widget-digest.json"

    let file: JSONFileStore<WidgetDigest>

    public init(directory: URL) {
        file = JSONFileStore(url: directory.appendingPathComponent(Self.fileName))
    }

    /// The store in the shared App Group container, or `nil` when this
    /// process has no access to the group (a build without the entitlement).
    public static func appGroup(fileManager: FileManager = .default) -> WidgetDigestStore? {
        fileManager.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier).map(WidgetDigestStore.init(directory:))
    }

    public var url: URL { file.url }

    public func load() -> WidgetDigest? {
        guard let digest = try? file.load(), digest.version == WidgetDigest.currentVersion else { return nil }
        return digest
    }

    public func save(_ digest: WidgetDigest) throws {
        try file.save(digest)
    }
}
