package com.chelseakr.cafishplanting.core

import java.io.File
import java.time.Instant

/** The same builders as `TS` in ios/PlantingCore's tests, so a scenario means the same thing on both. */
object TS {
    fun date(iso: String): PlainDate = PlainDate.parse(iso)!!

    fun week(sundayISO: String): Week {
        val start = date(sundayISO)
        return Week(start, start.plusDays(6), "week of $sundayISO")
    }

    fun plant(sundayISO: String, species: String = "Trout", status: PlantStatus = PlantStatus.LISTED): Plant =
        Plant(week(sundayISO), species, status, Instant.EPOCH, Instant.EPOCH)

    fun water(id: String, name: String = "Test Lake", plants: List<Plant>, counties: List<String> = listOf("Siskiyou"), aliases: List<String> = emptyList()): Water =
        Water(
            id = id,
            cdfwStockID = 1,
            name = name,
            nameReviewed = true,
            slug = "test-lake",
            aliases = aliases,
            counties = counties,
            region = "R1",
            cdfwMapURL = "https://nrm.dfg.ca.gov/FishPlants/",
            location = null,
            lastListedWeek = plants.lastOrNull { it.status == PlantStatus.LISTED }?.week,
            plants = plants,
        )

    fun snapshot(sourceWeek: String, waters: List<Water>, thisWeek: List<ThisWeekEntry> = emptyList()): Snapshot = Snapshot(
        schemaVersion = 1,
        generatedAt = Instant.EPOCH,
        source = SourceInfo(
            "CDFW Fish Planting Schedule", "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch", Instant.EPOCH,
            date(sourceWeek), date(sourceWeek), date(sourceWeek), "a".repeat(64),
        ),
        sourceWeek = week(sourceWeek),
        attribution = Attribution("CDFW", "https://nrm.dfg.ca.gov/FishPlants/"),
        license = License("test", emptyList()),
        regions = listOf(Region("R1", "Northern")),
        counties = listOf(County("Siskiyou", "R1")),
        species = listOf("Trout"),
        waters = waters,
        thisWeek = thisWeek,
        coverage = Coverage(0, 0, waters.size, 0, 0, 0, 0, 0.0),
    )

    val repoRoot: File by lazy {
        System.getProperty("repoRoot")?.let(::File)
            ?: generateSequence(File("").absoluteFile) { it.parentFile }.first { File(it, "ios/PlantingCore").isDirectory }
    }

    val swiftFixtures: File get() = File(repoRoot, "ios/PlantingCore/Tests/PlantingCoreTests/Fixtures")

    /** The v1 snapshot the Android app ships (android/scripts/sync-bundled-snapshot.sh). */
    val bundledSnapshot: File get() = File(repoRoot, "android/app/src/main/assets/snapshot.json")

    /** The one-water fixture `Fixture.minimalValid` in the Swift tests. */
    val minimalValid = """
    {
      "schema_version": 1,
      "generated_at": "2026-09-13T06:12:44Z",
      "source": {
        "name": "CDFW Fish Planting Schedule",
        "url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch",
        "fetched_at": "2026-09-13T06:10:02Z",
        "stated_today": "2026-09-13",
        "stated_period": { "start": "2026-04-05", "end": "2026-09-27" },
        "content_sha256": "${"a".repeat(64)}"
      },
      "source_week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
      "attribution": { "text": "Planting data: California Department of Fish and Wildlife.", "url": "https://nrm.dfg.ca.gov/FishPlants/" },
      "licence": {
        "summary": "Public domain, CDFW CC-BY.",
        "sources": [ { "name": "CDFW Fish Planting Schedule", "url": "https://nrm.dfg.ca.gov/FishPlants/",
          "terms_url": "https://wildlife.ca.gov/Conditions-of-Use", "terms_read_on": "2026-09-13",
          "commercial_reuse": "permitted", "attribution_required": true } ]
      },
      "regions": [ { "code": "R1", "name": "Northern" } ],
      "counties": [ { "name": "Siskiyou", "region": "R1" } ],
      "species": [ "Trout" ],
      "waters": [ {
          "id": "cdfw-1001", "cdfw_stock_id": 1001, "name": "Lake Siskiyou", "name_status": "reviewed",
          "slug": "lake-siskiyou", "aliases": [], "counties": [ "Siskiyou" ], "region": "R1",
          "cdfw_map_url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch?stockid=1001", "location": null,
          "last_listed_week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
          "plants": [
            { "week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
              "species": "Trout", "status": "listed", "first_observed_at": "2026-09-13T06:10:02Z", "last_observed_at": "2026-09-13T06:10:02Z" },
            { "week": { "start": "2026-09-20", "end": "2026-09-26", "label": "week of 2026-09-20" },
              "species": "Trout", "status": "listed", "first_observed_at": "2026-09-13T06:10:02Z", "last_observed_at": "2026-09-13T06:10:02Z" }
          ] } ],
      "this_week": [ { "water_id": "cdfw-1001", "species": "Trout" } ],
      "coverage": { "waters_this_week": 1, "waters_known": 895, "waters_with_history": 1, "names_matched": 1,
        "names_seen": 1, "rows_parsed": 2, "weeks_of_history_min": 2, "weeks_of_history_median": 2 }
    }
    """.trimIndent()
}
