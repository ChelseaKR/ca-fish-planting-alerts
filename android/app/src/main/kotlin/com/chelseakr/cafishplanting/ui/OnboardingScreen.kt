package com.chelseakr.cafishplanting.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.EventAvailable
import androidx.compose.material.icons.filled.LocalShipping
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.chelseakr.cafishplanting.core.OnboardingCopy
import com.chelseakr.cafishplanting.BuildConfig
import com.chelseakr.cafishplanting.core.FreeLaunch
import com.chelseakr.cafishplanting.core.StateChoice
import com.chelseakr.cafishplanting.core.StateOption
import com.chelseakr.cafishplanting.rememberHaptics
import kotlinx.coroutines.launch

/**
 * The introduction: four pages on a first launch, swiped or stepped through
 * with Continue, skippable. The words are `OnboardingCopy` (shared rules with
 * the iOS app). It asks for nothing; the notification prompt stays behind
 * the first favorite's own explanation. The "Find your waters" page asks
 * which state, from the snapshot's own list, with nothing chosen for the
 * person (DECISIONS 0053); a pick is saved as it is made, and skipping
 * leaves no state chosen, so Browse opens on the list of states.
 */
@Composable
fun OnboardingScreen(states: List<StateOption>, selectedState: String?, onPickState: (String) -> Unit, onFinish: () -> Unit) {
    val pages = if (BuildConfig.FREE_TIER) FreeLaunch.onboardingPages else OnboardingCopy.pages
    val pager = rememberPagerState { pages.size }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val isLast = pager.currentPage == pages.size - 1
    LaunchedEffect(pager.currentPage) { if (pager.currentPage > 0) haptics.selection() }
    BackHandler { if (pager.currentPage > 0) scope.launch { pager.animateScrollToPage(pager.currentPage - 1) } else onFinish() }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.surfaceContainer) {
        Column(Modifier.safeDrawingPadding(), horizontalAlignment = Alignment.CenterHorizontally) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), horizontalArrangement = Arrangement.End) {
                // Not on the last page, where the main button already ends it.
                TextButton(onClick = onFinish, enabled = !isLast, modifier = Modifier.alpha(if (isLast) 0f else 1f)) { Text("Skip") }
            }
            HorizontalPager(pager, Modifier.weight(1f)) { index ->
                Page(pages[index], index + 1, pages.size) {
                    if (pages[index].id == StateChoice.PICKER_PAGE_ID && states.isNotEmpty()) {
                        StatePickerCard(states, selectedState, onPickState)
                    }
                }
            }
            Row(Modifier.padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                pages.indices.forEach { i ->
                    Box(
                        Modifier.size(8.dp).background(
                            if (i == pager.currentPage) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
                            CircleShape,
                        ),
                    )
                }
            }
            Button(
                onClick = { if (isLast) onFinish() else scope.launch { pager.animateScrollToPage(pager.currentPage + 1) } },
                colors = ButtonDefaults.buttonColors(containerColor = prominentButtonFill, contentColor = Color.White),
                modifier = Modifier
                    .padding(16.dp)
                    .widthIn(max = 560.dp)
                    .fillMaxWidth()
                    .heightIn(min = 52.dp)
                    .semantics { contentDescription = if (isLast) "Start browsing" else "Continue, page ${pager.currentPage + 2} of ${pages.size}" },
            ) { Text(if (isLast) "Start browsing" else "Continue") }
        }
    }
}

@Composable
private fun Page(page: OnboardingCopy.Page, number: Int, count: Int, extra: @Composable () -> Unit = {}) {
    val icon = when (page.icon) {
        "truck" -> Icons.Filled.LocalShipping
        "map" -> Icons.Filled.Map
        "star" -> Icons.Filled.Star
        else -> Icons.Filled.EventAvailable
    }
    val large = isLargeText()
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Spacer(Modifier.size(if (large) 4.dp else 24.dp))
        Box(
            Modifier.size(if (large) 88.dp else 120.dp).background(MaterialTheme.colorScheme.primaryContainer, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Box(Modifier.size(if (large) 72.dp else 100.dp).background(prominentButtonFill, CircleShape), contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(if (large) 36.dp else 48.dp))
            }
        }
        Text(
            page.title,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(max = 560.dp).semantics { heading(); contentDescription = "${page.title}, page $number of $count" },
        )
        Text(page.body, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 560.dp))
        Column(
            Modifier
                .widthIn(max = 560.dp)
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.background, RoundedCornerShape(16.dp))
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            page.points.forEach { point ->
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Filled.CheckCircle, null, tint = MaterialTheme.colorScheme.primary)
                    Text(point, style = MaterialTheme.typography.bodyLarge)
                }
            }
        }
        extra()
        Spacer(Modifier.size(24.dp))
    }
}

@Composable
private fun StatePickerCard(states: List<StateOption>, selected: String?, onPick: (String) -> Unit) {
    Column(
        Modifier
            .widthIn(max = 560.dp)
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.background, RoundedCornerShape(16.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(StateChoice.PICKER_TITLE, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.semantics { heading() })
        Text(StateChoice.PICKER_NOTE, style = MaterialTheme.typography.bodySmall, color = secondaryText)
        StateChoiceList(states, selected, onPick)
    }
}
