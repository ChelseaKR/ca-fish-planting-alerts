package com.chelseakr.cafishplanting.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The v2 reader leaves out vocabulary this build does not know and still
 * refuses a corrupt file (DECISIONS 0034), the same cases as
 * `StatesWave2Tests.swift`. The documents are built from the pinned
 * `v2-all-states.json` (CA, MA, MI, TN), never from a daily-rewritten file,
 * by adding what states wave 2 adds: New York with `plan` semantics and the
 * `approximate` precision, and values this build has never heard of.
 */
class TolerantReaderTest {
    private val json = Json { prettyPrint = false }
    private val base: JsonObject by lazy {
        json.parseToJsonElement(File(TS.swiftFixtures, "v2-all-states.json").readText()).jsonObject
    }

    private fun JsonObject.with(key: String, value: JsonElement) = JsonObject(this + (key to value))
    private fun JsonObject.array(key: String) = getValue(key).jsonArray
    private fun JsonObject.text(key: String) = getValue(key).jsonPrimitive.content
    private fun List<JsonElement>.states() = map { it.jsonObject }
    private fun period(precision: String, label: String) = buildJsonObject {
        put("precision", JsonPrimitive(precision)); put("start", JsonPrimitive("2026-04-15"))
        put("end", JsonPrimitive("2026-04-21")); put("label", JsonPrimitive(label))
    }

    private fun plant(period: JsonObject, status: String) = buildJsonObject {
        put("period", period); put("species", JsonPrimitive("Rainbow Trout")); put("status", JsonPrimitive(status))
        put("count", JsonPrimitive(null as String?))
        put("first_observed_at", JsonPrimitive("2026-10-12T19:18:13Z"))
        put("last_observed_at", JsonPrimitive("2026-10-12T19:18:13Z"))
    }

    private fun newWater(id: String, state: String, plants: List<JsonObject>) = buildJsonObject {
        put("id", JsonPrimitive(id)); put("state", JsonPrimitive(state)); put("name", JsonPrimitive("Water $id"))
        put("name_status", JsonPrimitive("unreviewed")); put("slug", JsonPrimitive(id))
        put("counties", JsonArray(listOf(JsonPrimitive("Ulster")))); put("region", JsonPrimitive(null as String?))
        put("source_url", JsonPrimitive("https://example.org/$id")); put("plants", JsonArray(plants))
        put("a_field_from_the_future", JsonPrimitive("ignored"))
    }

    private fun stateLike(model: JsonObject, code: String, semantics: String, precisions: List<String>, waters: Int) =
        JsonObject(
            model + mapOf(
                "code" to JsonPrimitive(code), "name" to JsonPrimitive("State $code"),
                "semantics" to JsonPrimitive(semantics),
                "date_precisions" to JsonArray(precisions.map(::JsonPrimitive)),
                "waters_count" to JsonPrimitive(waters),
                "a_field_from_the_future" to JsonPrimitive(1),
            ),
        )

    private fun stateModel() = base.array("states").states().first { it.text("code") == "MA" }

    private val approximate = period("approximate", "April - third week, 2026")

    /** The pinned fixture plus New York (plan, approximate), a state with semantics from the future, and new values. */
    private fun wave2Document(): JsonObject {
        val ny = stateLike(stateModel(), "NY", "plan", listOf("approximate"), 2)
        val xx = stateLike(stateModel(), "XX", "forecast", listOf("day"), 1)
        val nyWaters = listOf(
            newWater("ny-ulster-a", "NY", listOf(plant(approximate, "listed"))),
            newWater("ny-ulster-b", "NY", listOf(plant(approximate, "listed"))),
            newWater("xx-one", "XX", listOf(plant(period("day", "2026-04-15"), "reported"))),
        )
        // New values inside states this build does know: a precision and a status from the future.
        val waters = base.array("waters").states().map { w ->
            when (w.text("id")) {
                "tn-monroe-tellico-river" -> w.with("plants", JsonArray(w.array("plants") + plant(period("quarter", "Q2 2026"), "listed")))
                "cdfw-${caId()}" -> w.with("plants", JsonArray(w.array("plants") + plant(period("week", "week of 2026-04-12"), "paused")))
                else -> w
            }
        }
        return base
            .with("states", JsonArray(base.array("states") + ny + xx))
            .with("waters", JsonArray(waters + nyWaters))
    }

    private fun caId() = base.array("waters").states().first { it.text("state") == "CA" }.text("id").removePrefix("cdfw-")

