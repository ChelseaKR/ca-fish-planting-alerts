import XCTest
@testable import PlantingCore

/// The About screen's national wording (DECISIONS 0049): no state is the
/// app's default, California's rule is said as California's, and the
/// unlocked states come from the snapshot, never a list in the code.
final class AboutCopyTests: XCTestCase {
    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/v2-wave2.json")
    }

    private func snapshot() throws -> Snapshot {
        try SnapshotDecoder().decode(Data(contentsOf: Self.fixtureURL))
    }

    func testTheGeneralLinesNameNoStateAndNoAgency() {
        for line in [AboutCopy.whatItDoes, AboutCopy.independence, AboutCopy.otherStates, AboutCopy.checking] {
            XCTAssertFalse(line.contains("California"), line)
            XCTAssertFalse(line.contains("CDFW"), line)
            XCTAssertFalse(line.localizedCaseInsensitiveContains("every state"), line)
            XCTAssertFalse(line.localizedCaseInsensitiveContains("tracking"), line)
        }
        XCTAssertTrue(AboutCopy.independence.contains("not affiliated with or endorsed by any state wildlife agency"))
    }

    func testCaliforniasWeekRuleIsSaidAsCalifornias() {
        XCTAssertTrue(AboutCopy.california.hasPrefix("In California, CDFW publishes the week"))
        XCTAssertTrue(AboutCopy.california.contains("For California waters this app shows a week, never a day"))
        XCTAssertTrue(AboutCopy.alertTiming.contains("each agency updates on its own rhythm (California's schedule is weekly)"))
    }

    /// Unlocked states follow the snapshot's order and names; nothing owned
    /// says nothing, and a product for a state the snapshot doesn't carry
    /// shows no line rather than a made-up name.
    func testUnlockedLinesComeFromTheSnapshot() throws {
        let states = try snapshot().states
        XCTAssertGreaterThan(states.count, 1, "sanity check: the fixture carries several states")
        XCTAssertEqual(AboutCopy.unlockedLines(states: states, entitled: []), [])
        let codes = Set(states.map(\.code))
        let all = AboutCopy.unlockedLines(states: states, entitled: codes.union(["ZZ"]))
        XCTAssertEqual(all, states.map { "\($0.name) unlocked" })
        let last = try XCTUnwrap(states.last)
        XCTAssertEqual(AboutCopy.unlockedLines(states: states, entitled: [last.code]), ["\(last.name) unlocked"])
        XCTAssertEqual(AboutCopy.dataSourceHeader(stateName: last.name), "\(last.name): data source and license")
    }
}
