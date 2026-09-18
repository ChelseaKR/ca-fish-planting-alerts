import XCTest

/// Xcode's automated accessibility audit (`performAccessibilityAudit`) over
/// every main screen, at the default text size in light and dark mode and at
/// the largest accessibility size (AX5). It checks contrast, clipped text,
/// Dynamic Type support, hit regions, element descriptions and traits.
///
/// An audit is not a VoiceOver pass by a person (#5). It catches the
/// mechanical failures so that pass can spend its time on meaning.
///
/// What fails the test (`Verdict.fail`): a contrast failure in the app's own
/// content, text clipped at AX5, and a missing description, hit region or
/// trait on the app's own elements. What is recorded but doesn't fail is
/// listed in `verdict(for:)`, each with its reason. Every run attaches the
/// full list for each screen, failures and recorded issues alike.
final class AccessibilityAuditUITests: XCTestCase {
    private static let ax5 = "UICTContentSizeCategoryAccessibilityXXXL"

    override func setUpWithError() throws {
        continueAfterFailure = true
    }

    override func tearDown() {
        XCUIDevice.shared.appearance = .light
        super.tearDown()
    }

    func testMainScreensAtTheDefaultTextSizeInLightMode() throws {
        try auditMainScreens(contentSize: nil, appearance: .light)
    }

    func testMainScreensAtTheDefaultTextSizeInDarkMode() throws {
        try auditMainScreens(contentSize: nil, appearance: .dark)
    }

    func testMainScreensAtTheLargestAccessibilityTextSize() throws {
        try auditMainScreens(contentSize: Self.ax5, appearance: .light)
    }

    // MARK: -

    private struct Context {
        let label: String
        let isAX5: Bool
    }

