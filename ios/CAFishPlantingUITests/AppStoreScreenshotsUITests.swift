import XCTest

/// Captures the App Store screenshot set from the snapshot bundled with the
/// app, which is real pipeline output (`ios/README.md`), never a fixture.
///
/// Skipped unless `ios/scripts/app-store-screenshots.sh` runs it. That script
/// reads the bundled snapshot, picks the region and waters below, and passes
/// them in as `TEST_RUNNER_` variables, so the shots follow the data instead
/// of names hardcoded here that go stale every week.
///
/// - `TT_REGION`: the region picker label to filter Browse by.
/// - `TT_HISTORY_WATER`: the water whose history is shown. It is also the
///   first favourite, so the notification explainer names it.
/// - `TT_FAVOURITES`: `|`-separated water names to favourite after it.
/// - `TT_OUTPUT_DIR`: where the PNGs are written, on the Mac running the
///   simulator.
final class AppStoreScreenshotsUITests: XCTestCase {
    private struct Plan {
        let region: String
        let historyWater: String
        let favourites: [String]
        let outputDirectory: URL
    }

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testCaptureAppStoreScreenshots() throws {
        let plan = try readPlan()
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.collectionViews.firstMatch.waitForExistence(timeout: 30), "Browse list should appear")

        // 1. Browse, filtered to the region with the most waters on this
        //    week's schedule, so the "This week" badges are on screen.
        selectRegion(plan.region, in: app)
        let badged = app.buttons.matching(NSPredicate(format: "label ENDSWITH %@", "scheduled this week"))
        XCTAssertTrue(badged.firstMatch.waitForExistence(timeout: 10), "a water scheduled this week should be listed in \(plan.region)")
        capture("01-this-week", app: app, into: plan.outputDirectory)
        selectRegion("All regions", in: app)

