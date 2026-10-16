package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant

class FreshnessAndSearchTest {
    private val snapshot = TS.snapshot(
        "2026-09-13",
        listOf(TS.water("cdfw-1", plants = listOf(TS.plant("2026-09-13")))),
        listOf(ThisWeekEntry("cdfw-1", "Trout"), ThisWeekEntry("cdfw-1", "Catfish")),
    )

    // Saturday 2026-09-19, 11 pm in Los Angeles: still the week. Midnight after it: ended.
    private val lastEvening = Instant.parse("2026-09-20T06:59:00Z")
    private val afterMidnight = Instant.parse("2026-09-20T07:01:00Z")

    @Test fun theWeekEndsAtMidnightInLosAngelesNotOnTheDeviceClock() {
        val fresh = SnapshotFreshness(snapshot, SnapshotOrigin.STORED, SnapshotMeta(), false, lastEvening)
        assertFalse(fresh.isStale)
        assertEquals("This week", fresh.listedBadge)
        val stale = SnapshotFreshness(snapshot, SnapshotOrigin.STORED, SnapshotMeta(), false, afterMidnight)
        assertTrue(stale.isStale)
        assertEquals("week of 2026-09-13", stale.listedBadge)
        assertTrue(stale.detail.endsWith("That week has ended, so this schedule is out of date."))
    }

    @Test fun aFailedCheckIsSaidPlainlyAndNeverBecomesNothingListed() {
        val meta = SnapshotMeta(lastAttemptAt = lastEvening, lastSuccessAt = null, lastOutcome = SnapshotStore.FAILED_OUTCOME)
        val f = SnapshotFreshness(snapshot, SnapshotOrigin.BUNDLED, meta, false, lastEvening)
        assertTrue(f.needsAttention)
        assertEquals("Couldn't check for a newer schedule, so this is the one that came with the app.", f.detail)
        assertEquals("1 water is listed for that week.", f.summary)
        assertEquals("Schedule for the week of 2026-09-13", f.headline)
    }

    @Test fun throttleWaitsSixHoursOrThirtyMinutesAfterAFailure() {
        val t = RefreshThrottle.FOREGROUND
        val ok = SnapshotMeta(lastAttemptAt = lastEvening, lastOutcome = "updated")
        val failed = ok.copy(lastOutcome = SnapshotStore.FAILED_OUTCOME)
        assertTrue(t.isDue(SnapshotMeta(), lastEvening))
        assertFalse(t.isDue(ok, lastEvening + Duration.ofHours(5)))
        assertTrue(t.isDue(ok, lastEvening + Duration.ofHours(6)))
        assertTrue(t.isDue(failed, lastEvening + Duration.ofMinutes(30)))
        assertTrue("a clock moved back never strands the app", t.isDue(ok, lastEvening - Duration.ofDays(1)))
    }

    private val waters = listOf(
        TS.water("cdfw-1", "American River Silver Fork", listOf(TS.plant("2026-09-13")), listOf("El Dorado")),
        TS.water("cdfw-2", "Lake Isabella", listOf(TS.plant("2026-09-13")), listOf("Kern"), listOf("Isabella Lake", "Lk Isabella")),
        TS.water("cdfw-3", "Kern River, Lower", listOf(TS.plant("2026-09-13")), listOf("Kern")),
        TS.water("cdfw-4", "Río Hondo Pond", listOf(TS.plant("2026-09-13")), listOf("Los Angeles")),
        TS.water("cdfw-5", "Twin Lakes", listOf(TS.plant("2026-09-13")), listOf("Mono", "Alpine")),
    )

    private fun ids(search: WaterSearch) = search.filter(waters).map { it.id }

    /** `WaterSearchTests.swift`, case for case. */
    @Test fun searchMatchesLikeTheIosApp() {
        assertEquals(listOf("cdfw-1", "cdfw-3", "cdfw-2", "cdfw-4", "cdfw-5"), ids(WaterSearch()))
        assertEquals(listOf("cdfw-2"), ids(WaterSearch("isabella")))
        assertEquals(listOf("cdfw-2"), ids(WaterSearch("lk isab")))
        assertEquals(listOf("cdfw-3", "cdfw-2"), ids(WaterSearch("KERN")))
        assertEquals(listOf("cdfw-4"), ids(WaterSearch("rio hondo")))
        assertEquals(listOf("cdfw-5"), ids(WaterSearch("alpine")))
        assertEquals(listOf("cdfw-1"), ids(WaterSearch("silver fork el dorado")))
        assertEquals(listOf("cdfw-3"), ids(WaterSearch("kern, lower")))
        assertEquals(emptyList<String>(), ids(WaterSearch("kern mono")))
        assertEquals(5, ids(WaterSearch("   ")).size)
        assertEquals(listOf("cdfw-2"), ids(WaterSearch("lake", "Kern")))
        assertEquals(listOf("Alpine", "El Dorado", "Kern", "Los Angeles", "Mono"), WaterSearch.counties(waters))
    }

    @Test fun namesSortNumbersAsNumbers() {
        assertEquals(listOf("Pond 2", "Pond 10", "pond 11"), listOf("Pond 10", "pond 11", "Pond 2").sortedWith(NameOrder))
    }
}
