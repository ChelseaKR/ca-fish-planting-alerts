package com.chelseakr.cafishplanting.core

/**
 * A state the app can show. Today the app reads one snapshot, California's
 * (schema v1, which carries no state field, so every v1 snapshot is
 * California). A parallel lane is adding Tennessee, Massachusetts and
 * Michigan as separate one-time purchases with a v2 snapshot per state;
 * this type, [ProductCatalog] and [Entitlements] are where that lands, so
 * adding a state is new entries here plus a state picker, not a rewrite.
 */
data class StateInfo(
    /** USPS code: "CA". */
    val code: String,
    val name: String,
    /** The one snapshot URL the app fetches for this state. */
    val snapshotURL: String,
    /** The Google Play one-time product that unlocks alerts and the widget for this state. */
    val productID: String,
)

object ProductCatalog {
    /**
     * California full access. A placeholder ID until the owner creates the
     * product in Play Console; Play product IDs can't contain the iOS ID's
     * reverse-DNS form by convention, so `fullaccess` mirrors its last part.
     */
    const val CALIFORNIA_FULL_ACCESS = "fullaccess"

    val california = StateInfo("CA", "California", SnapshotEndpoint.URL, CALIFORNIA_FULL_ACCESS)

    /** Every state this build can show, in the order a picker would list them. */
    val states: List<StateInfo> = listOf(california)

    /** Every one-time product this build sells. */
    val productIDs: List<String> get() = states.map { it.productID }.distinct()

    fun state(code: String): StateInfo? = states.firstOrNull { it.code == code }

    fun stateForProduct(productID: String): StateInfo? = states.firstOrNull { it.productID == productID }
}

/**
 * The one-time products this device owns, as Google Play last reported
 * them. Per state, not one flag, so a second state's purchase unlocks that
 * state only.
 */
data class Entitlements(val ownedProducts: Set<String> = emptySet()) {
    fun owns(state: StateInfo): Boolean = state.productID in ownedProducts

    /** California, the only state today; what "full access" means in the UI. */
    val californiaFullAccess: Boolean get() = owns(ProductCatalog.california)
}
