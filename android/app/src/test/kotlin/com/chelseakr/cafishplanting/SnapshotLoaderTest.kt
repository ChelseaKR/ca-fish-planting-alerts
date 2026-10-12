package com.chelseakr.cafishplanting

import com.chelseakr.cafishplanting.core.AppStorageLayout
import com.chelseakr.cafishplanting.core.BundledSnapshot
import com.chelseakr.cafishplanting.core.SnapshotOrigin
import com.chelseakr.cafishplanting.core.SnapshotStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExecutorCoroutineDispatcher
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.io.FileNotFoundException
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** The launch path: the snapshot opens off the caller's thread, behind a loading state. */
class SnapshotLoaderTest {
    private lateinit var dispatcher: ExecutorCoroutineDispatcher
    private lateinit var scope: CoroutineScope
    private lateinit var dir: File
    private var loaderThread: Thread? = null

    private val repoRoot: File by lazy {
        generateSequence(File("").absoluteFile) { it.parentFile }.first { File(it, "ios/PlantingCore").isDirectory }
    }
    private val bundledFile: File get() = File(repoRoot, "ios/CAFishPlanting/Resources/snapshot.json")

    @Before
    fun setUp() {
        dispatcher = Executors.newSingleThreadExecutor { r -> Thread(r, "snapshot-loader-test").also { loaderThread = it } }.asCoroutineDispatcher()
        scope = CoroutineScope(SupervisorJob())
        dir = Files.createTempDirectory("snapshot-loader").toFile()
    }

    @After
    fun tearDown() {
        scope.cancel()
        dispatcher.close()
        dir.deleteRecursively()
    }

    private fun await(loader: SnapshotLoader): SnapshotLoad = runBlocking { withTimeout(30_000) { loader.await() } }

    @Test
    fun opensTheRealBundledSnapshotOnTheGivenDispatcherNotTheCallers() {
        var openedOn: Thread? = null
        val loader = SnapshotLoader(scope, dispatcher) {
            openedOn = Thread.currentThread()
            SnapshotStore(AppStorageLayout(dir), BundledSnapshot { bundledFile.inputStream() })
        }
        val outcome = await(loader)
        assertTrue("expected Ready, got $outcome", outcome is SnapshotLoad.Ready)
        // Compared as threads: coroutine debug mode renames a thread while a coroutine runs on it.
        assertSame(loaderThread, openedOn)
        assertNotSame(Thread.currentThread(), openedOn)
        val store = (outcome as SnapshotLoad.Ready).store
        assertEquals(SnapshotOrigin.BUNDLED, store.origin)
        assertTrue(store.snapshot.waters.isNotEmpty())
        assertEquals(outcome, loader.state.value)
    }

    @Test
    fun staysLoadingUntilTheStoreHasOpened() {
        val gate = CountDownLatch(1)
        val loader = SnapshotLoader(scope, dispatcher) {
            check(gate.await(30, TimeUnit.SECONDS)) { "the test never opened the gate" }
            SnapshotStore(AppStorageLayout(dir), BundledSnapshot { bundledFile.inputStream() })
        }
        // The constructor has returned while the open is still blocked: the caller was never held up.
        assertEquals(SnapshotLoad.Loading, loader.state.value)
        gate.countDown()
        assertTrue(await(loader) is SnapshotLoad.Ready)
        assertTrue(loader.state.value is SnapshotLoad.Ready)
    }

    @Test
    fun aMissingAssetBecomesTheErrorScreensWordsNotASnapshot() {
        val loader = SnapshotLoader(scope, dispatcher) {
            SnapshotStore(AppStorageLayout(dir), BundledSnapshot { throw FileNotFoundException("snapshot.json") })
        }
        assertEquals(
            SnapshotLoad.Failed("No usable snapshot. Bundled: snapshot.json. Stored: missing."),
            await(loader),
        )
    }

    @Test
    fun anErrorStillCompletesSoNoRefreshWaitsForever() {
        val loader = SnapshotLoader(scope, dispatcher) { throw StackOverflowError("too deep") }
        assertEquals(SnapshotLoad.Failed("too deep"), await(loader))
        assertEquals(SnapshotLoad.Failed("too deep"), loader.state.value)
    }
}
