import Foundation
@testable import PlantingCore

/// Builders for constructing `Snapshot`/`Water`/`Plant` directly (not via
/// JSON) so pure-logic tests (`AlertPlanner`) don't need a decoder round trip.
enum TS {
    static func date(_ iso: String) -> PlainDate { PlainDate(isoDate: iso)! }

    static func week(_ sundayISO: String) -> Week {
        let start = date(sundayISO)
        let endDate = Calendar(identifier: .gregorian).date(byAdding: .day, value: 6, to: start.noonUTC)!
        var cal = Calendar(identifier: .gregorian); cal.timeZone = TimeZone(identifier: "UTC")!
        let comps = cal.dateComponents([.year, .month, .day], from: endDate)
        let end = PlainDate(year: comps.year!, month: comps.month!, day: comps.day!)
        return Week(start: start, end: end, label: "week of \(sundayISO)")
    }

    static func plant(_ sundayISO: String, species: String = "Trout", status: PlantStatus = .listed) -> Plant {
        Plant(week: week(sundayISO), species: species, status: status, firstObservedAt: Date(timeIntervalSince1970: 0), lastObservedAt: Date(timeIntervalSince1970: 0))
    }

    static func water(id: String, name: String = "Test Lake", plants: [Plant]) -> Water {
        Water(id: id, cdfwStockID: 1, name: name, nameReviewed: true, slug: "test-lake",
              aliases: [], counties: ["Siskiyou"], region: "R1",
              cdfwMapURL: URL(string: "https://nrm.dfg.ca.gov/FishPlants/")!,
              location: nil, lastListedWeek: plants.last(where: { $0.status == .listed })?.week, plants: plants)
    }

    static func snapshot(sourceWeek: String, waters: [Water]) -> Snapshot {
        Snapshot(
            schemaVersion: 1,
            generatedAt: Date(timeIntervalSince1970: 0),
            source: SourceInfo(name: "CDFW Fish Planting Schedule", url: URL(string: "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch")!,
                                fetchedAt: Date(timeIntervalSince1970: 0), statedToday: date(sourceWeek),
                                statedPeriodStart: date(sourceWeek), statedPeriodEnd: date(sourceWeek), contentSHA256: String(repeating: "a", count: 64)),
            sourceWeek: week(sourceWeek),
            attribution: Attribution(text: "CDFW", url: URL(string: "https://nrm.dfg.ca.gov/FishPlants/")!),
            licence: Licence(summary: "test", sources: []),
            regions: [Region(code: "R1", name: "Northern")],
            counties: [County(name: "Siskiyou", region: "R1")],
            species: ["Trout"],
            waters: waters,
            thisWeek: [],
            coverage: Coverage(watersThisWeek: 0, watersKnown: 0, watersWithHistory: waters.count, namesMatched: 0, namesSeen: 0, rowsParsed: 0, weeksOfHistoryMin: 0, weeksOfHistoryMedian: 0)
        )
    }
}
