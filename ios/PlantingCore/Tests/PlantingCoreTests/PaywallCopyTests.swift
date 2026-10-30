import XCTest
@testable import PlantingCore

/// The purchase sheet's words for every state (DECISIONS 0025): honest about
/// what the purchase adds and costs, no urgency, and plain about a state whose
/// source has stopped answering, before the buy button.
final class PaywallCopyTests: XCTestCase {
    private let decoder = SnapshotDecoder()
    private let enUS = Locale(identifier: "en_US")

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/v2-wave2.json")
    }

    private func json() throws -> String { try String(contentsOf: Self.fixtureURL, encoding: .utf8) }

    private func state(_ code: String, in text: String) throws -> StateInfo {
        try XCTUnwrap(decoder.decode(Data(text.utf8)).state(code: code), "\(code) must be in the fixture")
    }

    /// Every line the sheet can show for every state in the fixture.
    private func everyLine(in text: String) throws -> [String] {
        let snapshot = try decoder.decode(Data(text.utf8))
        var lines = FreeTier.fullAccessFeatures
        for s in snapshot.states {
            lines += FreeTier.stateFeatures(stateName: s.name, agencyShortName: s.agencyShortName, semantics: s.semantics)
            lines.append(PaywallCopy.terms(stateName: s.name))
            lines.append(PaywallCopy.freshness(s, locale: enUS))
        }
        return lines
    }

    func testTermsSayOnePaymentPerStateWithNoSubscriptionAndHowToRestore() {
        XCTAssertEqual(PaywallCopy.terms(stateName: "Tennessee"),
                       "One payment for Tennessee. No subscription and no account. Each state is its own purchase, and Restore purchases brings it back on a new device.")
    }

    func testFreshnessNamesTheAgencyAndTheDateOfTheLastGoodRead() throws {
        let tn = try state("TN", in: json())
        XCTAssertTrue(tn.lastAttemptOK, "sanity check: the fixture's Tennessee check succeeded")
        XCTAssertEqual(PaywallCopy.freshness(tn, locale: enUS),
                       "Latest update read from TWRA: Sep 13, 2026. Alerts follow TWRA's own page and are never more current than it is.")
    }

    /// Tennessee's real source refused the pipeline from 2026-10-15 on
    /// (issue #97). A buyer must see that on the sheet itself.
    func testAFailedCheckIsSaidBeforeTheBuyButton() throws {
        let text = try json()
        let marker = try XCTUnwrap(text.range(of: "\"code\": \"TN\""))
        let flag = try XCTUnwrap(text.range(of: "\"last_attempt_ok\": true", range: marker.upperBound..<text.endIndex),
                                 "the TN entry must carry last_attempt_ok, or this sabotage would change nothing")
        let sabotaged = text.replacingCharacters(in: flag, with: "\"last_attempt_ok\": false")
        let tn = try state("TN", in: sabotaged)
        XCTAssertFalse(tn.lastAttemptOK, "the sabotage must actually apply")
        XCTAssertEqual(PaywallCopy.freshness(tn, locale: enUS),
                       "Trout Truck's newest check of TWRA failed, so what you see is still the update read on Sep 13, 2026. Alerts for Tennessee resume when TWRA's page can be read again.")
        // The other states are untouched.
        XCTAssertTrue(try state("NY", in: sabotaged).lastAttemptOK)
    }

    func testNoLineOnTheSheetUsesUrgencyOrAPromiseTheDataCannotKeep() throws {
        let lines = try everyLine(in: json())
        XCTAssertGreaterThanOrEqual(lines.count, 3 + 5 * 5, "every state's lines must be checked")
        for line in lines {
            let words = line.lowercased()
            for banned in PaywallCopy.bannedWords {
                XCTAssertNil(words.range(of: "\\b\(NSRegularExpression.escapedPattern(for: banned))\\b", options: .regularExpression),
                             "\"\(banned)\" must not appear on the purchase sheet: \(line)")
            }
        }
    }

    /// Negative control: the check above would catch the old footnote.
    func testNegativeControlTheOldFootnoteWouldFail() {
        let old = "One payment, forever, for this state. No subscription, no account. Each state is its own purchase."
        XCTAssertTrue(PaywallCopy.bannedWords.contains { old.lowercased().contains($0) })
    }
}
