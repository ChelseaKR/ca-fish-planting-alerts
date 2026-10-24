package com.chelseakr.cafishplanting.core

import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The purchase sheet's plain-language lines, as `PaywallCopy.swift`, kept
 * here so the unit tests can hold them to the rules below. The sheet for any
 * state shows, in this order: what the purchase adds
 * ([FreeTier.stateFeatures]), what it costs and how ([terms]), and how
 * current that state's data is ([freshness]), before the buy button.
 *
 * Rules (DECISIONS 0025):
 * - No urgency or scarcity: no countdown, sale, "limited", "today", "last
 *   chance".
 * - No promise the data can't keep. Never "forever": a purchase keeps
 *   working as long as the state's agency publishes and Trout Truck can read
 *   it, and that is what the sheet says.
 * - When the newest check of a state's source failed, the sheet says so
 *   before the buy button, not only on the Browse screen.
 */
object PaywallCopy {
    /** Words the sheet never uses. `PaywallCopyTest` checks every line here against them. */
    val bannedWords = listOf(
        "forever", "lifetime", "limited", "hurry", "today only", "last chance",
        "sale", "discount", "% off", "only", "first", "best",
    )

    /** What the purchase costs and how it works, under the feature list. */
    fun terms(stateName: String): String =
        "One payment for $stateName. No subscription and no account. Each state is its own purchase, " +
            "and Restore purchases brings it back on a new device."

    /** "Sep 13, 2026", as `PlainDate.formatted` on iOS in en_US. */
    private val DATE: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)

    /**
     * How current the state's data is, from the snapshot the app already
     * has. Uses the last good fetch's civil date ([StateInfo.asOf]).
     */
    fun freshness(state: StateInfo): String {
        val date = state.asOf.toLocalDate().format(DATE)
        if (state.lastAttemptOK) {
            return "Latest update read from ${state.agencyShortName}: $date. " +
                "Alerts follow ${state.agencyShortName}'s own page and are never more current than it is."
        }
        return "Trout Truck's newest check of ${state.agencyShortName} failed, so what you see is still the update read on $date. " +
            "Alerts for ${state.name} resume when ${state.agencyShortName}'s page can be read again."
    }
}
