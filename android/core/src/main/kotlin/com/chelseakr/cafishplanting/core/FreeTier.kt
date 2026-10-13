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

    // Per state (DECISIONS 0025), as `FreeTier.swift`.

    /** Alerts for a water need its state's purchase. California's is the original full access. */
    fun notificationsAllowed(state: String, entitledStates: Set<String>): Boolean = state in entitledStates

    /** The widget unlocks with any state's purchase, and then lists only favorites in states this device owns. */
    fun widgetsAllowed(entitledStates: Set<String>): Boolean = !WIDGETS_REQUIRE_FULL_ACCESS || entitledStates.isNotEmpty()

    /** What a state's purchase unlocks, in the purchase screen's words. A report says "stocked", a schedule "scheduled". */
    fun stateFeatures(stateName: String, agencyShortName: String, semantics: StateSemantics): List<String> {
        val alert = if (semantics == StateSemantics.SCHEDULE) {
            "An alert on this device when a $stateName favorite is newly on $agencyShortName's schedule"
        } else {
            ReportWording.alertFeature(stateName, agencyShortName)
        }
        return listOf(alert, "$stateName favorites in the Favorite waters widget")
    }

    /**
     * The alerts to post: each needs its own water's state's purchase, so a
     * California buyer gets no Tennessee alert, and the reverse. A water the
     * snapshot no longer has counts as California's, where every alert before
     * states came from (`AppEnvironment.alertsToSchedule` in the iOS app).
     */
    fun alertsToPost(planned: List<PlannedNotification>, snapshot: Snapshot, entitledStates: Set<String>): List<PlannedNotification> =
        planned.filter { notificationsAllowed(snapshot.water(it.waterID)?.state ?: "CA", entitledStates) }
}