    private fun decode(doc: JsonObject) = SnapshotDecoder.decodeReporting(json.encodeToString(JsonObject.serializer(), doc).toByteArray())

    private fun refused(doc: JsonObject): Throwable? =
        runCatching { SnapshotDecoder.decode(json.encodeToString(JsonObject.serializer(), doc)) }.exceptionOrNull()

    @Test fun theUnchangedFixtureIgnoresNothing() {
        val decoded = decode(base)
        assertTrue(decoded.ignored.toString(), decoded.ignored.isEmpty)
        assertEquals(listOf("CA", "MA", "MI", "TN"), decoded.snapshot.states.map { it.code })
        assertEquals(181, decoded.snapshot.waters.size)
    }

    @Test fun aWaveTwoDocumentDecodesWithOnlyTheKnownStatesWatersAndSaysWhatItLeftOut() {
        val decoded = decode(wave2Document())
        val snap = decoded.snapshot
        assertEquals(listOf("CA", "MA", "MI", "TN"), snap.states.map { it.code })
        assertEquals(setOf("CA", "MA", "MI", "TN"), snap.waters.map { it.state }.toSet())
        assertEquals("every water of the known states is kept", 181, snap.waters.size)
        assertNull(snap.water("ny-ulster-a"))
        assertNull(snap.water("xx-one"))
        assertEquals(listOf("NY", "XX"), decoded.ignored.states)
        assertEquals(listOf("ny-ulster-a", "ny-ulster-b", "xx-one"), decoded.ignored.waters)
        assertEquals("a quarter and a paused plant", 2, decoded.ignored.plants)
        assertTrue(snap.waters.all { w -> w.plants.all { it.status in PlantStatus.entries } })
    }

    @Test fun anUnknownPlantValueDropsThePlantNotTheWater() {
        val snap = decode(wave2Document()).snapshot
        val tellico = snap.water("tn-monroe-tellico-river")!!
        val original = SnapshotDecoder.decode(File(TS.swiftFixtures, "v2-all-states.json").readBytes()).water("tn-monroe-tellico-river")!!
        assertEquals(original.plants, tellico.plants)
        assertTrue(tellico.plants.none { it.week.label == "Q2 2026" })
    }

    @Test fun anUnknownValueIsNeverTakenForAKnownOne() {
        assertNull(StateSemantics.fromWire("plan"))
        assertNull(DatePrecision.fromWire("approximate"))
        assertNull(PlantStatus.fromWire("paused"))
        assertFalse(StateProducts.isKnown("NY"))
        // Not a known state's semantics, and no default: a Michigan that says "plan" is left out whole, not read as a schedule.
        val doc = base.with(
            "states",
            JsonArray(
                base.array("states").states().map {
                    if (it.text("code") == "MI") it.with("semantics", JsonPrimitive("plan")) else it
                },
            ),
        )
        val decoded = decode(doc)
        assertEquals(listOf("MI"), decoded.ignored.states)
        assertTrue(decoded.snapshot.waters.none { it.state == "MI" })
        assertEquals(listOf("mi-1234", "mi-5678", "mi-9012"), decoded.ignored.waters)
    }

    @Test fun aStateLeftWithNoWaterAfterItsPlantsWereIgnoredGoesToo() {
        val doc = base.with(
            "waters",
            JsonArray(
                base.array("waters").states().map { w ->
                    if (w.text("state") == "MI") w.with("plants", JsonArray(w.array("plants").states().map { it.with("status", JsonPrimitive("paused")) })) else w
                },
            ),
        )
        val decoded = decode(doc)
        assertEquals(listOf("CA", "MA", "TN"), decoded.snapshot.states.map { it.code })
        assertEquals(listOf("MI"), decoded.ignored.states)
        assertEquals(3, decoded.ignored.waters.size)
    }

    @Test fun thisWeekFollowsADroppedWater() {
        val tw = JsonObject(mapOf("water_id" to JsonPrimitive("ny-ulster-a"), "species" to JsonPrimitive("Rainbow Trout")))
        val doc = wave2Document().with("this_week", JsonArray(base.array("this_week") + tw))
        val snap = decode(doc).snapshot
        assertEquals(4, snap.thisWeek.size)
        assertTrue(snap.thisWeek.none { it.waterID == "ny-ulster-a" })
    }

    // A corrupt document still fails loudly. Each case lands its damage on a known state.

