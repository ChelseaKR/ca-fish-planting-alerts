package com.chelseakr.cafishplanting.core

import java.time.Instant

/**
 * The snapshot contract as the app reads it, mirroring
 * `schema/snapshot.v1.json` (schema_version 1) field for field, and
 * `Snapshot.swift` in ios/PlantingCore. Unknown keys are ignored
 * (`schema/README.md`: "readers must ignore unknown fields").
 *
 * Absence is modeled, never defaulted: [Water.location] is `null` unless a
 * licensed source supplied it; [Water.lastListedWeek] is `null` when every
 * observed plant is in the future. Every planting is a [Week]; there is no
 * day anywhere in this model.
 */
data class Snapshot(
    val schemaVersion: Int,
    val generatedAt: Instant,
    val source: SourceInfo,
    /** The CDFW week containing `source.statedToday`. "This week" means this, not the device clock. */
    val sourceWeek: Week,
    val attribution: Attribution,
    val license: License,
    val regions: List<Region>,
    val counties: List<County>,
    val species: List<String>,
    val waters: List<Water>,
    val thisWeek: List<ThisWeekEntry>,
    val coverage: Coverage,
) {
    private val byID: Map<String, Water> by lazy { waters.associateBy { it.id } }

    fun water(id: String): Water? = byID[id]

    fun watersInRegion(code: String): List<Water> = waters.filter { it.region == code }

    fun region(code: String): Region? = regions.firstOrNull { it.code == code }

    /** Regions that have at least one water, in [regions] order. */
    val regionsWithWaters: List<Region>
        get() {
            val present = waters.map { it.region }.toSet()
            return regions.filter { it.code in present }
        }

    /** Distinct waters listed for [sourceWeek]. */
    val thisWeekWaterIDs: Set<String> get() = thisWeek.map { it.waterID }.toSet()

    companion object {
        const val SUPPORTED_SCHEMA_VERSION = 1
    }
}

data class SourceInfo(
    val name: String,
    val url: String,
    val fetchedAt: Instant,
    val statedToday: PlainDate,
    val statedPeriodStart: PlainDate,
    val statedPeriodEnd: PlainDate,
    val contentSHA256: String,
)

/** Shown verbatim wherever data from the snapshot is displayed. */
data class Attribution(val text: String, val url: String)

enum class CommercialReuse(val wire: String) {
    PERMITTED("permitted"),
    NOT_PERMITTED("not-permitted"),
    UNKNOWN("unknown"),
    ;

    companion object {
        fun fromWire(value: String): CommercialReuse? = entries.firstOrNull { it.wire == value }
    }
}

data class LicenseSource(
    val name: String,
    val url: String,
    val termsURL: String,
    val termsReadOn: PlainDate,
    val commercialReuse: CommercialReuse,
    val attributionRequired: Boolean,
)

data class License(val summary: String, val sources: List<LicenseSource>)

data class Region(val code: String, val name: String)

data class County(val name: String, val region: String)

data class GeoLocation(val lat: Double, val lon: Double, val source: String)

enum class PlantStatus(val wire: String) {
    LISTED("listed"),
    REMOVED("removed"),
    ;

    companion object {
        fun fromWire(value: String): PlantStatus? = entries.firstOrNull { it.wire == value }
    }
}

/**
 * One (week, species) CDFW listed for a water. Equality is over the identity
 * CDFW gives a plant (week, species, status), so re-fetches that only refresh
 * observation timestamps compare equal, as in Swift.
 */
class Plant(
    val week: Week,
    val species: String,
    val status: PlantStatus,
    val firstObservedAt: Instant,
    val lastObservedAt: Instant,
) {
    override fun equals(other: Any?): Boolean =
        other is Plant && other.week == week && other.species == species && other.status == status

    override fun hashCode(): Int = (week.hashCode() * 31 + species.hashCode()) * 31 + status.hashCode()

    override fun toString(): String = "Plant(${week.label}, $species, ${status.wire})"
}

data class ThisWeekEntry(val waterID: String, val species: String)

class Water(
    /** `cdfw-<StockingWaterID>`: CDFW's own key. Names are not keys. */
    val id: String,
    val cdfwStockID: Int,
    val name: String,
    val nameReviewed: Boolean,
    /** Site path segment: `/water/<slug>/`. */
    val slug: String,
    val aliases: List<String>,
    val counties: List<String>,
    /** Region of the first listed county. */
    val region: String,
    val cdfwMapURL: String,
    val location: GeoLocation?,
    /** Newest listed week that is not in the future. `null` if every observed plant is in the future. */
    val lastListedWeek: Week?,
    plants: List<Plant>,
) {
    /** Every (week, species) ever observed, oldest first. */
    val plants: List<Plant> = plants.sortedBy { it.week }

    /** Listed plants at or after [week], oldest first: what the alert planner diffs. */
    fun listedPlants(onOrAfter: Week): List<Plant> =
        plants.filter { it.status == PlantStatus.LISTED && it.week >= onOrAfter }

    fun plantsInYear(year: Int): List<Plant> = plants.filter { it.week.start.year == year }

    /** Distinct species across the kept history, most recently observed first. */
    val speciesSeen: List<String>
        get() = plants.asReversed().map { it.species }.distinct()

    /**
     * Distinct species listed in [lastListedWeek], in the order first observed.
     * Empty when [lastListedWeek] is `null`; never falls back to [speciesSeen].
     */
    val lastListedSpecies: List<String>
        get() {
            val week = lastListedWeek ?: return emptyList()
            return plants.filter { it.week == week && it.status == PlantStatus.LISTED }.map { it.species }.distinct()
        }

    /** Years with history, newest first. */
    val years: List<Int> get() = plants.map { it.week.start.year }.distinct().sortedDescending()

    val countyLabel: String get() = if (counties.isEmpty()) "County not stated" else counties.joinToString(", ")

    override fun equals(other: Any?): Boolean =
        other is Water && other.id == id && other.name == name && other.plants == plants &&
            other.counties == counties && other.aliases == aliases && other.lastListedWeek == lastListedWeek

    override fun hashCode(): Int = id.hashCode()

    override fun toString(): String = "Water($id, $name)"
}

data class Coverage(
    val watersThisWeek: Int,
    val watersKnown: Int,
    val watersWithHistory: Int,
    val namesMatched: Int,
    val namesSeen: Int,
    val rowsParsed: Int,
    val weeksOfHistoryMin: Int,
    val weeksOfHistoryMedian: Double,
)
