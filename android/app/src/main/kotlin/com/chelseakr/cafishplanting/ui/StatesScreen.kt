package com.chelseakr.cafishplanting.ui

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
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.chelseakr.cafishplanting.AppEnvironment
import com.chelseakr.cafishplanting.PurchaseBackend
import com.chelseakr.cafishplanting.PurchaseUi
import com.chelseakr.cafishplanting.core.StateInfo
import com.chelseakr.cafishplanting.core.StateProducts

/**
 * The States screen (DECISIONS 0025), the twin of `StatesView.swift`: every
 * state in the snapshot, what its agency publishes, and whether this device
 * has its full access. Browsing and history are free everywhere; each
 * state's alerts and widget are a one-time purchase. California's is the
 * original full access, so anyone who bought it before states sees
 * California as unlocked here.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StatesSheet(env: AppEnvironment, purchases: PurchaseBackend, onBuy: (String) -> Unit, onDismiss: () -> Unit) {
    val state by env.state.collectAsStateWithLifecycle()
    val ui by purchases.ui.collectAsStateWithLifecycle()
    val states = state.snapshot?.states.orEmpty()
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 24.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("States", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.semantics { heading() })
            Text(
                "Browsing, every water's history and favorites are free in every state. " +
                    "Alerts and the widget are a one-time purchase for each state.",
                style = MaterialTheme.typography.bodySmall,
                color = secondaryText,
            )
            states.forEach { info ->
                StateCard(
                    info,
                    unlocked = state.isEntitled(info.code),
                    price = StateProducts.productID(info.code)?.let { ui.prices[it] },
                    onBrowse = {
                        env.setBrowseState(info.code)
                        onDismiss()
                    },
                    onBuy = { onBuy(info.code) },
                )
            }
            TextButton(onClick = purchases::restore, enabled = ui.busy == PurchaseUi.Busy.IDLE) { Text("Restore purchases") }
            TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) { Text("Done") }
        }
    }
}

@Composable
private fun StateCard(info: StateInfo, unlocked: Boolean, price: String?, onBrowse: () -> Unit, onBuy: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Column(Modifier.semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(info.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    if (unlocked) {
                        Icon(Icons.Filled.Verified, contentDescription = null, tint = Color(0xFF34C759), modifier = Modifier.size(18.dp))
                        Text("Unlocked", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                    }
                }
                Text(
                    "${info.agencyName}: ${info.kindLabel.lowercase()}, ${info.watersCount} waters",
                    style = MaterialTheme.typography.bodySmall,
                    color = secondaryText,
                )
                if (info.code == "CA") {
                    Text("California full access is the original one-time purchase.", style = MaterialTheme.typography.bodySmall, color = secondaryText)
                }
            }
            OutlinedButton(onClick = onBrowse, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text("Browse ${info.name}") }
            if (!unlocked) {
                OutlinedButton(onClick = onBuy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Text(if (price != null) "Unlock alerts and widget — $price" else "Unlock alerts and widget")
                }
            }
        }
    }
}
