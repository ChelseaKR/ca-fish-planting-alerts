package com.chelseakr.cafishplanting.widget

import android.content.Context
import android.content.Intent
import androidx.core.net.toUri
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.LocalSize
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.color.ColorProvider
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.semantics.contentDescription
import androidx.glance.semantics.semantics
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import com.chelseakr.cafishplanting.MainActivity
import com.chelseakr.cafishplanting.R
import com.chelseakr.cafishplanting.core.AppStorageLayout
import com.chelseakr.cafishplanting.core.Palette
import com.chelseakr.cafishplanting.core.UnlockLink
import com.chelseakr.cafishplanting.core.WaterLink
import com.chelseakr.cafishplanting.core.WidgetDigest
import java.io.File
import java.time.Instant

/**
 * "Favorite waters" on the home screen, the twin of the iOS widget. It reads
 * only the digest file the app writes and never fetches anything. Every line
 * names its week; before the purchase it says it is part of full access and
 * a tap opens the purchase screen (`trouttruck://unlock`).
 */
class FavoriteWatersWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Responsive(setOf(SMALL, MEDIUM, LARGE))

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val digest = WidgetDigest.load(AppStorageLayout(File(context.filesDir, "trout-truck")))
        provideContent { GlanceTheme { Content(digest, Instant.now()) } }
    }

    companion object {
        val SMALL = DpSize(110.dp, 110.dp)
        val MEDIUM = DpSize(250.dp, 110.dp)
        val LARGE = DpSize(250.dp, 250.dp)
    }
}

class FavoriteWatersReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = FavoriteWatersWidget()
}

private fun rgb(value: Int) = Color(0xFF000000 or value.toLong())

private val background = ColorProvider(day = Color.White, night = rgb(Palette.SURFACE_DARK))
private val primaryText = ColorProvider(day = Color.Black, night = Color.White)
private val secondary = ColorProvider(day = rgb(Palette.SECONDARY_TEXT_LIGHT), night = rgb(Palette.SECONDARY_TEXT_DARK))
private val accent = ColorProvider(day = rgb(Palette.ACCENT_LIGHT), night = rgb(Palette.ACCENT_DARK))

private fun open(url: String) = actionStartActivity(Intent(Intent.ACTION_VIEW, url.toUri()).setClassName("com.chelseakr.cafishplanting", MainActivity::class.java.name))

@Composable
private fun Content(digest: WidgetDigest?, now: Instant) {
    val size = LocalSize.current
    val small = size.width < FavoriteWatersWidget.MEDIUM.width
    val maxRows = when {
        small -> 3
        size.height < FavoriteWatersWidget.LARGE.height -> 2
        else -> 7
    }
    val tap = when {
        digest?.locked == true -> open(UnlockLink.URL)
        small && digest != null && digest.favoritesByStatus.isNotEmpty() -> open(WaterLink.url(digest.favoritesByStatus.first().id))
        else -> actionStartActivity(Intent().setClassName("com.chelseakr.cafishplanting", MainActivity::class.java.name))
    }
    Column(
        GlanceModifier.fillMaxSize().background(background).cornerRadius(16.dp).padding(12.dp).clickable(tap),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(ImageProvider(R.drawable.ic_stat_trout), contentDescription = null, modifier = GlanceModifier.size(18.dp), colorFilter = androidx.glance.ColorFilter.tint(accent))
            Spacer(GlanceModifier.width(6.dp))
            val title = when {
                digest == null || digest.locked -> "Trout Truck"
                small && digest.isStale(now) -> "Week ended"
                else -> digest.headline(now)
            }
            Text(title, style = TextStyle(fontWeight = FontWeight.Bold, fontSize = 15.sp, color = primaryText), maxLines = 1)
        }
        if (digest != null && !digest.locked && !small) {
            Text(
                digest.subheadline(now),
                style = TextStyle(fontSize = 11.sp, color = if (digest.isStale(now) || digest.lastCheckFailed) primaryText else secondary),
                maxLines = 2,
            )
        }
        Spacer(GlanceModifier.height(6.dp))
        val empty = if (digest == null) WidgetDigest.NO_DIGEST_MESSAGE else digest.emptyMessage()
        if (empty != null) {
            Text(empty, style = TextStyle(fontSize = 13.sp, color = primaryText))
            if (digest?.locked == true) {
                Spacer(GlanceModifier.height(4.dp))
                Text("Tap to unlock", style = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Bold, color = accent))
            }
            if (digest != null && !small) {
                Spacer(GlanceModifier.height(4.dp))
                Text(digest.scheduleContext(), style = TextStyle(fontSize = 11.sp, color = secondary))
            }
            return@Column
        }
        val favorites = digest!!.favoritesByStatus.take(maxRows)
        favorites.forEach { favorite ->
            val status = digest.statusLine(favorite, now)
            val listed = favorite.isListedThisWeek
            Row(
                GlanceModifier.fillMaxWidth().padding(vertical = 3.dp)
                    .semantics { contentDescription = "${favorite.name}, $status" }
                    .then(if (small) GlanceModifier else GlanceModifier.clickable(open(WaterLink.url(favorite.id)))),
                verticalAlignment = Alignment.Top,
            ) {
                // A mark that doesn't rely on color: filled for listed this week, hollow otherwise.
                Text(if (listed) "●" else "○", style = TextStyle(fontSize = 12.sp, color = if (listed) accent else secondary))
                Spacer(GlanceModifier.width(6.dp))
                Column {
                    Text(favorite.name, style = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Medium, color = primaryText), maxLines = 1)
                    if (!small) Text(status, style = TextStyle(fontSize = 11.sp, color = secondary), maxLines = 2)
                }
            }
        }
        val hidden = maxOf(0, digest.favorites.size - maxRows) + digest.missingFavorites
        if (small) {
            Text(digest.summary(now), style = TextStyle(fontSize = 11.sp, color = secondary), maxLines = 2)
        } else if (hidden > 0) {
            Text(if (hidden == 1) "1 more favorite in the app" else "$hidden more favorites in the app", style = TextStyle(fontSize = 11.sp, color = secondary))
        }
    }
}
