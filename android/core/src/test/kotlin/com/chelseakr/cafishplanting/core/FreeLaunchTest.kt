package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Android's free launch (DECISIONS 0044): every state's alerts and the widget, and no sales words. */
class FreeLaunchTest {
    private val snapshot: Snapshot by lazy { SnapshotDecoder.decode(File(TS.swiftFixtures, "v2-all-states.json").readBytes()) }

    /** One alert per water, in every state of the fixture. */
    private fun oneAlertPerWater(): List<PlannedNotification> =
        snapshot.waters.map { PlannedNotification(it.id, it.name, listOf(PlantKey(PlainDate(2026, 11, 1), "Rainbow Trout"))) }

    @Test fun theFreeBuildOwnsEveryStateThisBuildKnows() {
        val owned = FreeLaunch.entitlements
        assertEquals(StateProducts.productIDsByState.keys, owned.entitledStates)
        for (state in snapshot.states.map { it.code }) assertTrue(state, owned.owns(state))
    }

    @Test fun everyStatesAlertsAndTheWidgetPassTheGate() {
        val entitled = FreeLaunch.entitlements.entitledStates
        assertTrue(FreeTier.widgetsAllowed(entitled))
        for (state in StateProducts.productIDsByState.keys) assertTrue(state, FreeTier.notificationsAllowed(state, entitled))
        val planned = oneAlertPerWater()
        assertEquals(snapshot.states.map { it.code }.toSet(), snapshot.waters.map { it.state }.toSet())
        assertEquals(planned, FreeTier.alertsToPost(planned, snapshot, entitled))
    }

    /** The negative control: with nothing owned, the same gate still blocks, so the free build's access comes from [FreeLaunch.entitlements] alone. */
    @Test fun withoutTheFreeEntitlementsTheGateStillBlocks() {
        val none = Entitlements().entitledStates
        assertFalse(FreeTier.widgetsAllowed(none))
        val planned = oneAlertPerWater()
        assertTrue(planned.isNotEmpty())
        assertEquals(emptyList<PlannedNotification>(), FreeTier.alertsToPost(planned, snapshot, none))
    }

    @Test fun theFreeWordsSellNothing() {
        val sales = listOf("purchase", "buy", "unlock", "full access", "price", "pay", "$", "subscription", "restore", "coming soon", "upgrade", "premium", "pro version")
        val lines = FreeLaunch.allLines
        assertTrue(lines.size > 10)
        for (line in lines) for (word in sales) assertFalse("\"$word\" in: $line", line.contains(word, ignoreCase = true))
        // The negative control: the paid introduction does name the purchase, so the check can fail.
        val paid = OnboardingCopy.pages.flatMap { it.points }
        assertTrue(paid.any { it.contains("purchase", ignoreCase = true) })
    }

    @Test fun theFreeIntroductionChangesOnlyTheFavoritesPoints() {
        val free = FreeLaunch.onboardingPages
        val paid = OnboardingCopy.pages
        assertEquals(paid.map { it.id }, free.map { it.id })
        for ((f, p) in free.zip(paid)) {
            assertEquals(p.title, f.title)
            assertEquals(p.body, f.body)
            if (p.id == "favorites") assertNotEquals(p.points, f.points) else assertEquals(p.points, f.points)
        }
    }
}
