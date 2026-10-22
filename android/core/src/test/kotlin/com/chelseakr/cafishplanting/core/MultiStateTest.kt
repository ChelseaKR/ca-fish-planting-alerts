package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.Instant

/**
 * Snapshot v2 and the per-state rules (DECISIONS 0025), the same cases as
 * `MultiStateTests.swift`, against the same fixture: real pipeline output for
 * California and Tennessee, labeled synthetic fixtures for Massachusetts and
 * Michigan.
 */
class MultiStateTest {
    private val v2File = File(TS.swiftFixtures, "v2-all-states.json")
    private val v2: Snapshot by lazy { SnapshotDecoder.decode(v2File.readBytes()) }

    @Test fun v2DecodesEveryStateWithCaliforniaFirst() {
        assertEquals(2, v2.schemaVersion)
        assertEquals(listOf("CA", "MA", "MI", "TN"), v2.states.map { it.code })
        assertEquals(StateSemantics.SCHEDULE, v2.state("TN")?.semantics)
        assertEquals(StateSemantics.REPORT, v2.state("MA")?.semantics)
        assertNotNull(v2.state("MI")?.recencyNote)
        assertEquals("the top level is California's, as in v1", v2.state("CA")?.currentWeek, v2.sourceWeek)
        assertNull("v2 has no coverage numbers, and none is made up", v2.coverage)
        assertTrue(v2.waters.filter { it.state == "CA" }.all { it.id.startsWith("cdfw-") })
    }

    @Test fun aV1FileIsCaliforniaAlone() {
        val v1 = SnapshotDecoder.decode(File(TS.swiftFixtures, "alert-parity-real-2026-09-27.json").readBytes())
        assertEquals(1, v1.schemaVersion)
        assertEquals(listOf("CA"), v1.states.map { it.code })
        assertTrue(v1.waters.all { it.state == "CA" && it.semantics == StateSemantics.SCHEDULE })
    }

    @Test fun theBundledSnapshotIsV2WithTennessee() {
        val bundled = SnapshotDecoder.decode(TS.bundledSnapshot.readBytes())
        assertEquals(2, bundled.schemaVersion)
        assertEquals("CA", bundled.states.first().code)
        assertNotNull("the app ships Tennessee", bundled.state("TN"))
    }

    @Test fun tennesseeKeepsTheAgencysPrecision() {
        val mckenzie = v2.water("tn-caroll-mckenzie-city-park")!!
        val month = mckenzie.plants.first { it.week.precision == DatePrecision.MONTH }
        assertEquals("December 2026", month.week.label)
        assertEquals("December 2026", month.week.phrase)
        val tellico = v2.water("tn-monroe-tellico-river")!!
        assertTrue(tellico.plants.first { it.week.precision == DatePrecision.WEEK }.week.phrase.startsWith("the week of "))
        assertEquals("/tn/water/tellico-river-monroe-county/", tellico.sitePath)
        assertEquals(
            "https://chelseakr.github.io/ca-fish-planting-alerts/tn/water/tellico-river-monroe-county/",
            SnapshotEndpoint.siteWaterURL(tellico),
        )
    }

    @Test fun aMonthOnlyWaterSaysSoAndIsNeverGivenADate() {
        val lettersOnly = v2.waters.first { it.state == "TN" && it.plants.isEmpty() }
        val line = ScheduleWording.lastScheduledLine(lettersOnly, v2.currentWeek(lettersOnly))
        assertTrue(line, line.contains(lettersOnly.monthsNote!!))
    }

    @Test fun aReportWaterSaysStockedAndHasNoFuture() {
        val swift = v2.water("ma-swift-belch")!!
        assertEquals(StateSemantics.REPORT, swift.semantics)
        assertEquals("Massachusetts reports a town", "Belchertown", swift.countyLabel)
        assertEquals("Last stocked on 2026-10-09", ScheduleWording.lastScheduledLine(swift, v2.currentWeek(swift)))
        assertNull(ScheduleWording.nextScheduledLine(swift, v2.currentWeek(swift)))
        assertEquals(4000, v2.water("mi-1234")!!.plants.last().count)
    }

