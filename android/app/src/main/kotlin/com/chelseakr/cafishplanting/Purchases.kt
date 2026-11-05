package com.chelseakr.cafishplanting

import android.app.Activity
import com.chelseakr.cafishplanting.core.Entitlements
import com.chelseakr.cafishplanting.core.FreeLaunch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** What the purchase sheet shows. */
data class PurchaseUi(
    /** Price text per product ID, from Google Play. Empty until Play answers. */
    val prices: Map<String, String> = emptyMap(),
    val productLoadError: String? = null,
    val busy: Busy = Busy.IDLE,
    val message: String? = null,
    /** A purchase Play has accepted but not been paid for yet (a pending payment method). */
    val pending: Boolean = false,
) {
    enum class Busy { IDLE, PURCHASING, RESTORING }
}

/**
 * The store behind the purchase screen. One implementation talks to Google
 * Play Billing; debug builds can swap in a local one for tests and
 * screenshots (src/debug), the way the iOS app uses a local StoreKit file.
 * The free build (DECISIONS 0044) uses [FreeLaunchBackend] and has no Play
 * Billing at all; [PlayStore] picks the backend for the build.
 * Every product in `StateProducts` is a one-time (non-consumable) product,
 * so a second state's purchase is one more ID, not new code.
 */
interface PurchaseBackend {
    val ui: StateFlow<PurchaseUi>
    fun start(onEntitlements: (Entitlements) -> Unit)
    fun purchase(activity: Activity, productID: String)
    /** "Restore purchases": asks Play again what this account owns. */
    fun restore()

    /** Asks Play for the price again after a failed first try. Does nothing while prices are loaded or loading. */
    fun retryProducts() = Unit

    /** The app came back to the foreground: re-checks what the account owns (throttled) and retries a failed price query. */
    fun onForeground() = Unit
}

/**
 * The free build's store (DECISIONS 0044): it sells nothing and reports every
 * state as owned, so the unchanged per-state gate lets every alert through and
 * unlocks the widget. Nothing is written for Google Play, because nothing
 * talks to it.
 */
object FreeLaunchBackend : PurchaseBackend {
    override val ui: StateFlow<PurchaseUi> = MutableStateFlow(PurchaseUi())

    override fun start(onEntitlements: (Entitlements) -> Unit) = onEntitlements(FreeLaunch.entitlements)

    override fun purchase(activity: Activity, productID: String) = Unit

    override fun restore() = Unit
}