        // 2. One water's week-by-week history, the newest year expanded.
        openWater(plan.historyWater, in: app)
        let newestYear = app.buttons.matching(NSPredicate(format: "label MATCHES %@", "^[0-9]{4}$")).firstMatch
        XCTAssertTrue(newestYear.waitForExistence(timeout: 10), "the history should have at least one year")
        newestYear.tap()
        let planted = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "week of ")).firstMatch
        XCTAssertTrue(planted.waitForExistence(timeout: 5), "expanding the year should list its weeks")
        capture("02-water-history", app: app, into: plan.outputDirectory)

        // 4. The first favourite shows the notification explainer. It names
        //    the paid unlock but never a price.
        favouriteOpenWater(plan.historyWater, in: app)
        XCTAssertTrue(app.staticTexts["Stay in the loop"].waitForExistence(timeout: 10), "the first favourite should show the explainer")
        capture("04-notifications", app: app, into: plan.outputDirectory)
        app.buttons["Not now"].tap()
        goBackToWaters(in: app)

        for name in plan.favourites {
            openWater(name, in: app)
            favouriteOpenWater(name, in: app)
            goBackToWaters(in: app)
        }

        // 3. Favourites.
        app.tabBars.buttons["Favourites"].tap()
        let favouritesList = app.collectionViews.firstMatch
        XCTAssertTrue(favouritesList.waitForExistence(timeout: 10))
        let firstFavourite = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", plan.historyWater + ",")).firstMatch
        XCTAssertTrue(firstFavourite.waitForExistence(timeout: 10), "\(plan.historyWater) should be listed under Favourites")
        capture("03-favourites", app: app, into: plan.outputDirectory)

        // 5. About, scrolled so the Privacy section sits just under the
        //    navigation bar, with the CDFW attribution and the "not
        //    affiliated" line below it.
        app.tabBars.buttons["About"].tap()
        XCTAssertTrue(app.staticTexts["Full access"].waitForExistence(timeout: 10), "About did not open")
        let privacyHeader = app.staticTexts["Privacy"]
        scroll(privacyHeader, toJustBelowNavigationBarIn: app)
        XCTAssertTrue(privacyHeader.isHittable, "the Privacy section should be on screen:\n\(app.debugDescription)")
        let notAffiliated = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "not affiliated with or endorsed by")).firstMatch
        XCTAssertTrue(notAffiliated.isHittable, "the not-affiliated line should be on screen")
        let attribution = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "California Department of Fish and Wildlife")).firstMatch
        XCTAssertTrue(attribution.exists, "the CDFW attribution should be on screen")
        capture("05-about", app: app, into: plan.outputDirectory)
    }

    // MARK: - Steps

    private func readPlan() throws -> Plan {
        let env = ProcessInfo.processInfo.environment
        try XCTSkipUnless(env["TT_SCREENSHOTS"] == "1", "captures App Store screenshots; run ios/scripts/app-store-screenshots.sh")
        func required(_ key: String) throws -> String {
            try XCTUnwrap(env[key].flatMap { $0.isEmpty ? nil : $0 }, "\(key) is not set")
        }
        return Plan(
            region: try required("TT_REGION"),
            historyWater: try required("TT_HISTORY_WATER"),
            favourites: try required("TT_FAVOURITES").split(separator: "|").map(String.init),
            outputDirectory: URL(fileURLWithPath: try required("TT_OUTPUT_DIR"), isDirectory: true)
        )
    }

    private func selectRegion(_ region: String, in app: XCUIApplication) {
        let picker = app.buttons.matching(NSPredicate(format: "label == 'Region' OR label BEGINSWITH 'Region,'")).firstMatch
        XCTAssertTrue(picker.waitForExistence(timeout: 10), "region picker not found:\n\(app.debugDescription)")
        picker.tap()
        let option = app.buttons[region].exists ? app.buttons[region] : app.menuItems[region]
        XCTAssertTrue(option.waitForExistence(timeout: 5), "region option \(region) not found:\n\(app.debugDescription)")
        option.tap()
    }

    /// Searches Browse for the water by name and opens it. Rows carry a
    /// combined accessibility label that starts with "<name>, <county>".
    private func openWater(_ name: String, in app: XCUIApplication) {
        let field = app.searchFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 10), "search field not found:\n\(app.debugDescription)")
        field.tap()
        // Deleting characters would start wherever the tap put the cursor.
        let clear = field.buttons["Clear text"]
        if clear.exists { clear.tap() }
        field.typeText(name)
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", name + ",")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), "no row for \(name):\n\(app.debugDescription)")
        row.tap()
        XCTAssertTrue(app.navigationBars[name].waitForExistence(timeout: 10), "\(name) detail did not open")
    }

    private func favouriteOpenWater(_ name: String, in app: XCUIApplication) {
        let star = app.buttons["Add \(name) to favourites"]
        XCTAssertTrue(star.waitForExistence(timeout: 5), "favourite button for \(name) not found")
        star.tap()
        XCTAssertTrue(app.buttons["Remove \(name) from favourites"].waitForExistence(timeout: 5), "\(name) was not favourited")
    }

    private func goBackToWaters(in app: XCUIApplication) {
        let back = app.navigationBars.buttons["Waters"].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5), "back button not found:\n\(app.debugDescription)")
        back.tap()
    }

    /// Drags the list in slow, held steps (no fling) until `element` sits
    /// just under the navigation bar, so no text is left half-hidden under
    /// the bar's blur. List rows below the screen don't exist until they
    /// are scrolled near, so it keeps dragging until the element appears.
    private func scroll(_ element: XCUIElement, toJustBelowNavigationBarIn app: XCUIApplication) {
        let middle = app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55))
        func drag(_ distance: CGFloat) {
            middle.press(forDuration: 0.1, thenDragTo: middle.withOffset(CGVector(dx: 0, dy: -distance)),
                         withVelocity: .slow, thenHoldForDuration: 0.4)
        }
        for _ in 0..<12 {
            guard element.exists else { drag(300); continue }
            let target = app.navigationBars.firstMatch.frame.maxY + 12
            let distance = element.frame.minY - target
            if abs(distance) < 6 { break }
            drag(max(-300, min(300, distance)))
        }
    }

    /// Waits for animations to settle, then writes the full-resolution
    /// screen (status bar included) as `<name>.png` and attaches it too.
    private func capture(_ name: String, app: XCUIApplication, into directory: URL) {
        Thread.sleep(forTimeInterval: 1.5)
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try screenshot.pngRepresentation.write(to: directory.appendingPathComponent("\(name).png"))
        } catch {
            XCTFail("could not write \(name).png: \(error)")
        }
    }
}
