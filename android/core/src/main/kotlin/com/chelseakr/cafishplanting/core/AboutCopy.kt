package com.chelseakr.cafishplanting.core

/**
 * The About screen's words that describe the app rather than a purchase:
 * the iOS app's `AboutCopy.swift`, with Android's own names for its
 * surfaces ("home screen widget", "Android decides when the app may
 * refresh"). National framing (docs/DECISIONS.md 0049): no state is the
 * app's default, California's week-only rule is stated as California's, and
 * any list of states comes from the snapshot, never from this file.
 * `AboutCopyTest` holds every other word to the iOS file.
 */
object AboutCopy {
    const val WHAT_IT_DOES =
        "Favorite any water for free and browse its full history. A state's full access adds a notification on this device when a favorite there " +
            "is newly on its agency's schedule or stocking report, or its planned period begins, and a home screen widget with your favorites."

    const val CALIFORNIA =
        "In California, CDFW publishes the week a plant is scheduled, not the day, and all plants are subject to change. " +
            "For California waters this app shows a week, never a day, and says \"scheduled\" rather than \"stocked\"."

    const val OTHER_STATES =
        "Other states come from their own wildlife agencies. Each date is shown as precisely as the agency gives it: a day, a week, or a month. " +
            "Where an agency reports stockings after they happen instead of scheduling them, the app says so and shows how recent its newest record is."

    const val ALERT_TIMING =
        "Android decides when the app may refresh in the background, and each agency updates on its own rhythm (California's schedule is weekly), " +
            "so an alert can arrive a day or more after the agency posts, not the minute it does."

    const val CHECKING =
        "The app also checks for newer data when you open it, at most every few hours. If it can't, it says so and keeps showing the last data it has, " +
            "with the week or date it covers."

    const val INDEPENDENCE = "This app is independent. It is not affiliated with or endorsed by any state wildlife agency."

    /** A data-source section's heading, the same for every state. */
    fun dataSourceHeader(stateName: String): String = "$stateName: data source and license"

    /** One line per unlocked state, in the snapshot's order, named as the snapshot names it; a state it doesn't carry isn't shown. */
    fun unlockedLines(states: List<StateInfo>, entitled: Set<String>): List<String> =
        states.filter { it.code in entitled }.map { "${it.name} unlocked" }
}
