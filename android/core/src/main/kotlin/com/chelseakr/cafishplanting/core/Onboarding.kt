package com.chelseakr.cafishplanting.core

import kotlinx.serialization.Serializable

/** Whether the person has been through the introduction, as `OnboardingState.swift`. */
@Serializable
data class OnboardingState(val completedVersion: Int = 0) {
    /** Shows once, on a first launch; not to someone who already keeps favorites. */
    fun shouldShow(hasFavorites: Boolean, currentVersion: Int = OnboardingCopy.VERSION): Boolean =
        completedVersion < currentVersion && !hasFavorites
}

/**
 * The words of the introduction: the iOS app's `OnboardingCopy`, page for
 * page, with more states (docs/DECISIONS.md 0025). Two phrases name
 * Android's own surfaces where the iOS words name Apple's: "home screen"
 * for "Home Screen and Lock Screen", and "Swipe down" for "Pull down".
 * `CopyAndRulesTest` holds every other word to `Onboarding.swift`.
 */
object OnboardingCopy {
    const val VERSION = 1

    data class Page(val id: String, val icon: String, val title: String, val body: String, val points: List<String>)

    val pages: List<Page> = listOf(
        Page(
            id = "welcome",
            icon = "truck",
            title = "Welcome to Trout Truck",
            body = "California's fish planting schedule from the Department of Fish and Wildlife, a week at a time, " +
                "and other states' trout schedules and reports from their own agencies.",
            points = listOf(
                "Every water on CDFW's weekly schedule",
                "Each water's history, which the agencies' own pages don't keep",
            ),
        ),
        Page(
            id = "browse",
            icon = "map",
            title = "Find your waters",
            body = "Pick a state, then browse by region and county, or search by a water's name, " +
                "a name the agency used before, or its county.",
            points = listOf(
                "Waters on the current week's schedule are tagged This week",
                "Swipe down on a list to check for a newer schedule",
            ),
        ),
        Page(
            id = "favorites",
            icon = "star",
            title = "Star the waters you fish",
            body = "Favorites, browsing and history are free and unlimited, in every state.",
            points = listOf(
                "Full access is a one-time purchase for each state. It adds an alert when a favorite there is " +
                    "newly on the agency's schedule or in its stocking report",
                "It also adds that state's favorites to a Favorite waters widget for your home screen",
                "Mute one water's alerts from the alert itself, and keep it as a favorite",
            ),
        ),
        Page(
            id = "honest",
            icon = "calendar",
            title = "A week, never a day",
            body = "CDFW schedules plants by the week and says plans can change, so the app shows the week and says \"scheduled\".",
            points = listOf(
                "If the app can't check for a newer schedule, it says so and keeps the last one, labeled with its week",
                "No account and no tracking. Favorites stay on this device",
            ),
        ),
    )
}
