package com.chelseakr.cafishplanting

import com.chelseakr.cafishplanting.core.Snapshot
import com.chelseakr.cafishplanting.core.UnlockLink
import com.chelseakr.cafishplanting.core.WaterLink
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

enum class Tab { BROWSE, FAVORITES, ABOUT }

/** A water to open in a tab's list-detail pane. [serial] makes two requests for the same water distinct. */
data class OpenRequest(val waterID: String, val serial: Long)

data class RouterState(
    val tab: Tab = Tab.BROWSE,
    val openInBrowse: OpenRequest? = null,
    val openInFavorites: OpenRequest? = null,
    val pendingWaterID: String? = null,
    val showingPurchase: Boolean = false,
    val showingOnboarding: Boolean = false,
)

/**
 * Which tab shows and which water opens, the twin of the iOS `AppRouter`:
 * a tapped alert and a `trouttruck://water/<id>` link (the widget) land on
 * the same screen. A favorite opens under Favorites, any other water under
 * Browse, and a water the snapshot doesn't have is never opened as a blank page.
 */
class Router {
    private val _state = MutableStateFlow(RouterState())
    val state: StateFlow<RouterState> = _state
    private var serial = 0L

    fun select(tab: Tab) = _state.update { it.copy(tab = tab) }

    fun setPurchase(showing: Boolean) = _state.update { it.copy(showingPurchase = showing) }

    fun setOnboarding(showing: Boolean) = _state.update { it.copy(showingOnboarding = showing) }

    /** Handles the app's own links. `false`, and nothing asked, for any other URL. */
    fun handle(url: String): Boolean {
        if (UnlockLink.matches(url)) {
            _state.update { it.copy(tab = Tab.ABOUT, showingPurchase = true) }
            return true
        }
        val id = WaterLink.waterID(url) ?: return false
        _state.update { it.copy(pendingWaterID = id) }
        return true
    }

    fun openPending(snapshot: Snapshot?, isFavorite: (String) -> Boolean): Boolean {
        val id = _state.value.pendingWaterID ?: return false
        val favorite = isFavorite(id)
        if (snapshot?.water(id) == null) {
            _state.update { it.copy(pendingWaterID = null, tab = if (favorite) Tab.FAVORITES else it.tab) }
            return false
        }
        serial += 1
        val request = OpenRequest(id, serial)
        _state.update {
            if (favorite) {
                it.copy(pendingWaterID = null, tab = Tab.FAVORITES, openInFavorites = request)
            } else {
                it.copy(pendingWaterID = null, tab = Tab.BROWSE, openInBrowse = request)
            }
        }
        return true
    }
}
