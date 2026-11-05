package com.chelseakr.cafishplanting.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.Instant

/**
 * A state whose latest check failed (source-outage audit 2026-11-05, TT-1):
 * the same cases as `StateCheckWordingTests.swift`. The widget and the alerts
 * footer say TWRA couldn't be checked since the last good read and never show
 * that read's weeks as current. Each test has its control: the same snapshot
 * with the check marked good.
 */
class StateCheckTest {
    private val tellico = "tn-monroe-tellico-river"
    private val now = Instant.parse("2026-10-14T19:00:00Z")

    private fun v2(tnFailed: Boolean): Snapshot {
        val bytes = File(TS.swiftFixtures, "v2-all-states.json").readBytes()
        if (!tnFailed) return SnapshotDecoder.decode(bytes)
        val root = Json.parseToJsonElement(bytes.decodeToString()).jsonObject
        val states = root.getValue("states").jsonArray.map { element ->
            val state = element.jsonObject
            if (state.getValue("code").jsonPrimitive.content != "TN") return@map state
            val checks = JsonObject(
                state.getValue("checks").jsonObject +
                    mapOf("last_attempt_ok" to JsonPrimitive(false), "last_attempt_at" to JsonPrimitive("2026-10-14T13:22:00Z")),
            )
            JsonObject(state + ("checks" to checks))
        }
        return SnapshotDecoder.decode(JsonObject(root + ("states" to JsonArray(states))).toString().encodeToByteArray())
    }

    private fun digest(snapshot: Snapshot) = WidgetDigest.build(
        snapshot,
        SnapshotMeta(lastAttemptAt = now, lastSuccessAt = now, lastOutcome = "updated"),
        listOf(tellico, "cdfw-2227"),
        locked = false,
        entitledStates = setOf("CA", "TN"),
    )

    @Test fun theFailedSinceDateIsTheLastGoodRead() {
        val tn = v2(tnFailed = true).state("TN")!!
        assertEquals("2026-10-12", StateCheckWording.failedSince(tn)?.isoDate)
        assertEquals(
            "Couldn't check TWRA's schedule since 2026-10-12. What's shown is from that last read and may be out of date.",
            StateCheckWording.notice(tn),
        )
        assertEquals(
            "Alerts for Tennessee waters are paused until TWRA's schedule can be checked again.",
            StateCheckWording.alertsPaused(tn),
        )
        val ok = v2(tnFailed = false).state("TN")!!
        assertNull(StateCheckWording.failedSince(ok))
        assertNull(StateCheckWording.notice(ok))
        assertNull(StateCheckWording.alertsPaused(ok))
    }

    @Test fun theWidgetNeverShowsAFailedStatesOldWeeks() {
        val failed = digest(v2(tnFailed = true))
        val fav = failed.favorites.first { it.id == tellico }
        assertEquals("Couldn't check TWRA's schedule since 2026-10-12", failed.statusLine(fav, now))
        assertEquals(WidgetDigest.Status.CheckFailed(PlainDate(2026, 10, 12)), failed.status(fav, now))
        assertTrue(fav.speciesThisWeek.isEmpty())
        assertNull(fav.nextWeek)
        assertEquals("a failed state's favorite sorts last", tellico, failed.favoritesByStatus.last().id)
        val ok = digest(v2(tnFailed = false))
        val okFav = ok.favorites.first { it.id == tellico }
        assertFalse(ok.statusLine(okFav, now).contains("Couldn't check"))
        assertTrue(ok.statusLine(okFav, now).startsWith("Scheduled"))
    }

    @Test fun theDigestRoundTripsAtItsNewVersion() {
        val failed = digest(v2(tnFailed = true))
        assertEquals(4, failed.version)
        val json = Json.encodeToString(WidgetDigest.serializer(), failed)
        assertEquals(failed, Json.decodeFromString(WidgetDigest.serializer(), json))
    }

    @Test fun aReportStateSaysItsOwnKind() {
        val since = PlainDate(2026, 10, 13)
        assertEquals(
            "Couldn't check MassWildlife's stocking report since 2026-10-13",
            StateCheckWording.short("MassWildlife", StateSemantics.REPORT, since),
        )
        assertEquals("Couldn't check DEC's plan since 2026-10-13", StateCheckWording.short("DEC", StateSemantics.PLAN, since))
    }
}
