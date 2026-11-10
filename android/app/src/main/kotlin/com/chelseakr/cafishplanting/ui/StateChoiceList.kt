package com.chelseakr.cafishplanting.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.chelseakr.cafishplanting.core.StateOption

/**
 * The states to pick from (DECISIONS 0053), one row each, in the snapshot's
 * order, none chosen until the person picks. A paused state says so in words
 * and with a warning mark, never as current.
 */
@Composable
fun StateChoiceList(options: List<StateOption>, selected: String?, onPick: (String) -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().selectableGroup()) {
        options.forEachIndexed { index, option ->
            if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 56.dp)
                    .selectable(selected = option.code == selected, role = Role.RadioButton, onClick = { onPick(option.code) })
                    .padding(vertical = 8.dp)
                    .semantics(mergeDescendants = true) { contentDescription = "${option.name}. ${option.detail}. ${option.status}" },
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                RadioButton(selected = option.code == selected, onClick = null)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(option.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(option.detail, style = MaterialTheme.typography.bodySmall, color = secondaryText)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        if (option.isPaused) {
                            Icon(Icons.Filled.Warning, contentDescription = null, tint = Color(0xFFFF9500), modifier = Modifier.size(16.dp))
                        }
                        Text(
                            option.status,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (option.isPaused) MaterialTheme.colorScheme.onSurface else secondaryText,
                        )
                    }
                }
            }
        }
    }
}
