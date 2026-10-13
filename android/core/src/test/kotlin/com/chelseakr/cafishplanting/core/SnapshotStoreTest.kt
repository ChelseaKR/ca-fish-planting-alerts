package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.IOException
import java.time.Instant

class SnapshotStoreTest {
    @get:Rule val tmp = TemporaryFolder()

    private val older = TS.minimalValid
    private val newer = TS.minimalValid.replace("2026-09-13T06:12:44Z", "2026-09-20T06:12:44Z")
    private fun bundled(text: String) = BundledSnapshot { text.byteInputStream() }
    private val now = Instant.parse("2026-09-15T12:00:00Z")

    @Test fun theNewerOfStoredAndBundledWinsAndATieGoesToStored() {
        val layout = AppStorageLayout(tmp.newFolder())
        assertEquals(SnapshotOrigin.BUNDLED, SnapshotStore(layout, bundled(older)).origin)
        layout.snapshotFile.writeText(newer)
        val store = SnapshotStore(layout, bundled(older))
        assertEquals(SnapshotOrigin.STORED, store.origin)
        assertFalse("an older bundled copy is never decoded", store.decodedBundledCopy)
        layout.snapshotFile.writeText(older)
        assertEquals(SnapshotOrigin.STORED, SnapshotStore(layout, bundled(older)).origin)
        assertEquals(SnapshotOrigin.BUNDLED, SnapshotStore(layout, bundled(newer)).origin)
    }

    @Test fun aCorruptStoredCopyIsReportedNotUsedAndNotDeleted() {
        val layout = AppStorageLayout(tmp.newFolder())
        layout.snapshotFile.writeText("{ not json")
        val store = SnapshotStore(layout, bundled(older))
        assertEquals(SnapshotOrigin.BUNDLED, store.origin)
        assertNotNull(store.storedCopyProblem)
        assertTrue(layout.snapshotFile.exists())
    }

    @Test fun nothingUsableThrows() {
        assertThrows(NoUsableSnapshotException::class.java) { SnapshotStore(AppStorageLayout(tmp.newFolder()), null) }
    }

    @Test fun replaceDecodesFirstAndNeverDisplacesTheLastGoodSnapshot() {
        val layout = AppStorageLayout(tmp.newFolder())
        val store = SnapshotStore(layout, bundled(older))
        store.replace(newer.toByteArray(), "\"e1\"", now)
        assertEquals(SnapshotOrigin.STORED, store.origin)
        assertThrows(NotNewerException::class.java) { store.replace(older.toByteArray(), null, now) }
        assertThrows(SnapshotDecodingException::class.java) { store.replace(newer.substring(0, 100).toByteArray(), null, now) }
        assertEquals(newer, layout.snapshotFile.readText())
        assertEquals("\"e1\"", store.meta.etag)
    }

    @Test fun readsV2AndFallsBackToV1OnlyWhenV2IsNotThere() {
        val layout = AppStorageLayout(tmp.newFolder())
        val store = SnapshotStore(layout, bundled(older))
        val asked = mutableListOf<String>()
        fun refresher(v2Status: Int) = SnapshotRefresher({ url, _, _ ->
            asked += url
            if (url == SnapshotEndpoint.URL) HttpResponse(v2Status, null, ByteArray(0)) else HttpResponse(200, "\"v1\"", newer.toByteArray())
        })
        assertTrue(SnapshotEndpoint.URL.endsWith("/snapshot/v2.json"))
        assertTrue(SnapshotEndpoint.V1_URL.endsWith("/snapshot/v1.json"))

        assertEquals(RefreshOutcome.Updated, refresher(404).refresh(store, now))
        assertEquals(listOf(SnapshotEndpoint.URL, SnapshotEndpoint.V1_URL), asked)

        // Any other failure of v2 is a failure, never a quiet switch to v1.
        asked.clear()
        assertTrue(refresher(500).refresh(store, now) is RefreshOutcome.Failed)
        assertEquals(listOf(SnapshotEndpoint.URL), asked)
    }

    @Test fun refreshOutcomesAndAFailureKeepsTheSnapshot() {
        val layout = AppStorageLayout(tmp.newFolder())
        val store = SnapshotStore(layout, bundled(older))
        var seen: Map<String, String> = emptyMap()
        fun refresher(status: Int, body: String = "", fail: Boolean = false) = SnapshotRefresher({ url, headers, _ ->
            assertEquals(SnapshotEndpoint.URL, url)
            seen = headers
            if (fail) throw IOException("offline")
            HttpResponse(status, "\"e2\"", body.toByteArray())
        })
        assertEquals(RefreshOutcome.Updated, refresher(200, newer).refresh(store, now))
        assertEquals(RefreshOutcome.NotModified, refresher(304).refresh(store, now))
        assertEquals("\"e2\"", seen["If-None-Match"])
        assertEquals("CAFishPlanting", seen["User-Agent"])
        assertEquals(setOf("Accept", "User-Agent", "If-None-Match"), seen.keys)
        val week = store.snapshot.sourceWeek
        for (r in listOf(refresher(500), refresher(200, "garbage"), refresher(0, fail = true))) {
            assertTrue(r.refresh(store, now) is RefreshOutcome.Failed)
            assertTrue(store.meta.lastAttemptFailed)
            assertEquals("a failed check never changes the snapshot", week, store.snapshot.sourceWeek)
        }
        // The ledger survives a relaunch.
        assertTrue(SnapshotStore(layout, bundled(older)).meta.lastAttemptFailed)
    }

    @Test fun peeksGeneratedAtWithoutDecoding() {
        assertEquals(Instant.parse("2026-09-13T06:12:44Z"), SnapshotStore.peekGeneratedAt(bundled(older)))
        assertEquals(null, SnapshotStore.peekGeneratedAt(bundled("{}")))
    }

    @Test fun storesReadMissingOrCorruptFilesAsTheirEmptyValues() {
        val layout = AppStorageLayout(tmp.newFolder())
        val stores = Stores(layout)
        assertTrue(stores.loadFavorites().isEmpty)
        stores.saveFavorites(Favorites.of(listOf("cdfw-2", "cdfw-1", "cdfw-2")))
        assertEquals(listOf("cdfw-2", "cdfw-1"), stores.loadFavorites().ids)
        stores.saveMuted(MutedWaters(setOf("cdfw-7")))
        assertTrue(stores.loadMuted().contains("cdfw-7"))
        layout.mutedWatersFile.writeText("not json")
        assertTrue("a corrupt file can only turn alerts back on", stores.loadMuted().isEmpty)
        layout.entitlementFile.writeText("{")
        assertFalse("never a false unlock", stores.loadEntitlement().isPurchased)
        val state = AlertState(mapOf("cdfw-1" to setOf(PlantKey(TS.date("2026-09-20"), "Trout"))))
        stores.saveAlertState(state)
        assertEquals(state, stores.loadAlertState())
        assertTrue(layout.alertStateFile.readText().contains("\"weekStart\": \"2026-09-20\""))
    }
}
