import XCTest
@testable import PlantingCore

final class ScheduleAnswerTests: XCTestCase {
    private let midWeek = ISO8601DateFormatter().date(from: "2026-09-16T19:00:00Z")!  // Wed, LA
    private let nextSunday = ISO8601DateFormatter().date(from: "2026-09-20T07:30:00Z")! // Sun 00:30, LA

    private func answer(_ water: Water, at now: Date? = nil) -> String {
        let snapshot = TS.snapshot(sourceWeek: "2026-09-13", waters: [water])
        return ScheduleAnswer.nextScheduled(for: water, in: snapshot, now: now ?? midWeek)
    }

    func testListedThisWeek() {
        let water = TS.water(id: "cdfw-1", name: "Lake A", plants: [
            TS.plant("2026-09-13", species: "Rainbow Trout"),
            TS.plant("2026-09-13", species: "Brown Trout"),
            TS.plant("2026-09-27"),
        ])
        XCTAssertEqual(answer(water), "Lake A is on the schedule this week, the week of 2026-09-13 (Rainbow Trout, Brown Trout). After that, the week of 2026-09-27. CDFW gives the week, not the day, and plans can change.")
    }

    func testListedForALaterWeek() {
        let water = TS.water(id: "cdfw-2", name: "Lake B", plants: [
            TS.plant("2026-08-30"),
            TS.plant("2026-09-13", status: .removed),
            TS.plant("2026-10-04"),
        ])
        XCTAssertEqual(answer(water), "Lake B is next scheduled for the week of 2026-10-04 (Trout). CDFW gives the week, not the day, and plans can change.",
                       "a removed week is not a scheduled one")
    }

    func testNotListedNamesTheWeekAndTheLastScheduledOne() {
        let water = TS.water(id: "cdfw-3", name: "Lake C", plants: [TS.plant("2026-07-05")])
        XCTAssertEqual(answer(water), "Lake C isn't on the schedule for the week of 2026-09-13 or later. It was last scheduled for the week of 2026-07-05.")
        let never = TS.water(id: "cdfw-4", name: "Lake D", plants: [])
        XCTAssertEqual(answer(never), "Lake D isn't on the schedule for the week of 2026-09-13 or later. It hasn't been on the schedule in this app's history.")
    }

    /// Once the week has ended (midnight, Los Angeles), "this week" stops
    /// and the answer says the schedule is old.
    func testAnEndedWeekIsNeverThisWeek() {
        let water = TS.water(id: "cdfw-1", name: "Lake A", plants: [TS.plant("2026-09-13")])
        let text = answer(water, at: nextSunday)
        XCTAssertEqual(text, "Lake A is next scheduled for the week of 2026-09-13 (Trout). CDFW gives the week, not the day, and plans can change. This schedule is for the week of 2026-09-13, which has ended. Open Trout Truck to check for a newer one.")
        XCTAssertFalse(text.contains("this week"))
    }

    func testTheAnswerKeepsTheWordingRule() {
        let waters = [
            TS.water(id: "cdfw-1", name: "Lake A", plants: [TS.plant("2026-09-13")]),
            TS.water(id: "cdfw-3", name: "Lake C", plants: [TS.plant("2026-07-05")]),
            TS.water(id: "cdfw-4", name: "Lake D", plants: []),
        ]
        for water in waters {
            for now in [midWeek, nextSunday] {
                let text = answer(water, at: now)
                for word in ["stocked", "planted", "no fish", "confirmed"] {
                    XCTAssertFalse(text.localizedCaseInsensitiveContains(word), "\(text): \(word)")
                }
                XCTAssertTrue(text.contains("week of 2026-09-13"), "every answer names the schedule's week: \(text)")
            }
        }
    }
}
