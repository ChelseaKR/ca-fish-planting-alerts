package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The About screen's national wording (docs/DECISIONS.md 0049), the same
 * cases as `AboutCopyTests.swift`, and every word the iOS app's
 * `AboutCopy.swift` apart from Android's own names for its surfaces.
 */
class AboutCopyTest {
    private val states: List<StateInfo> by lazy {
        SnapshotDecoder.decode(File(TS.swiftFixtures, "v2-wave2.json").readBytes()).states
    }

    @Test fun theGeneralLinesNameNoStateAndNoAgency() {
        for (line in listOf(AboutCopy.WHAT_IT_DOES, AboutCopy.INDEPENDENCE, AboutCopy.OTHER_STATES, AboutCopy.CHECKING)) {
            assertFalse(line, line.contains("California"))
            assertFalse(line, line.contains("CDFW"))
            assertFalse(line, line.contains("every state", ignoreCase = true))
            assertFalse(line, line.contains("tracking", ignoreCase = true))
        }
        assertTrue(AboutCopy.INDEPENDENCE.contains("not affiliated with or endorsed by any state wildlife agency"))
    }

    @Test fun californiasWeekRuleIsSaidAsCalifornias() {
        assertTrue(AboutCopy.CALIFORNIA.startsWith("In California, CDFW publishes the week"))
        assertTrue(AboutCopy.CALIFORNIA.contains("For California waters this app shows a week, never a day"))
        assertTrue(AboutCopy.ALERT_TIMING.contains("each agency updates on its own rhythm (California's schedule is weekly)"))
    }

    @Test fun unlockedLinesComeFromTheSnapshot() {
        assertTrue("sanity check: the fixture carries several states", states.size > 1)
        assertEquals(emptyList<String>(), AboutCopy.unlockedLines(states, emptySet()))
        assertEquals(states.map { "${it.name} unlocked" }, AboutCopy.unlockedLines(states, states.map { it.code }.toSet() + "ZZ"))
        val last = states.last()
        assertEquals(listOf("${last.name} unlocked"), AboutCopy.unlockedLines(states, setOf(last.code)))
        assertEquals("${last.name}: data source and license", AboutCopy.dataSourceHeader(last.name))
    }

    /** Every line is the iOS app's, except the two platform phrases. */
    @Test fun theWordsAreTheIosCopyWithOnlyThePlatformWordsChanged() {
        val swift = File(TS.repoRoot, "ios/PlantingCore/Sources/PlantingCore/AboutCopy.swift").readText()
        val androidOnly = listOf(
            "a home screen widget with your favorites" to "a Home Screen and Lock Screen widget with your favorites",
            "Android decides when the app may refresh" to "iOS decides when the app is allowed to refresh",
        )
        val lines = listOf(
            AboutCopy.WHAT_IT_DOES, AboutCopy.CALIFORNIA, AboutCopy.OTHER_STATES,
            AboutCopy.ALERT_TIMING, AboutCopy.CHECKING, AboutCopy.INDEPENDENCE,
        )
        for (line in lines) {
            var ios = line.replace("\"", "\\\"")
            for ((android, apple) in androidOnly) ios = ios.replace(android, apple)
            assertTrue("not in the iOS copy: $ios", swift.contains("\"$ios\""))
        }
    }
}
