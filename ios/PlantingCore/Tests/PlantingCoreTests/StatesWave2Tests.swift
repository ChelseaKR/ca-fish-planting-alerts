import XCTest
@testable import PlantingCore

/// Wave 2 (DECISIONS 0028): Michigan and Massachusetts reports, and New
/// York's spring plan, read from the real bundled snapshot.
final class StatesWave2Tests: XCTestCase {
    private func bundled() throws -> Snapshot {
        try SnapshotDecoder().decode(Fixture.bundledAppFixtureData())
    }

    private func bundledJSON() throws -> String {
        String(decoding: try Fixture.bundledAppFixtureData(), as: UTF8.self)
    }

    func testTheBundledSnapshotCarriesEveryStateWithItsWords() throws {
        let s = try bundled()
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "NY", "TN"])
        XCTAssertEqual(s.state(code: "NY")?.semantics, .plan)
        XCTAssertEqual(s.state(code: "MI")?.semantics, .report)
        XCTAssertNotNil(s.state(code: "MI")?.recencyNote)
        let ny = s.waters(inState: "NY")
        XCTAssertFalse(ny.isEmpty)
        for plant in ny.flatMap(\.plants) {
            XCTAssertEqual(plant.week.precision, .approximate)
            XCTAssertTrue(plant.week.label.hasSuffix(", 2026"), plant.week.label)
        }
        XCTAssertTrue(s.waters(inState: "MI").flatMap(\.plants).allSatisfy { $0.species.lowercased().hasSuffix("trout") })
    }

    func testAPlanSaysPlannedForInTheAgencysWordsNeverADate() throws {
        let s = try bundled()
        let water = try XCTUnwrap(s.waters(inState: "NY").first { $0.plants.contains { $0.week.label.hasPrefix("April - third week") } })
        let line = ScheduleWording.lastScheduledLine(for: water, sourceWeek: Week(start: PlainDate(year: 2026, month: 3, day: 1), end: PlainDate(year: 2026, month: 3, day: 7), label: "week of 2026-03-01"))
        XCTAssertTrue(line.hasPrefix("Planned for "), line)
        XCTAssertFalse(line.contains("2026-04"), "never a date: \(line)")
    }

    func testRemindersOnlyForTightPlannedPeriodsInBoughtStatesAndNotMuted() throws {
        let s = try bundled()
        let water = try XCTUnwrap(s.waters(inState: "NY").first { w in
            w.plants.contains { $0.week.spanDays <= ReminderPlanner.maxSpanDays }
        })
        let today = PlainDate(year: 2026, month: 2, day: 1)
        let reminders = ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [], today: today)
        XCTAssertFalse(reminders.isEmpty)
        for r in reminders {
            XCTAssertTrue(r.body.contains(r.periodLabel))
            XCTAssertTrue(r.body.contains("not a date"))
            XCTAssertTrue(r.id.hasPrefix(PlannedReminder.idPrefix))
            let period = try XCTUnwrap(water.plants.first { $0.week.start == r.fireOn }?.week)
            XCTAssertLessThanOrEqual(period.spanDays, ReminderPlanner.maxSpanDays)
        }
        XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["CA"], muted: [], today: today).isEmpty,
                      "a reminder needs New York's purchase")
        XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [water.id], today: today).isEmpty,
                      "a muted favorite gets no reminder")
        XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [], today: PlainDate(year: 2026, month: 12, day: 31)).isEmpty,
                      "no reminder for a period that has begun")
    }

    func testSpringIsTooLooseToRemindAbout() throws {
        let s = try bundled()
        guard let water = s.waters(inState: "NY").first(where: { $0.plants.allSatisfy { $0.week.label.hasPrefix("Spring") } }) else {
            throw XCTSkip("no Spring-only water in this snapshot")
        }
        let reminders = ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [], today: PlainDate(year: 2026, month: 1, day: 1))
        XCTAssertTrue(reminders.isEmpty)
    }

    func testAPlanAlertSaysPlannedAndNeverScheduledOrStocked() {
        let key = PlantKey(weekStart: PlainDate(year: 2026, month: 4, day: 15), species: "Brown Trout", precision: .approximate, text: "April - third week, 2026")
        let n = PlannedNotification(waterID: "ny-x", waterName: "Argyle Lake", newKeys: [key], semantics: .plan, agencyShortName: "NYS DEC")
        XCTAssertEqual(n.title, "Argyle Lake is in the stocking plan")
        XCTAssertTrue(n.body().hasPrefix("Planned for April - third week, 2026 (Brown Trout)"), n.body())
        XCTAssertFalse(n.body().contains("cheduled"))
    }

    func testNegativeControlAReportedPlantInAPlanStateIsRefused() throws {
        let json = try bundledJSON()
        let ny = try XCTUnwrap(json.range(of: "\"state\": \"NY\""))
        let status = try XCTUnwrap(json.range(of: "\"status\": \"listed\"", range: ny.upperBound..<json.endIndex))
        let broken = json.replacingCharacters(in: status, with: "\"status\": \"reported\"")
        XCTAssertNotEqual(broken, json)
        XCTAssertThrowsError(try SnapshotDecoder().decode(Data(broken.utf8)))
    }

    func testNegativeControlAnApproximateLabelWithoutItsYearIsRefused() throws {
        let json = try bundledJSON()
        let broken = json.replacingOccurrences(of: "\"label\": \"April - third week, 2026\"", with: "\"label\": \"April - third week\"")
        XCTAssertNotEqual(broken, json)
        XCTAssertThrowsError(try SnapshotDecoder().decode(Data(broken.utf8)))
    }

    func testNewYorksProductIsItsOwn() {
        XCTAssertEqual(StateAccess.productID(forState: "NY"), "com.chelseakr.cafishplanting.state.ny")
        XCTAssertEqual(StateAccess.productID(forState: "CA"), "com.chelseakr.cafishplanting.fullaccess")
        XCTAssertEqual(StateAccess.allProductIDs.count, 5)
    }
}
