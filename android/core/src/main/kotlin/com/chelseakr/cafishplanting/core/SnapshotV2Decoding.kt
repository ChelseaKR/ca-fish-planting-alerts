package com.chelseakr.cafishplanting.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** What a decode left out, for tests and diagnostics. Never shown as a value. */
data class IgnoredVocabulary(
    val states: List<String> = emptyList(),
    val waters: List<String> = emptyList(),
    val plants: Int = 0,
) {
    val isEmpty: Boolean get() = states.isEmpty() && waters.isEmpty() && plants == 0
}

data class DecodedSnapshot(val snapshot: Snapshot, val ignored: IgnoredVocabulary)

/**
 * Decoder for `schema/snapshot.v2.json`: California plus every other state
 * with data, the same checks as `SnapshotV2Decoding.swift`. Unknown keys are
 * ignored. Two kinds of trouble are told apart (DECISIONS 0034):
 *
 * - A contract violation (a missing field, a week labeled as a day, a
 *   `reported` plant in a schedule state, California not first) throws, and
 *   the caller keeps the last good snapshot, as with v1.
 * - A vocabulary this build does not know is left out, never thrown on: a
 *   state whose `semantics` this build has no words for, a state it has no
 *   product for ([StateProducts]), a plant whose `status` or
 *   `period.precision` is new. The pipeline may add a state or a value
 *   before an app update ships; an install must keep refreshing through
 *   that. What is left out is counted in [IgnoredVocabulary], and `this_week` entries
 *   for those waters are dropped with them.
 *
 * California's waters keep v1's ids (`cdfw-<id>`), so favorites, alert
 * baselines and the widget carry over. The snapshot's top-level
 * `sourceWeek`, `source`, `attribution`, `license`, `regions` and `counties`
 * are California's.
 */
internal object SnapshotV2Decoding {
    private fun bad(what: String) = SnapshotDecodingException.malformed(what)

    fun decode(dto: SnapshotV2DTO): Snapshot = decodeReporting(dto).snapshot

    fun decodeReporting(dto: SnapshotV2DTO): DecodedSnapshot {
        val ignoredStates = mutableListOf<String>()
        val ignoredWaters = mutableListOf<String>()
        var ignoredPlants = 0
        val allStates = mutableListOf<StateInfo>()
        for (d in dto.states) {
            val st = state(d)
            if (st == null) ignoredStates += d.code else allStates += st
        }
        val ca = allStates.firstOrNull { it.code == "CA" }
        if (ca == null || dto.states.first().code != "CA") throw bad("a v2 snapshot must list California first")
        if (dto.states.map { it.code }.toSet().size != dto.states.size) throw bad("a state is listed twice")
        val byCode = allStates.associateBy { it.code }
        val ignoredStateSet = ignoredStates.toSet()

        val seen = HashSet<String>()
        val dropped = HashSet<String>()
        val waters = mutableListOf<Water>()
        for (w in dto.waters) {
            val id = w.id.trim()
            if (!seen.add(id)) throw bad("duplicate water id $id")
            if (w.state in ignoredStateSet) {
                dropped += id
                ignoredWaters += id
                continue
            }
            val st = byCode[w.state] ?: throw bad("water $id names a state the snapshot doesn't list: ${w.state}")
            val (water, plantsIgnored) = water(w, st)
            ignoredPlants += plantsIgnored
            if (water == null) {
                dropped += id
                ignoredWaters += id
                continue
            }
            waters += water
        }
        // The pipeline never publishes a state without a water (DECISIONS
        // 0025), so a state left with none after its plants were ignored goes
        // too, rather than listing a count of waters this build can't show.
        val withWaters = waters.map { it.state }.toSet()
        val states = allStates.filter { it.code == "CA" || it.code in withWaters }
        for (st in allStates) if (st !in states) ignoredStates += st.code
        val thisWeek = mutableListOf<ThisWeekEntry>()
        for (entry in dto.thisWeek) {
            val id = entry.waterID.trim()
            val species = entry.species.trim()
            if (id in dropped) continue
            if (id !in seen || species.isEmpty()) throw bad("this_week entry $id names no water or no species")
            thisWeek += ThisWeekEntry(id, species)
        }
        val species = mutableListOf<String>()
        for (w in waters) for (p in w.plants) if (p.species !in species) species += p.species

        val caSource = dto.states.first().source
        if (caSource.contentSHA256.length != 64) throw bad("content_sha256 is not 64 hex digits")
        val source = SourceInfo(
            name = ca.sourceName, url = ca.sourceURL, fetchedAt = ca.fetchedAt,
            statedToday = ca.currentWeek.start,
            statedPeriodStart = ca.currentWeek.start, statedPeriodEnd = ca.currentWeek.end,
            contentSHA256 = caSource.contentSHA256,
        )
        val snapshot = Snapshot(
            schemaVersion = 2,
            generatedAt = SnapshotDecoder.datetime(dto.generatedAt, "generated_at"),
            source = source, sourceWeek = ca.currentWeek, attribution = ca.attribution,
            license = ca.license, regions = ca.regions, counties = ca.counties,
            species = species.sorted(), waters = waters, thisWeek = thisWeek,
            coverage = null, states = states,
        )
        return DecodedSnapshot(snapshot, IgnoredVocabulary(ignoredStates, ignoredWaters, ignoredPlants))
    }

