package com.chelseakr.cafishplanting.core

import java.time.Instant

/**
 * The snapshot contract as the app reads it, mirroring
 * `schema/snapshot.v1.json` and `schema/snapshot.v2.json`, and
 * `Snapshot.swift` in ios/PlantingCore. Unknown keys are ignored
 * (`schema/README.md`: "readers must ignore unknown fields").
 *
 * Absence is modeled, never defaulted: [Water.location] is `null` unless a
 * licensed source supplied it; [Water.lastListedWeek] is `null` when every
 * observed plant is in the future. Every record is a [Week] at the agency's
 * own precision; nothing is ever shown finer than the agency gave it.
 *
 * [sourceWeek], [source], [attribution], [license], [regions] and
 * [counties] are California's, as they always were, so every screen that
 * read them from v1 reads the same thing from v2.
 */
data class Snapshot(
    val schemaVersion: Int,
    val generatedAt: Instant,
    val source: SourceInfo,
    /** The CDFW week containing `source.statedToday`. California's "this week", not the device clock. */
    val sourceWeek: Week,
    val attribution: Attribution,
    val license: License,
    val regions: List<Region>,
    val counties: List<County>,
    val species: List<String>,
    val waters: List<Water>,
    /** Listed plants for each state's current week. Can legitimately be empty. */
    val thisWeek: List<ThisWeekEntry>,
    /** v1's coverage numbers. v2 has none, and none is made up. */
    val coverage: Coverage?,
    /** Every state the snapshot carries, California first. A v1 file is California alone. */
    val states: List<StateInfo> = listOf(
        StateInfo.california(source, sourceWeek, attribution, license, regions, counties, waters.size),
    ),
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

    /** Distinct waters listed for their state's current week. */
    val thisWeekWaterIDs: Set<String> get() = thisWeek.map { it.waterID }.toSet()

    // States

    fun state(code: String): StateInfo? = states.firstOrNull { it.code == code }

    fun stateOf(water: Water): StateInfo? = state(water.state)

    fun watersInState(code: String): List<Water> = waters.filter { it.state == code }

    /** The regions of one state that have a water, in the state's order. */
    fun regionsWithWaters(stateCode: String): List<Region> {
        val state = state(stateCode) ?: return emptyList()
        val present = watersInState(stateCode).map { it.region }.toSet()
        return state.regions.filter { it.code in present }
    }

    /** What "this week" means for this water: its state's current week. */
    fun currentWeek(water: Water): Week = stateOf(water)?.currentWeek ?: sourceWeek

    /**
     * The records the alert planner diffs for a favorite. A schedule: listed
     * periods that haven't ended before the state's current week. A report:
     * reported stockings from [REPORT_LOOKBACK_DAYS] before the current week
     * on, because a report's records arrive after the fact.
     */
    fun alertBasis(water: Water): List<Plant> {
        val week = currentWeek(water)
        return when (water.semantics) {
            StateSemantics.SCHEDULE, StateSemantics.PLAN -> water.listedPlants(week)
            StateSemantics.REPORT -> {
                val since = week.start.plusDays(-REPORT_LOOKBACK_DAYS)
                water.plants.filter { it.status == PlantStatus.REPORTED && it.week.start >= since }
            }
        }
    }

    companion object {
        /** The newest version this app reads. It reads v1 too: a v1 file is California alone. */
        const val SUPPORTED_SCHEMA_VERSION = 2
        val SUPPORTED_SCHEMA_VERSIONS: Set<Int> = setOf(1, 2)
        const val REPORT_LOOKBACK_DAYS = 120L
    }
}

/** What a state's records mean (`$defs/state/semantics`, schema v2). */
enum class StateSemantics(val wire: String) {
    /** The agency says when fish will be stocked, and plans can change. Say "scheduled". */
    SCHEDULE("schedule"),

    /** The agency reports stockings already done. Say "stocked". */
    REPORT("report"),

