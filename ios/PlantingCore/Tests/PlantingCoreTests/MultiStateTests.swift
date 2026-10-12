import XCTest
@testable import PlantingCore

/// Snapshot v2 and the per-state rules (docs/adr/0021). The fixture is real
/// pipeline output: California from the 2026-09-13 CDFW fixture, Tennessee
/// from TWRA's real 2026-10-12 file, and Massachusetts and Michigan from the
/// pipeline's labeled synthetic fixtures (their hosts' robots.txt could not
/// be read, so no live data was taken).
final class MultiStateTests: XCTestCase {
    private let decoder = SnapshotDecoder()

    private func v2() throws -> Snapshot {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/v2-all-states.json")
        return try decoder.decode(Data(contentsOf: url))
    }

    private func v2JSON() throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/v2-all-states.json")
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: decoding

    func testV2DecodesEveryStateWithCaliforniaFirst() throws {
        let s = try v2()
        XCTAssertEqual(s.schemaVersion, 2)
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "TN"])
        XCTAssertEqual(s.state(code: "TN")?.semantics, .schedule)
        XCTAssertEqual(s.state(code: "MA")?.semantics, .report)
        XCTAssertNotNil(s.state(code: "MI")?.recencyNote)
        XCTAssertEqual(s.sourceWeek, s.state(code: "CA")?.currentWeek, "the top level is California's, as in v1")
        XCTAssertNil(s.coverage, "v2 has no coverage numbers, and none is made up")
        XCTAssertTrue(s.waters.filter { $0.state == "CA" }.allSatisfy { $0.id.hasPrefix("cdfw-") })
    }

    func testAV1FileIsCaliforniaAlone() throws {
        let s = try decoder.decode(Fixture.data(Fixture.minimalValid))
        XCTAssertEqual(s.states.map(\.code), ["CA"])
        XCTAssertTrue(s.waters.allSatisfy { $0.state == "CA" && $0.semantics == .schedule })
    }

    func testTennesseeKeepsTheAgencysPrecision() throws {
        let s = try v2()
        let mckenzie = try XCTUnwrap(s.water(id: "tn-caroll-mckenzie-city-park"))
        let month = try XCTUnwrap(mckenzie.plants.first { $0.week.precision == .month })
        XCTAssertEqual(month.week.label, "December 2026")
        XCTAssertEqual(month.week.phrase, "December 2026")
        let tellico = try XCTUnwrap(s.water(id: "tn-monroe-tellico-river"))
        let week = try XCTUnwrap(tellico.plants.first { $0.week.precision == .week })
        XCTAssertTrue(week.week.phrase.hasPrefix("the week of "))
        XCTAssertEqual(tellico.sitePath, "/tn/water/tellico-river-monroe-county/")
        XCTAssertEqual(SnapshotEndpoint.siteWaterURL(for: tellico)?.absoluteString, "https://chelseakr.github.io/ca-fish-planting-alerts/tn/water/tellico-river-monroe-county/")
    }

    func testAMonthOnlyWaterSaysSoAndIsNeverGivenADate() throws {
        let s = try v2()
        let lettersOnly = try XCTUnwrap(s.waters.first { $0.state == "TN" && $0.plants.isEmpty })
        let line = ScheduleWording.lastScheduledLine(for: lettersOnly, sourceWeek: s.currentWeek(for: lettersOnly))
        XCTAssertTrue(line.contains(try XCTUnwrap(lettersOnly.monthsNote)), line)
    }

    func testAReportWaterSaysStockedAndHasNoFuture() throws {
        let s = try v2()
        let swift = try XCTUnwrap(s.water(id: "ma-swift-belch"))
        XCTAssertEqual(swift.semantics, .report)
        XCTAssertEqual(swift.countyLabel, "Belchertown", "Massachusetts reports a town")
        XCTAssertEqual(ScheduleWording.lastScheduledLine(for: swift, sourceWeek: s.currentWeek(for: swift)),
                       "Last stocked on 2026-10-09")
        XCTAssertNil(ScheduleWording.nextScheduledLine(for: swift, sourceWeek: s.currentWeek(for: swift)))
        let mi = try XCTUnwrap(s.water(id: "mi-1234"))
        XCTAssertEqual(mi.plants.last?.count, 4000)
        XCTAssertTrue(ScheduleAnswer.nextScheduled(for: mi, in: s, now: Date()).contains("weeks after the stocking"))
    }

    // MARK: negative controls on the contract

    func testAReportedPlantInAScheduleStateIsRefused() throws {
        let json = try v2JSON()
        // The first Tennessee plant becomes "reported".
        let marker = "\"state\": \"TN\""
        let tnStart = try XCTUnwrap(json.range(of: marker))
        let statusRange = try XCTUnwrap(json.range(of: "\"status\": \"listed\"", range: tnStart.upperBound..<json.endIndex))
        let broken = json.replacingCharacters(in: statusRange, with: "\"status\": \"reported\"")
        XCTAssertNotEqual(broken, json, "the sabotage must land")
        XCTAssertThrowsError(try decoder.decode(Data(broken.utf8))) { error in
            guard case .malformed(let what)? = error as? SnapshotDecodingError else { return XCTFail("\(error)") }
            XCTAssertTrue(what.contains("schedule state"), what)
        }
    }

    func testAWeekLabeledAsADayIsRefused() throws {
        let json = try v2JSON()
        let broken = json.replacingOccurrences(of: "\"label\": \"week of 2026-10-11\"", with: "\"label\": \"2026-10-11\"")
        XCTAssertNotEqual(broken, json)
        XCTAssertThrowsError(try decoder.decode(Data(broken.utf8)))
    }

    // MARK: stored data from older builds

    func testABaselineStoredBeforeStatesStillMatchesCaliforniaWeeks() throws {
        let old = Data(#"{"weekStart":"2026-09-13","species":"Trout"}"#.utf8)
        let key = try JSONDecoder().decode(PlantKey.self, from: old)
        XCTAssertEqual(key, PlantKey(TS.plant("2026-09-13")), "an old week baseline must not re-announce")
        let oldWeek = Data(#"{"start":"2026-09-13","end":"2026-09-19","label":"week of 2026-09-13"}"#.utf8)
        XCTAssertEqual(try JSONDecoder().decode(Week.self, from: oldWeek).precision, .week)
    }

    // MARK: alerts

    func testTennesseeAndMassachusettsAlertsUseTheirOwnWords() throws {
        let s = try v2()
        let tellico = try XCTUnwrap(s.water(id: "tn-monroe-tellico-river"))
        let swift = try XCTUnwrap(s.water(id: "ma-swift-belch"))
        // An empty baseline: everything current is new.
        let plan = AlertPlanner.plan(snapshot: s, favorites: [tellico.id, swift.id], state: AlertState())
        let tn = try XCTUnwrap(plan.notifications.first { $0.waterID == tellico.id })
        XCTAssertEqual(tn.title, "Tellico River is on the stocking schedule")
        XCTAssertTrue(tn.body().contains("TWRA gives the week, not the day"), tn.body())
        let ma = try XCTUnwrap(plan.notifications.first { $0.waterID == swift.id })
        XCTAssertEqual(ma.title, "Swift River was stocked")
        XCTAssertTrue(ma.body().hasPrefix("Stocked on 2026-10-06 and 2026-10-09"), ma.body())
        XCTAssertTrue(ma.body().contains("MassWildlife"))
        // Planned again against its own result: nothing new.
        XCTAssertTrue(AlertPlanner.plan(snapshot: s, favorites: [tellico.id, swift.id], state: plan.state).notifications.isEmpty)
    }

    func testAMonthPlantIsAnnouncedWithoutADay() {
        let key = PlantKey(weekStart: PlainDate(year: 2026, month: 12, day: 1), species: "Rainbow Trout", precision: .month)
        let n = PlannedNotification(waterID: "tn-x", waterName: "X", newKeys: [key], agencyShortName: "TWRA")
        XCTAssertEqual(n.body(), "Scheduled for December 2026 (Rainbow Trout). TWRA hasn't set the day yet. Plans can change.")
    }

    // MARK: purchases

    func testCaliforniaIsTheOriginalFullAccessProduct() {
        XCTAssertEqual(StateAccess.productID(forState: "CA"), "com.chelseakr.cafishplanting.fullaccess")
        XCTAssertEqual(StateAccess.entitledStates(fromProductIDs: ["com.chelseakr.cafishplanting.fullaccess"]), ["CA"])
        XCTAssertEqual(StateAccess.entitledStates(fromProductIDs: ["com.chelseakr.cafishplanting.state.tn", "unknown"]), ["TN"])
        XCTAssertEqual(StateAccess.allProductIDs.count, 4)
    }

    func testAlertsAndTheWidgetFollowEachStatesPurchase() throws {
        XCTAssertTrue(FreeTier.notificationsAllowed(forState: "TN", entitledStates: ["TN"]))
        XCTAssertFalse(FreeTier.notificationsAllowed(forState: "TN", entitledStates: ["CA"]))
        XCTAssertFalse(FreeTier.widgetsAllowed(entitledStates: []))
        XCTAssertTrue(FreeTier.widgetsAllowed(entitledStates: ["MA"]))

        let s = try v2()
        let meta = SnapshotMeta(lastAttemptAt: Date(), lastSuccessAt: Date(), lastOutcome: "updated")
        let ids = ["tn-monroe-tellico-river", "ma-swift-belch", s.waters[0].id]
        let digest = WidgetDigest(snapshot: s, meta: meta, favorites: ids, locked: false, entitledStates: ["TN"])
        XCTAssertEqual(digest.favorites.map(\.id), ["tn-monroe-tellico-river"])
        XCTAssertEqual(digest.favoritesInOtherStates, 2, "favorites in states not bought are counted, not dropped")
    }
}
