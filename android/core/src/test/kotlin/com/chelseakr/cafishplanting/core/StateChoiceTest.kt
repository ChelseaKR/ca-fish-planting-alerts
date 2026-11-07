package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.time.Duration
import java.time.Instant

/**
 * The first-run state picker (DECISIONS 0053, plan N6 decision 9A): the
 * states come only from a v2 snapshot, nothing is chosen for the person,
 * California is never the fallback, and a paused state says so.
 */
class StateChoiceTest {
    private val wave2: Snapshot by lazy { SnapshotDecoder.decode(File(TS.swiftFixtures, "v2-wave2.json").readBytes()) }
    private val bundled: Snapshot by lazy {
        SnapshotDecoder.decode(File(TS.repoRoot, "android/app/src/main/assets/snapshot.json").readBytes())
    }
    private val now: Instant = Instant.parse("2026-11-05T20:00:00Z")

    @Test fun theStatesOfferedAreTheV2SnapshotsInItsOrder() {
        assertTrue("sanity check: the fixture carries several states", wave2.states.size > 1)
        assertEquals(2, wave2.schemaVersion)
        val options = StateChoice.options(wave2, now)
        assertEquals(wave2.states.map { it.code }, options.map { it.code })
        assertEquals(wave2.states.map { it.name }, options.map { it.name })
    }

    @Test fun aV1FileOrNoSnapshotOffersNoState() {
        val v1 = TS.snapshot("2026-06-07", waters = emptyList())
        assertEquals(1, v1.schemaVersion)
        assertEquals(emptyList<StateOption>(), StateChoice.options(v1, now))
        assertEquals(emptyList<StateOption>(), StateChoice.options(null, now))
    }

    @Test fun nothingIsChosenForThePersonAndCaliforniaIsNeverTheFallback() {
        assertNull(BrowseChoice().state)
        assertNull(StateChoice.resolve(BrowseChoice(), wave2))
        // A pick the snapshot no longer carries is no pick, not California.
        assertNull(StateChoice.resolve(BrowseChoice("ZZ"), wave2))
        assertNull(StateChoice.resolve(BrowseChoice("CA"), null))
        for (info in wave2.states) assertEquals(info.code, StateChoice.resolve(BrowseChoice(info.code), wave2))
    }

    @Test fun aSavedPickSurvivesAndAMissingOrCorruptFileIsNoPick() {
        val dir = Files.createTempDirectory("state-choice").toFile()
        try {
            val layout = AppStorageLayout(dir)
            val stores = Stores(layout)
            assertEquals(BrowseChoice(null), stores.loadBrowseChoice())
            // A file written before 0053 keeps its pick.
            layout.browseStateFile.writeText("{\"state\": \"CA\"}")
            assertEquals(BrowseChoice("CA"), stores.loadBrowseChoice())
            assertTrue(stores.saveBrowseChoice(BrowseChoice("MI")))
            assertEquals(BrowseChoice("MI"), stores.loadBrowseChoice())
            layout.browseStateFile.writeText("{not json")
            assertEquals(BrowseChoice(null), stores.loadBrowseChoice())
            layout.browseStateFile.writeText("{}")
            assertEquals(BrowseChoice(null), stores.loadBrowseChoice())
        } finally {
            dir.deleteRecursively()
        }
    }

    @Test fun aStaleStateShowsPausedNeverCurrent() {
        val base = wave2.states.last()
        val lastGood = Instant.parse("2026-10-15T13:31:10Z")
        val failed = base.copy(lastAttemptOK = false, lastSuccessAt = lastGood, lastAttemptAt = now)

        val paused = StateChoice.option(failed, lastGood + Duration.ofDays(7) + Duration.ofSeconds(1))
        assertEquals(PlainDate.parse("2026-10-15"), paused.pausedSince)
        assertEquals("Updates paused since Oct 15, 2026", paused.status)
        assertFalse(paused.status.startsWith("Read"))

        // The site's rule: inside seven days a failed check is not yet a pause, and says the read's date.
        val recent = StateChoice.option(failed, lastGood + Duration.ofDays(7))
        assertNull(recent.pausedSince)
        assertEquals("Read Oct 15, 2026", recent.status)

        // A check that worked is never a pause, however old the read.
        val ok = base.copy(lastAttemptOK = true, lastSuccessAt = lastGood)
        assertNull(StateChoice.option(ok, lastGood + Duration.ofDays(60)).pausedSince)
    }

    /** The bundled data: Tennessee's last good read is 10-15 and its newest check failed. */
    @Test fun theBundledSnapshotShowsTennesseePausedAndTheOthersRead() {
        val options = StateChoice.options(bundled, now).associateBy { it.code }
        assertEquals(bundled.states.map { it.code }.toSet(), options.keys)
        assertEquals("Updates paused since Oct 15, 2026", options.getValue("TN").status)
        for ((code, option) in options) {
            if (code == "TN") continue
            assertNull(code, option.pausedSince)
            assertTrue(option.status, option.status.startsWith("Read "))
        }
    }

    @Test fun aStateWithNoCountShowsNoZero() {
        val none = wave2.states.last().copy(watersCount = 0)
        val detail = StateChoice.option(none, now).detail
        assertFalse(detail, detail.contains("0"))
        assertTrue(StateChoice.option(wave2.states.first(), now).detail.endsWith("${wave2.states.first().watersCount} waters"))
    }

    @Test fun theIntroductionHasThePickersPage() {
        assertTrue(OnboardingCopy.pages.any { it.id == StateChoice.PICKER_PAGE_ID })
        assertTrue(FreeLaunch.onboardingPages.any { it.id == StateChoice.PICKER_PAGE_ID })
    }

    @Test fun thePickersWordsNameNoStateAndClaimNoCoverage() {
        val lines = listOf(StateChoice.PICKER_TITLE, StateChoice.PICKER_NOTE, StateChoice.BROWSE_TITLE, StateChoice.BROWSE_BODY, StateChoice.NONE_LISTED)
        for (line in lines) {
            assertFalse(line, line.contains("California"))
            assertFalse(line, line.contains("CDFW"))
            assertFalse(line, line.contains("every state", ignoreCase = true))
            assertFalse(line, line.contains("all states", ignoreCase = true))
            assertFalse(line, line.contains("tracking", ignoreCase = true))
        }
    }
}
