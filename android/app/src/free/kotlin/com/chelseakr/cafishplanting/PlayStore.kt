package com.chelseakr.cafishplanting

import android.content.Context

/**
 * The free build's store (DECISIONS 0044): nothing for sale, no Play Billing.
 * The paid build's twin is in src/billing.
 */
object PlayStore {
    fun backend(@Suppress("UNUSED_PARAMETER") context: Context): PurchaseBackend = FreeLaunchBackend
}
