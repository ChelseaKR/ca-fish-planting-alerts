package com.chelseakr.cafishplanting.ui

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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.AppState
import com.chelseakr.cafishplanting.Haptics
import com.chelseakr.cafishplanting.core.RefreshOutcome
import com.chelseakr.cafishplanting.core.WaterSearch
import com.chelseakr.cafishplanting.rememberHaptics
import kotlinx.coroutines.launch

/** Swipe down, or the toolbar's Refresh, to check now past the throttle. A success tap, or a warning when it failed. */
suspend fun refreshWithFeedback(env: AppEnvironment, haptics: Haptics) {
    if (env.refreshNow() is RefreshOutcome.Failed) haptics.warning() else haptics.success()
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RefreshAction(env: AppEnvironment, state: AppState) {
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    IconButton(onClick = { scope.launch { refreshWithFeedback(env, haptics) } }, enabled = !state.isRefreshing) {
        Icon(Icons.Filled.Refresh, contentDescription = "Check for a newer schedule")
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BrowseList(env: AppEnvironment, state: AppState, selected: String?, onOpen: (String) -> Unit, onShowStates: () -> Unit) {
    val snapshot = state.snapshot
    var text by rememberSaveable { mutableStateOf("") }
    var region by rememberSaveable { mutableStateOf<String?>(null) }
    var county by rememberSaveable { mutableStateOf<String?>(null) }
    val code = state.browseState
    // A new state starts with no region or county chosen; a rotation keeps them.
    var filtersFor by rememberSaveable { mutableStateOf(code) }
    if (filtersFor != code) {
        filtersFor = code
        region = null
        county = null
    }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val manyStates = (snapshot?.states?.size ?: 1) > 1

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Waters") },
                actions = {
                    if (manyStates) {
                        IconButton(onClick = onShowStates) { Icon(Icons.Outlined.Map, contentDescription = "States and full access") }
                    }
                    RefreshAction(env, state)
                },
            )
        },
    ) { padding ->
        if (snapshot == null) {
            EmptyState(Icons.Filled.Search, "Can't load the stocking schedule", "No stocking schedule is available yet.", Modifier.padding(padding))
            return@Scaffold
        }
        val thisWeek = snapshot.thisWeekWaterIDs
        val stateInfo = snapshot.state(code)
        val stateWaters = snapshot.watersInState(code)
        val regions = snapshot.regionsWithWaters(code)
        val regionWaters = region?.let { r -> stateWaters.filter { it.region == r } } ?: stateWaters
        val waters = WaterSearch(text, county).filter(regionWaters)
        val freshness = state.freshness()
        PullToRefreshBox(
            isRefreshing = state.isRefreshing,
            onRefresh = { scope.launch { refreshWithFeedback(env, haptics) } },
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            LazyColumn(Modifier.fillMaxSize()) {
                item {
                    Column(Modifier.padding(horizontal = 16.dp).then(ReadableWidth)) {
                        OutlinedTextField(
                            value = text,
                            onValueChange = { text = it },
                            label = { Text("Water or county") },
                            leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
                            trailingIcon = {
                                if (text.isNotEmpty()) {
                                    IconButton(onClick = { text = "" }) { Icon(Icons.Filled.Clear, contentDescription = "Clear search") }
                                }
                            },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        if (manyStates) {
                            Spacer(Modifier.height(8.dp))
                            StatePicker(snapshot.states.map { it.code to it.name }, code, onSelect = env::setBrowseState)
                        }
                        if (regions.isNotEmpty()) {
                            Spacer(Modifier.height(8.dp))
                            Picker(
                                label = "Region",
                                allLabel = "All regions",
                                options = regions.map { it.code to it.name },
                                selected = region,
                                onSelect = { region = it; county = null },
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        // Only the counties (Massachusetts: towns) with a water in the chosen region.
                        Picker(
                            label = if (code == "MA") "Town" else "County",
                            allLabel = if (code == "MA") "All towns" else "All counties",
                            options = WaterSearch.counties(regionWaters).map { it to it },
                            selected = county,
                            onSelect = { county = it },
                        )
                    }
                }
                if (code == "CA" && freshness != null) {
                    item {
                        Spacer(Modifier.height(12.dp))
                        Card(ReadableWidth) { FreshnessRow(freshness) }
                        Spacer(Modifier.height(12.dp))
                    }
                } else if (code != "CA" && stateInfo != null) {
                    item {
                        Spacer(Modifier.height(12.dp))
                        Card(ReadableWidth) { StateFreshnessRow(stateInfo) }
                        Spacer(Modifier.height(12.dp))
                    }
                }
                if (waters.isEmpty()) {
                    item {
                        Box(Modifier.fillMaxWidth().height(240.dp)) {
                            EmptyState(Icons.Filled.Search, "No results", if (text.isBlank()) "No waters match these filters." else "No waters match “$text”.")
                        }
                    }
                }
                items(waters, key = { it.id }) { water ->
                    Column(ReadableWidth) {
                        // The "This week" tag reads California's week; another state's
                        // rows show their dates on the water's page instead.
                        WaterRow(
                            water,
                            if (water.state == "CA" && water.id in thisWeek) freshness else null,
                            onClick = { onOpen(water.id) },
                            selected = water.id == selected,
                        )
                        HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
                    }
                }
            }
        }
    }
}

/** Which state Browse shows: a labeled menu with no "All" choice, the twin of the iOS state picker. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StatePicker(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val current = options.firstOrNull { it.first == selected }?.second ?: selected
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = current,
            onValueChange = {},
            readOnly = true,
            label = { Text("State") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            singleLine = true,
            modifier = Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (value, name) ->
                DropdownMenuItem(text = { Text(name) }, onClick = { onSelect(value); expanded = false })
            }
        }
    }
}

/** A labeled menu of options with an "All" choice, the twin of the iOS menu pickers. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Picker(label: String, allLabel: String, options: List<Pair<String, String>>, selected: String?, onSelect: (String?) -> Unit) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val current = options.firstOrNull { it.first == selected }?.second ?: allLabel
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = current,
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            singleLine = true,
            modifier = Modifier.menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable).fillMaxWidth(),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(text = { Text(allLabel) }, onClick = { onSelect(null); expanded = false })
            options.forEach { (value, name) ->
                DropdownMenuItem(text = { Row { Text(name) } }, onClick = { onSelect(value); expanded = false })
            }
        }
    }
}
