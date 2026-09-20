import XCTest
@testable import PlantingCore

final class WaterLinkTests: XCTestCase {
    func testALinkRoundTripsToTheSameWater() throws {
        let url = WaterLink.url(for: "cdfw-125")
        XCTAssertEqual(url.absoluteString, "trouttruck://water/cdfw-125")
        XCTAssertEqual(WaterLink.waterID(from: url), "cdfw-125")
    }

    func testTheSchemeAndHostAreCaseInsensitive() throws {
        let url = try XCTUnwrap(URL(string: "TroutTruck://Water/cdfw-7"))
        XCTAssertEqual(WaterLink.waterID(from: url), "cdfw-7")
    }

    func testAnythingElseIsNotAWaterLink() throws {
        let notLinks = [
            "https://chelseakr.github.io/ca-fish-planting-alerts/water/annie-lake/",
            "trouttruck://water",
            "trouttruck://water/",
            "trouttruck://water/cdfw-1/extra",
            "trouttruck://county/cdfw-1",
            "otherapp://water/cdfw-1",
        ]
        for string in notLinks {
            let url = try XCTUnwrap(URL(string: string), string)
            XCTAssertNil(WaterLink.waterID(from: url), "\(string) must not open a water")
        }
    }

    func testTheUnlockLinkIsItsOwnLink() throws {
        XCTAssertEqual(UnlockLink.url.absoluteString, "trouttruck://unlock")
        XCTAssertTrue(UnlockLink.matches(UnlockLink.url))
        XCTAssertTrue(UnlockLink.matches(try XCTUnwrap(URL(string: "TroutTruck://Unlock"))))
        XCTAssertNil(WaterLink.waterID(from: UnlockLink.url), "the unlock link never opens a water")
        XCTAssertFalse(UnlockLink.matches(WaterLink.url(for: "cdfw-1")))
        XCTAssertFalse(UnlockLink.matches(try XCTUnwrap(URL(string: "otherapp://unlock"))))
    }

    func testANotificationCarriesItsWaterID() {
        XCTAssertEqual(WaterLink.waterID(fromNotificationUserInfo: [WaterLink.notificationWaterIDKey: "cdfw-9"]), "cdfw-9")
        XCTAssertNil(WaterLink.waterID(fromNotificationUserInfo: [:]), "an alert without a water opens the app, not a blank screen")
        XCTAssertNil(WaterLink.waterID(fromNotificationUserInfo: [WaterLink.notificationWaterIDKey: ""]))
        XCTAssertNil(WaterLink.waterID(fromNotificationUserInfo: [WaterLink.notificationWaterIDKey: 42]))
    }

    /// The alert and its link must agree on the water, or a tapped alert
    /// opens a different screen than it names.
    func testAPlannedAlertCarriesTheWaterItNames() {
        let planned = PlannedNotification(waterID: "cdfw-3", waterName: "Test Lake",
                                          newKeys: [PlantKey(weekStart: TS.date("2026-09-13"), species: "Trout")])
        XCTAssertEqual(planned.userInfo[WaterLink.notificationWaterIDKey] as? String, "cdfw-3")
        XCTAssertEqual(WaterLink.waterID(fromNotificationUserInfo: planned.userInfo), planned.waterID)
    }
}
