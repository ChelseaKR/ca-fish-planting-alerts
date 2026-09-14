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
}
