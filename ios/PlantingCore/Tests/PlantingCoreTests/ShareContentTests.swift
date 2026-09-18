import XCTest
@testable import PlantingCore

final class ShareContentTests: XCTestCase {
    private let siteURL = SnapshotEndpoint.siteWaterURL(slug: "test-lake")!

    /// The message minus the product name. "Trout Truck" contains "Trout",
    /// which is a brand, not a species claim, so species assertions run on
    /// the rest of the message.
    private func withoutBrand(_ message: String) -> String {
        message.replacingOccurrences(of: ShareContent.productName, with: "")
    }

    func testMessageNamesTheWaterAndTheRealLastScheduledSpeciesAndWeek() {
        let water = TS.water(id: "cdfw-1", name: "Test Lake", plants: [
            TS.plant("2026-08-30", species: "Catfish"),
            TS.plant("2026-09-06", species: "Trout"),
        ])
        XCTAssertEqual(water.lastListedWeek?.label, "week of 2026-09-06")

        let message = ShareContent.message(for: water, siteURL: siteURL)

        XCTAssertTrue(message.contains("Test Lake"), "should name the water")
        XCTAssertTrue(message.contains("Trout Truck"), "should name the product (DECISIONS 0010)")
        XCTAssertTrue(message.contains("Last scheduled for the week of 2026-09-06: Trout."),
                       "should state the real species and week for the real last-listed plant, not the earlier catfish week")
        XCTAssertFalse(message.contains("Catfish"), "must not surface an older week's species as the current status")
        XCTAssertTrue(message.contains(siteURL.absoluteString), "should include the real per-water site URL")
        XCTAssertFalse(message.localizedCaseInsensitiveContains("stocked"),
                        "schema/README.md: never say \"stocked\"")
        XCTAssertFalse(message.localizedCaseInsensitiveContains("planted"),
                        "CDFW publishes scheduled plants: never claim one was planted")
    }

    func testMessageJoinsMultipleSpeciesListedTheSameWeek() {
        let water = TS.water(id: "cdfw-2", name: "Twin Water", plants: [
            TS.plant("2026-09-06", species: "Trout"),
            TS.plant("2026-09-06", species: "Catfish"),
        ])

        let message = ShareContent.message(for: water, siteURL: siteURL)

        XCTAssertTrue(message.contains("Last scheduled for the week of 2026-09-06: Trout, Catfish."))
    }

    func testMessageForAWaterWithNoHistoryNeverClaimsAPlanting() {
        let water = TS.water(id: "cdfw-3", name: "Empty Water", plants: [])
        XCTAssertNil(water.lastListedWeek)

        let message = ShareContent.message(for: water, siteURL: siteURL)

        XCTAssertTrue(message.contains("Not on the schedule for any week so far in this app's history."))
        XCTAssertFalse(message.contains("Last scheduled"), "no real last-scheduled week exists — must not invent one")
        XCTAssertFalse(withoutBrand(message).localizedCaseInsensitiveContains("trout"),
                        "must not name a species with nothing in the real history to back it")
    }

    func testMessageForAWaterWhoseOnlyPlantsAreFutureOrRemovedNeverClaimsAPlanting() {
        // lastListedWeek is nil whenever there is no *listed*, non-future
        // plant — a removed (cancelled) plant must not read as a real one.
        let water = TS.water(id: "cdfw-4", name: "Cancelled Water", plants: [
            TS.plant("2026-09-20", species: "Trout", status: .removed),
        ])
        XCTAssertNil(water.lastListedWeek)

        let message = ShareContent.message(for: water, siteURL: siteURL)

        XCTAssertTrue(message.contains("Not on the schedule for any week so far in this app's history."))
        XCTAssertFalse(withoutBrand(message).contains("Trout"), "a removed/cancelled plant is not a real planting")
    }

    func testMessageOmitsTheLinkSentenceRatherThanFabricatingAURLWhenNoneIsAvailable() {
        let water = TS.water(id: "cdfw-5", name: "No Link Water", plants: [TS.plant("2026-09-06")])

        let message = ShareContent.message(for: water, siteURL: nil)

        XCTAssertFalse(message.contains("http"), "must not invent a URL when the site URL can't be formed")
        XCTAssertTrue(message.contains("No Link Water"))
    }
}