    /** One state, or null when this build has no words or no product for it. */
    private fun state(d: StateDTO): StateInfo? {
        val code = d.code
        if (code.length != 2 || code != code.uppercase()) throw bad("state code is not two capitals: $code")
        val semantics = StateSemantics.fromWire(d.semantics)
        if (semantics == null || !StateProducts.isKnown(code)) return null
        // A precision this build does not know is left out of the list; the
        // plants that use it are left out below, water by water.
        val precisions = d.datePrecisions.mapNotNull { DatePrecision.fromWire(it) }
        val regions = d.regions.map { r ->
            if (code == "CA" && r.code !in SnapshotDecoder.regionCodes) throw bad("region has an unrecognized code: ${r.code}")
            Region(r.code, r.name)
        }
        val license = License(
            d.license.summary,
            d.license.sources.map { s ->
                val reuse = CommercialReuse.fromWire(s.commercialReuse)
                    ?: throw bad("license source ${s.name} has an unrecognized commercial_reuse: ${s.commercialReuse}")
                LicenseSource(
                    name = s.name,
                    url = SnapshotDecoder.url(s.url, "$code.license.url"),
                    termsURL = SnapshotDecoder.url(s.termsURL, "$code.license.terms_url"),
                    termsReadOn = SnapshotDecoder.date(s.termsReadOn, "$code.license.terms_read_on"),
                    commercialReuse = reuse,
                    attributionRequired = s.attributionRequired,
                    termsQuote = s.termsQuote,
                )
            },
        )
        return StateInfo(
            code = code, name = d.name, agencyName = d.agency.name, agencyShortName = d.agency.shortName,
            agencyURL = SnapshotDecoder.url(d.agency.url, "$code.agency.url"),
            semantics = semantics, datePrecisions = precisions, removalInference = d.removalInference,
            currentWeek = SnapshotDecoder.week(d.currentWeek, "$code.current_week"),
            asOf = SnapshotDecoder.date(d.asOf, "$code.as_of"),
            newestRecord = d.newestRecord?.let { period(it, "$code.newest_record") },
            recencyNote = d.recencyNote,
            sourceName = d.source.name, sourceURL = SnapshotDecoder.url(d.source.url, "$code.source.url"),
            fetchedAt = SnapshotDecoder.datetime(d.source.fetchedAt, "$code.source.fetched_at"),
            lastModified = d.source.lastModified,
            lastAttemptAt = SnapshotDecoder.datetime(d.checks.lastAttemptAt, "$code.checks.last_attempt_at"),
            lastSuccessAt = SnapshotDecoder.datetime(d.checks.lastSuccessAt, "$code.checks.last_success_at"),
            lastAttemptOK = d.checks.lastAttemptOK,
            attribution = Attribution(d.attribution.text, SnapshotDecoder.url(d.attribution.url, "$code.attribution.url")),
            disclaimer = d.disclaimer, license = license, regions = regions,
            counties = d.counties.map { County(it.name, it.region ?: "") },
            watersCount = d.watersCount,
        )
    }

