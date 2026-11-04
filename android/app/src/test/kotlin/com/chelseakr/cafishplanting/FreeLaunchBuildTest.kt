package com.chelseakr.cafishplanting

import com.chelseakr.cafishplanting.core.Entitlements
import com.chelseakr.cafishplanting.core.FreeLaunch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The build flag (DECISIONS 0044). The same test runs in both builds: with
 * `troutTruck.androidFreeTier=true` it checks the free build carries no Play
 * Billing and owns every state; with `false` (the negative control) it checks
 * Play Billing is back and nothing is owned until Google Play says so.
 */
class FreeLaunchBuildTest {
    private fun billingOnClasspath(): Boolean =
        runCatching { Class.forName("com.android.billingclient.api.BillingClient") }.isSuccess

    @Test fun theBillingLibraryIsInTheBuildOnlyWhenTheFlagIsOff() {
        assertEquals("FREE_TIER=${BuildConfig.FREE_TIER}", !BuildConfig.FREE_TIER, billingOnClasspath())
        assertEquals(!BuildConfig.FREE_TIER, runCatching { Class.forName("com.chelseakr.cafishplanting.PlayBillingBackend") }.isSuccess)
    }

    @Test fun theFreeStoreSellsNothingAndOwnsEveryState() {
        var reported: Entitlements? = null
        FreeLaunchBackend.start { reported = it }
        assertEquals(FreeLaunch.entitlements, reported)
        assertTrue(FreeLaunchBackend.ui.value.prices.isEmpty())
    }

    /** The paid build's store needs a real Context for Play, so only the free build's choice is checked here. */
    @Test fun theFreeBuildPicksTheFreeStore() {
        if (BuildConfig.FREE_TIER) assertEquals(FreeLaunchBackend, PlayStore.backend(android.content.ContextWrapper(null)))
    }
}
