import XCTest
@testable import PlantingCore

final class AlertMutesTests: XCTestCase {
    private func alert(_ id: Water.ID) -> PlannedNotification {
        PlannedNotification(waterID: id, waterName: "Water \(id)",
                            newKeys: [PlantKey(weekStart: PlainDate(year: 2026, month: 9, day: 13), species: "Rainbow trout")])
    }

    func testAMutedWaterGetsNoAlertAndTheOthersStillDo() {
        var muted = MutedWaters()
        muted.mute("cdfw-1")
        let shown = muted.unmuted([alert("cdfw-1"), alert("cdfw-2")])
        XCTAssertEqual(shown.map(\.waterID), ["cdfw-2"])
    }

    func testUnmutingLetsAlertsThroughAgain() {
        var muted = MutedWaters(ids: ["cdfw-1"])
        muted.unmute("cdfw-1")
        XCTAssertTrue(muted.isEmpty)
        XCTAssertEqual(muted.unmuted([alert("cdfw-1")]).count, 1)
    }

    /// Muting is a filter after the plan, not a change to it: the planner
    /// still moves a muted water's baseline forward, so unmuting later never
    /// announces the weeks it missed while muted.
    func testMutingLeavesTheBaselineMovingForward() throws {
        let snapshot = try SnapshotDecoder().decode(Data(Fixture.minimalValid.utf8))
        let id = try XCTUnwrap(snapshot.waters.first?.id)
        let plan = AlertPlanner.plan(snapshot: snapshot, favorites: [id], state: AlertState())
        XCTAssertFalse(plan.notifications.isEmpty, "the fixture's listed plants are new against an empty baseline")
        let muted = MutedWaters(ids: [id])
        XCTAssertTrue(muted.unmuted(plan.notifications).isEmpty)
        let next = AlertPlanner.plan(snapshot: snapshot, favorites: [id], state: plan.state)
        XCTAssertTrue(next.notifications.isEmpty, "the muted water's baseline still advanced")
    }

    func testMutedWatersRoundTripAndAMissingOrCorruptFileReadsAsNoneMuted() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-mutes-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let layout = AppStorageLayout(directory: dir)
        let store = MutedWatersStore(layout: layout)
        XCTAssertTrue(store.load().isEmpty)
        try store.save(MutedWaters(ids: ["cdfw-7"]))
        XCTAssertEqual(store.load(), MutedWaters(ids: ["cdfw-7"]))
        try Data("not json".utf8).write(to: layout.mutedWatersFile)
        XCTAssertTrue(store.load().isEmpty, "a corrupt file can only turn alerts back on")
    }

    /// iOS keeps the registered category by these strings; a change would
    /// leave alerts already delivered without their button.
    func testTheAlertActionIdentifiersDoNotChange() {
        XCTAssertEqual(PlantingAlertAction.categoryIdentifier, "TT_PLANTING_ALERT")
        XCTAssertEqual(PlantingAlertAction.muteIdentifier, "mute")
    }
}
