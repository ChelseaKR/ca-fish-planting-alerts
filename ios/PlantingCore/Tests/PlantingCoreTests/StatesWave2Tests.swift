import XCTest
@testable import PlantingCore

/// Wave 2 (DECISIONS 0034): Michigan and Massachusetts reports, New York's
/// spring plan, and a v2 reader that ignores a vocabulary it does not know
/// instead of refusing the file.
///
/// The fixture is real pipeline output trimmed to a few waters per state:
/// California from the 2026-09-13 CDFW fixture, Tennessee from TWRA's real
/// 2026-10-12 file, Massachusetts from the real 2026-10-12 Hub download,
/// Michigan from the DNR's real CSV and New York from OPEN-NY's real 2026
/// plan. It was validated with the pipeline's own schema and invariants
/// before it was pinned here. Its states' current week is the week of
/// 2026-10-18, after New York's spring plan; tests that need the plan ahead
/// of them move New York's current week to March by string substitution,
/// the way `MultiStateTests` sabotages fields.
final class StatesWave2Tests: XCTestCase {
    private let decoder = SnapshotDecoder()

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/v2-wave2.json")
    }

    private func json() throws -> String { try String(contentsOf: Self.fixtureURL, encoding: .utf8) }
    private func fixture() throws -> Snapshot { try decoder.decode(Data(try json().utf8)) }
    private func decode(_ text: String) throws -> Snapshot { try decoder.decode(Data(text.utf8)) }

    /// `text` with the first `old` after `marker` replaced by `new`. Fails
    /// the test, rather than silently changing nothing, when either is missing.
    private func replaceFirst(in text: String, after marker: String, _ old: String, with new: String) throws -> String {
        try replaceFirst(in: text, after: [marker], old, with: new)
    }

    /// The same, after each marker in turn (a water's id, then its `plants`).
    private func replaceFirst(in text: String, after markers: [String], _ old: String, with new: String) throws -> String {
        var from = text.startIndex
        for marker in markers {
            from = try XCTUnwrap(text.range(of: marker, range: from..<text.endIndex), "marker \(marker) must be in the fixture").upperBound
        }
        let target = try XCTUnwrap(text.range(of: old, range: from..<text.endIndex), "\(old) must follow \(markers)")
        return text.replacingCharacters(in: target, with: new)
    }

    /// The fixture with New York's current week moved to 2026-03-01, before
    /// its spring plan, so "next" and "planned for" have something ahead.
    private func fixtureWithNewYorkInMarch() throws -> Snapshot {
        var text = try json()
        for (old, new) in [("\"start\": \"2026-10-18\"", "\"start\": \"2026-03-01\""),
                           ("\"end\": \"2026-10-24\"", "\"end\": \"2026-03-07\""),
                           ("\"label\": \"week of 2026-10-18\"", "\"label\": \"week of 2026-03-01\"")] {
            text = try replaceFirst(in: text, after: "\"code\": \"NY\"", old, with: new)
        }
        let s = try decode(text)
        XCTAssertEqual(s.state(code: "NY")?.currentWeek.label, "week of 2026-03-01", "the move must land")
        XCTAssertEqual(s.state(code: "TN")?.currentWeek.label, "week of 2026-10-18", "and touch New York alone")
        return s
    }

    private static let march1 = Week(start: PlainDate(year: 2026, month: 3, day: 1), end: PlainDate(year: 2026, month: 3, day: 7), label: "week of 2026-03-01")
    private static let july5 = Week(start: PlainDate(year: 2026, month: 7, day: 5), end: PlainDate(year: 2026, month: 7, day: 11), label: "week of 2026-07-05")

    // MARK: every state, with its words

    func testTheFixtureCarriesEveryStateWithItsWords() throws {
        let s = try fixture()
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "NY", "TN"])
        XCTAssertEqual(s.state(code: "NY")?.semantics, .plan)
        XCTAssertEqual(s.state(code: "NY")?.datePrecisions, [.approximate])
        XCTAssertEqual(s.state(code: "NY")?.kindLabel, "Spring stocking plan")
        XCTAssertFalse(try XCTUnwrap(s.state(code: "NY")?.removalInference))
        XCTAssertEqual(s.state(code: "MI")?.semantics, .report)
        XCTAssertNotNil(s.state(code: "MI")?.recencyNote)
        XCTAssertEqual(s.state(code: "MA")?.semantics, .report)
        let ny = s.waters(inState: "NY")
        XCTAssertEqual(ny.count, 5)
        for plant in ny.flatMap(\.plants) {
            XCTAssertEqual(plant.week.precision, .approximate)
            XCTAssertEqual(plant.status, .listed)
            XCTAssertTrue(plant.week.label.hasSuffix(", 2026"), plant.week.label)
        }
        XCTAssertTrue(s.waters(inState: "MI").flatMap(\.plants).allSatisfy { $0.species.lowercased().hasSuffix("trout") })
        let wyola = try XCTUnwrap(s.water(id: "ma-34103-272"))
        XCTAssertEqual(wyola.name, "Lake Wyola")
        XCTAssertEqual(wyola.countyLabel, "Shutesbury", "Massachusetts reports a town")
        // Every state in the snapshot is one the States screen can sell.
        for state in s.states { XCTAssertNotNil(StateAccess.productID(forState: state.code), state.code) }
    }

    func testAPlanSaysPlannedForInTheAgencysWordsNeverADate() throws {
        let s = try fixtureWithNewYorkInMarch()
        let water = try XCTUnwrap(s.water(id: "ny-allegany-amity-genesee-river"))
        let line = ScheduleWording.lastScheduledLine(for: water, sourceWeek: s.currentWeek(for: water))
        XCTAssertEqual(line, "Planned for March - third week, 2026")
        XCTAssertFalse(line.contains("2026-0"), "never a date: \(line)")
        XCTAssertEqual(ScheduleWording.nextScheduledLine(for: water, sourceWeek: Self.march1), "Planned for March - third week, 2026")
        let answer = ScheduleAnswer.nextScheduled(for: water, in: s, now: Date())
        XCTAssertEqual(answer, "Genesee River is planned for March - third week, 2026 (Brown Trout, Rainbow Trout), in NYS DEC's own words. A plan, not a date and not a confirmed stocking.")
        XCTAssertFalse(answer.lowercased().contains("scheduled"), answer)
    }

    func testAPlanWaterWithNothingAheadSaysSoHonestly() throws {
        let s = try fixture()
        let water = try XCTUnwrap(s.water(id: "ny-cattaraugus-ashford-crandall-pond"))
        XCTAssertNil(ScheduleWording.nextScheduledLine(for: water, sourceWeek: Self.july5))
        XCTAssertEqual(ScheduleWording.lastScheduledLine(for: water, sourceWeek: Self.july5), "Last planned for Mid April, 2026")
        XCTAssertEqual(ScheduleWording.lastScheduledLine(for: water), "Last planned for Mid April, 2026")
        XCTAssertEqual(ScheduleAnswer.nextScheduled(for: water, in: s, now: Date()),
                       "Crandall Pond isn't in NYS DEC's plan for later this season. It was last planned for Mid April, 2026.")
    }

    // MARK: reminders

    func testRemindersOnlyForTightPlannedPeriodsInBoughtStatesAndNotMuted() throws {
        let s = try fixture()
        let water = try XCTUnwrap(s.water(id: "ny-allegany-amity-genesee-river"))
        let today = PlainDate(year: 2026, month: 2, day: 1)
        let reminders = ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [], today: today)
        XCTAssertEqual(reminders.map(\.periodLabel), ["March - third week, 2026", "April - first week, 2026", "April - third week, 2026", "May - first week, 2026"])
        XCTAssertEqual(reminders.first?.species, ["Brown Trout", "Rainbow Trout"])
        for r in reminders {
            XCTAssertEqual(r.title, "Genesee River: planned stocking period")
            XCTAssertTrue(r.body.hasPrefix("NYS DEC plans to stock Genesee River in \(r.periodLabel)"), r.body)
            XCTAssertTrue(r.body.hasSuffix("A plan in NYS DEC's own words, not a date and not a confirmed stocking."), r.body)
            XCTAssertTrue(r.id.hasPrefix(PlannedReminder.idPrefix))
            let period = try XCTUnwrap(water.plants.first { $0.week.start == r.fireOn }?.week)
            XCTAssertLessThanOrEqual(period.spanDays, ReminderPlanner.maxSpanDays)
        }
        XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["CA", "TN"], muted: [], today: today).isEmpty,
                      "a reminder needs New York's purchase")
        XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [water.id], today: today).isEmpty,
                      "a muted favorite gets no reminder")
        XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [water.id], entitledStates: ["NY"], muted: [], today: PlainDate(year: 2026, month: 12, day: 31)).isEmpty,
                      "no reminder for a period that has begun")
    }

    func testSpringAndATwoMonthRangeAreTooLooseToRemindAbout() throws {
        let s = try fixture()
        let today = PlainDate(year: 2026, month: 1, day: 1)
        for id in ["ny-albany-berne-thompsons-lake", "ny-albany-city-of-albany-six-mile-waterworks"] {
            let water = try XCTUnwrap(s.water(id: id))
            XCTAssertTrue(water.plants.allSatisfy { $0.week.spanDays > ReminderPlanner.maxSpanDays }, id)
            XCTAssertTrue(ReminderPlanner.reminders(snapshot: s, favorites: [id], entitledStates: ["NY"], muted: [], today: today).isEmpty, id)
        }
        // The control: a tight period in the same state does remind.
        let tight = try XCTUnwrap(s.water(id: "ny-cattaraugus-ashford-crandall-pond"))
        XCTAssertEqual(ReminderPlanner.reminders(snapshot: s, favorites: [tight.id], entitledStates: ["NY"], muted: [], today: today).map(\.periodLabel), ["Mid April, 2026"])
    }

    func testAReminderNeedsOnlyItsOwnStatesPurchase() throws {
        let s = try fixture()
        let ny = try XCTUnwrap(s.water(id: "ny-cattaraugus-ashford-crandall-pond"))
        let tn = try XCTUnwrap(s.water(id: "tn-monroe-tellico-river"))
        let today = PlainDate(year: 2026, month: 1, day: 1)
        let reminders = ReminderPlanner.reminders(snapshot: s, favorites: [tn.id, ny.id], entitledStates: ["NY"], muted: [], today: today)
        XCTAssertEqual(reminders.map(\.waterID), [ny.id], "a Tennessee favorite never gets a plan reminder")
        XCTAssertTrue(FreeTier.notificationsAllowed(forState: "NY", entitledStates: ["NY"]))
        XCTAssertFalse(FreeTier.notificationsAllowed(forState: "NY", entitledStates: ["CA", "TN", "MI", "MA"]))
    }

    // MARK: alerts, purchase sheet, widget and watch words

    func testAPlanAlertSaysPlannedAndNeverScheduledOrStocked() throws {
        let s = try fixtureWithNewYorkInMarch()
        let water = try XCTUnwrap(s.water(id: "ny-cattaraugus-ashford-crandall-pond"))
        let plan = AlertPlanner.plan(snapshot: s, favorites: [water.id], state: AlertState())
        let n = try XCTUnwrap(plan.notifications.first)
        XCTAssertEqual(n.title, "Crandall Pond is in the stocking plan")
        XCTAssertEqual(n.body(), "Planned for Mid April, 2026 (Rainbow Trout), in NYS DEC's own words. A plan, not a date, and not a confirmed stocking.")
        XCTAssertTrue(AlertPlanner.plan(snapshot: s, favorites: [water.id], state: plan.state).notifications.isEmpty, "planned again: nothing new")
    }

    func testThePurchaseSheetWordsForEachNewState() {
        XCTAssertEqual(FreeTier.stateFeatures(stateName: "New York", agencyShortName: "NYS DEC", semantics: .plan), [
            "A reminder on this device when a New York favorite's planned stocking period begins, in NYS DEC's own words",
            "New York favorites in the Favorite waters widget",
            "New York favorites on Apple Watch",
        ])
        XCTAssertEqual(FreeTier.stateFeatures(stateName: "Michigan", agencyShortName: "Michigan DNR", semantics: .report).first,
                       "An alert on this device when Michigan DNR reports stocking a Michigan favorite")
        XCTAssertEqual(FreeTier.stateFeatures(stateName: "Massachusetts", agencyShortName: "MassWildlife", semantics: .report).first,
                       "An alert on this device when MassWildlife reports stocking a Massachusetts favorite")
        XCTAssertEqual(FreeTier.fullAccessFeatures.first, "An alert on this device when a favorite is newly on CDFW's weekly schedule", "California is unchanged")
    }

    func testTheWidgetAndWatchSayPlannedForAPlanFavorite() throws {
        let s = try fixtureWithNewYorkInMarch()
        let meta = SnapshotMeta(lastAttemptAt: Date(), lastSuccessAt: Date(), lastOutcome: "updated")
        let spring = "ny-albany-berne-thompsons-lake"
        let genesee = "ny-allegany-amity-genesee-river"
        let digest = WidgetDigest(snapshot: s, meta: meta, favorites: [spring, genesee], locked: false, entitledStates: ["NY"])
        XCTAssertEqual(digest.version, 3)
        let now = Date(timeIntervalSince1970: 1_772_323_200) // 2026-03-01T00:00:00Z
        let ahead = try XCTUnwrap(digest.favorites.first { $0.id == genesee })
        XCTAssertTrue(ahead.isPlan)
        XCTAssertEqual(digest.statusLine(of: ahead, at: now), "Planned for March - third week, 2026")
        XCTAssertEqual(digest.shortStatus(of: ahead, at: now), "Planned: March - third week, 2026")
        XCTAssertEqual(digest.nextScheduledLine(of: ahead), "Planned for March - third week, 2026")
        // "Spring" began on March 1: it overlaps the current week, but the
        // agency's words never read as "this week", and nothing is ahead.
        let begun = try XCTUnwrap(digest.favorites.first { $0.id == spring })
        XCTAssertFalse(begun.isListedThisWeek)
        XCTAssertEqual(digest.statusLine(of: begun, at: now), "No planned period ahead. Last planned for Spring, 2026")
        XCTAssertEqual(digest.shortStatus(of: begun, at: now), "No planned period ahead")
        XCTAssertEqual(digest.lastScheduledLine(of: begun), "Last planned for Spring, 2026")
        for line in [digest.statusLine(of: ahead, at: now), digest.statusLine(of: begun, at: now), digest.summary(at: now)] {
            XCTAssertFalse(line.lowercased().contains("scheduled") && line.contains("Planned"), line)
        }
    }

    func testNewYorksProductIsItsOwnAndCaliforniasIsUnchanged() {
        XCTAssertEqual(StateAccess.productID(forState: "NY"), "com.chelseakr.cafishplanting.state.ny")
        XCTAssertEqual(StateAccess.productID(forState: "MI"), "com.chelseakr.cafishplanting.state.mi")
        XCTAssertEqual(StateAccess.productID(forState: "MA"), "com.chelseakr.cafishplanting.state.ma")
        XCTAssertEqual(StateAccess.productID(forState: "TN"), "com.chelseakr.cafishplanting.state.tn")
        XCTAssertEqual(StateAccess.productID(forState: "CA"), "com.chelseakr.cafishplanting.fullaccess")
        XCTAssertEqual(StateAccess.allProductIDs.count, 5)
        XCTAssertEqual(StateAccess.entitledStates(fromProductIDs: ["com.chelseakr.cafishplanting.state.ny"]), ["NY"])
        XCTAssertFalse(StateAccess.isKnown(state: "OR"))
    }

    // MARK: the contract still holds

    func testNegativeControlAReportedPlantInAPlanStateIsRefused() throws {
        let text = try json()
        let broken = try replaceFirst(in: text, after: "\"state\": \"NY\"", "\"status\": \"listed\"", with: "\"status\": \"reported\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        XCTAssertThrowsError(try decode(broken)) { error in
            guard case .malformed(let what)? = error as? SnapshotDecodingError else { return XCTFail("\(error)") }
            XCTAssertTrue(what.contains("plan state"), what)
        }
    }

    func testNegativeControlAnApproximateLabelWithoutItsYearIsRefused() throws {
        let text = try json()
        let broken = text.replacingOccurrences(of: "\"label\": \"Mid April, 2026\"", with: "\"label\": \"Mid April\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        XCTAssertThrowsError(try decode(broken))
    }

    func testNegativeControlAMalformedFileStillKeepsTheLastGoodSnapshot() throws {
        let text = try json()
        // California demoted from first place: a contract violation, not a vocabulary.
        let broken = try replaceFirst(in: text, after: "\"states\": [", "\"code\": \"CA\"", with: "\"code\": \"XX\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        XCTAssertThrowsError(try decode(broken)) { error in
            guard case .malformed(let what)? = error as? SnapshotDecodingError else { return XCTFail("\(error)") }
            XCTAssertTrue(what.contains("California first"), what)
        }
        // A Tennessee plant's week labeled as a day.
        let dayAsWeek = try replaceFirst(in: text, after: ["\"id\": \"tn-greene-dillard-ponds\"", "\"plants\": ["],
                                         "\"label\": \"week of 2026-10-18\"", with: "\"label\": \"2026-10-18\"")
        XCTAssertNotEqual(dayAsWeek, text, "the sabotage must land")
        XCTAssertThrowsError(try decode(dayAsWeek)) { error in
            guard case .malformed(let what)? = error as? SnapshotDecodingError else { return XCTFail("\(error)") }
            XCTAssertTrue(what.contains("is a week but reads"), what)
        }
    }

    // MARK: a vocabulary this build does not know is ignored, not refused

    func testAStateWithUnknownSemanticsIsLeftOutWithItsWatersAndTheRestDecodes() throws {
        let text = try json()
        let broken = text.replacingOccurrences(of: "\"semantics\": \"plan\"", with: "\"semantics\": \"forecast\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        let (s, ignored) = try SnapshotV2Decoding.decodeReporting(Data(broken.utf8))
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "TN"])
        XCTAssertTrue(s.waters(inState: "NY").isEmpty)
        XCTAssertEqual(ignored.states, ["NY"])
        XCTAssertEqual(ignored.waters.count, 5)
        XCTAssertEqual(s.waters.count, try fixture().waters.count - 5, "every other water is still there")
    }

    func testAStateThisBuildHasNoProductForIsLeftOut() throws {
        let text = try json()
        let broken = text.replacingOccurrences(of: "\"code\": \"MI\"", with: "\"code\": \"OR\"")
            .replacingOccurrences(of: "\"state\": \"MI\"", with: "\"state\": \"OR\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        XCTAssertTrue(broken.contains("\"code\": \"OR\"") && broken.contains("\"state\": \"OR\""))
        let (s, ignored) = try SnapshotV2Decoding.decodeReporting(Data(broken.utf8))
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "NY", "TN"])
        XCTAssertEqual(ignored.states, ["OR"])
        XCTAssertEqual(ignored.waters.count, 3)
        XCTAssertTrue(s.states.allSatisfy { StateAccess.isKnown(state: $0.code) })
    }

    func testAPlantWithAnUnknownPrecisionIsLeftOutAndItsWaterKept() throws {
        let text = try json()
        // One of Genesee River's six plants gets a precision this build has never seen.
        let broken = try replaceFirst(in: text, after: ["\"id\": \"ny-allegany-amity-genesee-river\"", "\"plants\": ["],
                                      "\"precision\": \"approximate\"", with: "\"precision\": \"fortnight\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        let (s, ignored) = try SnapshotV2Decoding.decodeReporting(Data(broken.utf8))
        XCTAssertEqual(ignored.plants, 1)
        XCTAssertTrue(ignored.waters.isEmpty)
        XCTAssertEqual(s.water(id: "ny-allegany-amity-genesee-river")?.plants.count, 5)
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "NY", "TN"])
    }

    func testAWaterWhoseEveryPlantIsUnknownIsLeftOutAndSoIsAStateLeftEmpty() throws {
        let text = try json()
        let broken = text.replacingOccurrences(of: "\"precision\": \"approximate\"", with: "\"precision\": \"fortnight\"")
        XCTAssertNotEqual(broken, text, "the sabotage must land")
        let (s, ignored) = try SnapshotV2Decoding.decodeReporting(Data(broken.utf8))
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "TN"], "a state with no water this build can show is left out too")
        XCTAssertEqual(ignored.waters.count, 5)
        XCTAssertEqual(ignored.states, ["NY"])
        XCTAssertGreaterThan(ignored.plants, 5)
    }

    func testAPlantWithAnUnknownStatusIsLeftOutAndThisWeekFollows() throws {
        let text = try json()
        let listedThisWeek = try XCTUnwrap(try fixture().thisWeek.first?.waterID)
        // Every plant of that water gets a status this build has never seen.
        let waterStart = try XCTUnwrap(text.range(of: "\"id\": \"\(listedThisWeek)\""))
        let waterEnd = try XCTUnwrap(text.range(of: "\n    }", range: waterStart.upperBound..<text.endIndex))
        let block = String(text[waterStart.lowerBound..<waterEnd.upperBound])
        let brokenBlock = block.replacingOccurrences(of: "\"status\": \"listed\"", with: "\"status\": \"penciled\"")
        XCTAssertNotEqual(brokenBlock, block, "the sabotage must land")
        let broken = text.replacingCharacters(in: waterStart.lowerBound..<waterEnd.upperBound, with: brokenBlock)
        let (s, ignored) = try SnapshotV2Decoding.decodeReporting(Data(broken.utf8))
        XCTAssertNil(s.water(id: listedThisWeek))
        XCTAssertEqual(ignored.waters, [listedThisWeek])
        XCTAssertFalse(s.thisWeek.contains { $0.waterID == listedThisWeek }, "its this_week entry goes with it, not refused")
        XCTAssertEqual(s.states.map(\.code), ["CA", "MA", "MI", "NY", "TN"], "the state keeps its other waters")
    }

    func testTheUnsabotagedFixtureIgnoresNothing() throws {
        let (s, ignored) = try SnapshotV2Decoding.decodeReporting(Data(try json().utf8))
        XCTAssertEqual(ignored, SnapshotV2Decoding.Ignored())
        XCTAssertEqual(s.thisWeek.count, 2)
    }
}
