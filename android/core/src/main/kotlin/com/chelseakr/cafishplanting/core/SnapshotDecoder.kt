package com.chelseakr.cafishplanting.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import java.net.URI
import java.net.URISyntaxException
import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeParseException

/** A contract violation. The caller keeps the last good snapshot. */
class SnapshotDecodingException(message: String) : Exception(message) {
    companion object {
        fun unsupportedSchemaVersion(version: Int) = SnapshotDecodingException(
            "Snapshot schema version $version is not supported (this app reads version ${Snapshot.SUPPORTED_SCHEMA_VERSION}).",
        )

        fun malformed(what: String) = SnapshotDecodingException("Snapshot is malformed: $what.")
    }
}

/**
 * Strict decoder for `schema/snapshot.v1.json`, the same checks as
 * `SnapshotDecoder.swift`. Unknown JSON keys are ignored, matching
 * `schema/README.md`'s reader contract; a missing required field, a bad
 * date, a non-https URL, an unknown status or region, a duplicate water or
 * an empty name throws.
 */
object SnapshotDecoder {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = false
        coerceInputValues = false
    }

    val regionCodes: Set<String> = setOf("R1", "R2", "R3", "R4", "R5", "R6")

    fun decode(bytes: ByteArray): Snapshot = decode(bytes.toString(Charsets.UTF_8))

    fun decode(text: String): Snapshot {
        val dto = try {
            json.decodeFromString(SnapshotDTO.serializer(), text)
        } catch (e: SerializationException) {
            throw SnapshotDecodingException.malformed(e.message ?: "not a snapshot document")
        } catch (e: IllegalArgumentException) {
            throw SnapshotDecodingException.malformed(e.message ?: "not a snapshot document")
        }
        if (dto.schemaVersion != Snapshot.SUPPORTED_SCHEMA_VERSION) {
            throw SnapshotDecodingException.unsupportedSchemaVersion(dto.schemaVersion)
        }
        val seen = HashSet<String>()
        val waters = dto.waters.map { w ->
            val water = water(w)
            if (!seen.add(water.id)) throw SnapshotDecodingException.malformed("duplicate water id ${water.id}")
            water
        }
        val thisWeek = dto.thisWeek.map { entry ->
            val id = entry.waterID.trim()
            if (id.isEmpty()) throw SnapshotDecodingException.malformed("this_week entry has an empty water_id")
            val species = entry.species.trim()
            if (species.isEmpty()) throw SnapshotDecodingException.malformed("this_week entry $id has an empty species")
            ThisWeekEntry(id, species)
        }
        val c = dto.coverage
        return Snapshot(
            schemaVersion = dto.schemaVersion,
            generatedAt = datetime(dto.generatedAt, "generated_at"),
            source = SourceInfo(
                name = dto.source.name,
                url = url(dto.source.url, "source.url"),
                fetchedAt = datetime(dto.source.fetchedAt, "source.fetched_at"),
                statedToday = date(dto.source.statedToday, "source.stated_today"),
                statedPeriodStart = date(dto.source.statedPeriod.start, "source.stated_period.start"),
                statedPeriodEnd = date(dto.source.statedPeriod.end, "source.stated_period.end"),
                contentSHA256 = dto.source.contentSHA256,
            ),
            sourceWeek = week(dto.sourceWeek, "source_week"),
            attribution = Attribution(dto.attribution.text, url(dto.attribution.url, "attribution.url")),
            license = License(
                summary = dto.license.summary,
                sources = dto.license.sources.map { s ->
                    val reuse = CommercialReuse.fromWire(s.commercialReuse)
                        ?: throw SnapshotDecodingException.malformed(
                            "license source ${s.name} has an unrecognized commercial_reuse: ${s.commercialReuse}",
                        )
                    LicenseSource(
                        name = s.name,
                        url = url(s.url, "licence.sources[${s.name}].url"),
                        termsURL = url(s.termsURL, "licence.sources[${s.name}].terms_url"),
                        termsReadOn = date(s.termsReadOn, "licence.sources[${s.name}].terms_read_on"),
                        commercialReuse = reuse,
                        attributionRequired = s.attributionRequired,
                    )
                },
            ),
            regions = dto.regions.map { r ->
                if (r.code !in regionCodes) throw SnapshotDecodingException.malformed("region has an unrecognized code: ${r.code}")
                Region(r.code, r.name)
            },
            counties = dto.counties.map { co ->
                if (co.region !in regionCodes) {
                    throw SnapshotDecodingException.malformed("county ${co.name} has an unrecognized region: ${co.region}")
                }
                County(co.name, co.region)
            },
            species = clean(dto.species),
            waters = waters,
            thisWeek = thisWeek,
            coverage = Coverage(
                c.watersThisWeek, c.watersKnown, c.watersWithHistory, c.namesMatched,
                c.namesSeen, c.rowsParsed, c.weeksOfHistoryMin, c.weeksOfHistoryMedian,
            ),
        )
    }

    private fun water(w: WaterDTO): Water {
        val id = w.id.trim()
        if (!id.startsWith("cdfw-") || id.removePrefix("cdfw-").toIntOrNull() == null) {
            throw SnapshotDecodingException.malformed("water id is not cdfw-<digits>: $id")
        }
        val name = w.name.trim()
        if (name.isEmpty()) throw SnapshotDecodingException.malformed("water $id has an empty name")
        val plants = w.plants.map { p ->
            val status = PlantStatus.fromWire(p.status)
                ?: throw SnapshotDecodingException.malformed("waters[$id].plants has an unrecognized status: ${p.status}")
            val species = p.species.trim()
            if (species.isEmpty()) throw SnapshotDecodingException.malformed("waters[$id] has a plant with an empty species")
            Plant(
                week = week(p.week, "waters[$id].plants[].week"),
                species = species,
                status = status,
                firstObservedAt = datetime(p.firstObservedAt, "waters[$id].plants[].first_observed_at"),
                lastObservedAt = datetime(p.lastObservedAt, "waters[$id].plants[].last_observed_at"),
            )
        }
        if (plants.isEmpty()) throw SnapshotDecodingException.malformed("water $id has no plants")
        return Water(
            id = id,
            cdfwStockID = w.cdfwStockID,
            name = name,
            nameReviewed = w.nameStatus == "reviewed",
            slug = w.slug,
            aliases = clean(w.aliases),
            counties = clean(w.counties),
            region = w.region,
            cdfwMapURL = url(w.cdfwMapURL, "waters[$id].cdfw_map_url"),
            location = w.location?.let { GeoLocation(it.lat, it.lon, it.source) },
            lastListedWeek = w.lastListedWeek?.let { week(it, "waters[$id].last_listed_week") },
            plants = plants,
        )
    }

    internal fun clean(list: List<String>?): List<String> = (list ?: emptyList()).map { it.trim() }.filter { it.isNotEmpty() }

    internal fun url(value: String, field: String): String {
        val uri = try {
            URI(value)
        } catch (_: URISyntaxException) {
            null
        }
        if (uri == null || !uri.scheme.equals("https", ignoreCase = true) || uri.host.isNullOrEmpty()) {
            throw SnapshotDecodingException.malformed("$field is not an https URL: $value")
        }
        return value
    }

    internal fun date(value: String, field: String): PlainDate =
        PlainDate.parse(value) ?: throw SnapshotDecodingException.malformed("$field is not a YYYY-MM-DD date: $value")

    internal fun week(dto: WeekDTO, field: String): Week {
        val start = date(dto.start, "$field.start")
        val end = date(dto.end, "$field.end")
        if (end < start) throw SnapshotDecodingException.malformed("$field has end before start")
        return Week(start, end, dto.label)
    }

    private val STRICT_UTC = Regex("""^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$""")
    private val FRACTIONAL = Regex("""^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+(Z|[+-]\d{2}:\d{2})$""")

    /**
     * `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` per `$defs/datetime`, with the
     * same tolerant fallback for fractional seconds as the Swift decoder.
     */
    fun datetime(value: String, field: String): Instant {
        if (STRICT_UTC.matches(value) || FRACTIONAL.matches(value)) {
            try {
                return OffsetDateTime.parse(value).toInstant()
            } catch (_: DateTimeParseException) {
                // Falls through to the refusal below.
            }
        }
        throw SnapshotDecodingException.malformed("$field is not an RFC 3339 UTC timestamp: $value")
    }
}

