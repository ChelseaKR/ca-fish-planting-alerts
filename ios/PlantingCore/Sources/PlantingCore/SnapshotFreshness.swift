import Foundation

/// How often the app may fetch the snapshot on its own while it is open: at
/// launch and each time it returns to the foreground.
///
/// The fetch is the same single GET `SnapshotRefresher` makes for the
/// background task, against the same host, and the throttle reads the same
/// `SnapshotMeta.lastAttemptAt` the background task writes, so a recent
/// background refresh also counts. The source changes weekly and the site is
/// rebuilt daily, so a few hours between checks loses nothing.
public struct RefreshThrottle: Equatable, Sendable {
    /// Wait after a check that reached the site (updated or not modified).
    public let afterSuccess: TimeInterval
    /// Wait after a check that failed. Shorter, so one bad connection at
    /// launch doesn't leave "couldn't check" up for hours, but still long
    /// enough that a failing network isn't retried on every foreground.
    public let afterFailure: TimeInterval

    /// At most one check every 6 hours, or every 30 minutes after a failure.
    public static let foreground = RefreshThrottle(afterSuccess: 6 * 60 * 60, afterFailure: 30 * 60)

    public init(afterSuccess: TimeInterval, afterFailure: TimeInterval) {
        self.afterSuccess = afterSuccess
        self.afterFailure = afterFailure
    }

    /// Whether a check may run now.
    public func isDue(meta: SnapshotMeta, now: Date) -> Bool {
        guard let last = meta.lastAttemptAt else { return true }
        let elapsed = now.timeIntervalSince(last)
        // A last attempt "in the future" means the device clock moved back.
        // Waiting for the clock to catch up could strand the app on old data
        // for days; the check re-stamps `lastAttemptAt`, so this can't loop.
        guard elapsed >= 0 else { return true }
        return elapsed >= (meta.lastAttemptFailed ? afterFailure : afterSuccess)
    }
}

/// What the app says about the schedule it is showing: which week it is
/// for, whether that week is over, and how the last check for a newer one
/// went.
///
/// The rule this type exists to keep: absence is never rendered as a value.
/// A failed check never changes the snapshot (`SnapshotStore` keeps the last
/// good one), so every count here comes from a snapshot the pipeline
/// published, and every sentence names that snapshot's week. Nothing here
/// says "this week" about a week that has ended, and a failed or stale check
/// is said plainly rather than shown as "nothing listed".
public struct SnapshotFreshness: Equatable, Sendable {
    public enum Check: Equatable, Sendable {
        /// A check is running now.
        case checking
        /// Nothing has been checked on this device yet.
        case never
        /// The last check reached the site, so this is the newest published schedule.
        case succeeded(at: Date)
        /// The last check failed. `lastSuccessAt` is the last one that worked, if any.
        case failed(at: Date, lastSuccessAt: Date?)
    }

    /// The schedule's own calendar (`schema/README.md`: dates are
    /// America/Los_Angeles civil dates). Staleness is judged in it, not in
    /// the device's time zone.
    public static let scheduleTimeZone = TimeZone(identifier: "America/Los_Angeles")!

    /// The week the snapshot is for (`source_week`).
    public let week: Week
    public let origin: SnapshotOrigin
    public let check: Check
    /// That week has ended by the schedule's calendar: the device's date is
    /// after `week.end`, so the schedule shown is out of date.
    public let isStale: Bool
    /// Distinct waters listed for `week`, from the snapshot's `this_week`.
    public let watersListed: Int

    public init(snapshot: Snapshot, origin: SnapshotOrigin, meta: SnapshotMeta, isChecking: Bool, now: Date) {
        week = snapshot.sourceWeek
        self.origin = origin
        watersListed = Set(snapshot.thisWeek.map(\.waterID)).count
        isStale = Self.scheduleDate(of: now) > snapshot.sourceWeek.end
        if isChecking {
            check = .checking
        } else if let attempt = meta.lastAttemptAt {
            check = meta.lastAttemptFailed
                ? .failed(at: attempt, lastSuccessAt: meta.lastSuccessAt)
                : .succeeded(at: attempt)
        } else {
            check = .never
        }
    }

    /// The civil date `now` falls on in the schedule's time zone.
    public static func scheduleDate(of now: Date) -> PlainDate {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = scheduleTimeZone
        let parts = calendar.dateComponents([.year, .month, .day], from: now)
        return PlainDate(year: parts.year!, month: parts.month!, day: parts.day!)
    }

    public var isChecking: Bool { check == .checking }

    public var checkFailed: Bool {
        if case .failed = check { return true }
        return false
    }

    /// Show the detail as a warning: the week is over or the check failed.
    public var needsAttention: Bool { isStale || checkFailed }

    /// "Schedule for the week of 2026-09-13". Always names the week, whatever
    /// happened to the last check.
    public var headline: String { "Schedule for the \(week.label)" }

    /// How many waters that week lists. An empty week is stated only because
    /// a published snapshot says so; a failed check can't produce one.
    public var summary: String {
        switch watersListed {
        case 0: return "No waters are listed for that week."
        case 1: return "1 water is listed for that week."
        default: return "\(watersListed) waters are listed for that week."
        }
    }

    /// The plain statement of how current this is.
    public var detail: String {
        var sentences: [String] = []
        switch check {
        case .checking:
            sentences.append("Checking for a newer schedule…")
        case .never:
            sentences.append(origin == .bundled
                ? "This is the schedule that came with the app. It hasn't been checked for a newer one yet."
                : "It hasn't been checked for a newer one yet.")
        case .succeeded:
            sentences.append(isStale
                ? "This is the newest schedule published so far."
                : "This is the newest published schedule.")
        case .failed:
            sentences.append(origin == .bundled
                ? "Couldn't check for a newer schedule, so this is the one that came with the app."
                : "Couldn't check for a newer schedule, so this is the last one downloaded.")
        }
        if isStale {
            sentences.append("That week has ended, so this schedule is out of date.")
        }
        return sentences.joined(separator: " ")
    }

    /// When the last check worked, for a "Last checked" line. `nil` while
    /// checking or before any check has worked on this device.
    public var lastSuccessfulCheck: Date? {
        switch check {
        case .succeeded(let at): return at
        case .failed(_, let lastSuccessAt): return lastSuccessAt
        case .checking, .never: return nil
        }
    }

    /// The tag on a water listed in the snapshot's week: "This week" only
    /// while that week is current, otherwise the week itself.
    public var listedBadge: String { isStale ? week.label : "This week" }

    /// The same, for VoiceOver: "scheduled this week" or "scheduled for the week of …".
    public var listedPhrase: String { isStale ? "scheduled for the \(week.label)" : "scheduled this week" }
}

extension SnapshotMeta {
    /// The last check failed (`SnapshotStore.recordFailure`).
    public var lastAttemptFailed: Bool { lastOutcome == SnapshotStore.failedOutcome }
}
