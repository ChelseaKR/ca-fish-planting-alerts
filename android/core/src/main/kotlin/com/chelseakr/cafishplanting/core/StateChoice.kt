package com.chelseakr.cafishplanting.core

import java.time.Duration
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * One state the person can pick, on the introduction's "Find your waters"
 * page and on Browse before a state is chosen (docs/DECISIONS.md 0053).
 * Everything here comes from the v2 snapshot's own state entry: no list of
 * states is typed into the app.
 */
data class StateOption(
    val code: String,
    val name: String,
    /** "CDFW stocking schedule, 412 waters". The count is left out when the snapshot gives none. */
    val detail: String,
    /** "Read Nov 3, 2026", or "Updates paused since Oct 15, 2026". */
    val status: String,
    /** The last good read's day when the state is paused, else `null`. A paused state is never shown as current. */
    val pausedSince: PlainDate?,
) {
    val isPaused: Boolean get() = pausedSince != null
}

/**
 * The first-run state picker (plan N6, decision 9A): ask, with no location
 * and no default. California is one state among the others, in the
 * snapshot's order. A skipped picker leaves no state chosen, and Browse then
 * shows the same list instead of any one state's waters.
 */
object StateChoice {
    /**
     * The site's rule for "Updates paused" (`state_coverage.py`,
     * DECISIONS 0051): the latest check failed and the last good read is more
     * than this many days old.
     */
    const val PAUSED_AFTER_DAYS = 7L

    /** The introduction page that carries the picker: "Find your waters". */
    const val PICKER_PAGE_ID = "browse"

    const val PICKER_TITLE = "Which state do you fish?"
    const val PICKER_NOTE = "No location needed. Pick one here, or later from the States list."
    const val BROWSE_TITLE = "Pick a state"
    const val BROWSE_BODY = "Each state's stocking data, shown the way its agency publishes it. Pick one to browse its waters."
    const val NONE_LISTED = "The data on this device doesn't list its states yet. Swipe down to check for a newer copy."

    private val day: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)

    /** The last good read's day (UTC, as the site) when [state] is paused at [now], else `null`. */
    fun pausedSince(state: StateInfo, now: Instant): PlainDate? {
        if (state.lastAttemptOK) return null
        if (Duration.between(state.lastSuccessAt, now) <= Duration.ofDays(PAUSED_AFTER_DAYS)) return null
        return PlainDate.of(state.lastSuccessAt.atZone(ZoneOffset.UTC).toLocalDate())
    }

    fun dayLabel(date: PlainDate): String = date.toLocalDate().format(day)

    fun option(state: StateInfo, now: Instant): StateOption {
        val paused = pausedSince(state, now)
        val kind = state.kindLabel.lowercase(Locale.US)
        val detail = if (state.watersCount > 0) "${state.agencyShortName} $kind, ${state.watersCount} waters" else "${state.agencyShortName} $kind"
        val read = PlainDate.of(state.lastSuccessAt.atZone(ZoneOffset.UTC).toLocalDate())
        val status = if (paused != null) "Updates paused since ${dayLabel(paused)}" else "Read ${dayLabel(read)}"
        return StateOption(state.code, state.name, detail, status, paused)
    }

    /**
     * The states to offer: only a v2 snapshot's, in its order. A v1 file
     * (California alone, from before states) offers none, rather than a
     * state taken from the app's own defaults.
     */
    fun options(snapshot: Snapshot?, now: Instant): List<StateOption> {
        if (snapshot == null || snapshot.schemaVersion < 2) return emptyList()
        return snapshot.states.map { option(it, now) }
    }

    /** The chosen state, while the snapshot still carries it; otherwise none, and never California in its place. */
    fun resolve(choice: BrowseChoice, snapshot: Snapshot?): String? =
        choice.state?.takeIf { snapshot?.state(it) != null }
}
