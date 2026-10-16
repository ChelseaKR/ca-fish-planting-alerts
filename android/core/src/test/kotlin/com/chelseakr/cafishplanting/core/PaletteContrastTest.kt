package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Every text color meets WCAG AA (4.5:1) on what it is drawn on, as the iOS contrast tests check. */
class PaletteContrastTest {
    private fun aa(fg: Int, bg: Int, what: String) =
        assertTrue("$what: %.2f:1".format(Palette.contrast(fg, bg)), Palette.contrast(fg, bg) >= 4.5)

    @Test fun textAndAccentsKeepAAInLightAndDark() {
        aa(Palette.ACCENT_LIGHT, Palette.BACKGROUND_LIGHT, "light accent on white")
        aa(Palette.ACCENT_LIGHT, Palette.SURFACE_GROUPED_LIGHT, "light accent on grouped")
        aa(Palette.ACCENT_DARK, Palette.BACKGROUND_DARK, "dark accent on black")
        aa(Palette.ACCENT_DARK, Palette.SURFACE_DARK, "dark accent on a dark row")
        aa(0xFFFFFF, Palette.PROMINENT_BUTTON_FILL, "white on the button fill")
        aa(Palette.SECONDARY_TEXT_LIGHT, Palette.BACKGROUND_LIGHT, "secondary on white")
        aa(Palette.SECONDARY_TEXT_LIGHT, Palette.SURFACE_GROUPED_LIGHT, "secondary on grouped")
        aa(Palette.SECONDARY_TEXT_DARK, Palette.BACKGROUND_DARK, "secondary on black")
        aa(Palette.SECONDARY_TEXT_DARK, Palette.SURFACE_DARK, "secondary on a dark row")
        aa(Palette.ON_SURFACE_LIGHT, Palette.blend(Palette.ACCENT_LIGHT, Palette.BACKGROUND_LIGHT, 0.18), "badge text, light")
        aa(Palette.ON_SURFACE_DARK, Palette.blend(Palette.ACCENT_DARK, Palette.SURFACE_DARK, 0.18), "badge text, dark")
    }

    /** Negative control: the check fails the colors it exists to stop. */
    @Test fun theCheckWouldCatchALowContrastColor() {
        assertTrue(Palette.contrast(0x007AFF, 0xFFFFFF) < 4.5)
        assertTrue(Palette.contrast(0xFFFFFF, Palette.ACCENT_DARK) < 4.5)
        assertTrue(Palette.contrast(0x8E8E93, 0xFFFFFF) < 4.5)
    }

    /** The accent is the iOS asset catalog's, so the two apps are one product. */
    @Test fun theAccentIsTheIosAccent() {
        val json = File(TS.repoRoot, "ios/CAFishPlanting/Resources/Assets.xcassets/AccentColor.colorset/Contents.json").readText()
        val hex = Regex("\"(red|green|blue)\" : \"0x([0-9A-F]{2})\"").findAll(json).map { it.groupValues[2] }.toList()
        assertEquals(6, hex.size)
        fun rgb(i: Int) = (hex[i + 2] + hex[i + 1] + hex[i]).let { "%06X".format(Integer.parseInt(it, 16)) }
        // The catalog lists blue, green, red per color.
        assertEquals("%06X".format(Palette.ACCENT_LIGHT), rgb(0))
        assertEquals("%06X".format(Palette.ACCENT_DARK), rgb(3))
    }
}
