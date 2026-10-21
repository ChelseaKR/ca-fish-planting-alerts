package com.chelseakr.cafishplanting

import android.app.Activity
import android.content.Context
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams
import com.chelseakr.cafishplanting.core.Entitlements
import com.chelseakr.cafishplanting.core.ProductCatalog
import com.chelseakr.cafishplanting.core.ResumeThrottle
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import java.time.Duration
import java.time.Instant

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
 * Every product in [ProductCatalog] is a one-time (non-consumable) product,
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

class PlayBillingBackend(context: Context) : PurchaseBackend {
    private val _ui = MutableStateFlow(PurchaseUi())
    override val ui: StateFlow<PurchaseUi> = _ui
    private var details: Map<String, ProductDetails> = emptyMap()
    private var report: (Entitlements) -> Unit = {}
    private var connecting = false
    private var loadingProducts = false
    private val ownedThrottle = ResumeThrottle(Duration.ofMinutes(15))

    private val client: BillingClient = BillingClient.newBuilder(context)
        .setListener { result, purchases ->
            when (result.responseCode) {
                BillingClient.BillingResponseCode.OK -> handle(purchases.orEmpty(), fromPurchase = true)
                BillingClient.BillingResponseCode.USER_CANCELED -> _ui.update { it.copy(busy = PurchaseUi.Busy.IDLE) }
                BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> restore()
                else -> fail(result)
            }
        }
        .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
        .enableAutoServiceReconnection()
        .build()

    override fun start(onEntitlements: (Entitlements) -> Unit) {
        report = onEntitlements
        ownedThrottle.markRan(Instant.now())
        connect()
    }

    /** Opens the connection to Play. Safe to call again after a failed setup; one attempt at a time. */
    private fun connect() {
        if (connecting || client.isReady) return
        connecting = true
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                connecting = false
                if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                    _ui.update { it.copy(productLoadError = result.debugMessage.ifEmpty { "Google Play isn't available" }) }
                    return
                }
                loadProducts()
                queryOwned()
            }

            override fun onBillingServiceDisconnected() = Unit
        })
    }

    override fun retryProducts() {
        if (details.isNotEmpty() || loadingProducts || connecting) return
        _ui.update { it.copy(productLoadError = null) }
        if (client.isReady) loadProducts() else connect()
    }

    override fun onForeground() {
        retryProducts()
        // Play's list is the truth, so a refund or a purchase elsewhere shows up without a restart.
        if (ownedThrottle.tryRun(Instant.now()) && client.isReady) queryOwned()
    }

    private fun loadProducts() {
        loadingProducts = true
        val params = QueryProductDetailsParams.newBuilder().setProductList(
            ProductCatalog.productIDs.map {
                QueryProductDetailsParams.Product.newBuilder().setProductId(it).setProductType(BillingClient.ProductType.INAPP).build()
            },
        ).build()
        client.queryProductDetailsAsync(params) { result, found ->
            loadingProducts = false
            if (result.responseCode != BillingClient.BillingResponseCode.OK || found.productDetailsList.isEmpty()) {
                _ui.update { it.copy(productLoadError = result.debugMessage.ifEmpty { "No product found" }) }
                return@queryProductDetailsAsync
            }
            details = found.productDetailsList.associateBy { it.productId }
            _ui.update { ui ->
                ui.copy(
                    productLoadError = null,
                    prices = details.mapNotNull { (id, d) -> d.oneTimePurchaseOfferDetailsList?.firstOrNull()?.formattedPrice?.let { id to it } }.toMap(),
                )
            }
        }
    }

    private fun queryOwned(fromRestore: Boolean = false) {
        client.queryPurchasesAsync(QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.INAPP).build()) { result, purchases ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                handle(purchases, fromPurchase = false)
                if (fromRestore) _ui.update { it.copy(busy = PurchaseUi.Busy.IDLE, message = null) }
            } else if (fromRestore) {
                fail(result)
            }
        }
    }

    /** Play's list is the truth: what it says is owned is owned, and nothing else (a refund locks again). */
    private fun handle(purchases: List<Purchase>, fromPurchase: Boolean) {
        val owned = purchases.filter { it.purchaseState == Purchase.PurchaseState.PURCHASED }
        owned.filter { !it.isAcknowledged }.forEach { p ->
            client.acknowledgePurchase(AcknowledgePurchaseParams.newBuilder().setPurchaseToken(p.purchaseToken).build()) { }
        }
        val pending = purchases.any { it.purchaseState == Purchase.PurchaseState.PENDING }
        if (fromPurchase) {
            // A purchase update lists only the new purchase; ask for everything owned.
            queryOwned()
            _ui.update { it.copy(busy = PurchaseUi.Busy.IDLE, pending = pending) }
            return
        }
        _ui.update { it.copy(pending = pending) }
        report(Entitlements(owned.flatMap { it.products }.toSet()))
    }

    override fun purchase(activity: Activity, productID: String) {
        val product = details[productID] ?: run {
            _ui.update { it.copy(message = "Not available right now") }
            return
        }
        _ui.update { it.copy(busy = PurchaseUi.Busy.PURCHASING, message = null) }
        val params = BillingFlowParams.newBuilder().setProductDetailsParamsList(
            listOf(BillingFlowParams.ProductDetailsParams.newBuilder().setProductDetails(product).build()),
        ).build()
        val result = client.launchBillingFlow(activity, params)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) fail(result)
    }

    override fun restore() {
        _ui.update { it.copy(busy = PurchaseUi.Busy.RESTORING, message = null) }
        queryOwned(fromRestore = true)
    }

    private fun fail(result: BillingResult) {
        _ui.update { it.copy(busy = PurchaseUi.Busy.IDLE, message = result.debugMessage.ifEmpty { "Google Play couldn't complete that (code ${result.responseCode})." }) }
    }
}