// Wire DTOs, private to decoding. The public model is [Snapshot].

@Serializable
internal class SnapshotDTO(
    @SerialName("schema_version") val schemaVersion: Int,
    @SerialName("generated_at") val generatedAt: String,
    val source: SourceDTO,
    @SerialName("source_week") val sourceWeek: WeekDTO,
    val attribution: AttributionDTO,
    // The published field name; spelling kept so every v1 file decodes.
    @SerialName("licence") val license: LicenseDTO,
    val regions: List<RegionDTO>,
    val counties: List<CountyDTO>,
    val species: List<String>,
    val waters: List<WaterDTO>,
    @SerialName("this_week") val thisWeek: List<ThisWeekDTO>,
    val coverage: CoverageDTO,
)

@Serializable
internal class SourceDTO(
    val name: String,
    val url: String,
    @SerialName("fetched_at") val fetchedAt: String,
    @SerialName("stated_today") val statedToday: String,
    @SerialName("stated_period") val statedPeriod: PeriodDTO,
    @SerialName("content_sha256") val contentSHA256: String,
)

@Serializable
internal class PeriodDTO(val start: String, val end: String)

@Serializable
internal class WeekDTO(val start: String, val end: String, val label: String)

@Serializable
internal class AttributionDTO(val text: String, val url: String)

