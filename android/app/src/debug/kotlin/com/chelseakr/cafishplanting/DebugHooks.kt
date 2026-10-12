package com.chelseakr.cafishplanting

import android.app.Activity
import android.content.Context
import android.util.Log
import com.chelseakr.cafishplanting.core.Entitlements
import com.chelseakr.cafishplanting.core.HttpResponse
import com.chelseakr.cafishplanting.core.HttpTransport
import com.chelseakr.cafishplanting.core.ProductCatalog
import com.chelseakr.cafishplanting.core.UrlConnectionTransport
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.File

/**
 * Debug builds only (this file is not in a release APK). Switches read from
 * files under the app's own `files/debug/`, written with `adb shell run-as`:
 *
 * - `network-snapshot.json`: served as the snapshot URL's 200 response
 *   instead of the network, so an alert can be produced on demand from a
 *   real snapshot. Logged on every use.
 * - `fake-billing`: a local store that "sells" every product at $9.99 and
 *   remembers it in `fake-billing-owned`, in place of Google Play, which
 *   has no product until the owner creates one in Play Console.
 * - `allow-review`: lets the review card be requested (debug builds never
 *   ask otherwise, so tests and screenshots aren't interrupted).
 */
object DebugHooks {
    private const val TAG = "TroutTruckDebug"

    private fun dir(context: Context) = File(context.filesDir, "debug")

    fun transport(context: Context): HttpTransport = HttpTransport { url, headers, maxBytes ->
        val local = File(dir(context), "network-snapshot.json")
        if (local.exists()) {
            Log.w(TAG, "DEBUG: serving ${local.path} for $url instead of the network")
            HttpResponse(200, "\"debug-${local.lastModified()}\"", local.readBytes())
        } else {
            UrlConnectionTransport.get(url, headers, maxBytes)
        }
    }

    fun purchaseBackend(context: Context): PurchaseBackend =
        if (File(dir(context), "fake-billing").exists()) FakeBackend(dir(context)) else PlayBillingBackend(context)

    private class FakeBackend(private val dir: File) : PurchaseBackend {
        private val owned = File(dir, "fake-billing-owned")
        private val _ui = MutableStateFlow(PurchaseUi(prices = ProductCatalog.productIDs.associateWith { "$9.99" }))
        override val ui: StateFlow<PurchaseUi> = _ui
        private var report: (Entitlements) -> Unit = {}

        private fun current() = Entitlements(if (owned.exists()) owned.readLines().filter { it.isNotBlank() }.toSet() else emptySet())

        override fun start(onEntitlements: (Entitlements) -> Unit) {
            Log.w(TAG, "DEBUG: fake billing in use")
            report = onEntitlements
            onEntitlements(current())
        }

        override fun purchase(activity: Activity, productID: String) {
            owned.appendText("$productID\n")
            report(current())
        }

        override fun restore() = report(current())
    }
}

object ReviewLaunchOverride {
    fun allowsAsking(context: Context): Boolean = File(File(context.filesDir, "debug"), "allow-review").exists()
}
