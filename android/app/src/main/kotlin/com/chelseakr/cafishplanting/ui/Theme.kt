package com.chelseakr.cafishplanting.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.graphics.Color
import com.chelseakr.cafishplanting.core.Palette

private fun rgb(value: Int) = Color(0xFF000000 or value.toLong())

/**
 * The iOS app's colors (`Palette` in core, checked for 4.5:1 contrast by
 * `PaletteContrastTest`), not the wallpaper's dynamic colors: those can't be
 * checked ahead of time, and the app's green is its identity.
 */
private val Light = lightColorScheme(
    primary = rgb(Palette.ACCENT_LIGHT),
    onPrimary = Color.White,
    primaryContainer = rgb(Palette.blend(Palette.ACCENT_LIGHT, Palette.BACKGROUND_LIGHT, 0.18)),
    onPrimaryContainer = Color.Black,
    secondaryContainer = rgb(Palette.blend(Palette.ACCENT_LIGHT, Palette.BACKGROUND_LIGHT, 0.18)),
    onSecondaryContainer = Color.Black,
    background = rgb(Palette.SURFACE_GROUPED_LIGHT),
    onBackground = Color.Black,
    surface = rgb(Palette.SURFACE_GROUPED_LIGHT),
    onSurface = Color.Black,
    surfaceContainer = Color.White,
    surfaceContainerLow = Color.White,
    surfaceContainerHigh = Color.White,
    surfaceContainerHighest = Color(0xFFE5E5EA),
    onSurfaceVariant = rgb(Palette.SECONDARY_TEXT_LIGHT),
    outline = rgb(Palette.SECONDARY_TEXT_LIGHT),
    outlineVariant = Color(0xFFD1D1D6),
)

private val Dark = darkColorScheme(
    primary = rgb(Palette.ACCENT_DARK),
    onPrimary = Color.Black,
    primaryContainer = rgb(Palette.blend(Palette.ACCENT_DARK, Palette.SURFACE_DARK, 0.18)),
    onPrimaryContainer = Color.White,
    secondaryContainer = rgb(Palette.blend(Palette.ACCENT_DARK, Palette.SURFACE_DARK, 0.30)),
    onSecondaryContainer = Color.White,
    background = rgb(Palette.BACKGROUND_DARK),
    onBackground = Color.White,
    surface = rgb(Palette.BACKGROUND_DARK),
    onSurface = Color.White,
    surfaceContainer = rgb(Palette.SURFACE_DARK),
    surfaceContainerLow = rgb(Palette.SURFACE_DARK),
    surfaceContainerHigh = rgb(Palette.SURFACE_DARK),
    surfaceContainerHighest = Color(0xFF2C2C2E),
    onSurfaceVariant = rgb(Palette.SECONDARY_TEXT_DARK),
    outline = rgb(Palette.SECONDARY_TEXT_DARK),
    outlineVariant = Color(0xFF3A3A3C),
)

@Composable
fun TroutTruckTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) Dark else Light, content = content)
}

/** Second-level text: 4.5:1 on every background the app draws it on. */
val secondaryText: Color
    @Composable @ReadOnlyComposable
    get() = MaterialTheme.colorScheme.onSurfaceVariant

/** The main button's fill with white text, in both modes (white on it is 5.5:1). */
val prominentButtonFill = rgb(Palette.PROMINENT_BUTTON_FILL)