@Serializable
internal class LicenseDTO(val summary: String, val sources: List<LicenseSourceDTO>)

@Serializable
internal class LicenseSourceDTO(
    val name: String,
    val url: String,
    @SerialName("terms_url") val termsURL: String,
    @SerialName("terms_read_on") val termsReadOn: String,
    @SerialName("commercial_reuse") val commercialReuse: String,
    @SerialName("attribution_required") val attributionRequired: Boolean,
)

@Serializable
internal class RegionDTO(val code: String, val name: String)

@Serializable
internal class CountyDTO(val name: String, val region: String)

@Serializable
internal class LocationDTO(val lat: Double, val lon: Double, val source: String)

@Serializable
internal class PlantDTO(
    val week: WeekDTO,
    val species: String,
    val status: String,
    @SerialName("first_observed_at") val firstObservedAt: String,
    @SerialName("last_observed_at") val lastObservedAt: String,
)

@Serializable
internal class WaterDTO(
    val id: String,
    @SerialName("cdfw_stock_id") val cdfwStockID: Int,
    val name: String,
    @SerialName("name_status") val nameStatus: String,
    val slug: String,
    val aliases: List<String>? = null,
    val counties: List<String>,
    val region: String,
    @SerialName("cdfw_map_url") val cdfwMapURL: String,
    val location: LocationDTO? = null,
    @SerialName("last_listed_week") val lastListedWeek: WeekDTO? = null,
    val plants: List<PlantDTO>,
)

@Serializable
internal class ThisWeekDTO(@SerialName("water_id") val waterID: String, val species: String)

@Serializable
internal class CoverageDTO(
    @SerialName("waters_this_week") val watersThisWeek: Int,
    @SerialName("waters_known") val watersKnown: Int,
    @SerialName("waters_with_history") val watersWithHistory: Int,
    @SerialName("names_matched") val namesMatched: Int,
    @SerialName("names_seen") val namesSeen: Int,
    @SerialName("rows_parsed") val rowsParsed: Int,
    @SerialName("weeks_of_history_min") val weeksOfHistoryMin: Int,
    @SerialName("weeks_of_history_median") val weeksOfHistoryMedian: Double,
)
