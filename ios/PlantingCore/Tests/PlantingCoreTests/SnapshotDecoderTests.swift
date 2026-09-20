import XCTest
@testable import PlantingCore

final class SnapshotDecoderTests: XCTestCase {
    let decoder = SnapshotDecoder()

    func testMinimalValidDecodes() throws {
        let snapshot = try decoder.decode(Fixture.data(Fixture.minimalValid))
        XCTAssertEqual(snapshot.schemaVersion, 1)
        XCTAssertEqual(snapshot.waters.count, 1)
        XCTAssertEqual(snapshot.sourceWeek.label, "week of 2026-09-13")
        XCTAssertEqual(snapshot.thisWeek.count, 1)
        XCTAssertEqual(snapshot.thisWeek.first?.waterID, "cdfw-1001")
    }

    // MARK: absence states — never a value, never a crash

    func testNullLocationDecodesAsNil() throws {
        let snapshot = try decoder.decode(Fixture.data(Fixture.minimalValid))
        XCTAssertNil(snapshot.waters.first?.location, "absent location must stay nil, never {0,0}")
    }

    func testNullLastListedWeekDecodesAsNil() throws {
        let json = Fixture.minimalValid.replacingOccurrences(
            of: "\"last_listed_week\": { \"start\": \"2026-09-13\", \"end\": \"2026-09-19\", \"label\": \"week of 2026-09-13\" },",
            with: "\"last_listed_week\": null,")
        let snapshot = try decoder.decode(Fixture.data(json))
        XCTAssertNil(snapshot.waters.first?.lastListedWeek, "a water with only future plants has no last-listed week — never defaulted to a fake week")
    }

    func testEmptyAliasesDecodeAsEmptyArrayNotNil() throws {
        let snapshot = try decoder.decode(Fixture.data(Fixture.minimalValid))
        XCTAssertEqual(snapshot.waters.first?.aliases, [])
    }

    func testEmptyThisWeekIsValidNotAnError() throws {
        let json = Fixture.minimalValid.replacingOccurrences(
            of: "\"this_week\": [ { \"water_id\": \"cdfw-1001\", \"species\": \"Trout\" } ],",
            with: "\"this_week\": [],")
        let snapshot = try decoder.decode(Fixture.data(json))
        XCTAssertEqual(snapshot.thisWeek, [], "a fresh page with no plants this week is a real empty state, not a decode failure")
    }

    // MARK: week-of granularity

    func testWeekCarriesStartEndLabelNoDay() throws {
        let snapshot = try decoder.decode(Fixture.data(Fixture.minimalValid))
        let week = try XCTUnwrap(snapshot.waters.first?.plants.first?.week)
        XCTAssertEqual(week.start, PlainDate(isoDate: "2026-09-13"))
        XCTAssertEqual(week.end, PlainDate(isoDate: "2026-09-19"))
        XCTAssertEqual(week.label, "week of 2026-09-13")
    }

    func testPlantsSortedOldestFirst() throws {
        let snapshot = try decoder.decode(Fixture.data(Fixture.minimalValid))
        let weeks = try XCTUnwrap(snapshot.waters.first).plants.map(\.week)
        XCTAssertEqual(weeks, weeks.sorted())
    }

    // MARK: contract violations throw, precisely

    func testUnsupportedSchemaVersionThrows() {
        let json = Fixture.minimalValid.replacingOccurrences(of: "\"schema_version\": 1,", with: "\"schema_version\": 2,")
        XCTAssertThrowsError(try decoder.decode(Fixture.data(json))) { error in
            XCTAssertEqual(error as? SnapshotDecodingError, .unsupportedSchemaVersion(2))
        }
    }

    func testMalformedDateThrows() {
        let json = Fixture.minimalValid.replacingOccurrences(of: "\"stated_today\": \"2026-09-13\",", with: "\"stated_today\": \"Sept 13\",")
        XCTAssertThrowsError(try decoder.decode(Fixture.data(json))) { error in
            guard case .malformed = error as? SnapshotDecodingError else { return XCTFail("expected .malformed, got \(error)") }
        }
    }

    func testBadWaterIDPatternThrows() {
        let json = Fixture.minimalValid.replacingOccurrences(of: "\"id\": \"cdfw-1001\",", with: "\"id\": \"lake-siskiyou\",")
        XCTAssertThrowsError(try decoder.decode(Fixture.data(json)))
    }

    func testDuplicateWaterIDThrows() {
        let dup = Fixture.minimalValid.replacingOccurrences(
            of: "\"waters\": [",
            with: "\"waters\": [ " + waterBlock() + ",")
        XCTAssertThrowsError(try decoder.decode(Fixture.data(dup))) { error in
            guard case .malformed(let message) = error as? SnapshotDecodingError else { return XCTFail("expected .malformed") }
            XCTAssertTrue(message.contains("duplicate"), message)
        }
    }

