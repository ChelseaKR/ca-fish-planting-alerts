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
    /// "stocked", never a price, and alerts only ever as part of full access.
    func testTheCopyKeepsTheAppsWordingRules() {
        let pages = OnboardingCopy.pages
        XCTAssertEqual(Set(pages.map(\.id)).count, pages.count, "page ids are unique")
        let text = pages.flatMap { [$0.title, $0.body] + $0.points }
        let days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "today", "tomorrow"]
        for line in text {
            XCTAssertFalse(line.localizedCaseInsensitiveContains("stocked"), line)
            XCTAssertFalse(line.contains("$"), "no price: \(line)")
            for day in days { XCTAssertFalse(line.localizedCaseInsensitiveContains(day), "\(day) in: \(line)") }
        }
        let alertLines = text.filter { $0.localizedCaseInsensitiveContains("an alert") }
        XCTAssertFalse(alertLines.isEmpty)
        for line in alertLines {
            XCTAssertTrue(line.contains("Full access"), "alerts are named with full access: \(line)")
        }
    }
}
