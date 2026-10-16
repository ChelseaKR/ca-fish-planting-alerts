package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** `AlertPlannerTests.swift`, case for case. The shared fixtures cover the same and more. */
class AlertPlannerTest {
    @Test fun aNewWeekNotifiesOnce() {
        val snap1 = TS.snapshot("2026-09-13", listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-13")))))
        val seeded = AlertPlanner.seeding(AlertState(), "cdfw-1", snap1)
        val plan1 = AlertPlanner.plan(snap1, listOf("cdfw-1"), seeded)
        assertEquals("what's visible at favorite time must not notify", 0, plan1.notifications.size)
        val snap2 = TS.snapshot("2026-09-20", listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-13"), TS.plant("2026-09-20")))))
        val plan2 = AlertPlanner.plan(snap2, listOf("cdfw-1"), plan1.state)
        assertEquals(1, plan2.notifications.size)
        assertEquals(listOf(TS.date("2026-09-20")), plan2.notifications[0].newKeys.map { it.weekStart })
    }

    @Test fun theSameWeekNeverNotifiesTwice() {
        val snap = TS.snapshot("2026-09-20", listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-13"), TS.plant("2026-09-20")))))
        var state = AlertPlanner.seeding(AlertState(), "cdfw-1", snap)
        repeat(3) {
            val plan = AlertPlanner.plan(snap, listOf("cdfw-1"), state)
            assertEquals(0, plan.notifications.size)
            state = plan.state
        }
    }

    @Test fun removedThenRelistedNotifiesAgain() {
        val listed = TS.snapshot("2026-09-13", listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-20")))))
        val removed = TS.snapshot("2026-09-13", listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-20", status = PlantStatus.REMOVED)))))
        val a = AlertPlanner.plan(listed, listOf("cdfw-1"), AlertState())
        assertEquals(1, a.notifications.size)
        val b = AlertPlanner.plan(removed, listOf("cdfw-1"), a.state)
        assertEquals(0, b.notifications.size)
        val c = AlertPlanner.plan(listed, listOf("cdfw-1"), b.state)
        assertEquals(1, c.notifications.size)
    }

    @Test fun unfavoritingPrunes() {
        val snap = TS.snapshot("2026-09-13", listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-13")))))
        val seeded = AlertPlanner.seeding(AlertState(), "cdfw-1", snap)
        assertNotNull(seeded.lastListed["cdfw-1"])
        assertNull(AlertPlanner.pruning(seeded, "cdfw-1").lastListed["cdfw-1"])
    }

    @Test fun theWordsNameTheWeekAndNeverADayOrStocked() {
        val n = PlannedNotification("cdfw-1", "Lake Siskiyou", listOf(PlantKey(TS.date("2026-09-20"), "Rainbow trout")))
        assertEquals("plant.cdfw-1.2026-09-20", n.id)
        assertEquals("Lake Siskiyou is on the stocking schedule", n.title)
        assertEquals("Scheduled for the week of 2026-09-20 (Rainbow trout). Plans can change; CDFW gives the week, not the day.", n.body())
        assertTrue(!n.body().contains("stocked"))
    }

    @Test fun mutingLeavesTheBaselineMovingForward() {
        val snapshot = SnapshotDecoder.decode(TS.minimalValid)
        val id = snapshot.waters.first().id
        val plan = AlertPlanner.plan(snapshot, listOf(id), AlertState())
        assertTrue(plan.notifications.isNotEmpty())
        assertTrue(MutedWaters(setOf(id)).unmuted(plan.notifications).isEmpty())
        assertTrue(AlertPlanner.plan(snapshot, listOf(id), plan.state).notifications.isEmpty())
    }

    @Test fun theAlertActionIdentifiersMatchTheIosApp() {
        assertEquals("TT_PLANTING_ALERT", PlantingAlertAction.CATEGORY_IDENTIFIER)
        assertEquals("mute", PlantingAlertAction.MUTE_IDENTIFIER)
        assertEquals("Mute this water", PlantingAlertAction.MUTE_TITLE)
    }
}
