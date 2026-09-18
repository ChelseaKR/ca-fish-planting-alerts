import XCTest
@testable import PlantingCore

final class WaterSearchTests: XCTestCase {
    private func water(_ id: String, _ name: String, counties: [String], aliases: [String] = []) -> Water {
        Water(id: id, cdfwStockID: 1, name: name, nameReviewed: true, slug: id, aliases: aliases,
              counties: counties, region: "R1", cdfwMapURL: URL(string: "https://nrm.dfg.ca.gov/FishPlants/")!,
              location: nil, lastListedWeek: nil, plants: [])
    }

    private lazy var waters = [
        water("cdfw-1", "American River Silver Fork", counties: ["El Dorado"]),
        water("cdfw-2", "Lake Isabella", counties: ["Kern"], aliases: ["Isabella Lake", "Lk Isabella"]),
        water("cdfw-3", "Kern River, Lower", counties: ["Kern"]),
        water("cdfw-4", "Río Hondo Pond", counties: ["Los Angeles"]),
        water("cdfw-5", "Twin Lakes", counties: ["Mono", "Alpine"]),
    ]

    func testEmptySearchMatchesEverythingSortedByName() {
        let search = WaterSearch()
        XCTAssertTrue(search.isEmpty)
        XCTAssertEqual(search.filter(waters).map(\.id), ["cdfw-1", "cdfw-3", "cdfw-2", "cdfw-4", "cdfw-5"])
    }

    func testMatchesNameAliasesAndCountyIgnoringCaseAndAccents() {
        XCTAssertEqual(WaterSearch(text: "isabella").filter(waters).map(\.id), ["cdfw-2"])
        XCTAssertEqual(WaterSearch(text: "lk isab").filter(waters).map(\.id), ["cdfw-2"], "a name CDFW used before still finds the water")
        XCTAssertEqual(WaterSearch(text: "KERN").filter(waters).map(\.id), ["cdfw-3", "cdfw-2"], "a county finds every water in it")
        XCTAssertEqual(WaterSearch(text: "rio hondo").filter(waters).map(\.id), ["cdfw-4"], "accents don't matter")
        XCTAssertEqual(WaterSearch(text: "alpine").filter(waters).map(\.id), ["cdfw-5"], "every county a water spans")
    }

    func testEveryWordMustMatchSomewhere() {
        XCTAssertEqual(WaterSearch(text: "silver fork el dorado").filter(waters).map(\.id), ["cdfw-1"])
        XCTAssertEqual(WaterSearch(text: "kern, lower").filter(waters).map(\.id), ["cdfw-3"])
        XCTAssertEqual(WaterSearch(text: "kern mono").filter(waters), [], "words from two different waters match neither")
        XCTAssertEqual(WaterSearch(text: "   ").filter(waters).count, waters.count, "whitespace is no search")
    }

    func testCountyFilterNarrowsAndCombinesWithText() {
        XCTAssertEqual(WaterSearch(county: "Kern").filter(waters).map(\.id), ["cdfw-3", "cdfw-2"])
        XCTAssertEqual(WaterSearch(text: "lake", county: "Kern").filter(waters).map(\.id), ["cdfw-2"])
        XCTAssertEqual(WaterSearch(county: "Alpine").filter(waters).map(\.id), ["cdfw-5"])
        XCTAssertEqual(WaterSearch(text: "silver", county: "Kern").filter(waters), [])
        XCTAssertFalse(WaterSearch(county: "Kern").isEmpty)
    }

    func testCountiesAreTheOnesTheWatersAreIn() {
        XCTAssertEqual(WaterSearch.counties(of: waters), ["Alpine", "El Dorado", "Kern", "Los Angeles", "Mono"])
        XCTAssertEqual(WaterSearch.counties(of: []), [])
    }
}
