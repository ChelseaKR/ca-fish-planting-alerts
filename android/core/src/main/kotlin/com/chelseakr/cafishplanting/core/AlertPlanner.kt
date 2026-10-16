package com.chelseakr.cafishplanting.core

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

/** `PlainDate` as its `YYYY-MM-DD` string, the same on disk as the Swift app writes. */
object PlainDateSerializer : KSerializer<PlainDate> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("PlainDate", PrimitiveKind.STRING)
    override fun serialize(encoder: Encoder, value: PlainDate) = encoder.encodeString(value.isoDate)
    override fun deserialize(decoder: Decoder): PlainDate {
        val raw = decoder.decodeString()
        return PlainDate.parse(raw) ?: throw IllegalArgumentException("not a YYYY-MM-DD date: $raw")
    }
}

/**
 * One (week, species) a favorited water had listed as of the last time the
 * planner evaluated a snapshot. A baseline, not a cumulative "ever notified"
 * set: a plant that goes `removed` then `listed` again is news again, as
 * `schema/README.md` specifies.
 */
@Serializable
data class PlantKey(
    @Serializable(with = PlainDateSerializer::class) val weekStart: PlainDate,
    val species: String,
) : Comparable<PlantKey> {
    constructor(plant: Plant) : this(plant.week.start, plant.species)

    /** Week first, then species, as `PlannedNotification` sorts in Swift. */
    override fun compareTo(other: PlantKey): Int =
        if (weekStart == other.weekStart) species.compareTo(other.species) else weekStart.compareTo(other.weekStart)
}

/** Per favorited water, the listed-plant baseline as of the last evaluation. */
@Serializable
data class AlertState(val lastListed: Map<String, Set<PlantKey>> = emptyMap())

/**
 * One alert. The words and the identifier are the same as
 * `PlannedNotification` in ios/PlantingCore: a week, never a day, and
 * "scheduled", never "stocked".
 */
class PlannedNotification(val waterID: String, val waterName: String, newKeys: Collection<PlantKey>) {
    /** Ascending. Usually one; more when a refresh reveals several new weeks at once. */
    val newKeys: List<PlantKey>

    /**
     * Deterministic: `plant.<water id>.<newest new week>`. The app posts the
     * notification under this tag, so a second post for the same evaluation
     * replaces the first rather than showing twice.
     */
    val id: String

    init {
        require(newKeys.isNotEmpty())
        this.newKeys = newKeys.sorted()
        id = "plant.$waterID.${this.newKeys.last().weekStart.isoDate}"
    }

    val title: String get() = "$waterName is on the stocking schedule"

    fun body(): String {
        val weeks = newKeys.map { it.weekStart }.distinct().sorted()
        val whenText = if (weeks.size == 1) {
            "Scheduled for the week of ${weeks[0].isoDate}"
        } else {
            "Scheduled for the weeks of " + weeks.joinToString(" and ") { it.isoDate }
        }
        val species = newKeys.map { it.species }.distinct()
        val what = if (species.isEmpty()) "species not stated" else species.joinToString(", ")
        return "$whenText ($what). Plans can change; CDFW gives the week, not the day."
    }

    override fun equals(other: Any?): Boolean =
        other is PlannedNotification && other.waterID == waterID && other.waterName == waterName && other.newKeys == newKeys

    override fun hashCode(): Int = id.hashCode()

    override fun toString(): String = "PlannedNotification($id, $newKeys)"
}

data class AlertPlan(val notifications: List<PlannedNotification>, val state: AlertState)

/**
 * Pure: no clock, no I/O, no notification manager. The same diff rule as
 * `AlertPlanner.swift`, held to the same shared fixtures
 * (`AlertPlannerParityTest`):
 *
 * - For each favorite, take its listed plants at or after the snapshot's
 *   week (current and future weeks, never past ones).
 * - Any (week, species) not in the water's stored baseline is new: one
 *   notification per water, naming every new (week, species).
 * - The baseline is replaced, not accumulated, so a removed week drops out
 *   and a relist later is news again.
 * - The same snapshot evaluated twice yields nothing the second time.
 * - A favorite the snapshot no longer has keeps its last baseline.
 */
object AlertPlanner {
    fun plan(snapshot: Snapshot, favorites: List<String>, state: AlertState): AlertPlan {
        val next = LinkedHashMap<String, Set<PlantKey>>()
        val notifications = mutableListOf<PlannedNotification>()
        for (id in favorites) {
            val water = snapshot.water(id)
            if (water == null) {
                state.lastListed[id]?.let { next[id] = it }
                continue
            }
            val current = water.listedPlants(snapshot.sourceWeek).map(::PlantKey).toSet()
            val previous = state.lastListed[id] ?: emptySet()
            val newKeys = current - previous
            if (newKeys.isNotEmpty()) notifications += PlannedNotification(id, water.name, newKeys)
            next[id] = current
        }
        return AlertPlan(notifications, AlertState(next))
    }

    /** On favoriting: seed the baseline at what is visible now, so it is not announced. */
    fun seeding(state: AlertState, favoriting: String, snapshot: Snapshot): AlertState {
        val water = snapshot.water(favoriting) ?: return state
        return AlertState(state.lastListed + (favoriting to water.listedPlants(snapshot.sourceWeek).map(::PlantKey).toSet()))
    }

    fun pruning(state: AlertState, unfavoriting: String): AlertState = AlertState(state.lastListed - unfavoriting)
}
