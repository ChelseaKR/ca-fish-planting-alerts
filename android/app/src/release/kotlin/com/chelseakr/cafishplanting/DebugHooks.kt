package com.chelseakr.cafishplanting

import android.content.Context
import com.chelseakr.cafishplanting.core.HttpTransport
import com.chelseakr.cafishplanting.core.UrlConnectionTransport

/** Release builds: the real network and Google Play, always. The debug twin is in src/debug. */
object DebugHooks {
    fun transport(@Suppress("UNUSED_PARAMETER") context: Context): HttpTransport = UrlConnectionTransport

    fun purchaseBackend(context: Context): PurchaseBackend = PlayBillingBackend(context)
}

object ReviewLaunchOverride {
    fun allowsAsking(@Suppress("UNUSED_PARAMETER") context: Context): Boolean = true
}