    /**
     * A period at a precision this build knows, or null for one it does not.
     * A known precision whose label or bounds break the contract throws.
     */
    fun period(d: PeriodV2DTO, field: String): Week? {
        val precision = DatePrecision.fromWire(d.precision) ?: return null
        val start = SnapshotDecoder.date(d.start, "$field.start")
        val end = SnapshotDecoder.date(d.end, "$field.end")
        if (start > end) throw bad("$field has end before start")
        when (precision) {
            DatePrecision.DAY -> if (start != end || d.label != start.isoDate) throw bad("$field is a day but reads ${d.label}")
            DatePrecision.WEEK -> if (d.label != "week of ${start.isoDate}") throw bad("$field is a week but reads ${d.label}")
            DatePrecision.MONTH -> if (start.day != 1 || start.month != end.month || d.label.contains("-")) {
                throw bad("$field is a month but reads ${d.label}")
            }
            // The agency's words and the year, verbatim: "April - third week, 2026".
            DatePrecision.APPROXIMATE -> if (!d.label.endsWith(", ${start.year}") || d.label.length <= 6) {
                throw bad("$field is approximate but reads ${d.label}")
            }
        }
        return Week(start, end, d.label, precision)
    }

    /**
     * One water, or null when every plant used a vocabulary this build does
     * not know and there is no months note to show instead.
     */
    private fun water(w: WaterV2DTO, state: StateInfo): Pair<Water?, Int> {
        val id = w.id.trim()
        var stockID = 0
        if (state.code == "CA") {
            stockID = id.removePrefix("cdfw-").takeIf { id.startsWith("cdfw-") }?.toIntOrNull()
                ?: throw bad("water id is not cdfw-<digits>: $id")
        } else if (!id.startsWith("${state.code.lowercase()}-")) {
            throw bad("water $id does not start with its state's code")
        }
        val name = w.name.trim()
        if (name.isEmpty()) throw bad("water $id has an empty name")
        val region = w.region ?: ""
        if (state.code == "CA" && region !in SnapshotDecoder.regionCodes) throw bad("water $id has an unrecognized region: $region")
        var ignoredPlants = 0
        val plants = mutableListOf<Plant>()
        for (p in w.plants) {
            val status = PlantStatus.fromWire(p.status)
            val week = if (status == null) null else period(p.period, "waters[$id].plants[].period")
            if (status == null || week == null) {
                ignoredPlants++
                continue
            }
            val fits = when (state.semantics) {
                StateSemantics.REPORT -> status == PlantStatus.REPORTED
                StateSemantics.SCHEDULE -> status != PlantStatus.REPORTED
                StateSemantics.PLAN -> status == PlantStatus.LISTED
            }
            if (!fits) throw bad("waters[$id] has a ${p.status} plant in a ${state.semantics.wire} state")
            val species = p.species.trim()
            if (species.isEmpty()) throw bad("waters[$id] has a plant with an empty species")
            plants += Plant(
                week = week,
                species = species,
                status = status,
                firstObservedAt = SnapshotDecoder.datetime(p.firstObservedAt, "waters[$id].plants[].first_observed_at"),
                lastObservedAt = SnapshotDecoder.datetime(p.lastObservedAt, "waters[$id].plants[].last_observed_at"),
                count = p.count,
            )
        }
        val monthsNote = w.monthsNote?.trim()?.takeIf { it.isNotEmpty() }
        if (plants.isEmpty() && monthsNote == null) {
            // Nothing this build can show. An empty list in the file is a
            // contract violation; a list emptied by unknown vocabulary is not.
            if (ignoredPlants == 0) throw bad("water $id has no plants and no months note")
            return null to ignoredPlants
        }
        val water = Water(
            id = id, cdfwStockID = stockID, name = name, nameReviewed = w.nameStatus == "reviewed",
            slug = w.slug, aliases = SnapshotDecoder.clean(w.aliases), counties = SnapshotDecoder.clean(w.counties),
            region = region, cdfwMapURL = SnapshotDecoder.url(w.sourceURL, "waters[$id].source_url"),
            location = w.location?.let { GeoLocation(it.lat, it.lon, it.source) },
            lastListedWeek = w.lastPeriod?.let { period(it, "waters[$id].last_period") },
            plants = plants, state = state.code, semantics = state.semantics,
            agencyShortName = state.agencyShortName, towns = SnapshotDecoder.clean(w.towns),
            sitePath = w.sitePath, monthsNote = monthsNote,
        )
        return water to ignoredPlants
    }
}

