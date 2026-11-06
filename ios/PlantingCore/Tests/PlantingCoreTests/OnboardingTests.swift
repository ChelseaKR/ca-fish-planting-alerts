import XCTest
@testable import PlantingCore

final class OnboardingTests: XCTestCase {
    func testShowsOnAFirstLaunchOnly() {
        XCTAssertTrue(OnboardingState().shouldShow(hasFavorites: false))
        XCTAssertFalse(OnboardingState(completedVersion: OnboardingCopy.version).shouldShow(hasFavorites: false))
    }

    /// Someone updating from 1.0.0 who already keeps favorites isn't stopped
    /// by an introduction to an app they use.
    func testAnUpdaterWithFavoritesSkipsIt() {
        XCTAssertFalse(OnboardingState().shouldShow(hasFavorites: true))
    }

    func testANewerIntroductionShowsAgain() {
        XCTAssertTrue(OnboardingState(completedVersion: 1).shouldShow(hasFavorites: false, currentVersion: 2))
    }

    func testStateRoundTripsAndACorruptFileReadsAsNotSeen() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-onboarding-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let layout = AppStorageLayout(directory: dir)
        let store = OnboardingStore(layout: layout)
        XCTAssertEqual(store.load(), OnboardingState())
        try store.save(OnboardingState(completedVersion: 1))
        XCTAssertEqual(store.load().completedVersion, 1)
        try Data("{".utf8).write(to: layout.onboardingFile)
        XCTAssertEqual(store.load(), OnboardingState())
    }

    /// The app's wording rules hold on every page: never a day, never
    /// "stocked" as the intro's own word (only quoted, as one of the words a
    /// report state's waters show), never a price, and alerts only ever as
    /// part of full access.
    func testTheCopyKeepsTheAppsWordingRules() {
        let pages = OnboardingCopy.pages
        XCTAssertEqual(Set(pages.map(\.id)).count, pages.count, "page ids are unique")
        let text = pages.flatMap { [$0.title, $0.body] + $0.points }
        let days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "today", "tomorrow"]
        for line in text {
            XCTAssertFalse(line.replacingOccurrences(of: "\"stocked\"", with: "").localizedCaseInsensitiveContains("stocked"), line)
            XCTAssertFalse(line.contains("$"), "no price: \(line)")
            for day in days { XCTAssertFalse(line.localizedCaseInsensitiveContains(day), "\(day) in: \(line)") }
        }
        let alertLines = text.filter { $0.localizedCaseInsensitiveContains("an alert") }
        XCTAssertFalse(alertLines.isEmpty)
        for line in alertLines {
            XCTAssertTrue(line.contains("Full access"), "alerts are named with full access: \(line)")
        }
    }

    /// National framing (DECISIONS 0049): the welcome names no state, no
    /// line names one agency as the app's source, and California appears
    /// only where a line is about California alone.
    func testTheIntroductionTakesNoStateAsTheDefault() throws {
        let pages = OnboardingCopy.pages
        let welcome = try XCTUnwrap(pages.first { $0.id == "welcome" })
        for line in [welcome.title, welcome.body] + welcome.points {
            XCTAssertFalse(line.contains("California"), line)
        }
        let text = pages.flatMap { [$0.title, $0.body] + $0.points }
        for line in text {
            XCTAssertFalse(line.contains("CDFW"), line)
            XCTAssertFalse(line.localizedCaseInsensitiveContains("every state"), line)
        }
        let honest = try XCTUnwrap(pages.first { $0.id == "honest" })
        for word in ["\"scheduled\"", "\"stocked\"", "\"planned\""] {
            XCTAssertTrue(honest.body.contains(word), "the honest page names \(word)")
        }
    }

    /// The national wording is something to say again: version 2, so a
    /// person who finished version 1 and keeps no favorites sees it.
    func testTheNationalIntroductionIsVersionTwo() {
        XCTAssertEqual(OnboardingCopy.version, 2)
        XCTAssertTrue(OnboardingState(completedVersion: 1).shouldShow(hasFavorites: false))
    }
}

/// The intro says only what is true: there is no account. It never claims
/// "no tracking" (`CopyAndRulesTest.kt` checks the Android twin).
final class OnboardingClaimsTests: XCTestCase {
    func testTheIntroductionNeverClaimsNoTracking() {
        let text = OnboardingCopy.pages.flatMap { [$0.title, $0.body] + $0.points }
        for line in text {
            XCTAssertFalse(line.localizedCaseInsensitiveContains("tracking"), "claims no tracking: \(line)")
        }
        XCTAssertTrue(text.contains { $0.hasPrefix("No account needed.") })
    }
}
