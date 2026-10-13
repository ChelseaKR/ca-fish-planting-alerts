package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The app's wording rules, the same as the iOS app's copy tests. */
class CopyAndRulesTest {
    private val days = listOf("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "today", "tomorrow")

    private fun assertKeepsTheRules(line: String) {
        assertFalse(line, line.contains("stocked", ignoreCase = true))
        assertFalse("no price: $line", line.contains("$"))
        for (day in days) assertFalse("$day in: $line", line.contains(day, ignoreCase = true))
    }

    @Test fun theIntroductionKeepsTheRulesAndNamesAlertsWithFullAccess() {
        val pages = OnboardingCopy.pages
        assertEquals(4, pages.size)
        assertEquals(pages.size, pages.map { it.id }.toSet().size)
        val text = pages.flatMap { listOf(it.title, it.body) + it.points }
        text.forEach(::assertKeepsTheRules)
        val alertLines = text.filter { it.contains("an alert", ignoreCase = true) }
        assertTrue(alertLines.isNotEmpty())
        alertLines.forEach { assertTrue("alerts are named with full access: $it", it.contains("Full access")) }
    }

    /**
     * Pinned word for word. This is the iOS app's California introduction as it
     * was before more states (DECISIONS 0025), with Android's two platform words.
     * The iOS app now says "Pick a state" and sells each state; this app reads
     * v1, California only, so its words stay these until it gains states too.
     */
    @Test fun theIntroductionIsTheCaliforniaCopyWithOnlyThePlatformWordsChanged() {
        val pinned = listOf(
            listOf(
                "Welcome to Trout Truck",
                "California's fish planting schedule from the Department of Fish and Wildlife, a week at a time.",
                "Every water on CDFW's weekly schedule",
                "Each water's week-by-week history, which CDFW's own page doesn't keep",
            ),
            listOf(
                "Find your waters",
                "Browse by region and county, or search by a water's name, a name CDFW used before, or its county.",
                "Waters on the current week's schedule are tagged This week",
                "Swipe down on a list to check for a newer schedule",
            ),
            listOf(
                "Star the waters you fish",
                "Favorites, browsing and history are free and unlimited.",
                "Full access, a one-time purchase, adds an alert when a favorite is newly on the schedule",
                "It also adds a Favorite waters widget for your home screen",
                "Mute one water's alerts from the alert itself, and keep it as a favorite",
            ),
            listOf(
                "A week, never a day",
                "CDFW schedules plants by the week and says plans can change, so the app shows the week and says \"scheduled\".",
                "If the app can't check for a newer schedule, it says so and keeps the last one, labeled with its week",
                "No account and no tracking. Favorites stay on this device",
            ),
        )
        assertEquals(pinned, OnboardingCopy.pages.map { listOf(it.title, it.body) + it.points })
    }

    @Test fun showsOnAFirstLaunchOnly() {
        assertTrue(OnboardingState().shouldShow(hasFavorites = false))
        assertFalse(OnboardingState(OnboardingCopy.VERSION).shouldShow(hasFavorites = false))
        assertFalse(OnboardingState().shouldShow(hasFavorites = true))
        assertTrue(OnboardingState(1).shouldShow(hasFavorites = false, currentVersion = 2))
    }

    @Test fun fullAccessNamesAlertsAndTheWidgetAndNothingElseIsGated() {
        assertEquals(2, FreeTier.fullAccessFeatures.size)
        assertTrue(FreeTier.fullAccessFeatures.any { it.contains("alert", ignoreCase = true) })
        assertTrue(FreeTier.fullAccessFeatures.any { it.contains("widget", ignoreCase = true) })
        assertFalse(FreeTier.notificationsAllowed(isEntitled = false))
        assertTrue(FreeTier.notificationsAllowed(isEntitled = true))
        assertFalse(FreeTier.widgetsAllowed(isEntitled = false))
        assertTrue(FreeTier.widgetsAllowed(isEntitled = true))
    }

    @Test fun primingCopyNamesNoPriceAndNoDay() {
        for (copy in listOf(NotificationPrimingCopy("Lake Siskiyou", false), NotificationPrimingCopy(null, true))) {
            (listOf(copy.headline, copy.footnote) + copy.points.map { it.text }).forEach(::assertKeepsTheRules)
        }
        assertTrue(NotificationPrimingCopy("X", false).points.any { it.text.contains("full access") })
        assertFalse(NotificationPrimingCopy("X", true).points.any { it.text.contains("full access") })
    }

    @Test fun scheduleWordingAndShareTextNameAWeek() {
        val water = TS.water("cdfw-1", "Lake Siskiyou", listOf(TS.plant("2026-09-06", "Rainbow trout"), TS.plant("2026-09-27")))
        val week = TS.week("2026-09-13")
        assertEquals("Last scheduled for the week of 2026-09-27", ScheduleWording.lastScheduledLine(water, week))
        val futureOnly = TS.water("cdfw-2", plants = listOf(TS.plant("2026-09-20"))).let {
            Water(it.id, 1, it.name, true, it.slug, it.aliases, it.counties, it.region, it.cdfwMapURL, null, null, it.plants)
        }
        assertEquals("Next scheduled: the week of 2026-09-20", ScheduleWording.lastScheduledLine(futureOnly, week))
        val share = ShareContent.message(water, SnapshotEndpoint.siteWaterURL("lake-siskiyou"), week)
        assertEquals(
            "Lake Siskiyou — Trout Truck, CA fish planting alerts. Last scheduled for the week of 2026-09-27: Trout. " +
                "Schedule history: https://chelseakr.github.io/ca-fish-planting-alerts/water/lake-siskiyou/",
            share,
        )
        assertKeepsTheRules(share)
    }

    @Test fun waterLinksRoundTripAndRejectEverythingElse() {
        assertEquals("trouttruck://water/cdfw-125", WaterLink.url("cdfw-125"))
        assertEquals("cdfw-125", WaterLink.waterID("trouttruck://water/cdfw-125"))
        assertEquals("cdfw-125", WaterLink.waterID("TroutTruck://WATER/cdfw-125"))
        for (bad in listOf("https://water/cdfw-1", "trouttruck://unlock", "trouttruck://water/", "trouttruck://water/a/b", "not a url")) {
            assertEquals(bad, null, WaterLink.waterID(bad))
        }
        assertTrue(UnlockLink.matches(UnlockLink.URL))
        assertFalse(UnlockLink.matches(WaterLink.url("cdfw-1")))
    }
}

class ProductCatalogTest {
    @Test fun californiaIsTheOnlyStateTodayAndItsProductUnlocksOnlyIt() {
        assertEquals(listOf("CA"), ProductCatalog.states.map { it.code })
        assertEquals(SnapshotEndpoint.URL, ProductCatalog.california.snapshotURL)
        assertEquals(listOf("fullaccess"), ProductCatalog.productIDs)
        assertTrue(Entitlements(setOf("fullaccess")).californiaFullAccess)
        assertFalse("another state's product never unlocks California", Entitlements(setOf("state_tn")).californiaFullAccess)
        assertTrue(PurchaseEntitlement(isPurchased = true).entitlements.californiaFullAccess)
        assertEquals(PurchaseEntitlement(true, setOf("fullaccess")), PurchaseEntitlement.of(Entitlements(setOf("fullaccess"))))
    }
}
