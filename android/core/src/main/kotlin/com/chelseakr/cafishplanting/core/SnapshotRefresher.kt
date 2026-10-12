package com.chelseakr.cafishplanting.core

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.time.Instant

sealed interface RefreshOutcome {
    data object Updated : RefreshOutcome
    data object NotModified : RefreshOutcome
    data class Failed(val message: String) : RefreshOutcome
}

/** What one GET returned. */
class HttpResponse(val status: Int, val etag: String?, val body: ByteArray)

/** The network, behind one function, so tests never touch it. */
fun interface HttpTransport {
    /** Throws [IOException] for a network failure or a body over [maxBytes]. */
    fun get(url: String, headers: Map<String, String>, maxBytes: Int): HttpResponse
}

/**
 * The app's entire network surface, the same as `SnapshotRefresher.swift`:
 * one plain GET of the snapshot URL with `If-None-Match`. No cookies, no
 * cache, no credentials, no identifiers, no other host.
 */
class SnapshotRefresher(private val transport: HttpTransport = UrlConnectionTransport, val endpoint: String = SnapshotEndpoint.URL) {
    /** Pure, so the headers can be asserted. */
    fun requestHeaders(etag: String?): Map<String, String> = buildMap {
        put("Accept", "application/json")
        // A fixed User-Agent with no version, device or locale.
        put("User-Agent", "CAFishPlanting")
        if (etag != null) put("If-None-Match", etag)
    }

    fun refresh(store: SnapshotStore, now: Instant): RefreshOutcome {
        check(WaterLink.parse(endpoint)?.host == SnapshotEndpoint.HOST) { "refresh is only ever against the snapshot host" }
        val response = try {
            transport.get(endpoint, requestHeaders(store.meta.etag), MAXIMUM_BODY_BYTES)
        } catch (e: IOException) {
            val message = e.message ?: e.javaClass.simpleName
            store.recordFailure(message, now)
            return RefreshOutcome.Failed(message)
        }
        return when (response.status) {
            304 -> {
                store.recordNotModified(now)
                RefreshOutcome.NotModified
            }
            200 -> try {
                store.replace(response.body, response.etag, now)
                RefreshOutcome.Updated
            } catch (_: NotNewerException) {
                store.recordNotModified(now)
                RefreshOutcome.NotModified
            } catch (e: Exception) {
                val message = e.message ?: e.toString()
                store.recordFailure(message, now)
                RefreshOutcome.Failed(message)
            }
            else -> {
                val message = "HTTP ${response.status}"
                store.recordFailure(message, now)
                RefreshOutcome.Failed(message)
            }
        }
    }

    companion object {
        const val MAXIMUM_BODY_BYTES = 32 * 1024 * 1024
    }
}

/**
 * `HttpURLConnection` with caching off and no cookie handler: the app never
 * installs a `CookieHandler`, so none is sent or kept. Redirects are
 * followed, as `schema/README.md` asks, and only to https.
 */
object UrlConnectionTransport : HttpTransport {
    override fun get(url: String, headers: Map<String, String>, maxBytes: Int): HttpResponse {
        val connection = URI(url).toURL().openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "GET"
            connection.useCaches = false
            connection.instanceFollowRedirects = true
            connection.connectTimeout = 30_000
            connection.readTimeout = 30_000
            headers.forEach { (k, v) -> connection.setRequestProperty(k, v) }
            val status = connection.responseCode
            if (connection.url.protocol != "https") throw IOException("redirected off https")
            val body = if (status == 200) readLimited(connection, maxBytes) else ByteArray(0)
            return HttpResponse(status, connection.getHeaderField("ETag"), body)
        } finally {
            connection.disconnect()
        }
    }

    private fun readLimited(connection: HttpURLConnection, maxBytes: Int): ByteArray {
        val out = ByteArrayOutputStream()
        connection.inputStream.use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                out.write(buffer, 0, n)
                if (out.size() > maxBytes) throw IOException("body too large: over $maxBytes bytes")
            }
        }
        return out.toByteArray()
    }
}
