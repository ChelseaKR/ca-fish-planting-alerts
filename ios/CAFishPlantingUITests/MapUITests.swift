import XCTest

/// The Map tab, Near me and a water's Location section (DECISIONS 0025),
/// against the bundled snapshot and locations. Screenshots are kept as
/// attachments for review.
///
/// Run with the app's location permission reset and a simulated location
/// set (`xcrun simctl privacy <udid> reset location …`, `xcrun simctl
/// location <udid> set 37.6485,-118.9721`): the explainer test needs the
/// permission undecided, and runs first (tests run in name order).
final class MapUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    override func tearDown() {
        XCUIDevice.shared.appearance = .light
        super.tearDown()
    }

    func testMapTabSaysHowManyWatersArePlaced() throws {
        let app = XCUIApplication.troutTruck()
        app.launch()
        app.tab("Map").tap()
        let caption = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "waters have a location")).firstMatch
        XCTAssertTrue(caption.waitForExistence(timeout: 20))
        XCTAssertTrue(caption.label.contains("never guessed onto the map"))
        XCTAssertTrue(app.buttons["Near me"].exists)
        settle()
        shot("map-tab-\(device)-light", app)
        // Dark mode only takes for a fresh launch.
        app.terminate()
        XCUIDevice.shared.appearance = .dark
        app.launch()
        app.tab("Map").tap()
        XCTAssertTrue(caption.waitForExistence(timeout: 20))
        settle()
        shot("map-tab-\(device)-dark", app)
    }

    func testNearMeExplainsBeforeIOSAsks() throws {
        let app = XCUIApplication.troutTruck()
        app.launch()
        app.tab("Map").tap()
        XCTAssertTrue(app.buttons["Near me"].waitForExistence(timeout: 20))
        app.buttons["Near me"].tap()
        XCTAssertTrue(app.staticTexts["Find waters near you"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "used on this iPhone only")).firstMatch.exists)
        settle()
        shot("near-me-explainer-\(device)", app)
        // Saying no leaves everything working.
        app.buttons["Not now"].tap()
        XCTAssertTrue(app.buttons["Near me"].waitForExistence(timeout: 10))
    }

    /// The list after the permission is granted, at the simulator's
    /// location (Mammoth Lakes).
    func testNearMeListsWatersWhenAllowed() throws {
        // The simulator's own permission prompt does not reliably appear
        // under UI automation (locationd logs it as in flight, SpringBoard
        // never shows it), so this runs only with the permission granted
        // up front by `xcrun simctl privacy <udid> grant location …`.
        try XCTSkipUnless(ProcessInfo.processInfo.environment["TT_LOCATION_GRANTED"] == "1", "grant location first")
        let app = XCUIApplication.troutTruck()
        app.launch()
        app.tab("Map").tap()
        app.buttons["Near me"].tap()
        if app.buttons["Continue"].waitForExistence(timeout: 10) {
            app.buttons["Continue"].tap()
            let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
            let allow = springboard.buttons["Allow While Using App"]
            if allow.waitForExistence(timeout: 10) { allow.tap() }
        }
        let footer = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "not saved or sent anywhere")).firstMatch
        XCTAssertTrue(footer.waitForExistence(timeout: 30))
        // Mammoth Lakes: Mammoth Creek is the nearest water, 1.2 miles away.
        let first = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Mammoth Creek")).firstMatch
        XCTAssertTrue(first.waitForExistence(timeout: 5))
        XCTAssertTrue(first.label.contains("1.2 mi"), first.label)
        settle()
        shot("near-me-list-\(device)", app)
        app.buttons["Done"].tap()
        settle()
        shot("map-near-me-\(device)", app)
    }

    func testWaterPagesShowALocationOrSayThereIsNone() throws {
        let app = XCUIApplication.troutTruck()
        app.launch()
        open("Crowley Lake", id: "cdfw-17884", in: app)
        XCTAssertTrue(app.staticTexts["A point inside the lake."].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Directions"].exists)
        settle()
        shot("water-lake-\(device)-light", app)

        open("American River Silver Fork", id: "cdfw-500017", in: app)
        let approximate = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Approximate")).firstMatch
        XCTAssertTrue(approximate.waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Directions to this point"].exists)
        settle()
        shot("water-stream-\(device)", app)

        open("Kenneth Hahn Lake", id: "cdfw-27436", in: app)
        let none = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "No map location.")).firstMatch
        XCTAssertTrue(none.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["Directions"].exists)
        settle()
        shot("water-no-location-\(device)", app)
    }

    private var device: String { UIDevice.current.userInterfaceIdiom == .pad ? "ipad" : "iphone" }

    /// Opens a water by the app's own link (trouttruck://water/<id>), the
    /// way a widget or an alert does: no typing into search, which is
    /// unreliable on iPad with a hardware keyboard.
    private func open(_ name: String, id: String, in app: XCUIApplication) {
        app.open(URL(string: "trouttruck://water/\(id)")!)
        XCTAssertTrue(app.navigationBars[name].waitForExistence(timeout: 15), name)
        app.swipeUp()
    }

    private func settle() { Thread.sleep(forTimeInterval: 2) }

    private func shot(_ name: String, _ app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
