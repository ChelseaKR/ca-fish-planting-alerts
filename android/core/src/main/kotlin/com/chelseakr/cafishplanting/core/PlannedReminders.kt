package com.chelseakr.cafishplanting.core

/**
 * A reminder that a favorite's planned stocking period is beginning (New
 * York), as `PlannedReminder` in ios/PlantingCore. New York publishes a
 * spring plan once a year, in its own words ("April - third week"), so
 * there is nothing new to alert on week by week. What the app can honestly
 * do is remind: on the first day of a planned period it says the period, in
 * the agency's words, and that it is a plan, not a date or a confirmed
 * stocking.
 */
data class PlannedReminder(
    /** Deterministic, so a replan replaces rather than duplicates. */
    val id: String,
    val waterID: String,
    val waterName: String,
    /** The period's first day: when the reminder shows. */
    val fireOn: PlainDate,
    val periodLabel: String,
    val species: List<String>,
    val agencyShortName: String,
) {
    val title: String get() = "$waterName: planned stocking period"

    val body: String
        get() {
            val what = if (species.isEmpty()) "" else " (${species.joinToString(", ")})"
            return "$agencyShortName plans to stock $waterName in $periodLabel$what. " +
                "A plan in $agencyShortName's own words, not a date and not a confirmed stocking."
        }

    companion object {
        const val ID_PREFIX = "remind."
    }
}

/** Pure: which reminders a set of favorites should have, as `ReminderPlanner` in Swift. */
object ReminderPlanner {
    /** A period longer than this ("Spring", "March - April") is too loose to remind about honestly, so it gets none. */
    const val MAX_SPAN_DAYS = 31

    fun reminders(
        snapshot: Snapshot,
        favorites: List<String>,
        entitledStates: Set<String>,
        muted: Set<String>,
        today: PlainDate,
    ): List<PlannedReminder> {
        val out = mutableListOf<PlannedReminder>()
        for (id in favorites) {
            if (id in muted) continue
            val water = snapshot.water(id) ?: continue
            if (water.semantics != StateSemantics.PLAN || water.state !in entitledStates) continue
            val upcoming = water.plants.filter {
                it.status == PlantStatus.LISTED && it.week.start > today && it.week.spanDays <= MAX_SPAN_DAYS
            }
            for ((period, plants) in upcoming.groupBy { it.week }) {
                out += PlannedReminder(
                    id = "${PlannedReminder.ID_PREFIX}$id.${period.start.isoDate}",
                    waterID = id,
                    waterName = water.name,
                    fireOn = period.start,
                    periodLabel = period.label,
                    species = plants.map { it.species }.distinct(),
                    agencyShortName = water.agencyShortName,
                )
            }
        }
        return out.sortedWith(compareBy({ it.fireOn }, { it.id }))
    }
}
