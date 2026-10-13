package com.chelseakr.cafishplanting.ui

import com.chelseakr.cafishplanting.core.StateSemantics
import com.chelseakr.cafishplanting.core.StateInfo
import android.text.format.DateUtils
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.outlined.NotificationsOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.chelseakr.cafishplanting.core.SnapshotFreshness
import com.chelseakr.cafishplanting.core.Water
import java.time.Instant

/** Font scale at which rows stack and two panes become one, like the iOS accessibility text sizes. */
const val LARGE_TEXT_SCALE = 1.5f

@Composable
fun isLargeText(): Boolean = LocalDensity.current.fontScale >= LARGE_TEXT_SCALE

/** Keeps rows to a readable width on a wide screen instead of edge to edge. */
val ReadableWidth = Modifier.widthIn(max = 720.dp)

@Composable
fun SectionHeader(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = secondaryText,
        modifier = modifier
            .padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 6.dp)
            .semantics { heading() },
    )
}

/** A rounded group of rows, like an iOS inset grouped list section. */
@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceContainer,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier.padding(horizontal = 16.dp).fillMaxWidth(),
    ) {
        Column(Modifier.padding(vertical = 4.dp)) { content() }
    }
}

/**
 * The offline-first promise made visible: which week's schedule this is,
 * whether that week is over, and how the last check went. A failed or stale
 * check is said plainly and the last good schedule stays, labeled with its week.
 */
@Composable
fun FreshnessRow(freshness: SnapshotFreshness, now: Instant = Instant.now()) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .semantics(mergeDescendants = true) {},
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Text(freshness.headline, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
        Text(freshness.summary, style = MaterialTheme.typography.bodySmall)
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (freshness.isChecking) {
                CircularProgressIndicator(Modifier.size(14.dp).padding(top = 2.dp), strokeWidth = 2.dp)
            } else if (freshness.needsAttention) {
                Icon(Icons.Filled.Warning, contentDescription = null, tint = Color(0xFFFF9500), modifier = Modifier.size(16.dp))
            }
            Text(
                freshness.detail,
                style = MaterialTheme.typography.bodySmall,
                color = if (freshness.needsAttention) MaterialTheme.colorScheme.onSurface else secondaryText,
            )
        }
        freshness.lastSuccessfulCheck?.let { checked ->
            val label = if (freshness.checkFailed) "Last successful check" else "Last checked"
            val relative = DateUtils.getRelativeTimeSpanString(checked.toEpochMilli(), now.toEpochMilli(), DateUtils.MINUTE_IN_MILLIS)
            Text("$label $relative", style = MaterialTheme.typography.bodySmall, color = secondaryText)
        }
    }
}

/**
 * Another state's freshness, as `StateFreshnessRow` in the iOS app: what the
 * agency publishes, its newest date, Michigan's lag note, and when its data
 * was last read, saying so when the newest check failed.
 */
@Composable
fun StateFreshnessRow(state: StateInfo, now: Instant = Instant.now()) {
    val read = DateUtils.getRelativeTimeSpanString(state.lastSuccessAt.toEpochMilli(), now.toEpochMilli(), DateUtils.MINUTE_IN_MILLIS)
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .semantics(mergeDescendants = true) {},
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        val kind = if (state.semantics == StateSemantics.SCHEDULE) "stocking schedule" else "stocking report"
        Text("${state.agencyShortName} $kind", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
        state.newestRecord?.let { Text("Newest date in it: ${it.label}", style = MaterialTheme.typography.bodySmall) }
        state.recencyNote?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (!state.lastAttemptOK) {
                Icon(Icons.Filled.Warning, contentDescription = null, tint = Color(0xFFFF9500), modifier = Modifier.size(16.dp))
            }
            Text(
                if (state.lastAttemptOK) "Read $read" else "The newest check failed. Showing the data read $read.",
                style = MaterialTheme.typography.bodySmall,
                color = if (state.lastAttemptOK) secondaryText else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

/** "This week", or the week once it has ended: primary text on a tinted capsule. */
@Composable
fun ListedBadge(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.SemiBold,
        color = MaterialTheme.colorScheme.onPrimaryContainer,
        modifier = Modifier
            .background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 4.dp),
    )
}

@Composable
fun WaterRow(
    water: Water,
    listed: SnapshotFreshness?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
    alertsMuted: Boolean = false,
    actions: List<CustomAccessibilityAction> = emptyList(),
) {
    val large = isLargeText()
    val description = buildList {
        add(water.name)
        add(water.countyLabel)
        listed?.let { add(it.listedPhrase) }
        if (alertsMuted) add("alerts muted")
    }.joinToString(", ")
    val content: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(water.name, style = MaterialTheme.typography.bodyLarge)
                if (alertsMuted) Icon(Icons.Outlined.NotificationsOff, null, tint = secondaryText, modifier = Modifier.size(16.dp))
            }
            Text(water.countyLabel, style = MaterialTheme.typography.bodySmall, color = secondaryText)
        }
    }
    Box(
        modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .background(if (selected) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent)
            .clickable(role = Role.Button, onClickLabel = "Open", onClick = onClick)
            .semantics(mergeDescendants = true) {
                contentDescription = description
                if (actions.isNotEmpty()) customActions = actions
            }
            .padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.CenterStart,
    ) {
        // At large text the tag goes under the name, so neither is squeezed or cut off.
        if (large) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                content()
                listed?.let { ListedBadge(it.listedBadge) }
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Row(Modifier.weight(1f)) { content() }
                Spacer(Modifier.size(8.dp))
                listed?.let { ListedBadge(it.listedBadge) }
            }
        }
    }
}

/** An empty or unavailable state, said plainly. */
@Composable
fun EmptyState(icon: ImageVector, title: String, message: String, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(icon, contentDescription = null, tint = secondaryText, modifier = Modifier.size(48.dp))
        Spacer(Modifier.size(12.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
        Spacer(Modifier.size(6.dp))
        Text(message, style = MaterialTheme.typography.bodyMedium, color = secondaryText, textAlign = TextAlign.Center)
    }
}
