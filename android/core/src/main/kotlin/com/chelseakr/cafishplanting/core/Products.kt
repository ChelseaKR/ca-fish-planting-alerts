package com.chelseakr.cafishplanting.core

/**
 * One Google Play one-time product per state (DECISIONS 0025), as
 * `StateAccess.swift`. Browsing, history and favorites are free in every
 * state; a state's product unlocks alerts for that state's favorites and
 * lists them in the widget.
 *
 * The Play product IDs map to the App Store ones like this:
 *
 * | State | App Store                                 | Google Play  |
 * |-------|-------------------------------------------|--------------|
 * | CA    | `com.chelseakr.cafishplanting.fullaccess` | `fullaccess` |
 * | TN    | `com.chelseakr.cafishplanting.state.tn`   | `state_tn`   |
 * | MA    | `com.chelseakr.cafishplanting.state.ma`   | `state_ma`   |
 * | MI    | `com.chelseakr.cafishplanting.state.mi`   | `state_mi`   |
 *
 * A Play product ID already belongs to this one app, so it drops the
 * package-name prefix the App Store IDs carry. California's stays
 * `fullaccess`, the product the Android app shipped with, unchanged in ID,
 * price and meaning. Tennessee's is USD 9.99, one time. Massachusetts' and
 * Michigan's are placeholders, unused while those states are off.
 */
object StateProducts {
    /** California's product, the one the app has always sold. Never renamed, never repointed. */
    const val CALIFORNIA = "fullaccess"
    const val TENNESSEE = "state_tn"

    val productIDsByState: Map<String, String> = linkedMapOf(
        "CA" to CALIFORNIA,
        "TN" to TENNESSEE,
        "MA" to "state_ma",
        "MI" to "state_mi",
    )

    /** The App Store product for the same state, for checking the two catalogs agree. */
    val appStoreProductIDsByState: Map<String, String> = mapOf(
        "CA" to "com.chelseakr.cafishplanting.fullaccess",
        "TN" to "com.chelseakr.cafishplanting.state.tn",
        "MA" to "com.chelseakr.cafishplanting.state.ma",
        "MI" to "com.chelseakr.cafishplanting.state.mi",
    )

    val allProductIDs: Set<String> get() = productIDsByState.values.toSet()

    fun productID(state: String): String? = productIDsByState[state]

    fun state(productID: String): String? = productIDsByState.entries.firstOrNull { it.value == productID }?.key

    /** The states a set of owned products unlocks. Unknown IDs unlock nothing. */
    fun entitledStates(productIDs: Set<String>): Set<String> = productIDs.mapNotNull(::state).toSet()
}

/**
 * The one-time products this device owns, as Google Play last reported
 * them. Per state, not one flag, so a state's purchase unlocks that state only.
 */
data class Entitlements(val ownedProducts: Set<String> = emptySet()) {
    val entitledStates: Set<String> get() = StateProducts.entitledStates(ownedProducts)

    fun owns(state: String): Boolean = state in entitledStates

    /** Any state unlocked: what the widget and the general alert copy need. */
    val hasAnyAccess: Boolean get() = entitledStates.isNotEmpty()

    /** California's full access, the original product. */
    val californiaFullAccess: Boolean get() = owns("CA")
}
