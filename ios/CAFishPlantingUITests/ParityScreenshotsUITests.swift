import XCTest

/// Screenshots of the main screens, in light and dark mode, in portrait
/// and (on iPad) landscape, kept as test attachments for review. Not the
/// App Store set (`AppStoreScreenshotsUITests` is).
///
/// Skipped unless `TEST_RUNNER_TT_PARITY_SHOTS=1` is set, so the normal
/// suite doesn't spend minutes on it.
final class ParityScreenshotsUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = true
        try XCTSkipUnless(ProcessInfo.processInfo.environment["TT_PARITY_SHOTS"] == "1", "set TEST_RUNNER_TT_PARITY_SHOTS=1 to capture")
    }

    override func tearDown() {
        XCUIDevice.shared.appearance = .light
        XCUIDevice.shared.orientation = .portrait
        super.tearDown()
    }

    func testCaptureLight() throws { try capture(appearance: .light) }

    func testCaptureDark() throws { try capture(appearance: .dark) }

    private func capture(appearance: XCUIDevice.Appearance) throws {
        XCUIDevice.shared.appearance = appearance
        let isPad = UIDevice.current.userInterfaceIdiom == .pad
        let orientations: [(String, UIDeviceOrientation)] = isPad ? [("portrait", .portrait), ("landscape", .landscapeLeft)] : [("portrait", .portrait)]
        let mode = appearance == .dark ? "dark" : "light"
        for (orientationName, orientation) in orientations {
            XCUIDevice.shared.orientation = orientation
            let suffix = "\(isPad ? "ipad" : "iphone")-\(orientationName)-\(mode)"

            let intro = XCUIApplication.troutTruck(onboarding: "show")
            intro.launch()
            XCTAssertTrue(intro.buttons["Continue"].waitForExistence(timeout: 30))
            settle()
            shot("onboarding-1-\(suffix)", intro)
            intro.buttons["Continue"].tap()
            intro.buttons["Continue"].tap()
            settle()
            shot("onboarding-3-\(suffix)", intro)
            intro.terminate()

            let app = XCUIApplication.troutTruck()
            app.launch()
            XCTAssertTrue(app.collectionViews.firstMatch.waitForExistence(timeout: 30))
            settle()
            shot("browse-\(suffix)", app)

            let search = app.searchFields.firstMatch
            if search.waitForExistence(timeout: 10) {
                for _ in 0..<3 where !app.keyboards.firstMatch.exists {
                    search.tap()
                    _ = app.keyboards.firstMatch.waitForExistence(timeout: 5)
                }
                search.typeText("Annie Lake\n")
                let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Annie Lake,")).firstMatch
                if row.waitForExistence(timeout: 10) {
                    row.tap()
                    XCTAssertTrue(app.navigationBars["Annie Lake"].waitForExistence(timeout: 10))
                    if app.buttons["Add Annie Lake to favorites"].exists {
                        app.buttons["Add Annie Lake to favorites"].tap()
                        if app.buttons["Not now"].waitForExistence(timeout: 3) { app.buttons["Not now"].tap() }
                    }
                    settle()
                    shot("water-\(suffix)", app)
                }
            }

            app.tab("Favorites").tap()
            settle()
            shot("favorites-\(suffix)", app)
            app.tab("About").tap()
            settle()
            shot("about-\(suffix)", app)
            app.terminate()
        }
    }

    /// The state picker, a Tennessee water and Tennessee's purchase sheet
    /// (DECISIONS 0025).
    func testCaptureStates() throws {
        let isPad = UIDevice.current.userInterfaceIdiom == .pad
        let suffix = isPad ? "ipad" : "iphone"
        let app = XCUIApplication.troutTruck()
        app.launch()
        XCTAssertTrue(app.collectionViews.firstMatch.waitForExistence(timeout: 30))
        let states = app.buttons["states-button"]
        XCTAssertTrue(states.waitForExistence(timeout: 10))
        states.tap()
        XCTAssertTrue(app.navigationBars["States"].waitForExistence(timeout: 10))
        settle()
        shot("states-\(suffix)", app)
        app.buttons["Browse Tennessee"].tap()
        settle()
        shot("browse-tn-\(suffix)", app)

        let search = app.searchFields.firstMatch
        if search.waitForExistence(timeout: 10) {
            for _ in 0..<3 where !app.keyboards.firstMatch.exists {
                search.tap()
                _ = app.keyboards.firstMatch.waitForExistence(timeout: 5)
            }
            search.typeText("Tellico River\n")
            let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Tellico River,")).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 10))
            row.tap()
            XCTAssertTrue(app.navigationBars["Tellico River"].waitForExistence(timeout: 10))
            if app.buttons["Add Tellico River to favorites"].exists {
                app.buttons["Add Tellico River to favorites"].tap()
                if app.buttons["Not now"].waitForExistence(timeout: 3) { app.buttons["Not now"].tap() }
            }
            settle()
            shot("water-tn-\(suffix)", app)
            let unlock = app.buttons["unlock-state"]
            if unlock.waitForExistence(timeout: 5) {
                unlock.tap()
                settle()
                shot("purchase-tn-\(suffix)", app)
            }
        }
        app.terminate()
    }

    private func settle() { Thread.sleep(forTimeInterval: 1.5) }

    private func shot(_ name: String, _ app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
