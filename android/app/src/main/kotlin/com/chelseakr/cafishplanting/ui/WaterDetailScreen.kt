package com.chelseakr.cafishplanting.ui

import java.util.Locale
import java.text.NumberFormat
import com.chelseakr.cafishplanting.core.StateSemantics
import com.chelseakr.cafishplanting.core.DatePrecision
import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.NotificationsOff
import androidx.compose.material.icons.outlined.StarOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.selection.toggleable
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.AppState
import com.chelseakr.cafishplanting.core.Plant
import com.chelseakr.cafishplanting.core.PlantStatus
import com.chelseakr.cafishplanting.core.ScheduleWording
import com.chelseakr.cafishplanting.core.ShareContent
import com.chelseakr.cafishplanting.core.SnapshotEndpoint
import com.chelseakr.cafishplanting.core.Water
import com.chelseakr.cafishplanting.core.Week
import com.chelseakr.cafishplanting.rememberHaptics

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WaterDetailScreen(
    env: AppEnvironment,
    state: AppState,
    water: Water,
    sourceWeek: Week,
    showBack: Boolean,
    onBack: () -> Unit,
    onUnlock: (String) -> Unit = {},
) {
    val context = LocalContext.current
    val uri = LocalUriHandler.current
    val haptics = rememberHaptics()
    val isFavorite = state.favorites.contains(water.id)
    val muted = state.muted.contains(water.id)
    // A favorite once alerts can come (full access), and a muted one whatever the purchase, so a mute can always be undone.
    val unlocked = state.isEntitled(water.state)
    val stateInfo = state.snapshot?.stateOf(water)
    val showsAlertsSwitch = isFavorite && (unlocked || muted)
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    // Opened, from an alert or anywhere else: its delivered alerts have been read.
    LaunchedEffect(water.id) { env.notifications.clearDelivered(water.id) }

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        topBar = {
            LargeTopAppBar(
                title = { Text(water.name, maxLines = 2, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    if (showBack) IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
                },
                actions = {
                    IconButton(onClick = {
                        // A firmer tap for adding a favorite than for removing one.
                        if (isFavorite) haptics.selection() else haptics.success()
                        env.toggleFavorite(water)
                    }) {
                        Icon(
                            if (isFavorite) Icons.Filled.Star else Icons.Outlined.StarOutline,
                            contentDescription = if (isFavorite) "Remove ${water.name} from favorites" else "Add ${water.name} to favorites",
                            tint = if (isFavorite) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                        )
                    }
                    IconButton(onClick = {
                        val text = ShareContent.message(water, SnapshotEndpoint.siteWaterURL(water), sourceWeek)
                        val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_SUBJECT, water.name).putExtra(Intent.EXTRA_TEXT, text)
                        context.startActivity(Intent.createChooser(send, null))
                    }) { Icon(Icons.Filled.Share, "Share ${water.name}") }
                },
                scrollBehavior = scroll,
            )
        },
    ) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize()) {
            item {
                Card(ReadableWidth) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(water.countyLabel, style = MaterialTheme.typography.bodyMedium, color = secondaryText)
                        Text(
                            ScheduleWording.lastScheduledLine(water, sourceWeek),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = if (water.lastListedWeek == null) secondaryText else MaterialTheme.colorScheme.onSurface,
                        )
                        if (water.speciesSeen.isNotEmpty()) {
                            Text("Species seen: ${water.speciesSeen.joinToString(", ")}", style = MaterialTheme.typography.bodyMedium)
                        }
                        water.monthsNote?.let { note ->
                            Text(
                                "${water.agencyShortName} also lists this water by month: $note. It writes each month as one letter, " +
                                    "so \"M\" may be March or May, and says the dates vary through those months.",
                                style = MaterialTheme.typography.bodySmall,
                                color = secondaryText,
                            )
                        }
                        stateInfo?.recencyNote?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = secondaryText) }
                    }
                }
            }
            if (isFavorite && !unlocked && !muted && stateInfo != null) {
                item {
                    Spacer(Modifier.size(12.dp))
                    Card(ReadableWidth) {
                        LinkRow("Unlock alerts for ${stateInfo.name}", external = false) { onUnlock(water.state) }
                    }
                    Text(
                        "Alerts and the widget for ${stateInfo.name} waters are a one-time purchase. Browsing and history stay free.",
                        style = MaterialTheme.typography.bodySmall,
                        color = secondaryText,
                        modifier = Modifier.padding(horizontal = 32.dp, vertical = 6.dp).then(ReadableWidth),
                    )
                }
            }
            if (showsAlertsSwitch) {
                item {
                    SectionHeader("Alerts", ReadableWidth)
                    Card(ReadableWidth) {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .heightIn(min = 56.dp)
                                .toggleable(value = !muted, role = Role.Switch) {
                                    env.setMutedAsync(!it, water.id)
                                    haptics.selection()
                                }
                                .padding(horizontal = 16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(if (muted) Icons.Outlined.NotificationsOff else Icons.Outlined.Notifications, null, tint = MaterialTheme.colorScheme.primary)
                            Text("Alerts for this water", Modifier.weight(1f).padding(horizontal = 12.dp))
                            Switch(checked = !muted, onCheckedChange = null)
                        }
                    }
                    Text(
                        if (muted) {
                            "Muted. ${water.name} stays in Favorites and the widget, with no alert when it is newly on the schedule."
                        } else if (water.state == "CA") {
                            "An alert on this device when ${water.name} is newly on CDFW's weekly schedule."
                        } else if (water.semantics == StateSemantics.PLAN) {
                            "An alert on this device when ${water.name} is in ${water.agencyShortName}'s spring plan, and a reminder when each planned period begins."
                        } else if (water.semantics == StateSemantics.REPORT) {
                            "An alert on this device when ${water.name} is new in ${water.agencyShortName}'s stocking report."
                        } else {
                            "An alert on this device when ${water.name} is newly on ${water.agencyShortName}'s schedule."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = secondaryText,
                        modifier = Modifier.padding(horizontal = 32.dp, vertical = 6.dp).then(ReadableWidth),
                    )
                }
            }
            item {
                SectionHeader("Links", ReadableWidth)
                Card(ReadableWidth) {
                    LinkRow(if (water.state == "CA") "CDFW schedule for this water" else "${water.agencyShortName} source for this water") {
                        uri.openUri(water.cdfwMapURL)
                    }
                    SnapshotEndpoint.siteWaterURL(water)?.let { site ->
                        HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
                        LinkRow("Full history on the site") { uri.openUri(site) }
                    }
                }
            }
            item {
                SectionHeader(
                    when (water.semantics) {
                        StateSemantics.REPORT -> "Stocking history"
                        StateSemantics.PLAN -> "Stocking plans"
                        StateSemantics.SCHEDULE -> "Schedule history"
                    },
                    ReadableWidth,
                )
                Card(ReadableWidth) {
                    if (water.plants.isEmpty()) {
                        Text("No plants observed yet for this water.", color = secondaryText, modifier = Modifier.padding(16.dp))
                    }
                    water.years.forEachIndexed { index, year ->
                        if (index > 0) HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
                        YearGroup(year, water.plantsInYear(year).asReversed())
                    }
                }
                Spacer(Modifier.size(24.dp))
            }
            if (water.state != "CA" && stateInfo != null) {
                item {
                    SectionHeader("Source", ReadableWidth)
                    Card(ReadableWidth) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(stateInfo.attribution.text, style = MaterialTheme.typography.bodyMedium)
                            Text(stateInfo.disclaimer, style = MaterialTheme.typography.bodySmall, color = secondaryText)
                        }
                    }
                    Spacer(Modifier.size(24.dp))
                }
            }
        }
    }
}

