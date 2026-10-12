import Foundation

/// Favorites whose alerts the person has turned off, from an alert's
/// "Mute this water" button or the switch on the water's screen. A muted
/// water stays a favorite: it stays in Favorites, in the widget and in
/// Shortcuts. Only its alerts stop.
///
/// Muting never touches the alert baseline (`AlertState`). The planner keeps
/// replanning a muted water like any other, so turning its alerts back on
/// announces only what is new after that, never the weeks it missed while
/// muted.
public struct MutedWaters: Codable, Equatable, Sendable {
    public private(set) var ids: Set<Water.ID>

    public init(ids: Set<Water.ID> = []) { self.ids = ids }

    public func contains(_ id: Water.ID) -> Bool { ids.contains(id) }

    public mutating func mute(_ id: Water.ID) { ids.insert(id) }

    public mutating func unmute(_ id: Water.ID) { ids.remove(id) }

    public var isEmpty: Bool { ids.isEmpty }

    /// The alerts a plan may show: every planned alert except those for a
    /// muted water. Call between `AlertPlanner.plan` and scheduling.
    public func unmuted(_ notifications: [PlannedNotification]) -> [PlannedNotification] {
        notifications.filter { !ids.contains($0.waterID) }
    }
}

extension AppStorageLayout {
    public var mutedWatersFile: URL { directory.appendingPathComponent("muted-alerts.json") }
}

/// Persistence for muted waters. A missing or corrupt file reads as "none
/// muted": a disk problem can only turn alerts back on, never silence a
/// water the person didn't mute.
public struct MutedWatersStore: Sendable {
    let file: JSONFileStore<MutedWaters>
    public init(layout: AppStorageLayout) { file = JSONFileStore(url: layout.mutedWatersFile) }

    public func load() -> MutedWaters {
        (try? file.load()) ?? MutedWaters()
    }

    public func save(_ muted: MutedWaters) throws {
        try file.save(muted)
    }
}

/// The buttons a planting alert carries, shown on a long press or a pull
/// down. The identifiers are stored by iOS with the app's registered
/// categories, so they never change once shipped.
public enum PlantingAlertAction {
    /// Set as the alert's `categoryIdentifier`.
    public static let categoryIdentifier = "TT_PLANTING_ALERT"
    /// Turns that water's alerts off without opening the app.
    public static let muteIdentifier = "mute"
    /// The button's title. iOS shows it under the alert, so it is short.
    public static let muteTitle = "Mute this water"
}
