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
        text.forEach(::assertKeepsTheRules)
        val alertLines = text.filter { it.contains("an alert", ignoreCase = true) }
        assertTrue(alertLines.isNotEmpty())
        alertLines.forEach { assertTrue("alerts are named with full access: $it", it.contains("Full access")) }
    }

    @Test fun theIntroductionIsTheIosCopyWithOnlyThePlatformWordsChanged() {
        val swift = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/Onboarding.swift").readText()
        val androidOnly = mapOf(
            "Swipe down on a list to check for a newer schedule" to "Pull down on a list to check for a newer schedule",
            "It also adds a Favorite waters widget for your home screen" to
                "It also adds a Favorite waters widget for your Home Screen and Lock Screen",
        )
        for (page in OnboardingCopy.pages) {
            for (line in listOf(page.title, page.body.replace("\"", "\\\"")) + page.points) {
                val ios = androidOnly[line] ?: line
                assertTrue("not in the iOS copy: $ios", swift.contains("\"$ios\""))
            }
        }
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
