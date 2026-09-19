import XCTest
@testable import PlantingCore

/// Pure-function tests, no simulator required (`swift test` on macOS). This
/// is deliverable #3's "new week -> notify once, same week -> never twice"
/// requirement.
final class AlertPlannerTests: XCTestCase {

    func testNewWeekNotifiesOnce() {
        let week1Water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-13")])
        let snap1 = TS.snapshot(sourceWeek: "2026-09-13", waters: [week1Water])

        // Seed the baseline at favoriting time: the current week is on screen already.
        let seeded = AlertPlanner.seeding(AlertState(), favoriting: "cdfw-1", snapshot: snap1)
        let plan1 = AlertPlanner.plan(snapshot: snap1, favorites: ["cdfw-1"], state: seeded)
        XCTAssertEqual(plan1.notifications.count, 0, "what's already visible at favorite time must not notify")

        // A refresh a week later reveals a new week's plant.
        let week2Water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-13"), TS.plant("2026-09-20")])
        let snap2 = TS.snapshot(sourceWeek: "2026-09-20", waters: [week2Water])
        let plan2 = AlertPlanner.plan(snapshot: snap2, favorites: ["cdfw-1"], state: plan1.state)
        XCTAssertEqual(plan2.notifications.count, 1)
        XCTAssertEqual(plan2.notifications.first?.newKeys.map(\.weekStart), [TS.date("2026-09-20")])
    }

    func testSameWeekNeverNotifiesTwice() {
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-13"), TS.plant("2026-09-20")])
        let snapshot = TS.snapshot(sourceWeek: "2026-09-20", waters: [water])
        let seeded = AlertPlanner.seeding(AlertState(), favoriting: "cdfw-1", snapshot: snapshot)

        let plan1 = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: seeded)
        XCTAssertEqual(plan1.notifications.count, 0, "nothing new relative to the seed")

        // Evaluate the identical snapshot again (e.g. a 304 refresh, or two BGAppRefreshTask runs).
        let plan2 = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: plan1.state)
        XCTAssertEqual(plan2.notifications.count, 0, "the same week must never notify twice")

        let plan3 = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: plan2.state)
        XCTAssertEqual(plan3.notifications.count, 0)
    }

    func testUnfavoritedWaterNeverNotifies() {
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-20")])
        let snapshot = TS.snapshot(sourceWeek: "2026-09-20", waters: [water])
        let plan = AlertPlanner.plan(snapshot: snapshot, favorites: [], state: AlertState())
        XCTAssertEqual(plan.notifications.count, 0)
        XCTAssertTrue(plan.state.lastListed.isEmpty)
    }

    func testPastPlantsNeverNotify() {
        // A water favorited today whose only plant is in the past (before source_week).
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-08-01")])
        let snapshot = TS.snapshot(sourceWeek: "2026-09-13", waters: [water])
        let seeded = AlertPlanner.seeding(AlertState(), favoriting: "cdfw-1", snapshot: snapshot)
        let plan = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: seeded)
        XCTAssertEqual(plan.notifications.count, 0, "week-of granularity: a past plant is history, never an alert")
    }

    func testRemovedStatusNeverNotifies() {
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-20", status: .removed)])
        let snapshot = TS.snapshot(sourceWeek: "2026-09-13", waters: [water])
        let seeded = AlertPlanner.seeding(AlertState(), favoriting: "cdfw-1", snapshot: snapshot)
        let plan = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: seeded)
        XCTAssertEqual(plan.notifications.count, 0, "a removed plant is not news")
    }

    func testRemovedThenRelistedNotifiesAgain() {
        // Snapshot A: listed. Favorite (seeded at nothing yet, before it appears)...
        let base = AlertState()
        let waterListed = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-20", status: .listed)])
        let snapA = TS.snapshot(sourceWeek: "2026-09-13", waters: [waterListed])
        let planA = AlertPlanner.plan(snapshot: snapA, favorites: ["cdfw-1"], state: base)
        XCTAssertEqual(planA.notifications.count, 1, "first sighting notifies")

        // Snapshot B: CDFW pulled it ("subject to change").
        let waterRemoved = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-20", status: .removed)])
        let snapB = TS.snapshot(sourceWeek: "2026-09-13", waters: [waterRemoved])
        let planB = AlertPlanner.plan(snapshot: snapB, favorites: ["cdfw-1"], state: planA.state)
        XCTAssertEqual(planB.notifications.count, 0)

        // Snapshot C: CDFW relisted the same week — this is news again.
        let waterRelisted = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-20", status: .listed)])
        let snapC = TS.snapshot(sourceWeek: "2026-09-13", waters: [waterRelisted])
        let planC = AlertPlanner.plan(snapshot: snapC, favorites: ["cdfw-1"], state: planB.state)
        XCTAssertEqual(planC.notifications.count, 1, "a relist after removal is newsworthy again, matching schema/README.md's diff rule")
    }

    func testUnfavoritingPrunesState() {
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-13")])
        let snapshot = TS.snapshot(sourceWeek: "2026-09-13", waters: [water])
        let seeded = AlertPlanner.seeding(AlertState(), favoriting: "cdfw-1", snapshot: snapshot)
        XCTAssertNotNil(seeded.lastListed["cdfw-1"])
        let pruned = AlertPlanner.pruning(seeded, unfavoriting: "cdfw-1")
        XCTAssertNil(pruned.lastListed["cdfw-1"])
    }

    func testMultipleNewWeeksInOneRefreshProduceOneNotificationNamingBoth() {
        let waterOld = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-13")])
        let snap1 = TS.snapshot(sourceWeek: "2026-09-13", waters: [waterOld])
        let seeded = AlertPlanner.seeding(AlertState(), favoriting: "cdfw-1", snapshot: snap1)

        let waterNew = TS.water(id: "cdfw-1", plants: [
            TS.plant("2026-09-13"), TS.plant("2026-09-20"), TS.plant("2026-09-27"),
        ])
        let snap2 = TS.snapshot(sourceWeek: "2026-09-13", waters: [waterNew])
        let plan = AlertPlanner.plan(snapshot: snap2, favorites: ["cdfw-1"], state: seeded)
        XCTAssertEqual(plan.notifications.count, 1, "one refresh, one notification per water")
        XCTAssertEqual(plan.notifications.first?.newKeys.count, 2)
    }

    func testNotificationIdentifierIsDeterministic() {
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-09-13"), TS.plant("2026-09-20")])
        let snapshot = TS.snapshot(sourceWeek: "2026-09-20", waters: [water])
        let planA = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: AlertState())
        let planB = AlertPlanner.plan(snapshot: snapshot, favorites: ["cdfw-1"], state: AlertState())
        XCTAssertEqual(planA.notifications.first?.id, planB.notifications.first?.id, "same input, same id — UNUserNotificationCenter dedupes on this")
    }
}
