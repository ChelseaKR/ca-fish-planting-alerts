package com.chelseakr.cafishplanting.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.NotificationsActive
import androidx.compose.material.icons.outlined.NotificationsOff
import androidx.compose.material.icons.outlined.PhoneAndroid
import androidx.compose.material.icons.outlined.Stars
import androidx.compose.material.icons.outlined.Warning
import androidx.compose.material.icons.outlined.Widgets
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.PurchaseBackend
import com.chelseakr.cafishplanting.PurchaseUi
import com.chelseakr.cafishplanting.core.FreeTier
import com.chelseakr.cafishplanting.core.NotificationAskMemory
import com.chelseakr.cafishplanting.core.NotificationPrimingCopy
import com.chelseakr.cafishplanting.core.StateProducts
import com.chelseakr.cafishplanting.core.StateSemantics
import com.chelseakr.cafishplanting.rememberHaptics
import java.io.File

/**
 * Whether Android will no longer show its notification prompt (asked before
 * on this install, and now refused for good). The flag file is stamped with
 * this install's first-install time, so one copied here by a device transfer
 * (which carries `files/`) is ignored and the prompt is shown. See
 * [NotificationAskMemory].
 */
object PermissionMemory {
    private fun flag(activity: Activity) = File(activity.filesDir, "trout-truck/notification-asked")

    private fun installStamp(activity: Activity): String = try {
        activity.packageManager.getPackageInfo(activity.packageName, 0).firstInstallTime.toString()
    } catch (_: Exception) {
        "unknown"
    }

    fun recordAsked(activity: Activity) {
        // A failed write only means the next tap asks Android again, which is harmless.
        try {
            flag(activity).apply { parentFile?.mkdirs() }.writeText(NotificationAskMemory.flagContents(installStamp(activity)))
        } catch (_: Exception) {
        }
    }

    fun refused(activity: Activity): Boolean {
        val contents = try {
            flag(activity).takeIf { it.exists() }?.readText()
        } catch (_: Exception) {
            null
        }
        return NotificationAskMemory.refused(
            flag = contents,
            installStamp = installStamp(activity),
            hasRuntimePermission = Build.VERSION.SDK_INT >= 33,
            rationaleWanted = { Build.VERSION.SDK_INT >= 33 && activity.shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS) },
        )
    }
}

