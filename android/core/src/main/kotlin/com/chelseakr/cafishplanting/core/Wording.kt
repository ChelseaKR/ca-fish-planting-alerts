package com.chelseakr.cafishplanting.core

/**
 * The words for a water's most recent scheduled week, shared by the water
 * page and the share text, as `ScheduleWording.swift`. Never "planted" or
 * "stocked", and every line names a week, never a day.
 */
object ScheduleWording {
    const val NO_SCHEDULED_WEEK_YET = "Not on the schedule for any week so far in this app's history"

    fun nextScheduledLine(water: Water, sourceWeek: Week): String? {
        val next = water.listedPlants(sourceWeek).firstOrNull()?.week ?: return null
        return "Next scheduled: the ${next.label}"
    }

    fun lastScheduledLine(water: Water, sourceWeek: Week): String {
        water.lastListedWeek?.let { return "Last scheduled for the ${it.label}" }
        return nextScheduledLine(water, sourceWeek) ?: NO_SCHEDULED_WEEK_YET
    }
}

/** The share text, grounded in the real water, as `ShareContent.swift`. */
object ShareContent {
    const val PRODUCT_NAME = "Trout Truck"

    fun message(water: Water, siteURL: String?, sourceWeek: Week): String {
        val parts = mutableListOf("${water.name} — $PRODUCT_NAME, CA fish planting alerts.", statusLine(water, sourceWeek))
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
data class NotificationPrimingCopy(val waterName: String?, val isEntitled: Boolean) {
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
                    "When CDFW's weekly schedule adds a week for $which, this device shows one alert. " +
                        "It names the week, never a day, and CDFW says plans can change.",
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
                    "Alerts are part of full access, a one-time purchase in About. " +
                        "If you allow notifications now, alerts start as soon as you unlock it.",
                )
            }
            return points
        }

    val footnote: String get() = "Next, Android asks for permission. You can change it any time in Settings."
}
