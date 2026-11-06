import XCTest
@testable import PlantingCore

/// A state whose latest check failed (source-outage audit 2026-11-05, TT-1):
/// the widget, the watch, Siri and the alerts footer say TWRA couldn't be
/// checked since the last good read, and never show that read's weeks as the
/// current schedule. Each test has its control: the same snapshot with the
/// check marked good says the schedule's words, so the change is the flag's.
final class StateCheckWordingTests: XCTestCase {
    private let tellico = "tn-monroe-tellico-river"
    private let now = ISO8601DateFormatter().date(from: "2026-10-14T19:00:00Z")!

    private func v2(tnFailed: Bool) throws -> Snapshot {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/v2-all-states.json")
        var data = try Data(contentsOf: url)
        if tnFailed { data = try MultiStateParityTests.failingChecks(data, ["TN": "2026-10-14T13:22:00Z"]) }
        return try SnapshotDecoder().decode(data)
    }

    private func digest(_ snapshot: Snapshot) -> WidgetDigest {
        WidgetDigest(snapshot: snapshot, meta: SnapshotMeta(lastAttemptAt: now, lastSuccessAt: now, lastOutcome: "updated"),
                     favorites: [tellico, "cdfw-2227"], locked: false, entitledStates: ["CA", "TN"])
    }

    func testTheFailedSinceDateIsTheLastGoodRead() throws {
        let tn = try XCTUnwrap(try v2(tnFailed: true).state(code: "TN"))
        XCTAssertEqual(StateCheckWording.failedSince(tn)?.isoDate, "2026-10-12")
        XCTAssertEqual(StateCheckWording.notice(tn),
                       "Couldn't check TWRA's schedule since 2026-10-12. What's shown is from that last read and may be out of date.")
        XCTAssertEqual(StateCheckWording.alertsPaused(tn),
                       "Alerts for Tennessee waters are paused until TWRA's schedule can be checked again.")
        // Control: a good check says nothing.
        let ok = try XCTUnwrap(try v2(tnFailed: false).state(code: "TN"))
        XCTAssertNil(StateCheckWording.failedSince(ok))
        XCTAssertNil(StateCheckWording.notice(ok))
        XCTAssertNil(StateCheckWording.alertsPaused(ok))
    }

    func testTheWidgetNeverShowsAFailedStatesOldWeeks() throws {
        let failed = digest(try v2(tnFailed: true))
        let fav = try XCTUnwrap(failed.favorites.first { $0.id == tellico })
        XCTAssertEqual(failed.statusLine(of: fav, at: now), "Couldn't check TWRA's schedule since 2026-10-12")
        XCTAssertEqual(failed.status(of: fav, at: now), .checkFailed(since: PlainDate(isoDate: "2026-10-12")!))
        XCTAssertTrue(fav.speciesThisWeek.isEmpty)
        XCTAssertNil(fav.nextWeek)
        XCTAssertEqual(failed.shortStatus(of: fav, at: now), "Couldn't check")
        XCTAssertEqual(failed.nextScheduledLine(of: fav), "Couldn't check TWRA's schedule since 2026-10-12")
        XCTAssertEqual(failed.favoritesByStatus.last?.id, tellico, "a failed state's favorite sorts last")
        XCTAssertNotEqual(failed.nextFavorite?.id, tellico)
        // Control: with the check good, the same favorite is on the schedule.
        let ok = digest(try v2(tnFailed: false))
        let okFav = try XCTUnwrap(ok.favorites.first { $0.id == tellico })
        XCTAssertFalse(ok.statusLine(of: okFav, at: now).contains("Couldn't check"))
        XCTAssertTrue(ok.statusLine(of: okFav, at: now).hasPrefix("Scheduled"))
    }

    func testTheDigestRoundTripsAtItsNewVersion() throws {
        let failed = digest(try v2(tnFailed: true))
        XCTAssertEqual(failed.version, 4)
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        let back = try decoder.decode(WidgetDigest.self, from: try encoder.encode(failed))
        XCTAssertEqual(back, failed)
    }

    func testSiriSaysTheCheckFailedInsteadOfAnOldWeek() throws {
        let snapshot = try v2(tnFailed: true)
        let water = try XCTUnwrap(snapshot.water(id: tellico))
        let answer = ScheduleAnswer.nextScheduled(for: water, in: snapshot, now: now)
        XCTAssertEqual(answer, "Trout Truck couldn't check TWRA's schedule since 2026-10-12, so it can't say what's current for \(water.name). Open Trout Truck to see what that last read listed.")
        XCTAssertFalse(answer.contains("week of"))
        // Control.
        let ok = try v2(tnFailed: false)
        let okAnswer = ScheduleAnswer.nextScheduled(for: try XCTUnwrap(ok.water(id: tellico)), in: ok, now: now)
        XCTAssertFalse(okAnswer.contains("couldn't check"))
    }

    func testAReportStateSaysItsOwnKind() {
        let since = PlainDate(isoDate: "2026-10-13")!
        XCTAssertEqual(StateCheckWording.short(agencyShortName: "MassWildlife", semantics: .report, since: since),
                       "Couldn't check MassWildlife's stocking report since 2026-10-13")
        XCTAssertEqual(StateCheckWording.short(agencyShortName: "DEC", semantics: .plan, since: since),
                       "Couldn't check DEC's plan since 2026-10-13")
    }

    func testTheWordsKeepTheCopyRules() throws {
        let tn = try XCTUnwrap(try v2(tnFailed: true).state(code: "TN"))
        let lines = [StateCheckWording.notice(tn), StateCheckWording.alertsPaused(tn)].compactMap { $0 }
        for line in lines {
            for word in ["stocked", "planted", "only", "first", "no fish", "none"] {
                XCTAssertFalse(line.lowercased().contains(word), "\(line) says \(word)")
            }
        }
    }
}
