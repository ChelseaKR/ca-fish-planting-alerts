import XCTest
@testable import PlantingCore

/// Everything that says what full access unlocks names both things it
/// unlocks, alerts and the widget (DECISIONS 0015), and the App Store
/// strings fit App Store Connect's limits.
final class FullAccessCopyTests: XCTestCase {
    private var repo: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // PlantingCoreTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // PlantingCore
            .deletingLastPathComponent() // ios
            .deletingLastPathComponent() // repo
    }

    private func read(_ path: String) throws -> String {
        try String(contentsOf: repo.appendingPathComponent(path), encoding: .utf8)
    }

    func testThePurchaseScreenListsAlertsAndTheWidget() {
        XCTAssertEqual(FreeTier.fullAccessFeatures.count, 2)
        XCTAssertTrue(FreeTier.fullAccessFeatures.contains { $0.localizedCaseInsensitiveContains("alert") })
        XCTAssertTrue(FreeTier.fullAccessFeatures.contains { $0.localizedCaseInsensitiveContains("widget") })
    }

    /// The in-app purchase description: the local StoreKit configuration,
    /// the App Store Connect instructions and the listing all carry the same
    /// line, within the 45-character limit, naming both.
    func testTheInAppPurchaseDescriptionIsOneLineEverywhereAndFits() throws {
        let storekit = try JSONSerialization.jsonObject(with: Data(read("ios/CAFishPlanting/Configuration.storekit").utf8)) as? [String: Any]
        let products = storekit?["products"] as? [[String: Any]] ?? []
        let product = try XCTUnwrap(products.first { $0["productID"] as? String == "com.chelseakr.cafishplanting.fullaccess" })
        let localization = try XCTUnwrap((product["localizations"] as? [[String: Any]])?.first)
        let description = try XCTUnwrap(localization["description"] as? String)

        XCTAssertLessThanOrEqual(description.count, 45, "App Store Connect's limit for an in-app purchase description")
        XCTAssertTrue(description.localizedCaseInsensitiveContains("alert"), description)
        XCTAssertTrue(description.localizedCaseInsensitiveContains("widget"), description)

        let appStore = try read("docs/APP-STORE.md")
        let listing = try read("docs/APP-STORE-LISTING.md")
        XCTAssertTrue(appStore.contains("| Description (customer-facing, 45 max) | `\(description)` (\(description.count) characters) |"),
                      "docs/APP-STORE.md's in-app purchase table must carry the StoreKit description and its length")
        XCTAssertTrue(appStore.contains("Description `\(description)`"), "the owner checklist's step must carry it too")
        XCTAssertTrue(listing.contains("| Description | 45 | `\(description)` | \(description.count) |"),
                      "docs/APP-STORE-LISTING.md must carry it with its length")
    }

    /// The listing's promotional text says what the purchase adds, within
    /// App Store Connect's 170 characters, and its stated count is right.
    func testThePromotionalTextNamesTheWidgetAndFits() throws {
        let listing = try read("docs/APP-STORE-LISTING.md")
        let row = try XCTUnwrap(listing.split(separator: "\n").first { $0.hasPrefix("| Promotional text | 170 |") })
        let cells = row.split(separator: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        let text = cells[2].trimmingCharacters(in: CharacterSet(charactersIn: "`"))
        XCTAssertLessThanOrEqual(text.count, 170)
        XCTAssertEqual(Int(cells[3]), text.count, "the stated count must be the real one")
        XCTAssertTrue(text.localizedCaseInsensitiveContains("widget"), text)
    }
}
