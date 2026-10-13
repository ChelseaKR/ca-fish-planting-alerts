package com.chelseakr.cafishplanting.core

/**
 * Every phrase that says "stocked", in one place, as `ReportWording.swift`
 * (DECISIONS 0025).
 *
 * California's rule stands: CDFW publishes a schedule, so nothing about
 * California may say "stocked" or "planted". Massachusetts and Michigan
 * report stockings that happened, and "scheduled" would understate that.
 * Those words live here, and only code that has already checked
 * `water.semantics == REPORT` calls them. `CopyAndRulesTest` skips this file
 * and nothing else when it scans for "stocked".
 */
object ReportWording {
    const val NO_STOCKING_ON_RECORD = "No stocking on record in this app's history"

    /** "Last stocked on 2026-10-09". */
    fun lastStocked(week: Week): String = "Last stocked ${if (week.precision == DatePrecision.DAY) "on " else ""}${week.phrase}"

    fun stockedThisWeek(species: List<String>): String = "Stocked this week: ${species.joinToString(", ")}"

    const val ROW_STATUS = "Stocked"

    fun alertTitle(waterName: String): String = "$waterName was stocked"

    fun alertBody(periods: List<String>, species: String, agencyShortName: String, lagging: Boolean): String {
        val lag = if (lagging) " Records can appear weeks after the stocking." else ""
        return "Stocked on ${periods.joinToString(" and ")} ($species), per $agencyShortName's report.$lag"
    }

    /** What a state's purchase unlocks for a report state. */
    fun alertFeature(stateName: String, agencyShortName: String): String =
        "An alert on this device when $agencyShortName reports stocking a $stateName favorite"
}
