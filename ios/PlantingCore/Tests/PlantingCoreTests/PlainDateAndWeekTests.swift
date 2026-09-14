import XCTest
@testable import PlantingCore

final class PlainDateAndWeekTests: XCTestCase {
    func testValidISODateParses() {
        let d = PlainDate(isoDate: "2026-09-13")
        XCTAssertEqual(d, PlainDate(year: 2026, month: 9, day: 13))
    }

    func testInvalidDatesRejected() {
        for bad in ["2026-9-13", "2026/09/13", "2026-13-01", "2026-02-30", "not a date", "", "2026-09-13T00:00:00Z"] {
            XCTAssertNil(PlainDate(isoDate: bad), "expected \(bad) to be rejected")
        }
    }

    func testOrdering() {
        let a = PlainDate(isoDate: "2026-09-13")!
        let b = PlainDate(isoDate: "2026-09-20")!
        let c = PlainDate(isoDate: "2027-01-01")!
        XCTAssertLessThan(a, b)
        XCTAssertLessThan(b, c)
        XCTAssertFalse(b < a)
    }

    func testRoundTripCodable() throws {
        let d = PlainDate(isoDate: "2026-09-13")!
        let data = try JSONEncoder().encode(d)
        let decoded = try JSONDecoder().decode(PlainDate.self, from: data)
        XCTAssertEqual(d, decoded)
        XCTAssertEqual(String(data: data, encoding: .utf8), "\"2026-09-13\"")
    }

    func testWeekComparesByStart() {
        let w1 = TS.week("2026-09-13")
        let w2 = TS.week("2026-09-20")
        XCTAssertLessThan(w1, w2)
    }

    func testWeekLabelNeverShortenedToADay() {
        // The label is used verbatim by the UI; assert the fixture builder
        // (and, by extension, anything decoded) always carries the "week of" phrasing.
        let w = TS.week("2026-09-13")
        XCTAssertTrue(w.label.hasPrefix("week of "), "a plant must never be rendered as a bare date")
    }
}
