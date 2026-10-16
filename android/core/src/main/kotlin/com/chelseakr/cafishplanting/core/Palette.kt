package com.chelseakr.cafishplanting.core

/**
 * The app's colors as 0xRRGGBB, the same values as the iOS app's asset
 * catalog and `TextColors.swift`, so both apps look like one product and
 * both meet WCAG AA. `PaletteContrastTest` checks every text color against
 * the backgrounds it is drawn on.
 */
object Palette {
    /** The icon's green; links and tinted controls in light mode. */
    const val ACCENT_LIGHT = 0x0F784B

    /** The accent in dark mode: lighter, so it stands out on near-black. */
    const val ACCENT_DARK = 0x2E9E68

    /** The fill of a main button with white text, in both modes. White on it is 5.5:1. */
    const val PROMINENT_BUTTON_FILL = 0x0F784B

    const val SECONDARY_TEXT_LIGHT = 0x5C5C61
    const val SECONDARY_TEXT_DARK = 0xA1A1A6

    const val BACKGROUND_LIGHT = 0xFFFFFF
    const val SURFACE_GROUPED_LIGHT = 0xF2F2F7
    const val BACKGROUND_DARK = 0x000000
    const val SURFACE_DARK = 0x1C1C1E
    const val ON_SURFACE_LIGHT = 0x000000
    const val ON_SURFACE_DARK = 0xFFFFFF

    /** The tinted badge behind "This week": the accent at 18% over the background. */
    fun blend(foreground: Int, background: Int, alpha: Double): Int {
        fun ch(c: Int, shift: Int) = (c shr shift) and 0xFF
        fun mix(shift: Int) = Math.round(ch(foreground, shift) * alpha + ch(background, shift) * (1 - alpha)).toInt()
        return (mix(16) shl 16) or (mix(8) shl 8) or mix(0)
    }

    fun contrast(a: Int, b: Int): Double {
        val la = luminance(a)
        val lb = luminance(b)
        return (maxOf(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
    }

    fun luminance(rgb: Int): Double {
        fun channel(v: Int): Double {
            val c = v / 255.0
            return if (c <= 0.03928) c / 12.92 else Math.pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel((rgb shr 16) and 0xFF) + 0.7152 * channel((rgb shr 8) and 0xFF) + 0.0722 * channel(rgb and 0xFF)
    }
}
