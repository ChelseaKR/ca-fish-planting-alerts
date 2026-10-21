package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.time.Duration
import java.time.Instant

class ResilienceTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun layout() = AppStorageLayout(File(tmp.root, "trout-truck").also { it.mkdirs() })

    /** A directory where the temporary file would go makes every write fail, like a full or read-only disk. */
    private fun breakWrites(file: File) {
        File(file.parentFile, ".${file.name}.tmp").mkdirs()
    }

    @Test fun aFailedWriteKeepsTheLastGoodFileAndDoesNotThrow() {
        val l = layout()
        val stores = Stores(l)
        assertTrue(stores.saveFavorites(Favorites.of(listOf("cdfw-1", "cdfw-2"))))
        breakWrites(l.favoritesFile)
        assertFalse(stores.saveFavorites(Favorites.of(listOf("cdfw-9"))))
        assertEquals(listOf("cdfw-1", "cdfw-2"), stores.loadFavorites().ids)
    }

    @Test fun theLowLevelSaveStillReportsTheFailure() {
        val l = layout()
        breakWrites(l.entitlementFile)
        val store = JsonFileStore(l.entitlementFile, PurchaseEntitlement.serializer())
        try {
            store.save(PurchaseEntitlement())
            throw AssertionError("expected an IOException")
        } catch (_: IOException) {
        }
    }

    @Test fun everyStoreSurvivesAFailedWrite() {
        val l = layout()
        val stores = Stores(l)
        listOf(l.alertStateFile, l.mutedWatersFile, l.onboardingFile, l.entitlementFile, l.reviewPromptFile).forEach(::breakWrites)
        assertFalse(stores.saveAlertState(AlertState()))
        assertFalse(stores.saveMuted(MutedWaters()))
        assertFalse(stores.saveOnboarding(OnboardingState()))
        assertFalse(stores.saveEntitlement(PurchaseEntitlement.of(Entitlements(setOf(ProductCatalog.CALIFORNIA_FULL_ACCESS)))))
        assertFalse(stores.saveReviewPrompt(ReviewPromptState()))
    }

    @Test fun aSuccessfulWriteReplacesTheOldFileAndLeavesNoTemporaryFile() {
        val l = layout()
        val stores = Stores(l)
        assertTrue(stores.saveFavorites(Favorites.of(listOf("a"))))
        assertTrue(stores.saveFavorites(Favorites.of(listOf("a", "b"))))
        assertEquals(listOf("a", "b"), stores.loadFavorites().ids)
        assertFalse(File(l.directory, ".favourites.json.tmp").exists())
    }

    @Test fun aFailedWidgetDigestWriteIsNotARedraw() {
        val l = layout()
        breakWrites(l.widgetDigestFile)
        val snapshot = TS.snapshot("2026-09-13", listOf(TS.water("cdfw-1", "Lake", listOf(TS.plant("2026-09-13")))))
        val digest = WidgetDigest.build(snapshot, SnapshotMeta(), listOf("cdfw-1"), locked = false)
        assertFalse(WidgetDigest.save(l, digest))
    }

    @Test fun resumeThrottleRunsOncePerInterval() {
        val t = ResumeThrottle(Duration.ofMinutes(15))
        val start = Instant.parse("2026-10-21T10:00:00Z")
        assertTrue(t.tryRun(start))
        assertFalse(t.tryRun(start.plusSeconds(60)))
        assertFalse(t.tryRun(start.plus(Duration.ofMinutes(14))))
        assertTrue(t.tryRun(start.plus(Duration.ofMinutes(15))))
        assertFalse(t.tryRun(start.plus(Duration.ofMinutes(16))))
    }

    @Test fun aStartupQueryCountsAsTheLastRun() {
        val t = ResumeThrottle(Duration.ofMinutes(15))
        val start = Instant.parse("2026-10-21T10:00:00Z")
        t.markRan(start)
        assertFalse(t.tryRun(start.plusSeconds(5)))
    }

    @Test fun aClockThatMovedBackIsDue() {
        val t = ResumeThrottle(Duration.ofMinutes(15))
        val start = Instant.parse("2026-10-21T10:00:00Z")
        t.markRan(start)
        assertTrue(t.tryRun(start.minusSeconds(3600)))
    }

    @Test fun anAskedFlagFromAnotherInstallIsIgnored() {
        // Copied by a device transfer: stamped by the old phone's install.
        assertFalse(NotificationAskMemory.refused("1700000000000", "1800000000000", true) { false })
        // The old format, a bare "1", is also from before the stamp.
        assertFalse(NotificationAskMemory.refused("1", "1800000000000", true) { false })
        assertFalse(NotificationAskMemory.refused(null, "1800000000000", true) { false })
    }

    @Test fun anAskedFlagFromThisInstallIsRefusedOnlyWhenAndroidWontExplain() {
        val stamp = "1800000000000"
        val flag = NotificationAskMemory.flagContents(stamp)
        assertTrue(NotificationAskMemory.refused(flag, stamp, true) { false })
        assertFalse(NotificationAskMemory.refused(flag, stamp, true) { true })
        // Before Android 13 there is no prompt to refuse.
        assertFalse(NotificationAskMemory.refused(flag, stamp, false) { false })
    }
}
