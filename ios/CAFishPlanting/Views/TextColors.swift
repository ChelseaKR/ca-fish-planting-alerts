import SwiftUI
import UIKit

// Gray text that meets WCAG AA without Increase Contrast.
//
// iOS's own `secondaryLabel` is 60% of the label color, which measures about
// 3.4:1 on white and 3.3:1 on the grouped list background in light mode:
// below AA's 4.5:1 for body text. These two grays keep the same hierarchy
// (primary, then secondary, then tertiary, each a step lighter in light mode
// and a step darker in dark mode) and meet 4.5:1 on every background the app
// draws text on, in light and dark mode, base and elevated (sheets).
// Increase Contrast gets a stronger pair. `TextColorContrastTests` checks
// every combination against the backgrounds as UIKit resolves them.

extension UIColor {
    /// Second-level text: county names, species, captions, footnotes,
    /// section headers.
    static let secondaryText = UIColor { traits in
        switch (traits.userInterfaceStyle, traits.accessibilityContrast) {
        case (.dark, .high): return UIColor(rgb: 0xC7C7CC)
        case (.dark, _): return UIColor(rgb: 0xA1A1A6)
        case (_, .high): return UIColor(rgb: 0x48484A)
        default: return UIColor(rgb: 0x5C5C61)
        }
    }

    /// Third-level text, a step below `secondaryText`, still 4.5:1.
    static let tertiaryText = UIColor { traits in
        switch (traits.userInterfaceStyle, traits.accessibilityContrast) {
        case (.dark, .high): return UIColor(rgb: 0xAEAEB2)
        case (.dark, _): return UIColor(rgb: 0x98989D)
        case (_, .high): return UIColor(rgb: 0x5C5C61)
        default: return UIColor(rgb: 0x6C6C70)
        }
    }

    convenience init(rgb: UInt32) {
        self.init(red: CGFloat((rgb >> 16) & 0xFF) / 255,
                  green: CGFloat((rgb >> 8) & 0xFF) / 255,
                  blue: CGFloat(rgb & 0xFF) / 255,
                  alpha: 1)
    }
}

extension ShapeStyle where Self == Color {
    /// Use instead of `.secondary` for text. See `UIColor.secondaryText`.
    static var secondaryText: Color { Color(uiColor: .secondaryText) }

    /// Use instead of `.tertiary` for text. See `UIColor.tertiaryText`.
    static var tertiaryText: Color { Color(uiColor: .tertiaryText) }
}

/// A list section header in `secondaryText`. The system header gray is
/// below 4.5:1 on the grouped background in light mode.
struct SectionHeader: View {
    let title: LocalizedStringKey

    init(_ title: LocalizedStringKey) {
        self.title = title
    }

    var body: some View {
        Text(title).foregroundStyle(.secondaryText)
    }
}
