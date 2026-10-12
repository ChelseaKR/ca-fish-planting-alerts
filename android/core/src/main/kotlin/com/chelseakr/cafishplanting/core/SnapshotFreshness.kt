package com.chelseakr.cafishplanting.core

import java.time.Duration
import java.time.Instant
import java.time.ZoneId

/**
 * How often the app may fetch the snapshot on its own while it is open, the
 * same throttle as `RefreshThrottle.swift`: at most once every 6 hours, or
 * every 30 minutes after a failed check. The background work's checks count
 * too, because both read the same [SnapshotMeta].
 */
data class RefreshThrottle(val afterSuccess: Duration, val afterFailure: Duration) {
    fun isDue(meta: SnapshotMeta, now: Instant): Boolean {
        val last = meta.lastAttemptAt ?: return true
        val elapsed = Duration.between(last, now)
        // A last attempt "in the future" means the clock moved back.
        if (elapsed.isNegative) return true
        return elapsed >= if (meta.lastAttemptFailed) afterFailure else afterSuccess
    }

    companion object {
        val FOREGROUND = RefreshThrottle(Duration.ofHours(6), Duration.ofMinutes(30))
    }
}

/**
 * What the app says about the schedule it is showing, as
 * `SnapshotFreshness.swift`: which week, whether that week is over, and how
 * the last check went. Absence is never rendered as a value: a failed check
 * never changes the snapshot, and every sentence names the snapshot's week.
 */
class SnapshotFreshness(snapshot: Snapshot, val origin: SnapshotOrigin, meta: SnapshotMeta, isChecking: Boolean, now: Instant) {
    sealed interface Check {
        data object Checking : Check
        data object Never : Check
        data class Succeeded(val at: Instant) : Check
        data class Failed(val at: Instant, val lastSuccessAt: Instant?) : Check
    }

    val week: Week = snapshot.sourceWeek
    val watersListed: Int = snapshot.thisWeekWaterIDs.size
    val isStale: Boolean = scheduleDate(now) > snapshot.sourceWeek.end
    val check: Check = when {
        isChecking -> Check.Checking
        meta.lastAttemptAt != null ->
            if (meta.lastAttemptFailed) Check.Failed(meta.lastAttemptAt, meta.lastSuccessAt) else Check.Succeeded(meta.lastAttemptAt)
        else -> Check.Never
    }

    val isChecking: Boolean get() = check == Check.Checking
    val checkFailed: Boolean get() = check is Check.Failed
    val needsAttention: Boolean get() = isStale || checkFailed

    val headline: String get() = "Schedule for the ${week.label}"

    val summary: String
        get() = when (watersListed) {
            0 -> "No waters are listed for that week."
            1 -> "1 water is listed for that week."
            else -> "$watersListed waters are listed for that week."
        }

    val detail: String
        get() {
            val sentences = mutableListOf<String>()
            sentences += when (check) {
                Check.Checking -> "Checking for a newer schedule…"
                Check.Never -> if (origin == SnapshotOrigin.BUNDLED) {
                    "This is the schedule that came with the app. It hasn't been checked for a newer one yet."
                } else {
                    "It hasn't been checked for a newer one yet."
                }
                is Check.Succeeded -> if (isStale) "This is the newest schedule published so far." else "This is the newest published schedule."
                is Check.Failed -> if (origin == SnapshotOrigin.BUNDLED) {
                    "Couldn't check for a newer schedule, so this is the one that came with the app."
                } else {
                    "Couldn't check for a newer schedule, so this is the last one downloaded."
                }
            }
            if (isStale) sentences += "That week has ended, so this schedule is out of date."
            return sentences.joinToString(" ")
        }

    /** When the last check worked; `null` while checking or before any check worked. */
    val lastSuccessfulCheck: Instant?
        get() = when (val c = check) {
            is Check.Succeeded -> c.at
            is Check.Failed -> c.lastSuccessAt
            else -> null
        }

    /** The tag on a water listed in the snapshot's week. */
    val listedBadge: String get() = if (isStale) week.label else "This week"

    /** The same, for TalkBack. */
    val listedPhrase: String get() = if (isStale) "scheduled for the ${week.label}" else "scheduled this week"

    companion object {
        /** The schedule's own calendar (`schema/README.md`). Staleness is judged in it, not the device's zone. */
        val SCHEDULE_ZONE: ZoneId = ZoneId.of("America/Los_Angeles")

        fun scheduleDate(now: Instant): PlainDate = PlainDate.of(now.atZone(SCHEDULE_ZONE).toLocalDate())
    }
}
