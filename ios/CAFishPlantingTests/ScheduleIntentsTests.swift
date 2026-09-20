import Foundation
import XCTest
@testable import CAFishPlanting
@testable import PlantingCore

/// The Shortcuts action finds waters the way Browse does and answers from
/// the schedule on this iPhone, naming its week.
@MainActor
final class ScheduleIntentsTests: XCTestCase {
    private func bundledSnapshot() throws -> Snapshot {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "snapshot", withExtension: "json"))
        return try SnapshotDecoder().decode(try Data(contentsOf: url))
    }

    func testFindsAWaterByNameCountyOrEveryWordTyped() throws {
        let waters = try bundledSnapshot().waters
        XCTAssertEqual(WaterEntityQuery.matching("annie lake", in: waters).map(\.id), ["cdfw-125"])
        XCTAssertEqual(WaterEntityQuery.matching("ANNIE modoc", in: waters).map(\.id), ["cdfw-125"], "a county word narrows it")
        XCTAssertTrue(WaterEntityQuery.matching("   ", in: waters).isEmpty)
        XCTAssertLessThanOrEqual(WaterEntityQuery.matching("lake", in: waters).count, WaterEntityQuery.maxResults)
    }

    func testTheAnswerComesFromTheSnapshotAndNamesItsWeek() throws {
        let snapshot = try bundledSnapshot()
        let listedID = try XCTUnwrap(snapshot.thisWeek.first?.waterID)
        let water = try XCTUnwrap(snapshot.water(id: listedID))
        let answer = NextScheduledWeekIntent.answer(waterID: water.id, name: water.name, snapshot: snapshot, now: Date())
        XCTAssertTrue(answer.hasPrefix(water.name), answer)
        XCTAssertTrue(answer.contains(snapshot.sourceWeek.label), "the answer names the schedule's week: \(answer)")
        XCTAssertFalse(answer.localizedCaseInsensitiveContains("stocked"))
    }

    /// A water that isn't in the schedule on this iPhone is said plainly,
    /// never answered as "not scheduled".
    func testAWaterTheSnapshotDoesNotHaveIsSaidPlainly() throws {
        let answer = NextScheduledWeekIntent.answer(waterID: "cdfw-gone", name: "Gone Lake", snapshot: try bundledSnapshot(), now: Date())
        XCTAssertEqual(answer, "Trout Truck doesn't have Gone Lake in the schedule on this iPhone. Open Trout Truck to check for a newer one.")
        let noSnapshot = NextScheduledWeekIntent.answer(waterID: "cdfw-125", name: "Annie Lake", snapshot: nil, now: Date())
        XCTAssertTrue(noSnapshot.hasPrefix("Trout Truck doesn't have Annie Lake"))
    }

    func testTheIntentReadsTheSnapshotOnThisDevice() throws {
        XCTAssertNotNil(IntentData.snapshot(), "the intent must find the bundled or downloaded snapshot")
    }
}
