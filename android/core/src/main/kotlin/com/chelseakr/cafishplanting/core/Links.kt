package com.chelseakr.cafishplanting.core

import java.net.URI
import java.net.URISyntaxException

/**
 * The one host this app ever fetches from, and the only URL it fetches.
 * The same constant as `SnapshotEndpoint.swift`; `HostAllowlistTest` fails
 * if any other host appears in the app's own source.
 */
object SnapshotEndpoint {
    const val URL = "https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json"
    const val HOST = "chelseakr.github.io"

    /** The per-water site page, derived from the snapshot's own origin. */
    fun siteWaterURL(slug: String): String? {
        if (slug.isEmpty() || slug.any { !(it.isLetterOrDigit() || it == '-' || it == '_') }) return null
        return "https://$HOST/ca-fish-planting-alerts/water/$slug/"
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
