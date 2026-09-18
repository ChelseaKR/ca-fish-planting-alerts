import XCTest

/// The app's accent color is the icon's green. It colors text (links, the
/// Region menu, toolbar buttons), so each appearance must keep WCAG AA
/// contrast, 4.5:1, on the backgrounds that text sits on. Read from the
/// asset catalog itself, so a later color change is checked too.
final class AccentColorContrastTests: XCTestCase {
    private struct RGB { let r, g, b: Double }

    // iOS system backgrounds the accent draws on.
    private let white = RGB(r: 1, g: 1, b: 1)                                 // list rows, light
    private let groupedLight = RGB(r: 242 / 255, g: 242 / 255, b: 247 / 255)  // grouped background, light
    private let black = RGB(r: 0, g: 0, b: 0)                                 // background, dark
    private let rowDark = RGB(r: 28 / 255, g: 28 / 255, b: 30 / 255)          // list rows, dark

    func testTheAccentKeepsAAContrastInLightAndDarkMode() throws {
        let colors = try accentColors()
        let light = try XCTUnwrap(colors.light, "the accent needs a light (any) appearance")
        let dark = try XCTUnwrap(colors.dark, "the accent needs a dark appearance: one green can't pass on both")
        for (name, background) in [("white", white), ("grouped", groupedLight)] {
            XCTAssertGreaterThanOrEqual(contrast(light, background), 4.5, "light accent on \(name)")
        }
        for (name, background) in [("black", black), ("dark row", rowDark)] {
            XCTAssertGreaterThanOrEqual(contrast(dark, background), 4.5, "dark accent on \(name)")
        }
        XCTAssertGreaterThanOrEqual(contrast(white, light), 4.5, "white button text on the light accent")
    }

    /// Negative control: the check fails the color it replaced
    /// (Xcode's default system blue in light mode is 4.02:1 on white).
    func testTheCheckWouldCatchALowContrastAccent() {
        let systemBlue = RGB(r: 0, g: 122 / 255, b: 1)
        XCTAssertLessThan(contrast(systemBlue, white), 4.5)
        XCTAssertLessThan(contrast(RGB(r: 1, g: 0.8, b: 0), white), 4.5, "yellow on white")
    }

    // MARK: -

    private func contrast(_ a: RGB, _ b: RGB) -> Double {
        let la = luminance(a), lb = luminance(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
    }

    private func luminance(_ c: RGB) -> Double {
        func channel(_ v: Double) -> Double { v <= 0.03928 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4) }
        return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b)
    }

    private func accentColors() throws -> (light: RGB?, dark: RGB?) {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // PlantingCoreTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // PlantingCore
            .deletingLastPathComponent() // ios
        let url = ios.appendingPathComponent("CAFishPlanting/Resources/Assets.xcassets/AccentColor.colorset/Contents.json")
        let json = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        var light: RGB?
        var dark: RGB?
        for entry in json?["colors"] as? [[String: Any]] ?? [] {
            guard let color = entry["color"] as? [String: Any],
                  color["color-space"] as? String == "srgb",
                  let components = color["components"] as? [String: String],
                  let r = components["red"].flatMap(Self.component),
                  let g = components["green"].flatMap(Self.component),
                  let b = components["blue"].flatMap(Self.component)
            else { continue }
            let appearances = entry["appearances"] as? [[String: String]] ?? []
            if appearances.contains(where: { $0["value"] == "dark" }) {
                dark = RGB(r: r, g: g, b: b)
            } else if appearances.isEmpty {
                light = RGB(r: r, g: g, b: b)
            }
        }
        return (light, dark)
    }

    /// Asset catalogs write components as "0x4B" or as "0.294".
    private static func component(_ string: String) -> Double? {
        if string.hasPrefix("0x"), let value = Int(string.dropFirst(2), radix: 16) { return Double(value) / 255 }
        return Double(string)
    }
}
