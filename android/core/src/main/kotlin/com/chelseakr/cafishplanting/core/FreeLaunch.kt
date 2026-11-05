package com.chelseakr.cafishplanting.core

/**
 * Android's free launch (docs/DECISIONS.md 0044). With the build's
 * `troutTruck.androidFreeTier` property on (the default in
 * `android/gradle.properties`), the app sells nothing: every state's alerts
 * and the Favorite waters widget are free, and the build carries no Play
 * Billing library. Google Play shows a personal account's full address only
 * when it sells, so a build with nothing for sale keeps it private.
 *
 * The gate itself is unchanged ([FreeTier]). The free build reports
 * [entitlements], every state's product, as owned, so the same per-state
 * checks let every alert through and unlock the widget. Turning the property
 * off brings back Play Billing and the purchase screens with no other edit.
 *
 * The words below replace the purchase words wherever the free build would
 * otherwise show them. None names a price, a purchase or an unlock.
 */
object FreeLaunch {
    /** Every state's product, as if owned: what the free build reports. */
    val entitlements: Entitlements get() = Entitlements(StateProducts.allProductIDs)

    /** The About screen's first section, in place of "Full access". */
    const val ABOUT_HEADER = "Alerts and the widget"

    const val ABOUT_BODY =
        "Favorites, browsing, history, alerts and the Favorite waters widget are free in each state. " +
            "Nothing in this app is for sale."

    const val ABOUT_WHAT_IT_DOES =
        "Favorite any water and browse its full schedule history. Get a notification on this device when a favorite is newly " +
            "on its agency's schedule or stocking report, or its planned period begins. A home screen widget shows your favorites."

    const val ABOUT_HOW_ALERTS_WORK =
        "Alerts are local notifications this app makes on this device. There is no server, no push service, and no account. "

    const val ABOUT_PRIVACY =
        "Data collected by this app: none. No analytics, no crash reporting, no advertising, no accounts. Favorites and alert history stay on this device. " +
            "The only network request this app makes is a plain, cookie-free fetch of the published stocking snapshot."

    const val STATES_INTRO = "Browsing, every water's history, favorites, alerts and the widget are free in each state."

    const val ABOUT_STATES_BUTTON = "States"

    const val FAVORITES_EMPTY_ALERTS = "You'll get an alert when one is newly on its agency's schedule or stocking report, and a widget with your favorites."

    /** The introduction's favorites page points, in place of the full-access ones. */
    val favoritesPoints: List<String> = listOf(
        "Get an alert when a favorite is newly on the agency's schedule or in its stocking report, or its planned period begins",
        "See your favorites in a Favorite waters widget for your home screen",
        "Mute one water's alerts from the alert itself, and keep it as a favorite",
    )

    /** The introduction for the free build: the same pages, with the favorites page's points from [favoritesPoints]. */
    val onboardingPages: List<OnboardingCopy.Page> =
        OnboardingCopy.pages.map { if (it.id == "favorites") it.copy(points = favoritesPoints) else it }

    /** Every line the free build shows in place of a purchase line, for the tests that hold them to "nothing for sale". */
    val allLines: List<String>
        get() = listOf(
            ABOUT_HEADER, ABOUT_BODY, ABOUT_WHAT_IT_DOES, ABOUT_HOW_ALERTS_WORK, ABOUT_PRIVACY,
            STATES_INTRO, ABOUT_STATES_BUTTON, FAVORITES_EMPTY_ALERTS,
        ) + onboardingPages.flatMap { listOf(it.title, it.body) + it.points }
}
