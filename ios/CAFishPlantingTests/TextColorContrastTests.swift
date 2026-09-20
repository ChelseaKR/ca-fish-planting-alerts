import UIKit
import XCTest
@testable import CAFishPlanting

/// The app's gray text meets WCAG AA (4.5:1 for body text) on every
/// background it sits on, in light and dark mode, base and elevated (sheets),
/// without Increase Contrast, and keeps its hierarchy. Backgrounds are
/// resolved by UIKit itself, not typed in.
final class TextColorContrastTests: XCTestCase {
    private static let aa = 4.5

    private let backgrounds: [(name: String, color: UIColor)] = [
        ("systemBackground", .systemBackground),
        ("systemGroupedBackground", .systemGroupedBackground),
        ("secondarySystemGroupedBackground", .secondarySystemGroupedBackground),
    ]

    private func traits(_ style: UIUserInterfaceStyle, _ contrast: UIAccessibilityContrast = .normal, _ level: UIUserInterfaceLevel = .base) -> UITraitCollection {
        UITraitCollection { traits in
            traits.userInterfaceStyle = style
            traits.accessibilityContrast = contrast
            traits.userInterfaceLevel = level
        }
    }

    private var allTraits: [(String, UITraitCollection)] {
        var result: [(String, UITraitCollection)] = []
        for style in [UIUserInterfaceStyle.light, .dark] {
            for contrast in [UIAccessibilityContrast.normal, .high] {
                for level in [UIUserInterfaceLevel.base, .elevated] {
                    let name = "\(style == .dark ? "dark" : "light")\(contrast == .high ? ", Increase Contrast" : ""), \(level == .elevated ? "elevated" : "base")"
                    result.append((name, traits(style, contrast, level)))
                }
            }
        }
        return result
    }

    func testSecondaryAndTertiaryTextMeetAAOnEveryBackground() {
        for (traitName, traits) in allTraits {
            for (bgName, background) in backgrounds {
                for (textName, text) in [("secondaryText", UIColor.secondaryText), ("tertiaryText", .tertiaryText)] {
                    let ratio = Self.contrast(text, on: background, traits: traits)
                    XCTAssertGreaterThanOrEqual(ratio, Self.aa, "\(textName) on \(bgName), \(traitName): \(String(format: "%.2f", ratio)):1")
                }
            }
        }
    }

    /// Primary, then secondary, then tertiary: each step has less contrast
    /// than the one above it, so the grays still read as a hierarchy.
    func testTheHierarchyIsKept() {
        for (traitName, traits) in allTraits {
            let background = UIColor.secondarySystemGroupedBackground
            let primary = Self.contrast(.label, on: background, traits: traits)
            let secondary = Self.contrast(.secondaryText, on: background, traits: traits)
            let tertiary = Self.contrast(.tertiaryText, on: background, traits: traits)
            XCTAssertGreaterThan(primary, secondary, traitName)
            XCTAssertGreaterThan(secondary, tertiary, traitName)
        }
    }

    func testIncreaseContrastIsAtLeastAsStrong() {
        for style in [UIUserInterfaceStyle.light, .dark] {
            for text in [UIColor.secondaryText, .tertiaryText] {
                let normal = Self.contrast(text, on: .systemGroupedBackground, traits: traits(style))
                let high = Self.contrast(text, on: .systemGroupedBackground, traits: traits(style, .high))
                XCTAssertGreaterThanOrEqual(high, normal)
            }
        }
    }

    /// Negative control: the same check fails iOS's own grays, which the
    /// app used before. Without this, a check that could never fail would
    /// pass too.
    func testTheCheckFailsTheSystemGraysTheAppUsedBefore() {
        let light = traits(.light)
        let white = Self.contrast(.secondaryLabel, on: .systemBackground, traits: light)
        let grouped = Self.contrast(.secondaryLabel, on: .systemGroupedBackground, traits: light)
        XCTAssertLessThan(white, Self.aa, "secondaryLabel on white: \(white)")
        XCTAssertLessThan(grouped, Self.aa, "secondaryLabel on the grouped background: \(grouped)")
        XCTAssertLessThan(Self.contrast(.tertiaryLabel, on: .systemBackground, traits: light), Self.aa)
    }

    // MARK: - WCAG 2 relative luminance and contrast

    /// Composites `text` (which may be translucent, like `secondaryLabel`)
    /// over `background`, then returns the contrast ratio.
    static func contrast(_ text: UIColor, on background: UIColor, traits: UITraitCollection) -> Double {
        let bg = rgba(background.resolvedColor(with: traits))
        let fg = rgba(text.resolvedColor(with: traits))
        let composite = (r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a))
        let l1 = luminance(composite), l2 = luminance((bg.r, bg.g, bg.b))
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
    }

    private static func rgba(_ color: UIColor) -> (r: Double, g: Double, b: Double, a: Double) {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        color.getRed(&r, green: &g, blue: &b, alpha: &a)
        return (Double(r), Double(g), Double(b), Double(a))
    }

    private static func luminance(_ c: (r: Double, g: Double, b: Double)) -> Double {
        func channel(_ v: Double) -> Double { v <= 0.03928 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4) }
        return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b)
    }
}
