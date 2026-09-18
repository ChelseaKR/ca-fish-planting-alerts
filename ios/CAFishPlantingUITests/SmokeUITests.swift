import XCTest

/// One smoke path: launch, see the Browse list populated from the bundled
/// snapshot, open a water's detail, favourite it, see the first-favourite
/// notification explainer, dismiss it, switch to Favourites and see the
/// water listed there.
final class SmokeUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testBrowseToFavouriteFlow() throws {
        let app = XCUIApplication()
        app.launch()

        let browseList = app.collectionViews.firstMatch
        XCTAssertTrue(browseList.waitForExistence(timeout: 10), "Browse list should appear")

        let firstWater = browseList.cells.firstMatch
        XCTAssertTrue(firstWater.waitForExistence(timeout: 10))
        firstWater.tap()

        // The favourite button's accessibility label includes the water's
        // name, so match on the stable "favourites" substring instead.
        let starButtons = app.navigationBars.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'favourites'"))
        XCTAssertTrue(starButtons.firstMatch.waitForExistence(timeout: 5))
        starButtons.firstMatch.tap()

        let explainerTitle = app.staticTexts["Stay in the loop"]
        if explainerTitle.waitForExistence(timeout: 3) {
            app.buttons["Not now"].tap()
        }

        app.navigationBars.buttons["Waters"].firstMatch.tap()
        app.tabBars.buttons["Favourites"].tap()
        XCTAssertTrue(app.collectionViews.firstMatch.cells.firstMatch.waitForExistence(timeout: 5), "the favourited water should appear under Favourites")
    }

    /// The link the widget uses (`WaterLink`) opens that water's screen from
    /// the running app: under Favorites when it is one, otherwise under
    /// Browse. `cdfw-125` is Annie Lake, CDFW's own key, in every snapshot
    /// so far. Whether it is a favorite depends on what earlier tests left
    /// on this simulator, so the test reads that first.
    func testAWaterLinkOpensThatWater() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.collectionViews.firstMatch.waitForExistence(timeout: 30), "Browse list should appear")
        app.tabBars.buttons["About"].tap()

        app.open(URL(string: "trouttruck://water/cdfw-125")!)

        XCTAssertTrue(app.navigationBars["Annie Lake"].waitForExistence(timeout: 15), "the link should open Annie Lake:\n\(app.debugDescription)")
        let isFavorite = app.buttons["Remove Annie Lake from favourites"].exists
        // Back is titled after the list the water opened from.
        let listTitle = isFavorite ? "Favourites" : "Waters"
        let back = app.navigationBars.buttons[listTitle].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5), "the water should open under \(listTitle):\n\(app.debugDescription)")
        back.tap()
        XCTAssertTrue(app.navigationBars[listTitle].waitForExistence(timeout: 5), "Back returns to the list")
    }
}