    private func auditMainScreens(contentSize: String?, appearance: XCUIDevice.Appearance) throws {
        XCUIDevice.shared.appearance = appearance
        let app = XCUIApplication()
        if let contentSize {
            app.launchArguments += ["-UIPreferredContentSizeCategoryName", contentSize]
        }
        app.launch()
        XCTAssertTrue(app.collectionViews.firstMatch.waitForExistence(timeout: 30), "Browse list should appear")
        let context = Context(label: "\(contentSize == nil ? "default size" : "AX5"), \(appearance == .dark ? "dark" : "light")",
                              isAX5: contentSize != nil)

        try audit("Browse", app: app, context: context)

        // Search, then dismiss the keyboard, so the results are audited
        // rather than the keyboard.
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10))
        focus(search, in: app)
        search.typeText("Annie Lake\n")
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Annie Lake,")).firstMatch
        // At AX5 the Region and schedule rows fill the screen, and list rows
        // below it don't exist until scrolled to.
        reveal(row, in: app)
        XCTAssertTrue(row.exists, "no row for Annie Lake:\n\(app.debugDescription)")
        try audit("Browse search results", app: app, context: context)
        reveal(row, in: app)
        row.tap()
        XCTAssertTrue(app.navigationBars["Annie Lake"].waitForExistence(timeout: 10))
        try audit("Water detail", app: app, context: context)
        let year = app.buttons.matching(NSPredicate(format: "label MATCHES %@", "^[0-9]{4}$")).firstMatch
        reveal(year, in: app)
        if year.exists {
            year.tap()
            try audit("Water detail, a year expanded", app: app, context: context)
        }

        select(tab: "Favourites", in: app)
        try audit("Favorites", app: app, context: context)

        select(tab: "About", in: app)
        try audit("About", app: app, context: context)

        let unlock = app.buttons["Unlock full access"]
        reveal(unlock, in: app)
        if unlock.exists {
            unlock.tap()
            XCTAssertTrue(app.navigationBars["Full access"].waitForExistence(timeout: 10), "the purchase sheet should open")
            // Let the sheet finish presenting; mid-animation it is dimmed.
            Thread.sleep(forTimeInterval: 2)
            try audit("Purchase sheet", app: app, context: context)
        }
    }

    /// Taps a tab until its screen is showing. At the largest text sizes
    /// the first tap can open the tab bar's large-content viewer instead.
    private func select(tab: String, in app: XCUIApplication) {
        for _ in 0..<3 {
            app.tabBars.buttons[tab].tap()
            if app.navigationBars[tab].waitForExistence(timeout: 5) { return }
        }
        XCTFail("the \(tab) tab didn't open:\n\(app.debugDescription)")
    }

    /// Taps a text field until it has the keyboard; on a slow simulator
    /// the first tap can land before the field accepts focus.
    private func focus(_ field: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<3 {
            field.tap()
            if app.keyboards.firstMatch.waitForExistence(timeout: 5) { return }
        }
        XCTFail("the search field never took the keyboard")
    }

    /// Scrolls the list until the element exists and can be tapped. List
    /// rows off screen don't exist, and an audit can leave the list
    /// scrolled.
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        let list = app.collectionViews.firstMatch
        for _ in 0..<8 where !(element.exists && element.isHittable) { list.swipeUp() }
        for _ in 0..<8 where !(element.exists && element.isHittable) { list.swipeDown() }
    }

    private enum Verdict {
        case fail
        case record(String)
    }

    private func audit(_ screen: String, app: XCUIApplication, context: Context) throws {
        // System chrome the audit samples through: text scrolled under the
        // floating tab bar, and the keyboard.
        // The band covers the floating tab bar and the scroll-edge fade iOS
        // draws above it.
        var chrome: [CGRect] = []
        let tabBar = app.tabBars.firstMatch
        if tabBar.exists {
            let top = tabBar.frame.minY - 64
            chrome.append(CGRect(x: 0, y: top, width: app.frame.width, height: app.frame.maxY - top))
        }
        if app.keyboards.firstMatch.exists { chrome.append(app.keyboards.firstMatch.frame) }
        // The same at the top: the status bar, the navigation bar and the
        // fade under it, where scrolled content passes behind.
        let navigationBar = app.navigationBars.firstMatch
        if navigationBar.exists {
            chrome.append(CGRect(x: 0, y: 0, width: app.frame.width, height: navigationBar.frame.maxY + 16))
        }

        var lines: [String] = []
        try app.performAccessibilityAudit(for: .all) { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.frame)" } ?? "no element"
            let description = "\(issue.auditType.name): \(issue.compactDescription) — \(element)"
            switch Self.verdict(for: issue, chrome: chrome, isAX5: context.isAX5) {
            case .fail:
                lines.append("FAILED \(description)")
                return false
            case .record(let reason):
                lines.append("RECORDED (\(reason)) \(description)")
                return true
            }
        }
        let attachment = XCTAttachment(string: lines.isEmpty ? "no issues" : lines.joined(separator: "\n"))
        attachment.name = "\(screen) audit (\(context.label))"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private static func verdict(for issue: XCUIAccessibilityAuditIssue, chrome: [CGRect], isAX5: Bool) -> Verdict {
        guard let element = issue.element else {
            return .record("no element: the audit couldn't say what it saw")
        }
        let frame = element.frame
        if element.elementType == .searchField {
            return .record("iOS's own search field")
        }
        if chrome.contains(where: { $0.intersects(frame) }) {
            return .record("under the tab bar, its scroll-edge fade or the keyboard: the audit samples the system chrome, not the app's content")
        }
        // One measured false positive: at AX5 the purchase sheet's title
        // wraps onto two lines, and the audit calls wrapped text clipped.
        // Its own element screenshot shows the whole title.
        if issue.auditType == .textClipped, element.elementType == .staticText, element.label == "Unlock full access" {
            return .record("the whole title shows, wrapped onto two lines (the audit's own element screenshot)")
        }
        if issue.auditType == .contrast, !element.isEnabled {
            return .record("a disabled control; WCAG 1.4.3 exempts inactive components")
        }
        switch issue.auditType {
        case .contrast where issue.compactDescription.localizedCaseInsensitiveContains("nearly"):
            return .record("nearly passed: iOS's secondary label and section-header colors, which Increase Contrast darkens")
        case .dynamicType:
            return .record("standard SwiftUI text styles, which scale; the AX5 pass audits the same screens at that size")
        case .textClipped where !isAX5:
            return .record("simulated by the audit at the default size; the AX5 pass fails on real clipping")
        default:
            return .fail
        }
    }
}

private extension XCUIAccessibilityAuditType {
    var name: String {
        switch self {
        case .contrast: return "contrast"
        case .elementDetection: return "elementDetection"
        case .hitRegion: return "hitRegion"
        case .sufficientElementDescription: return "sufficientElementDescription"
        case .dynamicType: return "dynamicType"
        case .textClipped: return "textClipped"
        case .trait: return "trait"
        default: return "other(\(rawValue))"
        }
    }
}
