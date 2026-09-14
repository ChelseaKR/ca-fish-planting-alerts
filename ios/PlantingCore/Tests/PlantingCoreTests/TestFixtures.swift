import Foundation
@testable import PlantingCore

/// Small, hand-written JSON matching `schema/snapshot.v1.json` structurally
/// (the app's decoder does not re-enforce the pipeline's own minItems
/// cardinality rules — e.g. "58 counties" — since a reader must tolerate
/// less than a producer's own build-time guarantees; see
/// `schema/README.md`: "readers must ignore unknown fields"). Tests mutate
/// this via simple string substitution to exercise specific fields without
/// re-typing the whole document each time.
enum Fixture {
    /// One water (`cdfw-1001`), one listed plant in `source_week`
    /// (2026-09-13, a Sunday), one future plant, schema-valid.
    static let minimalValid = """
    {
      "schema_version": 1,
      "generated_at": "2026-09-13T06:12:44Z",
      "source": {
        "name": "CDFW Fish Planting Schedule",
        "url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch",
        "fetched_at": "2026-09-13T06:10:02Z",
        "stated_today": "2026-09-13",
        "stated_period": { "start": "2026-04-05", "end": "2026-09-27" },
        "content_sha256": "\(String(repeating: "a", count: 64))"
      },
      "source_week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
      "attribution": {
        "text": "Planting data: California Department of Fish and Wildlife.",
        "url": "https://nrm.dfg.ca.gov/FishPlants/"
      },
      "licence": {
        "summary": "Public domain, CDFW CC-BY.",
        "sources": [
          {
            "name": "CDFW Fish Planting Schedule",
            "url": "https://nrm.dfg.ca.gov/FishPlants/",
            "terms_url": "https://wildlife.ca.gov/Conditions-of-Use",
            "terms_read_on": "2026-09-13",
            "commercial_reuse": "permitted",
            "attribution_required": true
          }
        ]
      },
      "regions": [ { "code": "R1", "name": "Northern" } ],
      "counties": [ { "name": "Siskiyou", "region": "R1" } ],
      "species": [ "Trout" ],
      "waters": [
        {
          "id": "cdfw-1001",
          "cdfw_stock_id": 1001,
          "name": "Lake Siskiyou",
          "name_status": "reviewed",
          "slug": "lake-siskiyou",
          "aliases": [],
          "counties": [ "Siskiyou" ],
          "region": "R1",
          "cdfw_map_url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch?stockid=1001",
          "location": null,
          "last_listed_week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
          "plants": [
            { "week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
              "species": "Trout", "status": "listed",
              "first_observed_at": "2026-09-13T06:10:02Z", "last_observed_at": "2026-09-13T06:10:02Z" },
            { "week": { "start": "2026-09-20", "end": "2026-09-26", "label": "week of 2026-09-20" },
              "species": "Trout", "status": "listed",
              "first_observed_at": "2026-09-13T06:10:02Z", "last_observed_at": "2026-09-13T06:10:02Z" }
          ]
        }
      ],
      "this_week": [ { "water_id": "cdfw-1001", "species": "Trout" } ],
      "coverage": {
        "waters_this_week": 1, "waters_known": 895, "waters_with_history": 1,
        "names_matched": 1, "names_seen": 1, "rows_parsed": 2,
        "weeks_of_history_min": 2, "weeks_of_history_median": 2
      }
    }
    """

    static func data(_ json: String) -> Data { Data(json.utf8) }

    /// Reads the app's bundled real-shaped fixture from disk via this test
    /// file's own path, independent of SwiftPM resource bundling.
    static func bundledAppFixtureData() throws -> Data {
        let thisFile = URL(fileURLWithPath: #filePath)
        // .../ios/PlantingCore/Tests/PlantingCoreTests/TestFixtures.swift
        // -> .../ios/CAFishPlanting/Resources/snapshot.json
        let iosDir = thisFile
            .deletingLastPathComponent() // PlantingCoreTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // PlantingCore
            .deletingLastPathComponent() // ios
        let path = iosDir.appendingPathComponent("CAFishPlanting/Resources/snapshot.json")
        return try Data(contentsOf: path)
    }
}
