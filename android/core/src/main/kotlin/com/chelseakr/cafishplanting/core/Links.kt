package com.chelseakr.cafishplanting.core

import java.net.URI
import java.net.URISyntaxException

/**
 * The one host this app ever fetches from, and the only URLs it fetches,
 * as `SnapshotEndpoint.swift`. `HostAllowlistTest` fails if any other host
 * appears in the app's own source.
 *
 * [URL] is snapshot v2, California plus every other state (DECISIONS 0025).
 * [V1_URL] is California alone, which stays byte for byte what it was; the
 * app reads it only when v2 isn't there ([SnapshotRefresher]).
 */
object SnapshotEndpoint {
    const val URL = "https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v2.json"
    const val V1_URL = "https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json"
    const val HOST = "chelseakr.github.io"

    /** A California water's site page, derived from the snapshot's own origin. */
    fun siteWaterURL(slug: String): String? {
        if (slug.isEmpty() || slug.any { !(it.isLetterOrDigit() || it == '-' || it == '_') }) return null
        return sitePageURL("/water/$slug/")
    }

    /** A water's page from its v2 `site_path` (`/tn/water/<slug>/`), or the California path when the snapshot gave none. */
    fun siteWaterURL(water: Water): String? = water.sitePath?.let(::sitePageURL) ?: siteWaterURL(water.slug)

    internal fun sitePageURL(path: String): String? {
        if (!path.startsWith("/") || path.contains("..")) return null
        if (path.any { !(it.isLetterOrDigit() || it == '-' || it == '_' || it == '/') }) return null
        return "https://$HOST/ca-fish-planting-alerts$path"
    }
}

/**
 * The app's own link to a water: `trouttruck://water/<water id>`, the same
 * scheme as the iOS app. A tapped alert and the widget open a water through
 * it. Opening one makes no network request.
 */
object WaterLink {
    const val SCHEME = "trouttruck"
    private const val WATER_HOST = "water"

    /** The extra that carries the water's ID on an alert. */
    const val NOTIFICATION_WATER_ID_KEY = "water_id"

    fun url(id: String): String = "$SCHEME://$WATER_HOST/$id"

    /** The water a link points to, or `null` for anything else. */
    fun waterID(url: String): String? {
        val uri = parse(url) ?: return null
        if (!uri.scheme.equals(SCHEME, ignoreCase = true) || !uri.host.equals(WATER_HOST, ignoreCase = true)) return null
        val parts = (uri.path ?: "").split('/').filter { it.isNotEmpty() }
        return parts.singleOrNull()
    }

    internal fun parse(url: String): URI? = try {
        URI(url)
    } catch (_: URISyntaxException) {
        null
    }
}

/** `trouttruck://unlock`: the locked widget's link to the purchase screen. */
object UnlockLink {
    const val URL = "trouttruck://unlock"

    fun matches(url: String): Boolean {
        val uri = WaterLink.parse(url) ?: return false
        return uri.scheme.equals(WaterLink.SCHEME, ignoreCase = true) && uri.host.equals("unlock", ignoreCase = true)
    }
}