// v2 wire DTOs.

@Serializable
internal class SnapshotV2DTO(
    @SerialName("generated_at") val generatedAt: String,
    val states: List<StateDTO>,
    val waters: List<WaterV2DTO>,
    @SerialName("this_week") val thisWeek: List<ThisWeekDTO>,
)

@Serializable
internal class AgencyDTO(val name: String, @SerialName("short_name") val shortName: String, val url: String)

@Serializable
internal class StateSourceDTO(
    val name: String,
    val url: String,
    @SerialName("fetched_at") val fetchedAt: String,
    @SerialName("content_sha256") val contentSHA256: String,
    @SerialName("last_modified") val lastModified: String? = null,
)

@Serializable
internal class ChecksDTO(
    @SerialName("last_attempt_at") val lastAttemptAt: String,
    @SerialName("last_success_at") val lastSuccessAt: String,
    @SerialName("last_attempt_ok") val lastAttemptOK: Boolean,
)

@Serializable
internal class LicenseSourceV2DTO(
    val name: String,
    val url: String,
    @SerialName("terms_url") val termsURL: String,
    @SerialName("terms_read_on") val termsReadOn: String,
    @SerialName("commercial_reuse") val commercialReuse: String,
    @SerialName("attribution_required") val attributionRequired: Boolean,
    @SerialName("terms_quote") val termsQuote: String? = null,
)

@Serializable
internal class LicenseV2DTO(val summary: String, val sources: List<LicenseSourceV2DTO>)

@Serializable
internal class CountyV2DTO(val name: String, val region: String? = null)

@Serializable
internal class PeriodV2DTO(val precision: String, val start: String, val end: String, val label: String)

@Serializable
internal class StateDTO(
    val code: String,
    val name: String,
    val agency: AgencyDTO,
    val semantics: String,
    @SerialName("date_precisions") val datePrecisions: List<String>,
    @SerialName("removal_inference") val removalInference: Boolean,
    @SerialName("current_week") val currentWeek: WeekDTO,
    @SerialName("as_of") val asOf: String,
    @SerialName("newest_record") val newestRecord: PeriodV2DTO? = null,
    @SerialName("recency_note") val recencyNote: String? = null,
    val source: StateSourceDTO,
    val checks: ChecksDTO,
    val attribution: AttributionDTO,
    val disclaimer: String,
    val license: LicenseV2DTO,
    val regions: List<RegionDTO>,
    val counties: List<CountyV2DTO>,
    @SerialName("waters_count") val watersCount: Int,
)

@Serializable
internal class PlantV2DTO(
    val period: PeriodV2DTO,
    val species: String,
    val status: String,
    val count: Int? = null,
    @SerialName("first_observed_at") val firstObservedAt: String,
    @SerialName("last_observed_at") val lastObservedAt: String,
)

@Serializable
internal class WaterV2DTO(
    val id: String,
    val state: String,
    val name: String,
    @SerialName("name_status") val nameStatus: String,
    val slug: String,
    val aliases: List<String>? = null,
    val counties: List<String>,
    val towns: List<String>? = null,
    val region: String? = null,
    @SerialName("source_url") val sourceURL: String,
    @SerialName("site_path") val sitePath: String? = null,
    val location: LocationDTO? = null,
    @SerialName("last_period") val lastPeriod: PeriodV2DTO? = null,
    @SerialName("months_note") val monthsNote: String? = null,
    val plants: List<PlantV2DTO>,
)
