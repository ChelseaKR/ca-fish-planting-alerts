package com.chelseakr.cafishplanting.core

/**
 * The free/paid gate, the same boundary as the iOS app (`FreeTier.swift`,
 * docs/DECISIONS.md 0009 and 0015):
 *
 * - Browsing, history and favorites are free and unlimited for everyone.
 * - Full access, one one-time in-app product, unlocks local alerts and the
 *   Favorite waters widget.
 */
object FreeTier {
    /** Call immediately before posting alerts, never on the favoriting path. */
    fun notificationsAllowed(isEntitled: Boolean): Boolean = isEntitled

    /** The widget is part of full access (DECISIONS 0015). */
    const val WIDGETS_REQUIRE_FULL_ACCESS = true

    fun widgetsAllowed(isEntitled: Boolean): Boolean = !WIDGETS_REQUIRE_FULL_ACCESS || isEntitled

    /**
     * What full access unlocks, in the purchase screen's words. The iOS app
     * names "your Home Screen and Lock Screen"; Android has a home screen
     * widget only, so that is all this says.
     */
    val fullAccessFeatures: List<String> = listOf(
        "An alert on this device when a favorite is newly on CDFW's weekly schedule",
        "The Favorite waters widget for your home screen",
    )
}
