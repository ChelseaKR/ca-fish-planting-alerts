package com.chelseakr.cafishplanting.ui

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.core.net.toUri
import android.os.Build
import android.provider.Settings
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.AppState
import com.chelseakr.cafishplanting.core.PlayStoreReviewLink
import com.chelseakr.cafishplanting.core.SnapshotOrigin
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AboutScreen(env: AppEnvironment, state: AppState, onUnlock: () -> Unit, onShowStates: () -> Unit, onShowIntroduction: () -> Unit) {
    val context = LocalContext.current
    val uri = LocalUriHandler.current
    var priming by remember { mutableStateOf(false) }
    val manyStates = (state.snapshot?.states?.size ?: 1) > 1

    Scaffold(topBar = { TopAppBar(title = { Text("About") }) }) { padding ->
        Column(Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()), horizontalAlignment = Alignment.CenterHorizontally) {
            SectionHeader("Full access", ReadableWidth.fillMaxWidth())
            Card(ReadableWidth) {
                if (state.isEntitled("CA")) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        // Green on the seal only: green text on white is below 4.5:1.
                        Icon(Icons.Filled.Verified, null, tint = Color(0xFF34C759))
                        Text("California unlocked", Modifier.padding(start = 12.dp))
                    }
                } else {
                    Para(
                        "Favoriting and browsing are free and unlimited. Full access adds an alert on this device when a favorite is newly on the schedule, " +
                            "and the Favorite waters widget for your home screen.",
                        secondary = true,
                    )
                    ButtonRow("Unlock full access", onUnlock)
                }
                if (manyStates) {
                    Para(
                        "Full access is a one-time purchase for each state. California's is the original purchase, and it stays what it was.",
                        secondary = true,
                        small = true,
                    )
                    ButtonRow("States and full access", onShowStates)
                }
            }

            SectionHeader("What this app does", ReadableWidth.fillMaxWidth())
            Card(ReadableWidth) {
                Para(
                    "Favorite any California water for free and browse its full schedule history. With full access, also get a notification on this device " +
                        "when a favorite appears in the California Department of Fish and Wildlife's weekly stocking schedule, and a home screen widget with your favorites.",
                )
                Para("CDFW publishes the week a plant is scheduled, not the day, and all plants are subject to change. This app always shows a week, never a day, and says \"scheduled\" rather than \"stocked\".")
                if (manyStates) {
                    Para(
                        "Other states come from their own wildlife agencies. Each date is shown as precisely as the agency gives it: a day, a week, or a month. " +
                            "Where an agency reports stockings after they happen instead of scheduling them, the app says so and shows how recent its newest record is.",
                    )
                }
                ButtonRow("Show the introduction", onShowIntroduction)
            }

            SectionHeader("How alerts work", ReadableWidth.fillMaxWidth())
            Card(ReadableWidth) {
                Para(
                    "Alerts are local notifications this app makes on this device for full-access purchasers only. There is no server, no push service, and no account. " +
                        "Android decides when the app may refresh in the background, and the schedule itself is weekly, so an alert arrives within the week a water is added, not the minute it is.",
                )
                Para("To stop one water's alerts and keep it as a favorite, choose Mute this water on its alert, or use the switch on the water's page.")
                Para("The app also checks for a newer schedule when you open it, at most every few hours. If it can't, it says so and keeps showing the last schedule it has, with that schedule's week.")
                val status = when {
                    state.notificationsAllowed -> "on"
                    Build.VERSION.SDK_INT >= 33 -> "off (turn them on to receive alerts)"
                    else -> "off (change in Settings to receive alerts)"
                }
                Para("Notification status: $status", secondary = true, small = true)
                if (!state.notificationsAllowed) {
                    if (Build.VERSION.SDK_INT >= 33 && env.notifications.shouldAsk() && (context as? Activity)?.let { !PermissionMemory.refused(it) } != false) {
                        ButtonRow("Turn on notifications") { priming = true }
                    } else {
                        ButtonRow("Open notification settings") {
                            context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
                        }
                    }
                }
            }

            SectionHeader("Google Play", ReadableWidth.fillMaxWidth())
            Card(ReadableWidth) {
                ButtonRow(PlayStoreReviewLink.ROW_TITLE) {
                    try {
                        context.startActivity(Intent(Intent.ACTION_VIEW, PlayStoreReviewLink.MARKET_URL.toUri()))
                    } catch (_: ActivityNotFoundException) {
                        // No Play Store app on this device: nothing to open.
                    }
                }
                Para(PlayStoreReviewLink.ROW_FOOTNOTE, secondary = true, small = true)
            }

            SectionHeader("Privacy", ReadableWidth.fillMaxWidth())
            Card(ReadableWidth) {
                Para(
                    "Data collected by this app: none. No analytics, no crash reporting, no advertising, no accounts. Favorites and alert history stay on this device. " +
                        "The only network request this app makes is a plain, cookie-free fetch of the published stocking snapshot. Purchases go through Google Play.",
                )
            }

            val snapshot = state.snapshot
            if (snapshot != null) {
                SectionHeader("Data source and license", ReadableWidth.fillMaxWidth())
                Card(ReadableWidth) {
                    Para(snapshot.attribution.text)
                    Para("This app is independent. It is not affiliated with or endorsed by the California Department of Fish and Wildlife.")
                    ButtonRow("CDFW Fish Planting Schedule") { uri.openUri(snapshot.attribution.url) }
                    Para(snapshot.license.summary, secondary = true, small = true)
                    snapshot.license.sources.forEach { source -> ButtonRow(source.name) { uri.openUri(source.termsURL) } }
                }

                snapshot.states.filter { it.code != "CA" }.forEach { other ->
                    SectionHeader("${other.name}: data source and license", ReadableWidth.fillMaxWidth())
                    Card(ReadableWidth) {
                        Para(other.attribution.text)
                        Para(other.disclaimer)
                        ButtonRow(other.sourceName) { uri.openUri(other.attribution.url) }
                        Para(other.license.summary, secondary = true, small = true)
                        other.license.sources.forEach { source -> ButtonRow(source.name) { uri.openUri(source.termsURL) } }
                    }
                }

                SectionHeader("This snapshot", ReadableWidth.fillMaxWidth())
                Card(ReadableWidth) {
                    Labeled("Schedule week", snapshot.sourceWeek.label)
                    val built = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT).withLocale(Locale.US).withZone(ZoneId.systemDefault())
                    Labeled("Built", built.format(snapshot.generatedAt))
                    Labeled("Source", if (state.origin == SnapshotOrigin.BUNDLED) "Bundled with the app" else "Downloaded on this device")
                    state.freshness()?.let { Para(it.detail, secondary = true, small = true) }
                }
            }
            Spacer(Modifier.size(32.dp))
        }
    }
    if (priming) {
        PrimingSheet(context as Activity, env, waterName = null, isEntitled = state.hasAnyAccess, onDone = { priming = false })
    }
}

@Composable
private fun Para(text: String, secondary: Boolean = false, small: Boolean = false) {
    Text(
        text,
        style = if (small) MaterialTheme.typography.bodySmall else MaterialTheme.typography.bodyMedium,
        color = if (secondary) secondaryText else MaterialTheme.colorScheme.onSurface,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

@Composable
private fun ButtonRow(title: String, onClick: () -> Unit) {
    Text(
        title,
        color = MaterialTheme.colorScheme.primary,
        style = MaterialTheme.typography.bodyLarge,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    )
}

@Composable
private fun Labeled(label: String, value: String) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = secondaryText)
        Text(value)
    }
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
}
