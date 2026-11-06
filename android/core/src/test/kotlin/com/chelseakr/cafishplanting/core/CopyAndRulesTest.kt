package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

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
        // "stocked" only quoted, as one of the words a report state's waters show.
        text.map { it.replace("\"stocked\"", "") }.forEach(::assertKeepsTheRules)
        val alertLines = text.filter { it.contains("an alert", ignoreCase = true) }
        assertTrue(alertLines.isNotEmpty())
        alertLines.forEach { assertTrue("alerts are named with full access: $it", it.contains("Full access")) }
    }

    /**
     * Every word of the introduction is the iOS app's (`Onboarding.swift`,
     * with more states, DECISIONS 0025), except Android's two platform phrases.
     */
    @Test fun theIntroductionIsTheIosCopyWithOnlyThePlatformWordsChanged() {
        val swift = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/Onboarding.swift").readText()
        val androidOnly = mapOf(
            "Swipe down on a list to check for a newer schedule" to "Pull down on a list to check for a newer schedule",
            "It also adds that state's favorites to a Favorite waters widget for your home screen" to
                "It also adds that state's favorites to a Favorite waters widget for your Home Screen and Lock Screen",
        )
        var checked = 0
        for (page in OnboardingCopy.pages) {
            for (line in listOf(page.title, page.body.replace("\"", "\\\"")) + page.points) {
                val ios = androidOnly[line] ?: line
                assertTrue("not in the iOS copy: $ios", swift.contains("\"$ios\""))
                checked += 1
            }
        }
        assertEquals(17, checked)
        assertTrue("the introduction names states", OnboardingCopy.pages.any { it.body.startsWith("Pick a state") })
    }

    /** National framing (DECISIONS 0049), as `OnboardingTests.swift`: no state is the default. */
    @Test fun theIntroductionTakesNoStateAsTheDefault() {
        val pages = OnboardingCopy.pages
        val welcome = pages.first { it.id == "welcome" }
        (listOf(welcome.title, welcome.body) + welcome.points).forEach { assertFalse(it, it.contains("California")) }
        pages.flatMap { listOf(it.title, it.body) + it.points }.forEach {
            assertFalse(it, it.contains("CDFW"))
            assertFalse(it, it.contains("every state", ignoreCase = true))
        }
        val honest = pages.first { it.id == "honest" }
        listOf("\"scheduled\"", "\"stocked\"", "\"planned\"").forEach { assertTrue("the honest page names $it", honest.body.contains(it)) }
        assertEquals(2, OnboardingCopy.VERSION)
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

    /** A schedule water with a later week coming up leads with it, then names its last week. */
    @Test fun anUpcomingWeekLeadsAndTheShareTextKeepsTheLastWeeksSpecies() {
        val week = TS.week("2026-11-01")
        val water = TS.water("cdfw-9", "Kern River", listOf(TS.plant("2026-10-04", "Rainbow trout"), TS.plant("2026-11-08"))).let {
            Water(it.id, 1, it.name, true, it.slug, it.aliases, it.counties, it.region, it.cdfwMapURL, null, TS.week("2026-10-04"), it.plants)
        }
        assertEquals(
            "Next scheduled: the week of 2026-11-08. Last scheduled for the week of 2026-10-04",
            ScheduleWording.lastScheduledLine(water, week),
        )
        assertEquals(
            "Next scheduled: the week of 2026-11-08. Last scheduled for the week of 2026-10-04: Rainbow trout.",
            ShareContent.statusLine(water, week),
        )
        // Listed this week and nothing later: the last week is the headline, as before.
        val thisWeek = TS.water("cdfw-10", plants = listOf(TS.plant("2026-11-01")))
        assertEquals("Last scheduled for the week of 2026-11-01", ScheduleWording.lastScheduledLine(thisWeek, week))
    }

    /** The intro never claims "no tracking"; it says only what is true: there is no account. */
    @Test fun theIntroductionNeverClaimsNoTrackingInEitherApp() {
        val text = OnboardingCopy.pages.flatMap { listOf(it.title, it.body) + it.points } +
            FreeLaunch.onboardingPages.flatMap { listOf(it.title, it.body) + it.points }
        text.forEach { assertFalse("claims no tracking: $it", it.contains("tracking", ignoreCase = true)) }
        assertTrue(text.any { it.startsWith("No account needed.") })
        val swift = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/Onboarding.swift").readText()
        assertFalse("the iOS intro claims no tracking", swift.contains("no tracking", ignoreCase = true))
    }

    /** The "not listed yet" words are the same in both apps, so a CDFW week that is still filling in reads alike. */
    @Test fun theNotListedYetWordsMatchTheIosApp() {
        val freshness = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/SnapshotFreshness.swift").readText()
        assertTrue(freshness.contains("\"${SnapshotFreshness.NO_WATERS_LISTED_YET}\""))
        val digest = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/WidgetDigest.swift").readText()
        assertTrue(digest.contains("\"${WidgetDigest.NO_FAVORITES_SCHEDULED_YET}\""))
        // The schedule line the locked widget and the watch show (`scheduleContext`).
        assertTrue(digest.contains("\"No waters are listed yet for the \\(week.label).\""))
        assertTrue(digest.contains("\"No waters are listed for the \\(week.label).\""))
        val wording = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/ScheduleWording.swift").readText()
        assertTrue(wording.contains("\"Next scheduled: \\(upcoming.phrase). Last scheduled for \\(last.phrase)\""))
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

class StateProductsTest {
    @Test fun californiaKeepsTheOriginalProductAndEachProductUnlocksOnlyItsState() {
        assertEquals("fullaccess", StateProducts.productID("CA"))
        assertEquals("state_tn", StateProducts.productID("TN"))
        assertTrue(Entitlements(setOf("fullaccess")).californiaFullAccess)
        assertFalse("another state's product never unlocks California", Entitlements(setOf("state_tn")).californiaFullAccess)
        assertEquals(setOf("TN"), Entitlements(setOf("state_tn", "unknown")).entitledStates)
        assertTrue(PurchaseEntitlement(isPurchased = true).entitlements.californiaFullAccess)
        assertEquals(PurchaseEntitlement(true, setOf("fullaccess")), PurchaseEntitlement.of(Entitlements(setOf("fullaccess"))))
    }

    /** Every Play product maps to the App Store product `StateAccess.swift` names for the same state. */
    @Test fun thePlayCatalogMatchesTheAppStoreCatalogStateForState() {
        val swift = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/StateAccess.swift").readText()
        assertEquals(StateProducts.productIDsByState.keys, StateProducts.appStoreProductIDsByState.keys)
        for ((state, appStoreID) in StateProducts.appStoreProductIDsByState) {
            val line = if (state == "CA") "californiaProductID = \"$appStoreID\"" else "\"$state\": \"$appStoreID\""
            assertTrue("StateAccess.swift has no $line", swift.contains(line))
        }
        // Play product IDs: lowercase letters, digits, underscores and periods, starting with a letter or digit.
        StateProducts.allProductIDs.forEach { assertTrue(it, Regex("^[a-z0-9][a-z0-9_.]*$").matches(it)) }
    }
}