/** Links open in the browser (an Intent), never an in-app web view, so the site's analytics stay the site's. */
@Composable
private fun LinkRow(title: String, external: Boolean = true, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.Button, onClick = onClick).padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f))
        if (external) {
            Icon(Icons.AutoMirrored.Filled.OpenInNew, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun YearGroup(year: Int, plants: List<Plant>) {
    var expanded by rememberSaveable(year) { mutableStateOf(false) }
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .clickable(role = Role.Button, onClickLabel = if (expanded) "Collapse" else "Expand") { expanded = !expanded }
            .semantics { stateDescription = if (expanded) "Expanded" else "Collapsed" }
            .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(year.toString(), Modifier.weight(1f))
        Icon(if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, contentDescription = null)
    }
    if (expanded) plants.forEach { PlantRow(it) }
}

@Composable
private fun PlantRow(plant: Plant) {
    val removed = plant.status == PlantStatus.REMOVED
    // The pipeline's own label, verbatim: a week is never shown as a day, and a month says its day isn't set.
    val period = when (plant.week.precision) {
        DatePrecision.MONTH -> "${plant.week.label}, day not set"
        // The agency's own words, said as a plan and never as a date.
        DatePrecision.APPROXIMATE -> "Planned for ${plant.week.label}"
        else -> plant.week.label
    }
    val what = plant.count?.let { "${plant.species}, ${NumberFormat.getIntegerInstance(Locale.US).format(it)} fish" } ?: plant.species
    Row(
        Modifier
            .fillMaxWidth()
            .padding(start = 32.dp, end = 16.dp, top = 6.dp, bottom = 6.dp)
            .semantics(mergeDescendants = true) {
                contentDescription = if (removed) "$period, $what, later removed from the schedule" else "$period, $what"
            },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(period)
            Text(what, style = MaterialTheme.typography.bodySmall, color = secondaryText)
        }
        if (removed) {
            Icon(Icons.Outlined.History, null, tint = secondaryText, modifier = Modifier.size(16.dp))
            Text("Schedule changed", style = MaterialTheme.typography.labelSmall, color = secondaryText, modifier = Modifier.padding(start = 4.dp))
        }
    }
}
