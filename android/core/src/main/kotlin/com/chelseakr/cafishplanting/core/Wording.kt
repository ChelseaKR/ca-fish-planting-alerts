package com.chelseakr.cafishplanting.core

/**
 * The words for a water's most recent and next dates, shared by the water
 * page and the share text, as `ScheduleWording.swift`. A schedule state
 * never says "planted" or "stocked", and every line names a period at the
 * agency's own precision ([Week.phrase]). A report state (Massachusetts,
 * Michigan) reports stockings that happened, so its lines say "stocked"
 * ([ReportWording]).
 */
object ScheduleWording {
    const val NO_SCHEDULED_WEEK_YET = "Not on the schedule for any week so far in this app's history"

    /** For a report-state water with nothing on record. */
    const val NO_STOCKING_ON_RECORD = ReportWording.NO_STOCKING_ON_RECORD

    /** "Next scheduled: the week of 2026-09-20", or `null` if nothing upcoming (always `null` for a report). */
    fun nextScheduledLine(water: Water, sourceWeek: Week): String? {
        if (water.semantics != StateSemantics.SCHEDULE) return null
        val next = water.listedPlants(sourceWeek).firstOrNull()?.week ?: return null
        return "Next scheduled: ${next.phrase}"
    }

    /** "Last scheduled for the week of 2026-09-06", "Last stocked on 2026-10-09", or an honest line when there is none. */
    fun lastScheduledLine(water: Water, sourceWeek: Week): String {
        if (water.semantics == StateSemantics.REPORT) {
            return water.lastListedWeek?.let(ReportWording::lastStocked) ?: NO_STOCKING_ON_RECORD
        }
        water.lastListedWeek?.let { return "Last scheduled for ${it.phrase}" }
        nextScheduledLine(water, sourceWeek)?.let { return it }
        water.monthsNote?.let { return "Listed by month only (${water.agencyShortName}'s letters): $it" }
        return NO_SCHEDULED_WEEK_YET
    }
}

/** The share text, grounded in the real water, as `ShareContent.swift`. */
object ShareContent {
    const val PRODUCT_NAME = "Trout Truck"

    fun message(water: Water, siteURL: String?, sourceWeek: Week): String {
        val tagline = if (water.state == "CA") "CA fish planting alerts" else "fish stocking alerts"
        val parts = mutableListOf("${water.name} — $PRODUCT_NAME, $tagline.", statusLine(water, sourceWeek))
        if (siteURL != null) parts += "Schedule history: $siteURL"
        return parts.joinToString(" ")
    }

    fun statusLine(water: Water, sourceWeek: Week): String {
        val line = ScheduleWording.lastScheduledLine(water, sourceWeek)
        val species = water.lastListedSpecies
        if (water.lastListedWeek == null || species.isEmpty()) return "$line."
        return "$line: ${species.joinToString(", ")}."
    }
}

/** The words before the system notification permission prompt (`NotificationPrimingCopy` in the iOS app). */
data class NotificationPrimingCopy(
    val waterName: String?,
    val isEntitled: Boolean,
    /** The water's agency and what its records mean. California's by default. */
    val agencyShortName: String = "CDFW",
    val semantics: StateSemantics = StateSemantics.SCHEDULE,
) {
    data class Point(val icon: String, val text: String)

    val headline: String
        get() = if (waterName != null) {
            "Get an alert when $waterName is on the schedule"
        } else {
            "Get an alert when a favorite is on the schedule"
        }

    val points: List<Point>
        get() {
            val which = waterName?.let { "$it or another favorite" } ?: "one of your favorites"
            val points = mutableListOf(
                Point(
                    "calendar",
                    when {
                        semantics == StateSemantics.REPORT ->
                            "When $agencyShortName's stocking report adds $which, this device shows one alert, " +
                                "naming the day $agencyShortName gives."
                        agencyShortName == "CDFW" ->
                            "When CDFW's weekly schedule adds a week for $which, this device shows one alert. " +
                                "It names the week, never a day, and CDFW says plans can change."
                        else ->
                            "When $agencyShortName's schedule adds a date for $which, this device shows one alert. " +
                                "It names the date as precisely as $agencyShortName gives it, and plans can change."
                    },
                ),
                Point(
                    "device",
                    "Alerts are made on this device from the schedule it downloads. There is no account and no server, " +
                        "and nothing about you or your favorites leaves the device.",
                ),
                Point("quiet", "No other notifications: no marketing, no reminders, no badges."),
            )
            if (!isEntitled) {
                points += Point(
                    "lock",
                    "Alerts are part of full access, a one-time purchase for each state in About. " +
                        "If you allow notifications now, alerts start as soon as you unlock the state.",
                )
            }
            return points
        }

    val footnote: String get() = "Next, Android asks for permission. You can change it any time in Settings."
}
