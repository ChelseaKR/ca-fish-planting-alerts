package com.chelseakr.cafishplanting.core

import kotlinx.serialization.Serializable
import java.io.File
import java.io.InputStream
import java.time.Instant

/** The stored snapshot's ETag and refresh ledger. Never anything from the device. */
@Serializable
data class SnapshotMeta(
    val etag: String? = null,
    @Serializable(with = InstantSerializer::class) val lastAttemptAt: Instant? = null,
    @Serializable(with = InstantSerializer::class) val lastSuccessAt: Instant? = null,
    val lastOutcome: String? = null,
    val lastError: String? = null,
) {
    val lastAttemptFailed: Boolean get() = lastOutcome == SnapshotStore.FAILED_OUTCOME
}

enum class SnapshotOrigin { BUNDLED, STORED }

class NoUsableSnapshotException(bundled: String?, stored: String?) :
    Exception("No usable snapshot. Bundled: ${bundled ?: "missing"}. Stored: ${stored ?: "missing"}.")

class NotNewerException : Exception("The fetched snapshot is not newer than the one held.")

/** The snapshot that ships inside the app (an Android asset), opened on demand. */
fun interface BundledSnapshot {
    fun open(): InputStream
}

/**
 * Offline first, the same rules as `SnapshotStore.swift`. Holds exactly one
 * last good snapshot:
 *
 * - On load, the newer (`generated_at`) of the stored and bundled copies
 *   wins; the stored copy wins a tie. A stored copy that fails to decode is
 *   ignored, not deleted, and reported. The bundled copy is decoded only
 *   when it could win.
 * - [replace] decodes before it writes and writes atomically, so a truncated
 *   download or a contract change never displaces the last good snapshot.
 *
 * Not thread-safe by design: the app drives it from one place, under a lock.
 */
class SnapshotStore(val layout: AppStorageLayout, private val bundled: BundledSnapshot?) {
    private val metaStore = JsonFileStore(layout.snapshotMetaFile, SnapshotMeta.serializer())

    var snapshot: Snapshot
        private set
    var origin: SnapshotOrigin
        private set
    var meta: SnapshotMeta
        private set
    var storedCopyProblem: String? = null
        private set
    var decodedBundledCopy: Boolean = false
        private set

    init {
        layout.ensureDirectory()
        var stored: Snapshot? = null
        var storedProblem: String? = null
        if (layout.snapshotFile.exists()) {
            try {
                stored = SnapshotDecoder.decode(layout.snapshotFile.readBytes())
            } catch (e: Exception) {
                storedProblem = e.message ?: e.toString()
            }
        }
        var bundledSnapshot: Snapshot? = null
        var bundledProblem: String? = null
        if (bundled != null) {
            val peeked = if (stored != null) peekGeneratedAt(bundled) else null
            if (stored != null && peeked != null && peeked <= stored.generatedAt) {
                // The bundled copy can't win, so decoding it would only cost launch time.
            } else {
                decodedBundledCopy = true
                try {
                    bundledSnapshot = bundled.open().use { SnapshotDecoder.decode(it.readBytes()) }
                } catch (e: Exception) {
                    bundledProblem = e.message ?: e.toString()
                }
            }
        } else {
            bundledProblem = "no bundled snapshot"
        }
        when {
            bundledSnapshot != null && stored != null ->
                if (stored.generatedAt >= bundledSnapshot.generatedAt) {
                    snapshot = stored
                    origin = SnapshotOrigin.STORED
                } else {
                    snapshot = bundledSnapshot
                    origin = SnapshotOrigin.BUNDLED
                }
            bundledSnapshot != null -> {
                snapshot = bundledSnapshot
                origin = SnapshotOrigin.BUNDLED
            }
            stored != null -> {
                snapshot = stored
                origin = SnapshotOrigin.STORED
            }
            else -> throw NoUsableSnapshotException(bundledProblem, storedProblem)
        }
        storedCopyProblem = storedProblem
        meta = metaStore.loadOrNull() ?: SnapshotMeta()
    }

    /** Decode, then write atomically, then swap. Throws and changes nothing if the bytes don't decode or aren't newer. */
    fun replace(bytes: ByteArray, etag: String?, now: Instant): Snapshot {
        val candidate = SnapshotDecoder.decode(bytes)
        if (!(candidate.generatedAt > snapshot.generatedAt || origin == SnapshotOrigin.BUNDLED)) throw NotNewerException()
        val temp = File(layout.directory, ".snapshot.json.tmp")
        temp.writeBytes(bytes)
        if (!temp.renameTo(layout.snapshotFile)) {
            layout.snapshotFile.delete()
            check(temp.renameTo(layout.snapshotFile)) { "could not write the snapshot" }
        }
        snapshot = candidate
        origin = SnapshotOrigin.STORED
        storedCopyProblem = null
        meta = meta.copy(etag = etag, lastAttemptAt = now, lastSuccessAt = now, lastOutcome = "updated", lastError = null)
        saveMeta()
        return candidate
    }

    fun recordNotModified(now: Instant) {
        meta = meta.copy(lastAttemptAt = now, lastSuccessAt = now, lastOutcome = "not modified", lastError = null)
        saveMeta()
    }

    fun recordFailure(message: String, now: Instant) {
        meta = meta.copy(lastAttemptAt = now, lastOutcome = FAILED_OUTCOME, lastError = message)
        saveMeta()
    }

    private fun saveMeta() {
        try {
            metaStore.save(meta)
        } catch (_: Exception) {
            // The ledger is best effort, as in the iOS app.
        }
    }

    companion object {
        const val FAILED_OUTCOME = "failed"
        private val GENERATED_AT = Regex(""""generated_at"\s*:\s*"([^"]+)"""")

        /** A snapshot's `generated_at`, read from its first bytes without decoding the rest. */
        fun peekGeneratedAt(bundled: BundledSnapshot, headBytes: Int = 512): Instant? = try {
            val head = bundled.open().use { stream ->
                val buffer = ByteArray(headBytes)
                var read = 0
                while (read < headBytes) {
                    val n = stream.read(buffer, read, headBytes - read)
                    if (n < 0) break
                    read += n
                }
                String(buffer, 0, read, Charsets.UTF_8)
            }
            GENERATED_AT.find(head)?.groupValues?.get(1)?.let { SnapshotDecoder.datetime(it, "generated_at") }
        } catch (_: Exception) {
            null
        }
    }
}
