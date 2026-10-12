import Foundation

/// What the phone sends Apple Watch, and the one thing the watch sends back.
///
/// The phone's App Group container stays on the phone, so the watch gets the
/// same small digest the widget reads (`WidgetDigest`, about 1 KB) through
/// WatchConnectivity's application context: the latest one wins, and the
/// system delivers it when the watch is in reach. Nothing goes through a
/// server, and the watch makes no network request of its own.
///
/// The phone builds the digest, so the phone decides what the watch may show
/// (`FreeTier.watchAllowed`). A locked digest has no favorites in it, so the
/// watch cannot show more than the phone allows.
///
/// The watch sends back only a mute request: the ID of a water whose alerts
/// someone muted from the alert on their wrist (`PlantingAlertAction`).
public enum WatchSync {
    /// The application-context key that carries the digest as JSON.
    public static let digestKey = "widget_digest"
    /// The user-info key that carries a water ID to mute.
    public static let muteWaterIDKey = "mute_water_id"

    /// The application context for `digest`.
    public static func applicationContext(for digest: WidgetDigest) throws -> [String: Any] {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return [digestKey: try encoder.encode(digest)]
    }

    /// The digest in an application context, or `nil` when there is none, it
    /// doesn't decode, or a different app version wrote it. `nil` reads as
    /// "open Trout Truck on your iPhone", never as "nothing scheduled".
    public static func digest(fromApplicationContext context: [String: Any]) -> WidgetDigest? {
        guard let data = context[digestKey] as? Data else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        guard let digest = try? decoder.decode(WidgetDigest.self, from: data),
              digest.version == WidgetDigest.currentVersion
        else { return nil }
        return digest
    }

    /// The user info the watch sends when someone taps "Mute this water" there.
    public static func muteRequest(for id: Water.ID) -> [String: Any] {
        [muteWaterIDKey: id]
    }

    /// The water a mute request is about.
    public static func waterIDToMute(fromUserInfo userInfo: [String: Any]) -> Water.ID? {
        guard let id = userInfo[muteWaterIDKey] as? String, !id.isEmpty else { return nil }
        return id
    }
}

extension WidgetDigest {
    /// The favorite a watch complication shows: the first one listed for
    /// the digest's week, otherwise the one with the soonest later listed
    /// week (the order favorites were added breaks a tie). `nil` when no
    /// favorite is listed for this week or later; the complication then says
    /// so, never naming a water as if it were scheduled.
    public var nextFavorite: Favorite? {
        if let listed = favorites.first(where: \.isListedThisWeek) { return listed }
        return favorites.enumerated()
            .compactMap { item in item.element.nextWeek.map { (week: $0, offset: item.offset, favorite: item.element) } }
            .min { ($0.week, $0.offset) < ($1.week, $1.offset) }?
            .favorite
    }

    /// A few words for a small space, relative to the digest's week:
    /// "This week", "Scheduled that week" (once that week has ended), "Next: week of …" or "Not listed".
    public func shortStatus(of favorite: Favorite, at now: Date) -> String {
        switch status(of: favorite, at: now) {
        case .scheduledThisWeek: return "This week"
        case .scheduledForEndedWeek: return "Scheduled that week"
        case .scheduledLater(let week): return "Next: \(week.label)"
        case .notListed: return "Not listed"
        }
    }

    /// The last listed week up to the digest's week, in words, for a
    /// favorite's watch screen. `nil` when the newest listed week is after
    /// the digest's week: the next-scheduled line already says that, and a
    /// "last" week in the future would read as a contradiction.
    public func lastScheduledLine(of favorite: Favorite) -> String? {
        guard let last = favorite.lastListedWeek else { return "No earlier week on record" }
        guard last <= week else { return nil }
        return "Last scheduled: \(last.label)"
    }

    /// The next listed week after the digest's week, in words.
    public func nextScheduledLine(of favorite: Favorite) -> String {
        guard let next = favorite.nextWeek else { return "No later week listed yet" }
        return "Next scheduled: \(next.label)"
    }

    /// The locked watch's one line. The purchase is made on the phone; the
    /// watch has no purchase screen of its own.
    public static let watchLockedMessage = "Part of full access, a one-time purchase in Trout Truck on your iPhone."

    /// What the watch says before the phone has sent anything.
    public static let watchNoDigestMessage = "Open Trout Truck on your iPhone to load the schedule here."
}
