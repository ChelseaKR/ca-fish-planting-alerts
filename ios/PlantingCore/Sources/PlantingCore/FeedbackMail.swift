import Foundation

/// About's "Write to the developer" row: a `mailto:` link with the app's
/// version in the subject, so a report says which build it came from. The
/// Android twin is `FeedbackMail.kt`, word for word (`docs/DECISIONS.md`
/// 0058, after 0057 on Android).
///
/// The address is the one `/support/` shows. Opening it hands off to Mail
/// (or the person's chosen email app); the app itself sends nothing, and
/// `mailto:` names no host, so `HostAllowlistTests` is unaffected.
public enum FeedbackMail {
    public static let address = "chelsea@chelseakr.com"
    public static let sectionHeader = "Questions and corrections"
    public static let rowTitle = "Write to the developer"
    public static let rowFootnote = "Opens your email app, addressed to \(address), with the app version in the subject. If a date looks wrong, say which water."

    /// "Trout Truck 1.2.0 for iOS", or "Trout Truck for iOS" when the build
    /// carries no version: a missing version is left out, never shown as one.
    public static func subject(version: String?, platform: String) -> String {
        let trimmed = version?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? "Trout Truck for \(platform)" : "Trout Truck \(trimmed) for \(platform)"
    }

    /// The row's link. `nil` only if the subject couldn't be encoded, which
    /// the row treats as "show the address, no link".
    public static func url(version: String?, platform: String) -> URL? {
        // RFC 3986 unreserved characters only: a space is %20, never "+".
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
        guard let encoded = subject(version: version, platform: platform).addingPercentEncoding(withAllowedCharacters: allowed) else { return nil }
        return URL(string: "mailto:\(address)?subject=\(encoded)")
    }

    /// The running app's marketing version, from its Info.plist.
    public static func appVersion(in bundle: Bundle = .main) -> String? {
        bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
    }
}
