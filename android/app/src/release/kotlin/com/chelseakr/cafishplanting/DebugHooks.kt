package com.chelseakr.cafishplanting

import android.content.Context
import com.chelseakr.cafishplanting.core.HttpTransport
import com.chelseakr.cafishplanting.core.UrlConnectionTransport

/** Release builds: the real network and the build's own store (Google Play, or nothing for sale in the free build), always. The debug twin is in src/debug. */
object DebugHooks {
    fun transport(@Suppress("UNUSED_PARAMETER") context: Context): HttpTransport = UrlConnectionTransport

    fun purchaseBackend(context: Context): PurchaseBackend = PlayStore.backend(context)
}

object ReviewLaunchOverride {
    fun allowsAsking(@Suppress("UNUSED_PARAMETER") context: Context): Boolean = true
}
