package com.chelseakr.cafishplanting.core

import kotlinx.serialization.Serializable

/**
 * Favorites whose alerts are off, from an alert's "Mute this water" button
 * or the switch on the water's page. A muted water stays a favorite; only
 * its alerts stop. Muting never touches the alert baseline, so turning
 * alerts back on announces only what is new after that.
 */
@Serializable
data class MutedWaters(val ids: Set<String> = emptySet()) {
    fun contains(id: String): Boolean = id in ids

    fun muting(id: String): MutedWaters = MutedWaters(ids + id)

    fun unmuting(id: String): MutedWaters = MutedWaters(ids - id)

    val isEmpty: Boolean get() = ids.isEmpty()

    /** Every planned alert except those for a muted water. Call between planning and posting. */
    fun unmuted(notifications: List<PlannedNotification>): List<PlannedNotification> =
        notifications.filter { it.waterID !in ids }
}

/** The button a planting alert carries. The identifiers match the iOS app's. */
object PlantingAlertAction {
    const val CATEGORY_IDENTIFIER = "TT_PLANTING_ALERT"
    const val MUTE_IDENTIFIER = "mute"
    const val MUTE_TITLE = "Mute this water"
}
