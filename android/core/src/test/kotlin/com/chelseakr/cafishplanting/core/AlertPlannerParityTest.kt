package com.chelseakr.cafishplanting.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
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

/**
 * Same inputs, same alerts: every scenario in the Swift package's
 * `Fixtures/alert-planner-parity.json` (recorded from the iOS planner) run
 * through this planner, step by step, compared field for field: each alert's
 * id, title, body and new weeks, the alerts left after mutes, and the
 * baseline carried to the next step.
 */
class AlertPlannerParityTest {
    private val fixtures = TS.swiftFixtures
    private val doc = Json.parseToJsonElement(File(fixtures, "alert-planner-parity.json").readText()).jsonObject

    private val snapshots: Map<String, Snapshot> = doc.getValue("snapshots").jsonObject.mapValues { (_, spec) -> snapshot(spec.jsonObject) }

    @Test
    fun everyScenarioMatchesTheSharedExpectations() {
        var checked = 0
        var alerts = 0
        for (scenario in doc.getValue("scenarios").jsonArray.map { it.jsonObject }) {
            val name = scenario.getValue("name").jsonPrimitive.content
            var state = AlertState(baseline(scenario["initial_state"]?.jsonObject ?: JsonObject(emptyMap())))
            for ((i, step) in scenario.getValue("steps").jsonArray.map { it.jsonObject }.withIndex()) {
                val actual: JsonObject = when (val op = step.getValue("op").jsonPrimitive.content) {
                    "seed" -> {
                        state = AlertPlanner.seeding(state, step.str("water"), snapshots.getValue(step.str("snapshot")))
                        buildJsonObject { put("state", encode(state)) }
                    }
                    "prune" -> {
                        state = AlertPlanner.pruning(state, step.str("water"))
                        buildJsonObject { put("state", encode(state)) }
                    }
                    "plan" -> {
                        val favorites = step.getValue("favorites").jsonArray.map { it.jsonPrimitive.content }
                        val plan = AlertPlanner.plan(snapshots.getValue(step.str("snapshot")), favorites, state)
                        state = plan.state
                        alerts += plan.notifications.size
                        val muted = MutedWaters(step["muted"]?.jsonArray?.map { it.jsonPrimitive.content }?.toSet() ?: emptySet())
                        buildJsonObject {
                            put("notifications", JsonArray(plan.notifications.map(::encode)))
                            put("shown", JsonArray(muted.unmuted(plan.notifications).map { kotlinx.serialization.json.JsonPrimitive(it.id) }))
                            put("state", encode(state))
                        }
                    }
                    else -> error("$name: unknown op $op")
                }
                val expected = step["expect"]?.jsonObject ?: error("$name step $i has no expect block")
                assertEquals("$name, step $i", normalize(expected), normalize(actual))
                checked += 1
            }
        }
        assertTrue("the fixture should exercise every scenario", checked > 20)
        assertTrue("and produce real alerts to compare", alerts >= 10)
    }

    private fun JsonObject.str(key: String) = getValue(key).jsonPrimitive.content

    private fun snapshot(spec: JsonObject): Snapshot {
        spec["file"]?.let { return SnapshotDecoder.decode(File(fixtures, it.jsonPrimitive.content).readBytes()) }
        val waters = spec.getValue("waters").jsonArray.map { w ->
            val water = w.jsonObject
            val plants = water.getValue("plants").jsonArray.map { p ->
                val plant = p.jsonObject
                TS.plant(plant.str("week"), plant.str("species"), PlantStatus.fromWire(plant.str("status"))!!)
            }
            TS.water(water.str("id"), water.str("name"), plants)
        }
        return TS.snapshot(spec.str("source_week"), waters)
    }

    private fun baseline(json: JsonObject): Map<String, Set<PlantKey>> = json.mapValues { (_, keys) ->
        keys.jsonArray.map { pair -> PlantKey(TS.date(pair.jsonArray[0].jsonPrimitive.content), pair.jsonArray[1].jsonPrimitive.content) }.toSet()
    }

    private fun encode(keys: List<PlantKey>): JsonArray = buildJsonArray {
        keys.forEach { add(buildJsonArray { add(kotlinx.serialization.json.JsonPrimitive(it.weekStart.isoDate)); add(kotlinx.serialization.json.JsonPrimitive(it.species)) }) }
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
