import XCTest
@testable import PlantingCore

/// The same cases as `FeedbackMailTest.kt`.
final class FeedbackMailTests: XCTestCase {
    func testTheSubjectCarriesTheVersionAndPlatform() {
        XCTAssertEqual(FeedbackMail.subject(version: "1.2.0", platform: "iOS"), "Trout Truck 1.2.0 for iOS")
        XCTAssertEqual(FeedbackMail.url(version: "1.2.0", platform: "iOS")?.absoluteString,
                       "mailto:chelsea@chelseakr.com?subject=Trout%20Truck%201.2.0%20for%20iOS")
    }

    func testAMissingVersionIsLeftOutNeverShownAsAValue() {
        for missing in [nil, "", "  "] as [String?] {
            let subject = FeedbackMail.subject(version: missing, platform: "iOS")
            XCTAssertEqual(subject, "Trout Truck for iOS")
            XCTAssertFalse(subject.contains("nil") || subject.contains("unknown"))
        }
    }

    func testSpacesAreNeverPlusSigns() throws {
        let url = try XCTUnwrap(FeedbackMail.url(version: "1.0.0 (7)", platform: "iOS")).absoluteString
        XCTAssertFalse(url.contains("+"))
        XCTAssertTrue(url.hasSuffix("subject=Trout%20Truck%201.0.0%20%287%29%20for%20iOS"))
    }

    func testTheFootnoteNamesTheAddressSoItWorksWithoutMail() {
        XCTAssertTrue(FeedbackMail.rowFootnote.contains(FeedbackMail.address))
        XCTAssertEqual(FeedbackMail.rowTitle, "Write to the developer")
        XCTAssertEqual(FeedbackMail.sectionHeader, "Questions and corrections")
    }

    /// The Android file says the same words; this keeps them from drifting.
    func testTheWordsMatchAndroid() throws {
        let kotlin = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("android/core/src/main/kotlin/com/chelseakr/cafishplanting/core/FeedbackMail.kt")
        guard FileManager.default.fileExists(atPath: kotlin.path) else {
            throw XCTSkip("the Android FeedbackMail.kt isn't in this checkout")
        }
        let text = try String(contentsOf: kotlin, encoding: .utf8)
        XCTAssertTrue(text.contains("\"\(FeedbackMail.address)\""))
        XCTAssertTrue(text.contains("\"\(FeedbackMail.sectionHeader)\""))
        XCTAssertTrue(text.contains("\"\(FeedbackMail.rowTitle)\""))
        let footnote = FeedbackMail.rowFootnote.replacingOccurrences(of: FeedbackMail.address, with: "$ADDRESS")
        XCTAssertTrue(text.contains("\"\(footnote)\""))
    }
}