    @Test fun aReportedPlantInAScheduleStateIsRefused() {
        val json = v2File.readText()
        val tnStart = json.indexOf("\"state\": \"TN\"")
        val status = json.indexOf("\"status\": \"listed\"", tnStart)
        val broken = json.substring(0, status) + "\"status\": \"reported\"" + json.substring(status + "\"status\": \"listed\"".length)
        assertNotEquals("the sabotage must land", json, broken)
        val error = runCatching { SnapshotDecoder.decode(broken) }.exceptionOrNull()
        assertTrue("$error", error is SnapshotDecodingException && error.message!!.contains("schedule state"))
    }

    @Test fun aWeekLabeledAsADayIsRefused() {
        val json = v2File.readText()
        val broken = json.replace("\"label\": \"week of 2026-10-11\"", "\"label\": \"2026-10-11\"")
        assertNotEquals(json, broken)
        assertTrue(runCatching { SnapshotDecoder.decode(broken) }.exceptionOrNull() is SnapshotDecodingException)
    }

    @Test fun aBaselineStoredBeforeStatesStillMatchesCaliforniaWeeks() {
        val old = storeJson.decodeFromString(PlantKey.serializer(), """{"weekStart":"2026-09-13","species":"Trout"}""")
        assertEquals("an old week baseline must not re-announce", PlantKey(TS.plant("2026-09-13")), old)
        val oldDigestWeek = storeJson.decodeFromString(
            DigestWeek.serializer(),
            """{"start":"2026-09-13","end":"2026-09-19","label":"week of 2026-09-13"}""",
        )
        assertEquals(DatePrecision.WEEK, oldDigestWeek.precision)
    }

    @Test fun tennesseeAndMassachusettsAlertsUseTheirOwnWords() {
        val ids = listOf("tn-monroe-tellico-river", "ma-swift-belch")
        val plan = AlertPlanner.plan(v2, ids, AlertState())
        val tn = plan.notifications.first { it.waterID == ids[0] }
        assertEquals("Tellico River is on the stocking schedule", tn.title)
        assertTrue(tn.body(), tn.body().contains("TWRA gives the week, not the day"))
        val ma = plan.notifications.first { it.waterID == ids[1] }
        assertEquals("Swift River was stocked", ma.title)
        assertTrue(ma.body(), ma.body().startsWith("Stocked on 2026-10-06 and 2026-10-09"))
        assertTrue(ma.body().contains("MassWildlife"))
        assertTrue(AlertPlanner.plan(v2, ids, plan.state).notifications.isEmpty())
    }

    @Test fun aMonthPlantIsAnnouncedWithoutADay() {
        val key = PlantKey(PlainDate(2026, 12, 1), "Rainbow Trout", DatePrecision.MONTH)
        val n = PlannedNotification("tn-x", "X", listOf(key), agencyShortName = "TWRA")
        assertEquals("Scheduled for December 2026 (Rainbow Trout). TWRA hasn't set the day yet. Plans can change.", n.body())
    }

    @Test fun alertsAndTheWidgetFollowEachStatesPurchase() {
        assertTrue(FreeTier.notificationsAllowed("TN", setOf("TN")))
        assertFalse(FreeTier.notificationsAllowed("TN", setOf("CA")))
        assertFalse(FreeTier.widgetsAllowed(emptySet()))
        assertTrue(FreeTier.widgetsAllowed(setOf("MA")))
        val meta = SnapshotMeta(lastAttemptAt = Instant.now(), lastSuccessAt = Instant.now(), lastOutcome = "updated")
        val ids = listOf("tn-monroe-tellico-river", "ma-swift-belch", v2.waters[0].id)
        val digest = WidgetDigest.build(v2, meta, ids, locked = false, entitledStates = setOf("TN"))
        assertEquals(listOf("tn-monroe-tellico-river"), digest.favorites.map { it.id })
        assertEquals("favorites in states not bought are counted, not dropped", 2, digest.favoritesInOtherStates)
    }

    @Test fun eachStateBuysOnlyItsOwnFeatures() {
        assertEquals(
            listOf(
                "An alert on this device when a Tennessee favorite is newly on TWRA's schedule",
                "Tennessee favorites in the Favorite waters widget",
            ),
            FreeTier.stateFeatures("Tennessee", "TWRA", StateSemantics.SCHEDULE),
        )
        assertTrue(FreeTier.stateFeatures("Massachusetts", "MassWildlife", StateSemantics.REPORT)[0].contains("reports stocking"))
    }
}
