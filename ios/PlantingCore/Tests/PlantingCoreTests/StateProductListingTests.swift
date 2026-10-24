import XCTest
@testable import PlantingCore

/// `docs/app-store/LISTING-MULTISTATE.md`, the listing for the multistate
/// version, against App Store Connect's limits and against the local StoreKit
/// configuration, so the copy the owner pastes can't drift from what the app
/// sells.
final class StateProductListingTests: XCTestCase {
    private var repo: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // PlantingCoreTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // PlantingCore
            .deletingLastPathComponent() // ios
            .deletingLastPathComponent() // repo
    }

    private func listing() throws -> String {
        try String(contentsOf: repo.appendingPathComponent("docs/app-store/LISTING-MULTISTATE.md"), encoding: .utf8)
    }

    private func storeKitProducts() throws -> [[String: Any]] {
        let url = repo.appendingPathComponent("ios/CAFishPlanting/Configuration.storekit")
        let json = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        return json?["products"] as? [[String: Any]] ?? []
    }

    /// The cells of every table row that starts with `prefix`.
    private func rows(_ text: String, prefix: String) -> [[String]] {
        text.split(separator: "\n")
            .filter { $0.hasPrefix(prefix) }
            .map { line in
                line.split(separator: "|", omittingEmptySubsequences: false)
                    .dropFirst().dropLast()
                    .map { $0.trimmingCharacters(in: .whitespaces) }
            }
    }

    private func unquote(_ cell: String) -> String {
        cell.trimmingCharacters(in: CharacterSet(charactersIn: "`"))
    }

    /// The text between the two rules after `heading`.
    private func block(_ text: String, after heading: String) throws -> String {
        let start = try XCTUnwrap(text.range(of: heading), heading).upperBound
        let open = try XCTUnwrap(text.range(of: "\n---\n", range: start..<text.endIndex)).upperBound
        let close = try XCTUnwrap(text.range(of: "\n---\n", range: open..<text.endIndex)).lowerBound
        return String(text[open..<close]).trimmingCharacters(in: .newlines)
    }

    func testShortFieldsFitAndTheirStatedCountsAreReal() throws {
        let text = try listing()
        var seen: [String] = []
        for name in ["Name", "Subtitle", "Keywords", "Promotional text"] {
            let row = try XCTUnwrap(rows(text, prefix: "| \(name) | ").first, name)
            let limit = try XCTUnwrap(Int(row[1]), name)
            let value = unquote(row[2])
            XCTAssertLessThanOrEqual(value.count, limit, "\(name): \(value)")
            XCTAssertEqual(Int(row[3]), value.count, "\(name)'s stated count must be the real one")
            seen.append(name)
        }
        XCTAssertEqual(seen.count, 4)
    }

    func testKeywordsRepeatNoWordFromTheNameOrSubtitle() throws {
        let text = try listing()
        let name = unquote(try XCTUnwrap(rows(text, prefix: "| Name | ").first)[2]).lowercased()
        let subtitle = unquote(try XCTUnwrap(rows(text, prefix: "| Subtitle | ").first)[2]).lowercased()
        let keywords = unquote(try XCTUnwrap(rows(text, prefix: "| Keywords | ").first)[2]).lowercased()
        XCTAssertFalse(keywords.contains(" ,") || keywords.contains(", "), "commas, no spaces around them")
        let titleWords = Set((name + " " + subtitle).split { !$0.isLetter }.map(String.init))
        for keyword in keywords.split(separator: ",") {
            for word in keyword.split(separator: " ") {
                XCTAssertFalse(titleWords.contains(String(word)), "\(word) is already in the name or subtitle")
            }
        }
    }

    func testLongFieldsFitAndTheirStatedCountsAreReal() throws {
        let text = try listing()
        let description = try block(text, after: "## Description\n")
        let whatsNew = try block(text, after: "## What's New\n")
        XCTAssertLessThanOrEqual(description.count, 4000)
        XCTAssertLessThanOrEqual(whatsNew.count, 4000)
        let stated = { (field: String) throws -> Int in
            let row = try XCTUnwrap(self.rows(text, prefix: "| \(field) | 4000 |").first, field)
            return try XCTUnwrap(Int(row[3].replacingOccurrences(of: ",", with: "")), field)
        }
        XCTAssertEqual(try stated("Description"), description.count)
        XCTAssertEqual(try stated("What's New"), whatsNew.count)
    }

    /// Every state sold beside California is in the purchase table with the
    /// StoreKit file's exact values, and nothing else is.
    func testThePurchaseTableIsTheStoreKitConfiguration() throws {
        let text = try listing()
        let table = rows(text, prefix: "| TN |") + rows(text, prefix: "| MA |") + rows(text, prefix: "| MI |") + rows(text, prefix: "| NY |")
        let expected = Set(StateAccess.productIDsByState.keys).subtracting(["CA"])
        XCTAssertEqual(Set(table.map { $0[0] }), expected)
        let products = try storeKitProducts()
        for row in table {
            let id = unquote(row[1])
            XCTAssertEqual(StateAccess.productID(forState: row[0]), id, row[0])
            let product = try XCTUnwrap(products.first { $0["productID"] as? String == id }, id)
            let localization = try XCTUnwrap((product["localizations"] as? [[String: Any]])?.first, id)
            XCTAssertEqual(product["referenceName"] as? String, unquote(row[2]), id)
            XCTAssertEqual(localization["displayName"] as? String, unquote(row[3]), id)
            XCTAssertEqual(localization["description"] as? String, unquote(row[4]), id)
            XCTAssertEqual(Int(row[5]), unquote(row[4]).count, "\(id)'s stated count")
            XCTAssertLessThanOrEqual(unquote(row[3]).count, 30, id)
            XCTAssertLessThanOrEqual(unquote(row[4]).count, 45, id)
            XCTAssertEqual(product["type"] as? String, "NonConsumable", id)
            XCTAssertEqual(product["displayPrice"] as? String, "9.99", id)
            XCTAssertEqual(product["familyShareable"] as? Bool, false, "\(id): Family Sharing matches California's (off)")
        }
    }

    /// New York's purchase adds reminders of a planned period, not alerts
    /// about a new listing, and its product says so.
    func testAPlanStatesProductSaysRemindersAndTheOthersSayAlerts() throws {
        for product in try storeKitProducts() {
            let id = try XCTUnwrap(product["productID"] as? String)
            let description = try XCTUnwrap(((product["localizations"] as? [[String: Any]])?.first)?["description"] as? String)
            if id == StateAccess.productID(forState: "NY") {
                XCTAssertTrue(description.hasPrefix("Reminders"), description)
            } else {
                XCTAssertTrue(description.hasPrefix("Alerts"), description)
            }
        }
    }

    /// No claim the listing rules forbid (`docs/APP-STORE-LISTING.md`: no
    /// "only" or "first", no "every state"), anywhere a customer reads.
    func testTheCustomerFacingCopyMakesNoForbiddenClaim() throws {
        let text = try listing()
        let promo = unquote(try XCTUnwrap(rows(text, prefix: "| Promotional text | ").first)[2])
        let copy = [promo,
                    try block(text, after: "## Description\n"),
                    try block(text, after: "## What's New\n"),
                    try block(text, after: "## App Review notes\n")]
        let forbidden = ["only", "first", "every state", "all states", "forever", "best", "fastest", "#1"]
        for part in copy {
            for phrase in forbidden {
                XCTAssertNil(part.range(of: "\\b\(NSRegularExpression.escapedPattern(for: phrase))\\b", options: [.regularExpression, .caseInsensitive]),
                             "\"\(phrase)\" in: \(part.prefix(80))")
            }
        }
    }
}
