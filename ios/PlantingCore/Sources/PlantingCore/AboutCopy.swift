import Foundation

/// The About screen's words that describe the app rather than a purchase,
/// kept apart from the view so a test can hold them to the national framing
/// (DECISIONS 0049): no state is the app's default, California's week-only
/// rule is stated as California's, and any list of states comes from the
/// snapshot, never from this file. Android's `AboutCopy.kt` carries the same
/// words, apart from the platform's own names (`AboutCopyTest.kt`).
public enum AboutCopy {
    public static let whatItDoes = "Favorite any water for free and browse its full history. A state's full access adds a notification on this device when a favorite there is newly on its agency's schedule or stocking report, or its planned period begins, and a Home Screen and Lock Screen widget with your favorites."

    public static let california = "In California, CDFW publishes the week a plant is scheduled, not the day, and all plants are subject to change. For California waters this app shows a week, never a day, and says \"scheduled\" rather than \"stocked\"."

    public static let otherStates = "Other states come from their own wildlife agencies. Each date is shown as precisely as the agency gives it: a day, a week, or a month. Where an agency reports stockings after they happen instead of scheduling them, the app says so and shows how recent its newest record is."

    public static let alertTiming = "iOS decides when the app is allowed to refresh in the background, and each agency updates on its own rhythm (California's schedule is weekly), so an alert can arrive a day or more after the agency posts, not the minute it does."

    public static let checking = "The app also checks for newer data when you open it, at most every few hours. If it can't, it says so and keeps showing the last data it has, with the week or date it covers."

    public static let independence = "This app is independent. It is not affiliated with or endorsed by any state wildlife agency."

    /// A data-source section's heading, the same for every state.
    public static func dataSourceHeader(stateName: String) -> String { "\(stateName): data source and license" }

    /// One line per state this device has unlocked, in the snapshot's order
    /// of states, named as the snapshot names them. A product for a state the
    /// snapshot doesn't carry isn't shown: there is no name to show for it.
    public static func unlockedLines(states: [StateInfo], entitled: Set<String>) -> [String] {
        states.filter { entitled.contains($0.code) }.map { "\($0.name) unlocked" }
    }
}
