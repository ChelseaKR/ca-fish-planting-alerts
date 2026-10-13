package com.chelseakr.cafishplanting.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.NotificationsOff
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.AppState
import com.chelseakr.cafishplanting.core.Water
import com.chelseakr.cafishplanting.core.WaterSearch
import com.chelseakr.cafishplanting.rememberHaptics
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FavoritesList(env: AppEnvironment, state: AppState, selected: String?, onOpen: (String) -> Unit, onBrowse: () -> Unit) {
    val snapshot = state.snapshot
    var text by rememberSaveable { mutableStateOf("") }
    var county by rememberSaveable { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()

    Scaffold(topBar = { TopAppBar(title = { Text("Favorites") }, actions = { RefreshAction(env, state) }) }) { padding ->
        if (snapshot == null) {
            EmptyState(Icons.Outlined.StarOutline, "Can't load the stocking schedule", "No stocking schedule is available yet.", Modifier.padding(padding))
            return@Scaffold
        }
        val ids = state.favorites.ids
        val present = ids.mapNotNull(snapshot::water)
        // Favorites the snapshot no longer has. Said plainly, never folded into "no favorites".
        val missing = ids.filter { snapshot.water(it) == null }
        if (present.isEmpty() && missing.isEmpty()) {
            val alerts = if (state.hasAnyAccess) {
                "You'll get an alert when one in a state you unlocked is newly on the schedule."
            } else {
                "With full access for a state, you also get an alert when one there is newly on the schedule, and a widget with your favorites."
            }
            Column(Modifier.padding(padding).fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                Box(Modifier.weight(1f, fill = false)) {
                    EmptyState(Icons.Outlined.StarOutline, "No favorite waters yet", "Tap the star on any water in Browse to keep its schedule here. $alerts")
                }
                TextButton(onClick = onBrowse) { Text("Browse waters") }
                Spacer(Modifier.height(24.dp))
            }
            return@Scaffold
        }
        val thisWeek = snapshot.thisWeekWaterIDs
        val freshness = state.freshness()
        val counties = WaterSearch.counties(present)
        // A county chosen earlier that no favorite is in any more.
        val search = WaterSearch(text, county?.takeIf { it in counties })
        val shown = search.filter(present)
        PullToRefreshBox(
            isRefreshing = state.isRefreshing,
            onRefresh = { scope.launch { refreshWithFeedback(env, haptics) } },
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            LazyColumn(Modifier.fillMaxSize()) {
                if (freshness != null) {
                    item {
                        Spacer(Modifier.height(8.dp))
                        Card(ReadableWidth) { FreshnessRow(freshness) }
                        Spacer(Modifier.height(8.dp))
                    }
                }
                item {
                    Column(Modifier.padding(horizontal = 16.dp).then(ReadableWidth)) {
                        OutlinedTextField(
                            value = text,
                            onValueChange = { text = it },
                            label = { Text("Favorite water or county") },
                            leadingIcon = { Icon(Icons.Filled.Search, null) },
                            trailingIcon = { if (text.isNotEmpty()) IconButton(onClick = { text = "" }) { Icon(Icons.Filled.Clear, "Clear search") } },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        if (counties.size > 1) {
                            Spacer(Modifier.height(8.dp))
                            Picker("Filter by county", "All counties", counties.map { it to it }, search.county) { county = it }
                        }
                        if (!search.isEmpty) {
                            Text(
                                if (shown.size == 1) "1 of ${present.size} favorites" else "${shown.size} of ${present.size} favorites",
                                style = MaterialTheme.typography.bodySmall,
                                color = secondaryText,
                                modifier = Modifier.padding(top = 8.dp),
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                    }
                }
                if (shown.isEmpty()) {
                    item {
                        Box(Modifier.fillMaxWidth().height(220.dp)) {
                            val c = search.county
                            if (text.isBlank() && c != null) {
                                EmptyState(Icons.Filled.Search, "No favorites in $c", "Choose All counties to see every favorite.")
                            } else {
                                EmptyState(Icons.Filled.Search, "No results", "No favorites match “$text”.")
                            }
                        }
                    }
                }
                items(shown, key = { it.id }) { water ->
                    FavoriteRow(env, state, water, if (water.state == "CA" && water.id in thisWeek) freshness else null, water.id == selected) { onOpen(water.id) }
                }
                if (missing.isNotEmpty() && search.isEmpty) {
                    item { SectionHeader("Not in this schedule") }
                    items(missing, key = { "missing-$it" }) { id -> MissingFavoriteRow(id) { env.removeFavorite(id) } }
                    item {
                        Text(
                            "This schedule no longer lists these favorites. CDFW may have renamed or dropped the water. Use Remove to take one off.",
                            style = MaterialTheme.typography.bodySmall,
                            color = secondaryText,
                            modifier = Modifier.padding(16.dp),
                        )
                    }
                }
            }
        }
    }
}

/**
 * Swipe from the start to mute or unmute (with full access, or when muted, so
 * a mute can always be undone), from the end to remove. TalkBack offers the
 * same as actions on the row.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FavoriteRow(env: AppEnvironment, state: AppState, water: Water, listed: com.chelseakr.cafishplanting.core.SnapshotFreshness?, selected: Boolean, onOpen: () -> Unit) {
    val muted = state.muted.contains(water.id)
    val canMute = state.isEntitled(water.state) || muted
    val haptics = rememberHaptics()
    val toggleMute = {
        env.setMutedAsync(!muted, water.id)
        haptics.selection()
    }
    val remove = {
        env.toggleFavorite(water)
        haptics.selection()
    }
    val dismiss = rememberSwipeToDismissBoxState()
    val rowScope = rememberCoroutineScope()
    val actions = buildList {
        if (canMute) add(CustomAccessibilityAction(if (muted) "Unmute alerts" else "Mute alerts") { toggleMute(); true })
        add(CustomAccessibilityAction("Remove from favorites") { remove(); true })
    }
    SwipeToDismissBox(
        state = dismiss,
        enableDismissFromStartToEnd = canMute,
        modifier = ReadableWidth,
        onDismiss = { value ->
            when (value) {
                SwipeToDismissBoxValue.EndToStart -> remove()
                SwipeToDismissBoxValue.StartToEnd -> if (canMute) toggleMute()
                SwipeToDismissBoxValue.Settled -> Unit
            }
            // Muting keeps the row, and a removed row leaves the list on its own.
            rowScope.launch { dismiss.snapTo(SwipeToDismissBoxValue.Settled) }
        },
        backgroundContent = {
            val toEnd = dismiss.dismissDirection == SwipeToDismissBoxValue.StartToEnd
            Row(
                Modifier.fillMaxSize().background(if (toEnd) Color(0xFF3F3AA8) else Color(0xFFB3261E)).padding(horizontal = 20.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = if (toEnd) Arrangement.Start else Arrangement.End,
            ) {
                val label = if (toEnd) (if (muted) "Unmute" else "Mute") else "Remove"
                if (toEnd) Icon(if (muted) Icons.Outlined.Notifications else Icons.Outlined.NotificationsOff, null, tint = Color.White)
                Text(label, color = Color.White, modifier = Modifier.padding(horizontal = 8.dp))
            }
        },
    ) {
        Column(Modifier.background(MaterialTheme.colorScheme.background)) {
            WaterRow(water, listed, onOpen, selected = selected, alertsMuted = muted, actions = actions)
            HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
        }
    }
}

/** A favorite the snapshot doesn't have: CDFW's own number, never a guessed name. */
@Composable
private fun MissingFavoriteRow(id: String, onRemove: () -> Unit) {
    val title = if (id.startsWith("cdfw-")) "CDFW water ${id.removePrefix("cdfw-")}" else "A favorite water ($id)"
    Row(Modifier.fillMaxWidth().then(ReadableWidth).padding(start = 16.dp, end = 8.dp, top = 6.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f).semantics(mergeDescendants = true) {}) {
            Text(title)
            Text("No longer in the schedule data", style = MaterialTheme.typography.bodySmall, color = secondaryText)
        }
        TextButton(onClick = onRemove) { Text("Remove") }
    }
}
