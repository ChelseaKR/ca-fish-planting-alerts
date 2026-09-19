import XCTest

/// One smoke path: launch, see the Browse list populated from the bundled
/// snapshot, open a water's detail, favorite it, see the first-favorite
/// notification explainer, dismiss it, switch to Favorites and see the
/// water listed there.
final class SmokeUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testBrowseToFavoriteFlow() throws {
        let app = XCUIApplication()
        app.launch()

        let browseList = app.collectionViews.firstMatch
        XCTAssertTrue(browseList.waitForExistence(timeout: 30), "Browse list should appear")

        // The first cells are the Region picker and the schedule's week, not
        // waters. Water rows are buttons labeled "<name>, <county>…";
        // search for one so the test doesn't depend on list order.
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10))
        // On a slow simulator the first tap can land before the field
        // accepts focus.
        for _ in 0..<3 where !app.keyboards.firstMatch.exists {
            search.tap()
            _ = app.keyboards.firstMatch.waitForExistence(timeout: 5)
        }
        search.typeText("Annie Lake")
        let firstWater = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Annie Lake,")).firstMatch
        XCTAssertTrue(firstWater.waitForExistence(timeout: 10), "no row for Annie Lake:\n\(app.debugDescription)")
        firstWater.tap()

        // Favorite it unless an earlier run on this simulator already did.
        let add = app.buttons["Add Annie Lake to favorites"]
        XCTAssertTrue(add.waitForExistence(timeout: 5) || app.buttons["Remove Annie Lake from favorites"].exists)
        if add.exists { add.tap() }

        let explainerTitle = app.staticTexts["Stay in the loop"]
        if explainerTitle.waitForExistence(timeout: 3) {
            app.buttons["Not now"].tap()
        }

        app.navigationBars.buttons["Waters"].firstMatch.tap()
        app.tabBars.buttons["Favorites"].tap()
        let favorite = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Annie Lake,")).firstMatch
        XCTAssertTrue(favorite.waitForExistence(timeout: 5), "the favorited water should appear under Favorites")
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
        let isFavorite = app.buttons["Remove Annie Lake from favorites"].exists
        // Back is titled after the list the water opened from.
        let listTitle = isFavorite ? "Favorites" : "Waters"
        let back = app.navigationBars.buttons[listTitle].firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5), "the water should open under \(listTitle):\n\(app.debugDescription)")
        back.tap()
        XCTAssertTrue(app.navigationBars[listTitle].waitForExistence(timeout: 5), "Back returns to the list")
    }

    /// The locked widget's link (`UnlockLink`) opens the purchase screen,
    /// from anywhere in the running app, and closing it leaves About.
    func testTheUnlockLinkOpensThePurchaseScreen() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.collectionViews.firstMatch.waitForExistence(timeout: 30), "Browse list should appear")

        app.open(URL(string: "trouttruck://unlock")!)

        XCTAssertTrue(app.navigationBars["Full access"].waitForExistence(timeout: 15), "the link should open the purchase screen:\n\(app.debugDescription)")
        let alerts = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "An alert on this device")).firstMatch
        let widget = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Favorite waters widget")).firstMatch
        XCTAssertTrue(alerts.exists && widget.exists, "the purchase screen lists alerts and the widget:\n\(app.debugDescription)")
        app.buttons["Not now"].tap()
        XCTAssertTrue(app.staticTexts["Full access"].waitForExistence(timeout: 10), "closing it leaves About")
    }
}
