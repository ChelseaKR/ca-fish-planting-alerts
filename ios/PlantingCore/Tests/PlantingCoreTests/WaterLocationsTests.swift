import XCTest
@testable import PlantingCore

final class WaterLocationsTests: XCTestCase {
    private func water(_ id: String, _ name: String, state: String = "CA", location: GeoLocation?) -> Water {
        Water(id: id, cdfwStockID: state == "CA" ? 1 : 0, name: name, nameReviewed: true, slug: id,
              aliases: [], counties: ["Mono"], region: "R6",
              cdfwMapURL: URL(string: "https://nrm.dfg.ca.gov/FishPlants/")!,
              location: location, lastListedWeek: nil, plants: [], state: state)
    }

    private let lake = GeoLocation(lat: 37.60259, lon: -118.74466, source: "USGS National Hydrography Dataset", kind: .waterbody)
    private let stream = GeoLocation(lat: 38.70499, lon: -120.21436, source: "USGS National Hydrography Dataset", kind: .streamPoint)

    private func snapshot(_ waters: [Water], thisWeek: [Water.ID] = []) -> Snapshot {
        let base = TS.snapshot(sourceWeek: "2026-10-11", waters: waters)
        return Snapshot(schemaVersion: base.schemaVersion, generatedAt: base.generatedAt, source: base.source,
                        sourceWeek: base.sourceWeek, attribution: base.attribution, license: base.license,
                        regions: base.regions, counties: base.counties, species: base.species, waters: base.waters,
                        thisWeek: thisWeek.map { ThisWeekEntry(waterID: $0, species: "Trout") }, coverage: base.coverage)
    }

    func testOnlyWatersWithALocationGetAPin() {
        let s = snapshot([
            water("cdfw-1", "Crowley Lake", location: lake),
            water("cdfw-2", "American River Silver Fork", location: stream),
            water("cdfw-3", "Twin Lakes", location: nil),
        ], thisWeek: ["cdfw-2", "cdfw-3"])
        let pins = s.mapPins
        XCTAssertEqual(pins.map(\.id), ["cdfw-2", "cdfw-1"])  // by name
        // Negative control: Twin Lakes is this week's but has no location,
        // and still gets no pin.
        XCTAssertFalse(pins.contains { $0.id == "cdfw-3" })
        XCTAssertEqual(pins.first { $0.id == "cdfw-2" }?.isThisWeek, true)
        XCTAssertEqual(pins.first { $0.id == "cdfw-2" }?.isApproximate, true)
        XCTAssertEqual(pins.first { $0.id == "cdfw-1" }?.isThisWeek, false)
        XCTAssertEqual(pins.first { $0.id == "cdfw-1" }?.state, "CA")
    }

    func testAnotherStatesWaterIsPinnedOnlyWithALocation() {
        let s = snapshot([
            water("cdfw-1", "Crowley Lake", location: lake),
            water("tn-a", "Tellico River", state: "TN", location: GeoLocation(lat: 35.3, lon: -84.2, source: "x", kind: .streamPoint)),
            water("tn-b", "Cove Lake", state: "TN", location: nil),
        ])
        XCTAssertEqual(s.mapPins.map(\.id), ["cdfw-1", "tn-a"])
        XCTAssertEqual(s.mapPins.last?.state, "TN")
    }

    func testTheRealBundledSnapshotIsStateAware() throws {
        let s = try SnapshotDecoder().decode(Fixture.bundledAppFixtureData())
        let coverage = Dictionary(uniqueKeysWithValues: s.mapCoverage.map { ($0.code, $0) })
        // California: the geocoder's confident matches. Tennessee: no location
        // source yet, so no pins at all.
        XCTAssertGreaterThan(coverage["CA"]?.placed ?? 0, 200)
        XCTAssertLessThan(coverage["CA"]?.placed ?? 0, coverage["CA"]?.total ?? 0)
        if let tn = coverage["TN"] {
            XCTAssertEqual(tn.placed, 0)
            XCTAssertGreaterThan(tn.total, 0)
        }
        XCTAssertEqual(s.mapPins.count, s.mapCoverage.map(\.placed).reduce(0, +))
        // v2 says what each point is; the decoder keeps it.
        XCTAssertTrue(s.mapPins.allSatisfy { $0.location.kind != nil })
        XCTAssertTrue(s.mapPins.contains { $0.isApproximate })
    }

    func testUnknownKindDecodesAsNilNotAGuess() throws {
        let dto = try JSONDecoder().decode(LocationDTO.self, from: Data(#"{"lat": 38, "lon": -120, "source": "x", "kind": "guess"}"#.utf8))
        XCTAssertNil(dto.geoLocation.kind)
        XCTAssertFalse(dto.geoLocation.isApproximate)
        let v1 = try JSONDecoder().decode(LocationDTO.self, from: Data(#"{"lat": 38, "lon": -120, "source": "x"}"#.utf8))
        XCTAssertNil(v1.geoLocation.kind)
    }

    func testNearestIsSortedAndLimited() {
        let pins = snapshot([
            water("cdfw-1", "Crowley Lake", location: lake),
            water("cdfw-2", "American River Silver Fork", location: stream),
        ]).mapPins
        // Mammoth Lakes: Crowley Lake is about 13 miles away, the Silver
        // Fork about 120.
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
        XCTAssertTrue(LocationWording.summary(stream).hasPrefix("Approximate"))
        XCTAssertEqual(LocationWording.summary(lake), "A point inside the lake.")
        XCTAssertFalse(LocationWording.summary(GeoLocation(lat: 38, lon: -120, source: "x", kind: .namedPoint))
            .contains("Approximate"))
    }
}
