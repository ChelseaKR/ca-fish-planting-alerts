package com.chelseakr.cafishplanting

import android.app.Application

class TroutTruckApplication : Application() {
    val router = Router()
    val purchases: PurchaseBackend by lazy { DebugHooks.purchaseBackend(this) }

    override fun onCreate() {
        super.onCreate()
        val env = AppEnvironment.get(this)
        env.notifications.createChannel()
        RefreshWorker.schedule(this)
        // Google Play is the truth for what this account owns: a purchase on
        // another device, a restore or a refund lands here.
        purchases.start(env::setEntitlements)
    }
}
