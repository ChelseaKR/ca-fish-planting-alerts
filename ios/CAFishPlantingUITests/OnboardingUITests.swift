import XCTest

extension XCUIApplication {
    /// The app with the introduction skipped (the default) or shown,
    /// whatever an earlier run left on the simulator. The argument is read
    /// by Debug builds only (`OnboardingLaunchOverride`).
    static func troutTruck(onboarding: String = "skip") -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments += ["-UITestOnboarding", onboarding]
        return app
    }
}

/// The introduction: four pages, stepped with Continue or swiped, skippable,
/// and audited at the default size in light and dark mode and at AX5.
final class OnboardingUITests: XCTestCase {
    private static let titles = [
        "Welcome to Trout Truck",
        "Find your waters",
        "Star the waters you fish",
        "A week, never a day",
    ]

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    override func tearDown() {
        XCUIDevice.shared.appearance = .light
        super.tearDown()
    }

    func testContinueStepsThroughEveryPageToBrowse() throws {
        let app = XCUIApplication.troutTruck(onboarding: "show")
        app.launch()
        for (offset, title) in Self.titles.enumerated() {
            XCTAssertTrue(heading(title, in: app).waitForExistence(timeout: 10), "page \(offset + 1) should read \(title):\n\(app.debugDescription)")
            if offset < Self.titles.count - 1 {
                app.buttons["Continue"].tap()
            }
        }
        XCTAssertFalse(app.buttons["Skip"].isHittable, "the last page ends with its own button, not Skip")
        app.buttons["Start browsing"].tap()
        XCTAssertTrue(app.navigationBars["Waters"].waitForExistence(timeout: 10), "Browse should show after the introduction")
    }

    func testSkipClosesItFromTheFirstPage() throws {
        let app = XCUIApplication.troutTruck(onboarding: "show")
        app.launch()
        XCTAssertTrue(heading(Self.titles[0], in: app).waitForExistence(timeout: 10))
        app.buttons["Skip"].tap()
        XCTAssertTrue(app.navigationBars["Waters"].waitForExistence(timeout: 10))
    }

    func testSwipingMovesBetweenPages() throws {
        let app = XCUIApplication.troutTruck(onboarding: "show")
        app.launch()
        XCTAssertTrue(heading(Self.titles[0], in: app).waitForExistence(timeout: 10))
        app.swipeLeft()
        XCTAssertTrue(heading(Self.titles[1], in: app).waitForExistence(timeout: 5))
        app.swipeRight()
        XCTAssertTrue(heading(Self.titles[0], in: app).waitForExistence(timeout: 5))
    }

    /// About can bring it back.
    func testAboutShowsItAgain() throws {
        let app = XCUIApplication.troutTruck()
        app.launch()
        XCTAssertTrue(app.navigationBars["Waters"].waitForExistence(timeout: 30))
        app.tabBars.buttons["About"].tap()
        let show = app.buttons["Show the introduction"]
        let list = app.collectionViews.firstMatch
        for _ in 0..<6 where !(show.exists && show.isHittable) { list.swipeUp() }
        show.tap()
        XCTAssertTrue(heading(Self.titles[0], in: app).waitForExistence(timeout: 10))
        app.buttons["Skip"].tap()
        XCTAssertTrue(app.navigationBars["About"].waitForExistence(timeout: 10))
    }

    func testEveryPagePassesTheAccessibilityAuditInLightMode() throws {
        try auditEveryPage(contentSize: nil, appearance: .light)
    }

    func testEveryPagePassesTheAccessibilityAuditInDarkMode() throws {
        try auditEveryPage(contentSize: nil, appearance: .dark)
    }

    func testEveryPagePassesTheAccessibilityAuditAtTheLargestTextSize() throws {
        try auditEveryPage(contentSize: "UICTContentSizeCategoryAccessibilityXXXL", appearance: .light)
    }

    // MARK: -

    /// A page's title. VoiceOver reads it with its place ("…, page 2 of 4").
    private func heading(_ title: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", title)).firstMatch
    }

    private func auditEveryPage(contentSize: String?, appearance: XCUIDevice.Appearance) throws {
        continueAfterFailure = true
        XCUIDevice.shared.appearance = appearance
        let app = XCUIApplication.troutTruck(onboarding: "show")
        if let contentSize {
            app.launchArguments += ["-UIPreferredContentSizeCategoryName", contentSize]
        }
        app.launch()
        let label = "\(contentSize == nil ? "default size" : "AX5"), \(appearance == .dark ? "dark" : "light")"
        for (offset, title) in Self.titles.enumerated() {
            XCTAssertTrue(heading(title, in: app).waitForExistence(timeout: 10), "page \(offset + 1):\n\(app.debugDescription)")
            // Let the page settle; mid-swipe two pages share the screen.
            Thread.sleep(forTimeInterval: 1)
            var lines: [String] = []
            try app.performAccessibilityAudit(for: .all) { issue in
                let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.frame)" } ?? "no element"
                let description = "\(issue.auditType.rawValue): \(issue.compactDescription) — \(element)"
                // The page dots are UIKit's own control, drawn by
                // `UIPageControl`; its hit region is the system's.
                if let element = issue.element, element.elementType == .pageIndicator {
                    lines.append("RECORDED (UIKit's page control) \(description)")
                    return true
                }
                lines.append("FAILED \(description)")
                return false
            }
            let attachment = XCTAttachment(string: lines.isEmpty ? "no issues" : lines.joined(separator: "\n"))
            attachment.name = "Introduction page \(offset + 1) audit (\(label))"
            attachment.lifetime = .keepAlways
            add(attachment)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "Introduction page \(offset + 1) (\(label))"
            shot.lifetime = .keepAlways
            add(shot)
            if offset < Self.titles.count - 1 {
                let next = app.buttons["Continue"]
                XCTAssertTrue(next.waitForExistence(timeout: 5))
                next.tap()
            }
        }
    }
}
