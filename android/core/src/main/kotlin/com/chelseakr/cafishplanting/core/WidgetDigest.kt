package com.chelseakr.cafishplanting.core

import kotlinx.serialization.Serializable
import java.time.Instant
import java.time.LocalTime

@Serializable
data class DigestWeek(
    @Serializable(with = PlainDateSerializer::class) val start: PlainDate,
    @Serializable(with = PlainDateSerializer::class) val end: PlainDate,
    val label: String,
    /** A digest written before precision existed reads as a week, which is what it was. */
    val precision: DatePrecision = DatePrecision.WEEK,
) {
    fun toWeek(): Week = Week(start, end, label, precision)

    companion object {
        fun of(week: Week): DigestWeek = DigestWeek(week.start, week.end, week.label, week.precision)
    }
}

/**
 * What the home screen widget shows: the schedule's week at the person's
 * favorite waters. The same type and words as `WidgetDigest.swift`. The app
 * writes it after every refresh, favorite change and entitlement change;
 * the widget only reads it and never fetches anything.
 *
 * Absence is never rendered as a value: every line names its week, an ended
 * week is never "this week", and a missing digest, a failed check or a
 * favorite the snapshot lacks is said plainly.
 */
@Serializable
data class WidgetDigest(
    val version: Int = CURRENT_VERSION,
    val week: DigestWeek,
    @Serializable(with = InstantSerializer::class) val snapshotGeneratedAt: Instant,
    val lastCheckFailed: Boolean,
    @Serializable(with = InstantSerializer::class) val lastSuccessfulCheck: Instant? = null,
    val watersListed: Int,
    val favorites: List<Favorite>,
    val missingFavorites: Int,
    val locked: Boolean,
    /** Favorites in states this device hasn't bought. Counted and said, never shown and never dropped silently. */
    val favoritesInOtherStates: Int = 0,
) {
    @Serializable
    data class Favorite(
        val id: String,
        val name: String,
        val countyLabel: String,
        val speciesThisWeek: List<String>,
        val nextWeek: DigestWeek? = null,
        val lastListedWeek: DigestWeek? = null,
        /** A report state's water: its rows say "stocked", never "scheduled". */
        val isReport: Boolean = false,
    ) {
        val isListedThisWeek: Boolean get() = speciesThisWeek.isNotEmpty()
    }

    sealed interface Status {
        data class ScheduledThisWeek(val species: List<String>) : Status
        data class ScheduledForEndedWeek(val week: Week, val species: List<String>) : Status
        data class ScheduledLater(val week: Week) : Status
        data class NotListed(val week: Week, val lastListed: Week?) : Status
    }

    fun isStale(now: Instant): Boolean = SnapshotFreshness.scheduleDate(now) > week.end

    /** Midnight after the week's Saturday, Los Angeles time: when "this week" has to stop. */
    val staleAt: Instant
        get() = week.end.toLocalDate().plusDays(1).atTime(LocalTime.MIDNIGHT).atZone(SnapshotFreshness.SCHEDULE_ZONE).toInstant()

    fun headline(now: Instant): String = if (isStale(now)) "Schedule for the ${week.label}" else "This week"

    fun subheadline(now: Instant): String = if (isStale(now)) {
        if (lastCheckFailed) {
            "That week has ended. Couldn't check for a newer schedule."
        } else {
            "That week has ended. Open Trout Truck to check for a newer schedule."
        }
    } else if (lastCheckFailed) {
        "Schedule for the ${week.label}. Couldn't check for a newer one."
    } else {
        "Schedule for the ${week.label}"
    }

    fun status(favorite: Favorite, now: Instant): Status {
        if (favorite.isListedThisWeek) {
            return if (isStale(now)) {
                Status.ScheduledForEndedWeek(week.toWeek(), favorite.speciesThisWeek)
            } else {
                Status.ScheduledThisWeek(favorite.speciesThisWeek)
            }
        }
        favorite.nextWeek?.let { return Status.ScheduledLater(it.toWeek()) }
        return Status.NotListed(week.toWeek(), favorite.lastListedWeek?.toWeek())
    }

    fun statusLine(favorite: Favorite, now: Instant): String {
        if (favorite.isReport) {
            if (favorite.isListedThisWeek && !isStale(now)) return ReportWording.stockedThisWeek(favorite.speciesThisWeek)
            return favorite.lastListedWeek?.let { ReportWording.lastStocked(it.toWeek()) } ?: ReportWording.NO_STOCKING_ON_RECORD
        }
        return when (val s = status(favorite, now)) {
            is Status.ScheduledThisWeek -> "Scheduled this week: ${s.species.joinToString(", ")}"
            is Status.ScheduledForEndedWeek -> "Scheduled for ${s.week.phrase}: ${s.species.joinToString(", ")}"
            is Status.ScheduledLater -> "Next scheduled for ${s.week.phrase}"
            is Status.NotListed -> {
                val listed = "Not listed for ${s.week.phrase}"
                if (s.lastListed == null) listed else "$listed. Last scheduled for ${s.lastListed.phrase}"
            }
        }
    }

    /** Listed for the digest's week first, then a later week, then the rest; within each, the order added. */
    val favoritesByStatus: List<Favorite>
        get() {
            fun rank(f: Favorite) = when {
                f.isListedThisWeek -> 0
                f.nextWeek != null -> 1
                else -> 2
            }
            return favorites.withIndex().sortedWith(compareBy({ rank(it.value) }, { it.index })).map { it.value }
        }

    val favoritesListedThisWeek: Int get() = favorites.count { it.isListedThisWeek }

    fun summary(now: Instant): String {
        if (locked) return "Unlock full access in Trout Truck"
        if (favorites.isEmpty()) {
            return when {
                missingFavorites > 0 -> "Favorites not in this schedule"
                favoritesInOtherStates > 0 -> "Favorites are in states not unlocked"
                else -> "No favorite waters yet"
            }
        }
        val count = favoritesListedThisWeek
        val noun = if (count == 1) "favorite" else "favorites"
        return if (isStale(now)) "$count $noun listed for the ${week.label}" else "$count $noun scheduled this week"
    }

    /** What to say when there are no favorites to list, or `null` when there are. */
    fun emptyMessage(): String? = when {
        locked -> "This widget is part of full access, a one-time purchase in Trout Truck."
        favorites.isNotEmpty() -> null
        missingFavorites > 0 -> "Your favorite waters aren't in this week's schedule data. Open Trout Truck to check them."
        else -> "Star a water in Trout Truck to see its schedule here."
    }

    /** A true line about the published schedule itself, shown with [emptyMessage]. */
    fun scheduleContext(): String {
        val waters = if (watersListed == 1) "1 water is" else "$watersListed waters are"
        return "$waters listed for the ${week.label}."
    }

    companion object {
        /**
         * 2: favorites carry their state's words ([Favorite.isReport]), and
         * favorites in a state without its purchase are counted, never shown.
         */
        const val CURRENT_VERSION = 2

        /** No digest yet: the widget says to open the app, never "nothing scheduled". */
        const val NO_DIGEST_MESSAGE = "Open Trout Truck to load the schedule here."

        /**
         * Builds the digest from what the app holds, favorites in the order
         * added. [entitledStates] `null` means every state (the shape before
         * states, kept for callers and tests that predate them).
         */
        fun build(
            snapshot: Snapshot,
            meta: SnapshotMeta,
            favoriteIDs: List<String>,
            locked: Boolean,
            entitledStates: Set<String>? = null,
        ): WidgetDigest {
            val favorites = mutableListOf<Favorite>()
            var missing = 0
            var otherStates = 0
            if (!locked) {
                for (id in favoriteIDs) {
                    val water = snapshot.water(id)
                    if (water == null) {
                        missing += 1
                        continue
                    }
                    if (entitledStates != null && water.state !in entitledStates) {
                        otherStates += 1
                        continue
                    }
                    val week = snapshot.currentWeek(water)
                    val species = water.plants
                        .filter { it.status != PlantStatus.REMOVED && it.week.precision != DatePrecision.MONTH && it.week.overlaps(week) }
                        .map { it.species }
                        .distinct()
                    val next = if (water.semantics == StateSemantics.SCHEDULE) {
                        water.plants.firstOrNull { it.status == PlantStatus.LISTED && it.week.start > week.end }?.week
                    } else {
                        null
                    }
                    favorites += Favorite(
                        id = water.id,
                        name = water.name,
                        countyLabel = water.countyLabel,
                        speciesThisWeek = species,
                        nextWeek = next?.let(DigestWeek::of),
                        lastListedWeek = water.lastListedWeek?.let(DigestWeek::of),
                        isReport = water.semantics == StateSemantics.REPORT,
                    )
                }
            }
            return WidgetDigest(
                week = DigestWeek.of(snapshot.sourceWeek),
                snapshotGeneratedAt = snapshot.generatedAt,
                lastCheckFailed = meta.lastAttemptFailed,
                lastSuccessfulCheck = meta.lastSuccessAt,
                watersListed = snapshot.thisWeekWaterIDs.size,
                favorites = favorites,
                missingFavorites = missing,
                locked = locked,
                favoritesInOtherStates = otherStates,
            )
        }

        private val store = { layout: AppStorageLayout -> JsonFileStore(layout.widgetDigestFile, serializer()) }

        /** A missing, unreadable or other-version file reads as `null`. */
        fun load(layout: AppStorageLayout): WidgetDigest? =
            store(layout).loadOrNull()?.takeIf { it.version == CURRENT_VERSION }

        /** Writes the digest; returns `false` when it was already the same, so the widget needn't redraw. */
        fun save(layout: AppStorageLayout, digest: WidgetDigest): Boolean {
            if (load(layout) == digest) return false
            // A failed write is not a redraw: the widget keeps what it had.
            return store(layout).trySave(digest)
        }
    }
}
