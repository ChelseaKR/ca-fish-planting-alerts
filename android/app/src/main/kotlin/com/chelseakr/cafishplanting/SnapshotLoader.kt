package com.chelseakr.cafishplanting

import com.chelseakr.cafishplanting.core.SnapshotStore
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

/** Where opening the snapshot store has got to. */
sealed interface SnapshotLoad {
    data object Loading : SnapshotLoad
    data class Ready(val store: SnapshotStore) : SnapshotLoad
    data class Failed(val message: String) : SnapshotLoad
}

/**
 * Opens the snapshot store on [dispatcher], never on the caller's thread.
 * Decoding the bundled snapshot (about 1 MB of JSON) on the main thread
 * held up launch and could stall a slow device into an ANR. Until [open]
 * returns, [state] is [SnapshotLoad.Loading]. A failure becomes
 * [SnapshotLoad.Failed] with the store's own words, and is never replaced
 * by a made-up snapshot.
 *
 * No Android types, so its JVM test runs without an emulator.
 */
class SnapshotLoader(scope: CoroutineScope, dispatcher: CoroutineDispatcher, open: () -> SnapshotStore) {
    private val _state = MutableStateFlow<SnapshotLoad>(SnapshotLoad.Loading)
    val state: StateFlow<SnapshotLoad> = _state
    private val result = CompletableDeferred<SnapshotLoad>()

    init {
        scope.launch(dispatcher) {
            val outcome = try {
                SnapshotLoad.Ready(open())
            } catch (e: Throwable) {
                // Any throwable, an Error included: an uncompleted result would leave every refresh waiting forever.
                SnapshotLoad.Failed(e.message ?: e.toString())
            }
            _state.value = outcome
            result.complete(outcome)
        }
    }

    /** Suspends until the store is open or has failed to open. */
    suspend fun await(): SnapshotLoad = result.await()
}
