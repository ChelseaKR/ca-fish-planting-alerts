import XCTest
@testable import PlantingCore

final class WaterLocationsTests: XCTestCase {
    private func table(_ entries: String, schema: String = WaterLocationTable.schema) throws -> WaterLocationTable {
        try WaterLocationTable.decode(Data("""
        {"schema": "\(schema)", "generated_on": "2026-10-12", "locations": {\(entries)}}
        """.utf8))
    }

    private let lake = #""cdfw-1": {"lat": 37.60259, "lon": -118.74466, "source": "USGS National Hydrography Dataset", "kind": "waterbody"}"#
    private let stream = #""cdfw-2": {"lat": 38.70499, "lon": -120.21436, "source": "USGS National Hydrography Dataset", "kind": "stream_point"}"#

    private func snapshot(thisWeek: [Water.ID]) -> Snapshot {
        let base = TS.snapshot(sourceWeek: "2026-10-11", waters: [
            TS.water(id: "cdfw-1", name: "Crowley Lake", plants: []),
            TS.water(id: "cdfw-2", name: "American River Silver Fork", plants: []),
            TS.water(id: "cdfw-3", name: "Twin Lakes", plants: []),
        ])
        return Snapshot(schemaVersion: base.schemaVersion, generatedAt: base.generatedAt, source: base.source,
                        sourceWeek: base.sourceWeek, attribution: base.attribution, license: base.license,
                        regions: base.regions, counties: base.counties, species: base.species, waters: base.waters,
                        thisWeek: thisWeek.map { ThisWeekEntry(waterID: $0, species: "Trout") }, coverage: base.coverage)
    }

    func testDecodesKindsAndApproximateStreams() throws {
        let t = try table([lake, stream].joined(separator: ","))
        XCTAssertEqual(t.generatedOn, "2026-10-12")
        XCTAssertEqual(t.locations["cdfw-1"]?.kind, .waterbody)
        XCTAssertEqual(t.locations["cdfw-1"]?.isApproximate, false)
        XCTAssertEqual(t.locations["cdfw-2"]?.kind, .streamPoint)
        XCTAssertEqual(t.locations["cdfw-2"]?.isApproximate, true)
    }

    func testRefusesAnotherSchemaAndPointsOutsideCalifornia() {
        XCTAssertThrowsError(try table(lake, schema: "other")) {
            XCTAssertEqual($0 as? WaterLocationTable.DecodeError, .wrongSchema("other"))
        }
        let seattle = #""cdfw-9": {"lat": 47.6, "lon": -122.3, "source": "x", "kind": "waterbody"}"#
        XCTAssertThrowsError(try table(seattle)) {
            XCTAssertEqual($0 as? WaterLocationTable.DecodeError, .outOfRange("cdfw-9"))
        }
    }

    func testOnlyWatersWithALocationGetAPin() throws {
        let pins = snapshot(thisWeek: ["cdfw-2", "cdfw-3"]).mapPins(try table([lake, stream].joined(separator: ",")))
        XCTAssertEqual(pins.map(\.id), ["cdfw-2", "cdfw-1"])  // by name
        // Negative control: Twin Lakes is scheduled this week but has no
        // location, and still gets no pin.
        XCTAssertFalse(pins.contains { $0.id == "cdfw-3" })
        XCTAssertEqual(pins.first { $0.id == "cdfw-2" }?.isThisWeek, true)
        XCTAssertEqual(pins.first { $0.id == "cdfw-1" }?.isThisWeek, false)
        XCTAssertEqual(pins.first { $0.id == "cdfw-2" }?.isApproximate, true)
        XCTAssertTrue(snapshot(thisWeek: []).mapPins(.empty).isEmpty)
    }

    func testTheSnapshotsOwnLocationWins() throws {
        let own = GeoLocation(lat: 38.0, lon: -120.0, source: "v2", kind: .namedPoint)
        let w = Water(id: "cdfw-1", cdfwStockID: 1, name: "Crowley Lake", nameReviewed: true, slug: "crowley-lake",
                      aliases: [], counties: ["Mono"], region: "R6",
                      cdfwMapURL: URL(string: "https://nrm.dfg.ca.gov/FishPlants/")!,
                      location: own, lastListedWeek: nil, plants: [])
        XCTAssertEqual(try table(lake).location(for: w), own)
    }

    func testNearestIsSortedAndLimited() throws {
        let pins = snapshot(thisWeek: []).mapPins(try table([lake, stream].joined(separator: ",")))
        // Mammoth Lakes: Crowley Lake is about 13 miles away, the Silver Fork
        // about 120.
        let near = NearMe.nearest(toLat: 37.6485, lon: -118.9721, pins: pins)
        XCTAssertEqual(near.map(\.id), ["cdfw-1", "cdfw-2"])
        XCTAssertEqual(near[0].meters, 20_700, accuracy: 1_500)
        XCTAssertEqual(NearMe.nearest(toLat: 37.6485, lon: -118.9721, pins: pins, limit: 1).map(\.id), ["cdfw-1"])
        XCTAssertTrue(NearMe.nearest(toLat: 37.6485, lon: -118.9721, pins: pins, limit: -3).isEmpty)
    }

    func testHaversineKnownDistance() {
        // San Francisco to Los Angeles city halls: about 559 km.
        let m = NearMe.meters(fromLat: 37.7793, lon: -122.4193, toLat: 34.0537, lon: -118.2427)
        XCTAssertEqual(m, 559_000, accuracy: 3_000)
        XCTAssertEqual(NearMe.meters(fromLat: 38, lon: -120, toLat: 38, lon: -120), 0, accuracy: 0.001)
    }

    func testMilesText() {
        XCTAssertEqual(NearMe.milesText(643.7), "0.4 mi")
        XCTAssertEqual(NearMe.milesText(19_312.1), "12 mi")
        XCTAssertEqual(NearMe.milesText(209_214.7), "130 mi")
    }

    func testWordingNeverPretendsAStreamIsExact() {
        XCTAssertTrue(LocationWording.summary(nil).hasPrefix("No map location."))
        XCTAssertTrue(LocationWording.summary(GeoLocation(lat: 38, lon: -120, source: "x", kind: .streamPoint))
            .hasPrefix("Approximate"))
        XCTAssertEqual(LocationWording.summary(GeoLocation(lat: 38, lon: -120, source: "x", kind: .waterbody)),
                       "A point inside the lake.")
        XCTAssertFalse(LocationWording.summary(GeoLocation(lat: 38, lon: -120, source: "x", kind: .namedPoint))
            .contains("Approximate"))
    }

    func testTheBundledAppTableDecodes() throws {
        let thisFile = URL(fileURLWithPath: #filePath)
        let ios = thisFile.deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let data = try Data(contentsOf: ios.appendingPathComponent("CAFishPlanting/Resources/water-locations.json"))
        let t = try WaterLocationTable.decode(data)
        XCTAssertGreaterThan(t.locations.count, 200)
        XCTAssertTrue(t.locations.values.allSatisfy { $0.kind != nil })
    }
}