/**
 * The screen before Android's permission prompt, from a first favorite or
 * from About: what an alert is, how often one comes, and that it is made on
 * this device (`NotificationPrimingCopy`, shared words). It asks nothing
 * until the person taps Allow.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PrimingSheet(
    activity: Activity,
    env: AppEnvironment,
    waterName: String?,
    isEntitled: Boolean,
    onDone: () -> Unit,
    agencyShortName: String = "CDFW",
    semantics: StateSemantics = StateSemantics.SCHEDULE,
) {
    val copy = NotificationPrimingCopy(waterName, isEntitled, agencyShortName, semantics)
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        env.refreshNotificationPermission()
        onDone()
    }
    ModalBottomSheet(onDismissRequest = onDone, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).navigationBarsPadding(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Stay in the loop", style = MaterialTheme.typography.labelLarge, color = secondaryText)
            Icon(Icons.Outlined.NotificationsActive, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(40.dp))
            Text(copy.headline, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.semantics { heading() })
            copy.points.forEach { point ->
                val icon = when (point.icon) {
                    "calendar" -> Icons.Outlined.CalendarMonth
                    "device" -> Icons.Outlined.PhoneAndroid
                    "quiet" -> Icons.Outlined.NotificationsOff
                    else -> Icons.Outlined.Lock
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
                    Text(point.text, style = MaterialTheme.typography.bodyLarge)
                }
            }
            Text(copy.footnote, style = MaterialTheme.typography.bodySmall, color = secondaryText)
            Button(
                onClick = {
                    if (Build.VERSION.SDK_INT >= 33 && !PermissionMemory.refused(activity)) {
                        PermissionMemory.recordAsked(activity)
                        launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        activity.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, activity.packageName))
                        onDone()
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = prominentButtonFill, contentColor = Color.White),
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
            ) { Text("Allow notifications") }
            TextButton(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("Not now") }
        }
    }
}

/**
 * The purchase sheet for one state (DECISIONS 0025). Browsing and
 * favoriting are always free; this opens from About, the States screen, a
 * water's page and the locked widget, never as an upsell on the favorite
 * action. California's is the original full access, in its original words;
 * another state names itself. Google Play's own sheet takes the payment:
 * the app never links to any other way to pay.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PurchaseSheet(activity: Activity, env: AppEnvironment, purchases: PurchaseBackend, stateCode: String, onDismiss: () -> Unit) {
    val state by env.state.collectAsStateWithLifecycle()
    val ui by purchases.ui.collectAsStateWithLifecycle()
    val haptics = rememberHaptics()
    val info = state.snapshot?.state(stateCode)
    val isCalifornia = stateCode == "CA"
    val stateName = info?.name ?: if (isCalifornia) "California" else stateCode
    val unlocked = state.isEntitled(stateCode)
    val product = StateProducts.productID(stateCode)
    val features = if (isCalifornia || info == null) {
        FreeTier.fullAccessFeatures
    } else {
        FreeTier.stateFeatures(info.name, info.agencyShortName, info.semantics)
    }
    var wasUnlocked by remember { mutableStateOf(unlocked) }
    LaunchedEffect(unlocked) {
        // The unlock landing, from a purchase or a restore.
        if (unlocked && !wasUnlocked) haptics.success()
        wasUnlocked = unlocked
    }
    // Opening the sheet with no price is a good moment to ask Play again (it was offline, or busy, the first time).
    LaunchedEffect(Unit) { purchases.retryProducts() }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).navigationBarsPadding(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(if (isCalifornia) "Full access" else stateName, style = MaterialTheme.typography.labelLarge, color = secondaryText)
            Icon(
                if (unlocked) Icons.Filled.Verified else Icons.Outlined.Stars,
                null,
                tint = if (unlocked) Color(0xFF34C759) else MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(48.dp),
            )
            if (unlocked && !isCalifornia) {
                Text("$stateName unlocked", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
                Text(
                    "Thank you. Your $stateName favorites now get alerts, and they show in the Favorite waters widget.",
                    textAlign = TextAlign.Center,
                )
            } else if (unlocked) {
                Text("Full access unlocked", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
                Text(
                    "Thank you. Every favorite now gets an alert when it's newly on the schedule, and the Favorite waters widget is unlocked: add it from your home screen.",
                    textAlign = TextAlign.Center,
                )
            } else {
                val title = if (isCalifornia) "Unlock full access" else "Unlock $stateName"
                Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
                Text(
                    if (isCalifornia) {
                        "Browsing and favoriting are always free. Full access for California adds:"
                    } else {
                        "Browsing, history and favorites in $stateName are always free. $stateName full access adds:"
                    },
                    textAlign = TextAlign.Center,
                )
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    features.zip(listOf<ImageVector>(Icons.Outlined.NotificationsActive, Icons.Outlined.Widgets)).forEach { (text, icon) ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
                            Text(text)
                        }
                    }
                }
                Text(
                    "One payment, forever, for this state. No subscription, no account. Each state is its own purchase.",
                    style = MaterialTheme.typography.bodySmall,
                    color = secondaryText,
                    textAlign = TextAlign.Center,
                )
                val price = product?.let { ui.prices[it] }
                Button(
                    onClick = { product?.let { purchases.purchase(activity, it) } },
                    enabled = price != null && ui.busy == PurchaseUi.Busy.IDLE,
                    colors = ButtonDefaults.buttonColors(containerColor = prominentButtonFill, contentColor = Color.White),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).semantics { contentDescription = title + (price?.let { ", $it" } ?: "") },
                ) {
                    if (ui.busy == PurchaseUi.Busy.PURCHASING) CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                    Text(
                        when {
                            price != null -> "$title — $price"
                            ui.productLoadError == null -> "Loading price…"
                            else -> "Not available right now"
                        },
                        modifier = Modifier.padding(start = 8.dp),
                    )
                }
                if (price == null && ui.productLoadError != null) {
                    TextButton(onClick = purchases::retryProducts, modifier = Modifier.fillMaxWidth()) { Text("Try again") }
                }
                TextButton(onClick = purchases::restore, enabled = ui.busy == PurchaseUi.Busy.IDLE) {
                    if (ui.busy == PurchaseUi.Busy.RESTORING) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    Text("Restore purchases", modifier = Modifier.padding(start = 6.dp))
                }
                if (ui.pending) {
                    Text(
                        "Your payment is pending with Google Play. $stateName unlocks as soon as it completes.",
                        style = MaterialTheme.typography.bodySmall,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                    )
                }
                ui.message?.let { message ->
                    Row(Modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        // Red on the symbol only: red text on white is below 4.5:1 at this size.
                        Icon(Icons.Outlined.Warning, "Purchase error", tint = Color(0xFFD70015))
                        Text(message, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            TextButton(onClick = onDismiss) { Text(if (unlocked) "Done" else "Not now") }
        }
    }
}