    /** A once-a-year plan in the agency's own words (New York). Say "planned for"; nothing is ever inferred as removed from it. */
    PLAN("plan"),
    ;

    companion object {
        fun fromWire(value: String): StateSemantics? = entries.firstOrNull { it.wire == value }
    }
}

/** One state's source, terms and freshness (`$defs/state`, schema v2), as `StateInfo` in Swift. */
data class StateInfo(
    val code: String,
    val name: String,
    val agencyName: String,
    val agencyShortName: String,
    val agencyURL: String,
    val semantics: StateSemantics,
    val datePrecisions: List<DatePrecision>,
    val removalInference: Boolean,
    /** What "this week" means for this state. */
    val currentWeek: Week,
    /** The civil date of the last good fetch, in the state's time zone. */
    val asOf: PlainDate,
    val newestRecord: Week?,
    /** Shown next to the data when the source lags (Michigan). */
    val recencyNote: String?,
    val sourceName: String,
    val sourceURL: String,
    val fetchedAt: Instant,
    val lastModified: String?,
    val lastAttemptAt: Instant,
    val lastSuccessAt: Instant,
    val lastAttemptOK: Boolean,
    val attribution: Attribution,
    val disclaimer: String,
    val license: License,
    val regions: List<Region>,
    val counties: List<County>,
    val watersCount: Int,
) {
    /** "Stocking schedule", "Stocking report" or "Spring stocking plan", for a list of states. */
    val kindLabel: String
        get() = when (semantics) {
            StateSemantics.SCHEDULE -> "Stocking schedule"
            StateSemantics.REPORT -> "Stocking report"
            StateSemantics.PLAN -> "Spring stocking plan"
        }

    companion object {
        const val CALIFORNIA_DISCLAIMER = "Trout Truck is independent and is not affiliated with or endorsed by CDFW. " +
            "CDFW: \"all fish plants are subject to change depending on road, water, weather and operational conditions.\""

        /** California as a v1 file describes it. */
        fun california(
            source: SourceInfo,
            sourceWeek: Week,
            attribution: Attribution,
            license: License,
            regions: List<Region>,
            counties: List<County>,
            watersCount: Int,
        ) = StateInfo(
            code = "CA", name = "California",
            agencyName = "California Department of Fish and Wildlife", agencyShortName = "CDFW",
            // From the file, never a second host in the app's source (`HostAllowlistTest`).
            agencyURL = source.url,
            semantics = StateSemantics.SCHEDULE, datePrecisions = listOf(DatePrecision.WEEK), removalInference = true,
            currentWeek = sourceWeek, asOf = source.statedToday, newestRecord = null, recencyNote = null,
            sourceName = source.name, sourceURL = source.url, fetchedAt = source.fetchedAt, lastModified = null,
            lastAttemptAt = source.fetchedAt, lastSuccessAt = source.fetchedAt, lastAttemptOK = true,
            attribution = attribution, disclaimer = CALIFORNIA_DISCLAIMER, license = license,
            regions = regions, counties = counties, watersCount = watersCount,
        )
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
    /** The license clause, verbatim (v2). `null` from a v1 file. */
    val termsQuote: String? = null,
)

data class License(val summary: String, val sources: List<LicenseSource>)

data class Region(val code: String, val name: String)

data class County(val name: String, val region: String)

data class GeoLocation(val lat: Double, val lon: Double, val source: String)

/** `listed` and `removed` belong to a schedule; `reported` to a report (a stocking the agency says it did). */
enum class PlantStatus(val wire: String) {
    LISTED("listed"),
    REMOVED("removed"),
    REPORTED("reported"),
    ;

    companion object {
        fun fromWire(value: String): PlantStatus? = entries.firstOrNull { it.wire == value }
    }
}

/**
 * One record for a water: a period, a species, and what the agency said.
 * Equality is over the identity the agency gives it (period, species,
 * status), so re-fetches that only refresh observation timestamps compare
 * equal, as in Swift.
 */
class Plant(
    /** The period, at the agency's precision (`week.precision`). */
    val week: Week,
    val species: String,
    val status: PlantStatus,
    val firstObservedAt: Instant,
    val lastObservedAt: Instant,
    /** How many fish, when the agency says (Michigan). Never guessed. */
    val count: Int? = null,
) {
    override fun equals(other: Any?): Boolean =
        other is Plant && other.week == week && other.species == species && other.status == status

    override fun hashCode(): Int = (week.hashCode() * 31 + species.hashCode()) * 31 + status.hashCode()

    override fun toString(): String = "Plant(${week.label}, $species, ${status.wire})"
}

data class ThisWeekEntry(val waterID: String, val species: String)

class Water(
    /** `cdfw-<StockingWaterID>` for California (CDFW's own key), `tn-…` and so on elsewhere. Names are not keys. */
    val id: String,
    /** CDFW's stock ID for California; 0 for a water in another state. */
    val cdfwStockID: Int,
    val name: String,
    val nameReviewed: Boolean,
    /** Site path segment: `/water/<slug>/`. */
    val slug: String,
    val aliases: List<String>,
    val counties: List<String>,
    /** The region code, or "" for a state that has none. */
    val region: String,
    /** The agency's page for this water (CDFW's map link in California). */
    val cdfwMapURL: String,
    val location: GeoLocation?,
    /** Newest listed or reported period that is not in the future. `null` if there is none. */
    val lastListedWeek: Week?,
    plants: List<Plant>,
    /** The state's postal code ("CA" for every v1 water). */
    val state: String = "CA",
    /** What this water's records mean, from its state. */
    val semantics: StateSemantics = StateSemantics.SCHEDULE,
    /** The agency's short name ("CDFW", "TWRA"), for the words on screen. */
    val agencyShortName: String = "CDFW",
    /** Massachusetts reports a town, not a county. */
    val towns: List<String> = emptyList(),
    /** The water's page from the site root (`site_path`, v2). `null` from v1, where it is `/water/<slug>/`. */
    val sitePath: String? = null,
    /** Tennessee's month letters, verbatim (`months_note`). Never dates. */
    val monthsNote: String? = null,
) {
    /** Every record ever observed, oldest first. */
    val plants: List<Plant> = plants.sortedBy { it.week }

    /**
     * Listed plants whose period hasn't ended before [onOrAfter] starts,
     * oldest first: what the alert planner diffs for a schedule. For
     * California's aligned weeks this is "at or after the week", as it was.
     */
    fun listedPlants(onOrAfter: Week): List<Plant> =
        plants.filter { it.status == PlantStatus.LISTED && it.week.end >= onOrAfter.start }

    fun plantsInYear(year: Int): List<Plant> = plants.filter { it.week.start.year == year }

    /** Distinct species across the kept history, most recently observed first. */
    val speciesSeen: List<String>
        get() = plants.asReversed().map { it.species }.distinct()

    /**
     * Distinct species in [lastListedWeek], in the order first observed.
     * Empty when [lastListedWeek] is `null`; never falls back to [speciesSeen].
     */
    val lastListedSpecies: List<String>
        get() {
            val week = lastListedWeek ?: return emptyList()
            return plants.filter { it.week == week && it.status != PlantStatus.REMOVED }.map { it.species }.distinct()
        }

    /** Years with history, newest first. */
    val years: List<Int> get() = plants.map { it.week.start.year }.distinct().sortedDescending()

    val countyLabel: String
        get() = when {
            counties.isNotEmpty() -> counties.joinToString(", ")
            towns.isNotEmpty() -> towns.joinToString(", ")
            else -> "County not stated"
        }

    override fun equals(other: Any?): Boolean =
        other is Water && other.id == id && other.name == name && other.plants == plants &&
            other.counties == counties && other.aliases == aliases && other.lastListedWeek == lastListedWeek &&
            other.state == state && other.monthsNote == monthsNote

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
