package com.chelseakr.cafishplanting.ui

import android.app.Activity
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.unit.dp
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material.icons.outlined.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.adaptive.ExperimentalMaterial3AdaptiveApi
import androidx.compose.material3.adaptive.currentWindowAdaptiveInfo
import androidx.compose.material3.adaptive.layout.AnimatedPane
import androidx.compose.material3.adaptive.layout.ListDetailPaneScaffoldRole
import androidx.compose.material3.adaptive.layout.PaneAdaptedValue
import androidx.compose.material3.adaptive.layout.calculatePaneScaffoldDirective
import androidx.compose.material3.adaptive.navigation.NavigableListDetailPaneScaffold
import androidx.compose.material3.adaptive.navigation.rememberListDetailPaneScaffoldNavigator
import androidx.compose.material3.adaptive.navigationsuite.NavigationSuiteScaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.AppState
import com.chelseakr.cafishplanting.OpenRequest
import com.chelseakr.cafishplanting.PurchaseBackend
import com.chelseakr.cafishplanting.Router
import com.chelseakr.cafishplanting.Tab
import com.chelseakr.cafishplanting.rememberHaptics
import kotlinx.coroutines.launch

@Composable
fun AppRoot(env: AppEnvironment, router: Router, purchases: PurchaseBackend, activity: Activity) {
    val state by env.state.collectAsStateWithLifecycle()
    val route by router.state.collectAsStateWithLifecycle()
    val haptics = rememberHaptics()

    if (state.isLoading) {
        LoadingSchedule()
        return
    }

    val error = state.loadError
    if (error != null) {
        EmptyState(Icons.Outlined.Warning, "Can't load the stocking schedule", error)
        return
    }

    // A tapped alert or a widget link: open that water once the snapshot is here.
    LaunchedEffect(route.pendingWaterID, state.snapshot) {
        if (route.pendingWaterID != null && state.snapshot != null) {
            router.openPending(state.snapshot) { state.favorites.contains(it) }
        }
    }

    NavigationSuiteScaffold(
        navigationSuiteItems = {
            item(
                selected = route.tab == Tab.BROWSE,
                onClick = { router.select(Tab.BROWSE) },
                icon = { Icon(if (route.tab == Tab.BROWSE) Icons.Filled.Map else Icons.Outlined.Map, null) },
                label = { Text("Browse") },
            )
            item(
                selected = route.tab == Tab.FAVORITES,
                onClick = { router.select(Tab.FAVORITES) },
                icon = { Icon(if (route.tab == Tab.FAVORITES) Icons.Filled.Star else Icons.Outlined.StarOutline, null) },
                label = { Text("Favorites") },
            )
            item(
                selected = route.tab == Tab.ABOUT,
                onClick = { router.select(Tab.ABOUT) },
                icon = { Icon(if (route.tab == Tab.ABOUT) Icons.Filled.Info else Icons.Outlined.Info, null) },
                label = { Text("About") },
            )
        },
    ) {
        when (route.tab) {
            Tab.BROWSE -> ListDetail(env, state, route.openInBrowse, "Choose a water from the list to see its schedule and history.", isBusy = { route.showingPurchase || route.showingOnboarding }) { open ->
                BrowseList(env, state, open.selected, open.onOpen)
            }
            Tab.FAVORITES -> ListDetail(env, state, route.openInFavorites, "Choose a favorite to see its schedule and history.", isBusy = { route.showingPurchase || route.showingOnboarding }) { open ->
                FavoritesList(env, state, open.selected, open.onOpen, onBrowse = { router.select(Tab.BROWSE) })
            }
            Tab.ABOUT -> AboutScreen(env, state, onUnlock = { router.setPurchase(true) }, onShowIntroduction = { router.setOnboarding(true) })
        }
    }

    state.primingFor?.let { water ->
        PrimingSheet(activity, env, waterName = water.name, isEntitled = state.isEntitled, onDone = env::dismissPriming)
    }
    if (route.showingPurchase) {
        PurchaseSheet(activity, env, purchases, onDismiss = { router.setPurchase(false) })
    }
    if (route.showingOnboarding) {
        OnboardingScreen(onFinish = {
            env.completeOnboarding()
            router.setOnboarding(false)
            haptics.success()
        })
    }
}

/** What a list pane gets: the water open beside it (on a wide screen) and how to open one. */
class ListOpen(val selected: String?, val onOpen: (String) -> Unit)

/**
 * A list beside the water's page on a wide window (tablet, unfolded
 * foldable, desktop window), one at a time on a phone, the twin of the iOS
 * app's `NavigationSplitView` on iPad. At large text sizes it is one pane at
 * every width, as on iPad, where the list's column is too narrow for the words.
 */
@OptIn(ExperimentalMaterial3AdaptiveApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun ListDetail(
    env: AppEnvironment,
    state: AppState,
    openRequest: OpenRequest?,
    placeholder: String,
    isBusy: () -> Boolean,
    list: @Composable (ListOpen) -> Unit,
) {
    val largeText = LocalDensity.current.fontScale >= LARGE_TEXT_SCALE
    val base = calculatePaneScaffoldDirective(currentWindowAdaptiveInfo())
    val directive = if (largeText) base.copy(maxHorizontalPartitions = 1) else base
    val navigator = rememberListDetailPaneScaffoldNavigator<String>(scaffoldDirective = directive)
    val scope = rememberCoroutineScope()
    val selected = navigator.currentDestination?.contentKey
    val twoPanes = navigator.scaffoldValue[ListDetailPaneScaffoldRole.List] == PaneAdaptedValue.Expanded &&
        navigator.scaffoldValue[ListDetailPaneScaffoldRole.Detail] == PaneAdaptedValue.Expanded

    LaunchedEffect(openRequest) {
        openRequest?.let { navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, it.waterID) }
    }

    // Back from a water's page: the end of a task, the only moment the app may ask for a review.
    var lastShown by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(selected) {
        val left = lastShown
        if (left != null && selected == null) env.finishedWithWater(left, isBusy())
        lastShown = selected
    }

    NavigableListDetailPaneScaffold(
        navigator = navigator,
        listPane = {
            AnimatedPane {
                list(ListOpen(if (twoPanes) selected else null) { id -> scope.launch { navigator.navigateTo(ListDetailPaneScaffoldRole.Detail, id) } })
            }
        },
        detailPane = {
            AnimatedPane {
                val water = selected?.let { state.snapshot?.water(it) }
                val snapshot = state.snapshot
                if (water != null && snapshot != null) {
                    WaterDetailScreen(
                        env = env,
                        state = state,
                        water = water,
                        sourceWeek = snapshot.sourceWeek,
                        showBack = !twoPanes,
                        onBack = { scope.launch { navigator.navigateBack() } },
                    )
                } else {
                    EmptyState(Icons.Outlined.Info, "No water chosen", placeholder, androidx.compose.ui.Modifier.semantics { contentDescription = "No water chosen. $placeholder" })
                }
            }
        },
    )
}

/** While the snapshot opens off the main thread: brief on a phone, never an empty screen. */
@Composable
private fun LoadingSchedule() {
    Column(
        Modifier.fillMaxSize().padding(32.dp).semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.size(16.dp))
        Text("Loading the stocking schedule…", style = MaterialTheme.typography.bodyMedium, color = secondaryText)
    }
}
