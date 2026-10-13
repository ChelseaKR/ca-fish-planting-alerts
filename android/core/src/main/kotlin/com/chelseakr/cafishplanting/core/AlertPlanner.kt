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
    /**
     * `null` for a week, so every baseline stored before precision existed
     * (California's, all weeks) still matches; a day or a month otherwise.
     */
    val precision: DatePrecision? = null,
) : Comparable<PlantKey> {
    constructor(plant: Plant) : this(
        plant.week.start,
        plant.species,
        plant.week.precision.takeIf { it != DatePrecision.WEEK },
    )

    /** The period the key names: "the week of 2026-10-11", "2026-10-14", or "December 2026". */
    val phrase: String
        get() = when (precision ?: DatePrecision.WEEK) {
            DatePrecision.WEEK -> "the week of ${weekStart.isoDate}"
            DatePrecision.DAY -> weekStart.isoDate
            DatePrecision.MONTH -> "${MONTH_NAMES[weekStart.month - 1]} ${weekStart.year}"
        }

    companion object {
        val MONTH_NAMES = listOf(
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December",
        )
    }

    /** Week first, then species, as `PlannedNotification` sorts in Swift. */
    override fun compareTo(other: PlantKey): Int =
        if (weekStart == other.weekStart) species.compareTo(other.species) else weekStart.compareTo(other.weekStart)
}

/** Per favorited water, the listed-plant baseline as of the last evaluation. */
@Serializable
data class AlertState(val lastListed: Map<String, Set<PlantKey>> = emptyMap())

/**
 * One alert. The words and the identifier are the same as
 * `PlannedNotification` in ios/PlantingCore. A schedule's alert says
 * "scheduled" and names each period at the agency's precision; California's
 * words are exactly as before. A report's alert says "stocked", in
 * [ReportWording].
 */
class PlannedNotification(
    val waterID: String,
    val waterName: String,
    newKeys: Collection<PlantKey>,
    val semantics: StateSemantics = StateSemantics.SCHEDULE,
    val agencyShortName: String = "CDFW",
    /** The state's lag note (Michigan), shortened into the alert. */
    val lagging: Boolean = false,
) {
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

    val title: String
        get() = if (semantics == StateSemantics.REPORT) ReportWording.alertTitle(waterName) else "$waterName is on the stocking schedule"

    fun body(): String {
        val species = newKeys.map { it.species }.distinct()
        val what = if (species.isEmpty()) "species not stated" else species.joinToString(", ")
        if (semantics == StateSemantics.REPORT) {
            return ReportWording.alertBody(newKeys.map { it.phrase }.distinct(), what, agencyShortName, lagging)
        }
        if (newKeys.all { it.precision == null }) {
            // Weeks only: California's words, exactly as before.
            val weeks = newKeys.map { it.weekStart }.distinct().sorted()
            val whenText = if (weeks.size == 1) {
                "Scheduled for the week of ${weeks[0].isoDate}"
            } else {
                "Scheduled for the weeks of " + weeks.joinToString(" and ") { it.isoDate }
            }
            return "$whenText ($what). Plans can change; $agencyShortName gives the week, not the day."
        }
        val periods = newKeys.map { it.phrase }.distinct()
        val unset = if (newKeys.any { it.precision == DatePrecision.MONTH }) " $agencyShortName hasn't set the day yet." else ""
        return "Scheduled for ${periods.joinToString(" and ")} ($what).$unset Plans can change."
    }

    override fun equals(other: Any?): Boolean =
        other is PlannedNotification && other.waterID == waterID && other.waterName == waterName && other.newKeys == newKeys &&
            other.semantics == semantics && other.agencyShortName == agencyShortName && other.lagging == lagging

    override fun hashCode(): Int = id.hashCode()

    override fun toString(): String = "PlannedNotification($id, $newKeys)"
}

data class AlertPlan(val notifications: List<PlannedNotification>, val state: AlertState)

/**
 * Pure: no clock, no I/O, no notification manager. The same diff rule as
 * `AlertPlanner.swift`, held to the same shared fixtures
 * (`AlertPlannerParityTest`):
 *
 * - For each favorite, take its alert basis ([Snapshot.alertBasis]): a
 *   schedule's listed periods from its state's current week on, or a
 *   report's recent stockings.
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
            val current = snapshot.alertBasis(water).map(::PlantKey).toSet()
            val previous = state.lastListed[id] ?: emptySet()
            val newKeys = current - previous
            if (newKeys.isNotEmpty()) {
                notifications += PlannedNotification(
                    id, water.name, newKeys,
                    semantics = water.semantics, agencyShortName = water.agencyShortName,
                    lagging = snapshot.stateOf(water)?.recencyNote != null,
                )
            }
            next[id] = current
        }
        return AlertPlan(notifications, AlertState(next))
    }

    /** On favoriting: seed the baseline at what is visible now, so it is not announced. */
    fun seeding(state: AlertState, favoriting: String, snapshot: Snapshot): AlertState {
        val water = snapshot.water(favoriting) ?: return state
        return AlertState(state.lastListed + (favoriting to snapshot.alertBasis(water).map(::PlantKey).toSet()))
    }

    fun pruning(state: AlertState, unfavoriting: String): AlertState = AlertState(state.lastListed - unfavoriting)
}
