import Foundation

/// What every surface says when a state's latest check failed
/// (`StateInfo.lastAttemptOK` is false): the widget, the watch, Favorites,
/// water detail, the alerts footer and Siri. The pipeline keeps the last
/// good read when a check fails, so the weeks the app holds for that state
/// are old ones. They are never presented as the current schedule: the
/// surface says the agency couldn't be checked, and since when.
///
/// The same words as `StateCheckWording` in the Android app's `StateCheck.kt`
/// (`MultiStateParityTests` checks both against one fixture). Dates are ISO
/// (`2026-10-15`), like every week label in the app, so the two apps and
/// every locale say the same thing.
public enum StateCheckWording {
    /// The civil date of the last good read when the state's latest check
    /// failed, or `nil` when it worked.
    public static func failedSince(_ state: StateInfo?) -> PlainDate? {
        guard let state, !state.lastAttemptOK else { return nil }
        return state.asOf
    }

    /// "schedule", "stocking report" or "plan": what the agency publishes.
    public static func kind(_ semantics: StateSemantics) -> String {
        switch semantics {
        case .schedule: return "schedule"
        case .report: return "stocking report"
        case .plan: return "plan"
        }
    }

    /// A widget or watch row: "Couldn't check TWRA's schedule since 2026-10-15".
    public static func short(agencyShortName: String, semantics: StateSemantics, since: PlainDate) -> String {
        "Couldn't check \(agencyShortName)'s \(kind(semantics)) since \(since.isoDate)"
    }

    /// The tag for a small space (the watch, the Lock Screen).
    public static let shortTag = "Couldn't check"

    /// Favorites and water detail: the short line, and what the weeks shown are.
    public static func notice(agencyShortName: String, semantics: StateSemantics, since: PlainDate) -> String {
        "\(short(agencyShortName: agencyShortName, semantics: semantics, since: since)). What's shown is from that last read and may be out of date."
    }

    public static func notice(_ state: StateInfo) -> String? {
        failedSince(state).map { notice(agencyShortName: state.agencyShortName, semantics: state.semantics, since: $0) }
    }

    /// The alerts footer while the check is failing: no alert can come
    /// until the agency can be read again.
    public static func alertsPaused(stateName: String, agencyShortName: String, semantics: StateSemantics) -> String {
        "Alerts for \(stateName) waters are paused until \(agencyShortName)'s \(kind(semantics)) can be checked again."
    }

    public static func alertsPaused(_ state: StateInfo) -> String? {
        guard failedSince(state) != nil else { return nil }
        return alertsPaused(stateName: state.name, agencyShortName: state.agencyShortName, semantics: state.semantics)
    }

    /// Siri and Shortcuts: never an old week as the answer.
    public static func answer(waterName: String, agencyShortName: String, semantics: StateSemantics, since: PlainDate) -> String {
        "Trout Truck couldn't check \(agencyShortName)'s \(kind(semantics)) since \(since.isoDate), so it can't say what's current for \(waterName). Open Trout Truck to see what that last read listed."
    }
}
