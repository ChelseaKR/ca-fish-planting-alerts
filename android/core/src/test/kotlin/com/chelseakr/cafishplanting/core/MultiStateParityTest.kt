package com.chelseakr.cafishplanting.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.Instant

/**
 * Same snapshot, same purchases, same alerts and widget rows: every scenario
 * in the Swift package's `Fixtures/alert-planner-parity-states.json`
 * (recorded from the iOS planner, DECISIONS 0025) run through this planner
 * and widget digest, step by step, compared field for field. A plan step
 * also checks which alerts each state's purchase lets the app post.
 */
class MultiStateParityTest {
    private val fixtures = TS.swiftFixtures
    private val doc = Json.parseToJsonElement(File(fixtures, "alert-planner-parity-states.json").readText()).jsonObject

    private val snapshots: Map<String, Snapshot> = doc.getValue("snapshots").jsonObject.mapValues { (_, spec) ->
        SnapshotDecoder.decode(File(fixtures, spec.jsonObject.getValue("file").jsonPrimitive.content).readBytes())
    }

    @Test
    fun everyScenarioMatchesTheSharedExpectations() {
        var checked = 0
        var alerts = 0
        val words = mutableSetOf<String>()
        for (scenario in doc.getValue("scenarios").jsonArray.map { it.jsonObject }) {
            val name = scenario.getValue("name").jsonPrimitive.content
            var state = AlertState(baseline(scenario["initial_state"]?.jsonObject ?: JsonObject(emptyMap())))
            for ((i, step) in scenario.getValue("steps").jsonArray.map { it.jsonObject }.withIndex()) {
                val actual: JsonObject = when (val op = step.str("op")) {
                    "seed" -> {
                        state = AlertPlanner.seeding(state, step.str("water"), snapshots.getValue(step.str("snapshot")))
                        buildJsonObject { put("state", encode(state)) }
                    }
                    "prune" -> {
                        state = AlertPlanner.pruning(state, step.str("water"))
                        buildJsonObject { put("state", encode(state)) }
                    }
                    "plan" -> {
                        val snapshot = snapshots.getValue(step.str("snapshot"))
                        val plan = AlertPlanner.plan(snapshot, step.strings("favorites"), state)
                        state = plan.state
                        alerts += plan.notifications.size
                        plan.notifications.forEach { words += it.body() }
                        val muted = MutedWaters(step["muted"]?.jsonArray?.map { it.jsonPrimitive.content }?.toSet() ?: emptySet())
                        val shown = FreeTier.alertsToPost(muted.unmuted(plan.notifications), snapshot, step.strings("entitled").toSet())
                        buildJsonObject {
                            put("notifications", JsonArray(plan.notifications.map(::encode)))
                            put("shown", JsonArray(shown.map { JsonPrimitive(it.id) }))
                            put("state", encode(state))
                        }
                    }
                    "widget" -> {
                        val snapshot = snapshots.getValue(step.str("snapshot"))
                        val entitled = step.strings("entitled").toSet()
                        val now = Instant.parse(step.str("now"))
                        val meta = SnapshotMeta(lastAttemptAt = now, lastSuccessAt = now, lastOutcome = "updated")
                        val digest = WidgetDigest.build(
                            snapshot, meta, step.strings("favorites"),
                            locked = !FreeTier.widgetsAllowed(entitled), entitledStates = entitled,
                        )
                        buildJsonObject {
                            put("locked", digest.locked)
                            put("favorites", JsonArray(digest.favoritesByStatus.map { JsonPrimitive(it.id) }))
                            put("status_lines", JsonArray(digest.favoritesByStatus.map { JsonPrimitive(digest.statusLine(it, now)) }))
                            put("summary", digest.summary(now))
                            put("favorites_in_other_states", digest.favoritesInOtherStates)
                            put("missing_favorites", digest.missingFavorites)
                        }
                    }
                    else -> error("$name: unknown op $op")
                }
                val expected = step["expect"]?.jsonObject ?: error("$name step $i has no expect block")
                assertEquals("$name, step $i", normalize(expected), normalize(actual))
                checked += 1
            }
        }
        assertTrue("the fixture should exercise every scenario", checked >= 18)
        assertTrue("and produce real alerts to compare", alerts >= 10)
        // Each kind of state's words is among them, so none goes unchecked.
        assertTrue(words.any { it.contains("TWRA gives the week, not the day") })
        assertTrue(words.any { it.contains("hasn't set the day yet") })
        assertTrue(words.any { it.startsWith("Stocked on") })
        assertTrue(words.any { it.contains("weeks after the stocking") })
        assertTrue(words.any { it.contains("CDFW gives the week, not the day") })
    }

    private fun JsonObject.str(key: String) = getValue(key).jsonPrimitive.content

    private fun JsonObject.strings(key: String) = getValue(key).jsonArray.map { it.jsonPrimitive.content }

    private fun baseline(json: JsonObject): Map<String, Set<PlantKey>> = json.mapValues { (_, keys) ->
        keys.jsonArray.map { row ->
            val parts = row.jsonArray.map { it.jsonPrimitive.content }
            val precision = parts.getOrNull(2)?.let { DatePrecision.fromWire(it)!! }?.takeIf { it != DatePrecision.WEEK }
            PlantKey(TS.date(parts[0]), parts[1], precision)
        }.toSet()
    }

    private fun encode(keys: List<PlantKey>): JsonArray = buildJsonArray {
        keys.forEach {
            add(
                buildJsonArray {
                    add(JsonPrimitive(it.weekStart.isoDate))
                    add(JsonPrimitive(it.species))
                    add(JsonPrimitive((it.precision ?: DatePrecision.WEEK).wire))
                },
            )
        }
    }

    private fun encode(state: AlertState): JsonObject = JsonObject(state.lastListed.mapValues { (_, keys) -> encode(keys.sorted()) })

    private fun encode(n: PlannedNotification): JsonObject = buildJsonObject {
        put("id", n.id)
        put("water_id", n.waterID)
        put("title", n.title)
        put("body", n.body())
        put("new_keys", encode(n.newKeys))
    }

    /** Object key order doesn't matter; array order does. */
    private fun normalize(e: JsonElement): JsonElement = when (e) {
        is JsonObject -> JsonObject(e.toSortedMap().mapValues { normalize(it.value) })
        is JsonArray -> JsonArray(e.map(::normalize))
        else -> e
    }
}