    @Test fun aKnownStatesMissingRequiredFieldStillThrows() {
        val doc = base.with(
            "waters",
            JsonArray(base.array("waters").states().mapIndexed { i, w -> if (i == 0) JsonObject(w - "name") else w }),
        )
        assertTrue(refused(doc) is SnapshotDecodingException)
    }

    @Test fun californiaNotFirstStillThrows() {
        val doc = base.with("states", JsonArray(base.array("states").reversed()))
        assertTrue(refused(doc)?.message, refused(doc)?.message!!.contains("California first"))
    }

    @Test fun aReportedPlantInAScheduleStateStillThrows() {
        val doc = base.with(
            "waters",
            JsonArray(
                base.array("waters").states().map { w ->
                    if (w.text("id") == "tn-monroe-tellico-river") {
                        w.with("plants", JsonArray(w.array("plants").states().map { it.with("status", JsonPrimitive("reported")) }))
                    } else {
                        w
                    }
                },
            ),
        )
        assertTrue(refused(doc)?.message, refused(doc)?.message!!.contains("schedule state"))
    }

    @Test fun aKnownPrecisionWithTheWrongLabelStillThrows() {
        val doc = base.with(
            "waters",
            JsonArray(
                base.array("waters").states().map { w ->
                    if (w.text("id") == "ma-swift-belch") {
                        w.with("plants", JsonArray(w.array("plants").states().map { it.with("period", period("day", "not a day")) }))
                    } else {
                        w
                    }
                },
            ),
        )
        assertTrue(refused(doc)?.message, refused(doc)?.message!!.contains("is a day but reads"))
    }

    @Test fun anEmptyPlantListWithNoNoteStillThrowsWhenNothingWasIgnored() {
        val doc = base.with(
            "waters",
            JsonArray(
                base.array("waters").states().map { w ->
                    if (w.text("id") == "ma-swift-belch") w.with("plants", JsonArray(emptyList())).with("months_note", JsonPrimitive(null as String?)) else w
                },
            ),
        )
        assertTrue(refused(doc)?.message, refused(doc)?.message!!.contains("no plants and no months note"))
    }

    @Test fun aWaterNamingAStateTheFileNeverListedStillThrows() {
        val doc = base.with("waters", JsonArray(base.array("waters") + newWater("zz-one", "ZZ", emptyList())))
        assertTrue(refused(doc)?.message, refused(doc)?.message!!.contains("names a state the snapshot doesn't list"))
    }

    @Test fun aDuplicateWaterIdStillThrowsEvenInAnIgnoredState() {
        val doc = wave2Document().let { it.with("waters", JsonArray(it.array("waters") + newWater("ny-ulster-a", "NY", emptyList()))) }
        assertTrue(refused(doc)?.message, refused(doc)?.message!!.contains("duplicate water id"))
    }

    @Test fun textThatIsNotASnapshotStillThrows() {
        assertTrue(runCatching { SnapshotDecoder.decode("{\"schema_version\": 2") }.exceptionOrNull() is SnapshotDecodingException)
        assertTrue(runCatching { SnapshotDecoder.decode("{\"schema_version\": 3}") }.exceptionOrNull() is SnapshotDecodingException)
    }

    /**
     * Negative control: the tolerance is what makes the wave 2 document decode,
     * and the document really carries vocabulary this build lacks. Were Android
     * taught "plan", "approximate" or a New York product, this would fail here
     * rather than let the cases above pass without exercising anything. The
     * strict rule the app had before is applied to the same document below, and
     * it refuses it.
     */
    @Test fun negativeControlTheStrictRuleRefusesTheSameDocument() {
        val doc = wave2Document()
        val states = doc.array("states").states()
        val unknownSemantics = states.map { it.text("semantics") }.filter { StateSemantics.fromWire(it) == null }
        assertEquals("the sabotage must land", listOf("plan", "forecast"), unknownSemantics)
        assertTrue(states.flatMap { it.array("date_precisions") }.any { DatePrecision.fromWire(it.jsonPrimitive.content) == null })
        assertNotEquals(base, doc)
        // The old rule, as the decoder had it: unknown semantics anywhere is a contract violation.
        val strict = runCatching {
            states.forEach { s ->
                StateSemantics.fromWire(s.text("semantics")) ?: throw SnapshotDecodingException.malformed("state ${s.text("code")} has unknown semantics ${s.text("semantics")}")
            }
        }.exceptionOrNull()
        assertTrue("$strict", strict is SnapshotDecodingException)
        assertTrue(runCatching { decode(doc) }.isSuccess)
    }
}
