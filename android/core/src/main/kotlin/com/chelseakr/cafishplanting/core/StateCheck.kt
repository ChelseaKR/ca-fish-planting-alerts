package com.chelseakr.cafishplanting.core

/**
 * What every surface says when a state's latest check failed
 * ([StateInfo.lastAttemptOK] is false): the widget, Favorites, water detail
 * and the alerts footer. The pipeline keeps the last good read when a check
 * fails, so the weeks the app holds for that state are old ones. They are
 * never presented as the current schedule: the surface says the agency
 * couldn't be checked, and since when.
 *
 * The same words as `StateCheckWording.swift` (`MultiStateParityTest` checks
 * both apps against one fixture). Dates are ISO (`2026-10-15`), like every
 * week label in the app.
 */
object StateCheckWording {
    /** The civil date of the last good read when the latest check failed, or `null` when it worked. */
    fun failedSince(state: StateInfo?): PlainDate? = state?.takeIf { !it.lastAttemptOK }?.asOf

    /** "schedule", "stocking report" or "plan": what the agency publishes. */
    fun kind(semantics: StateSemantics): String = when (semantics) {
        StateSemantics.SCHEDULE -> "schedule"
        StateSemantics.REPORT -> "stocking report"
        StateSemantics.PLAN -> "plan"
    }

    /** A widget row: "Couldn't check TWRA's schedule since 2026-10-15". */
    fun short(agencyShortName: String, semantics: StateSemantics, since: PlainDate): String =
        "Couldn't check $agencyShortName's ${kind(semantics)} since ${since.isoDate}"

    /** Favorites and water detail: the short line, and what the weeks shown are. */
    fun notice(agencyShortName: String, semantics: StateSemantics, since: PlainDate): String =
        "${short(agencyShortName, semantics, since)}. What's shown is from that last read and may be out of date."

    fun notice(state: StateInfo): String? = failedSince(state)?.let { notice(state.agencyShortName, state.semantics, it) }

    /** The alerts footer while the check is failing: no alert can come until the agency can be read again. */
    fun alertsPaused(stateName: String, agencyShortName: String, semantics: StateSemantics): String =
        "Alerts for $stateName waters are paused until $agencyShortName's ${kind(semantics)} can be checked again."

    fun alertsPaused(state: StateInfo): String? =
        failedSince(state)?.let { alertsPaused(state.name, state.agencyShortName, state.semantics) }
}