    /// Replaces the first occurrence only (unlike `replacingOccurrences`),
    /// so a token that legitimately repeats in the fixture can be targeted precisely.
    private func replacingFirst(_ needle: String, with replacement: String, in haystack: String) -> String {
        guard let range = haystack.range(of: needle) else {
            XCTFail("fixture no longer contains \(needle.debugDescription) — update the test")
            return haystack
        }
        return haystack.replacingCharacters(in: range, with: replacement)
    }

    func testUnrecognizedStatusThrows() {
        let json = replacingFirst("\"species\": \"Trout\", \"status\": \"listed\",",
                                   with: "\"species\": \"Trout\", \"status\": \"planted\",",
                                   in: Fixture.minimalValid)
        XCTAssertThrowsError(try decoder.decode(Fixture.data(json)))
    }

    func testWaterWithNoPlantsThrows() {
        // A purpose-built minimal document rather than surgery on the shared
        // fixture, since "plants": [] can't be targeted by a unique substring.
        let emptyPlantsWater = """
        {
          "schema_version": 1,
          "generated_at": "2026-09-13T06:12:44Z",
          "source": { "name": "CDFW Fish Planting Schedule", "url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch",
            "fetched_at": "2026-09-13T06:10:02Z", "stated_today": "2026-09-13",
            "stated_period": { "start": "2026-04-05", "end": "2026-09-27" }, "content_sha256": "\(String(repeating: "a", count: 64))" },
          "source_week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
          "attribution": { "text": "CDFW", "url": "https://nrm.dfg.ca.gov/FishPlants/" },
          "licence": { "summary": "test", "sources": [] },
          "regions": [ { "code": "R1", "name": "Northern" } ],
          "counties": [ { "name": "Siskiyou", "region": "R1" } ],
          "species": [ "Trout" ],
          "waters": [ { "id": "cdfw-1001", "cdfw_stock_id": 1001, "name": "Lake Siskiyou", "name_status": "reviewed",
            "slug": "lake-siskiyou", "aliases": [], "counties": [ "Siskiyou" ], "region": "R1",
            "cdfw_map_url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch?stockid=1001",
            "location": null, "last_listed_week": null, "plants": [] } ],
          "this_week": [],
          "coverage": { "waters_this_week": 0, "waters_known": 895, "waters_with_history": 1,
            "names_matched": 1, "names_seen": 1, "rows_parsed": 0, "weeks_of_history_min": 0, "weeks_of_history_median": 0 }
        }
        """
        XCTAssertThrowsError(try decoder.decode(Fixture.data(emptyPlantsWater)), "the schema requires minItems 1; a water with zero plants should never have been emitted")
    }

    func testUnknownTopLevelKeyIsIgnored() throws {
        let json = Fixture.minimalValid.replacingOccurrences(of: "\"schema_version\": 1,", with: "\"schema_version\": 1, \"a_future_field\": {\"anything\": true},")
        XCTAssertNoThrow(try decoder.decode(Fixture.data(json)), "additive fields must not break decoding — schema/README.md: readers must ignore unknown fields")
    }

    // MARK: the real, larger bundled fixture

    func testBundledAppFixtureDecodesAndIsSelfConsistent() throws {
        let data = try Fixture.bundledAppFixtureData()
        let snapshot = try decoder.decode(data)
        XCTAssertGreaterThan(snapshot.waters.count, 1)

        // this_week must agree with waters[].plants, per schema/README.md's
        // stated pipeline invariant — the app itself checks it too.
        var derived = Set<String>()
        for water in snapshot.waters {
            for plant in water.plants where plant.status == .listed && plant.week == snapshot.sourceWeek {
                derived.insert("\(water.id)|\(plant.species)")
            }
        }
        let declared = Set(snapshot.thisWeek.map { "\($0.waterID)|\($0.species)" })
        XCTAssertEqual(derived, declared, "this_week must be exactly the listed plants in source_week")
    }

    private func waterBlock() -> String {
        """
        {
          "id": "cdfw-1001", "cdfw_stock_id": 1001, "name": "Lake Siskiyou", "name_status": "reviewed",
          "slug": "lake-siskiyou-2", "aliases": [], "counties": ["Siskiyou"], "region": "R1",
          "cdfw_map_url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch?stockid=1001", "location": null,
          "last_listed_week": null,
          "plants": [ { "week": { "start": "2026-09-13", "end": "2026-09-19", "label": "week of 2026-09-13" },
            "species": "Trout", "status": "listed",
            "first_observed_at": "2026-09-13T06:10:02Z", "last_observed_at": "2026-09-13T06:10:02Z" } ]
        }
        """
    }
}
