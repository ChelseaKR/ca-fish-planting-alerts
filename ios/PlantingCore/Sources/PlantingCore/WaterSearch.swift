import Foundation

/// Search and county filter over waters, for Browse and Favorites.
///
/// Typing matches a water's name, any name CDFW has used for it (`aliases`,
/// since water names drift from week to week), and its counties. Case and
/// accents don't matter, and every word typed must match somewhere, so
/// "silver fork el dorado" finds American River Silver Fork. Pure, so it is
/// tested without the app.
public struct WaterSearch: Equatable, Sendable {
    public var text: String
    /// Only waters in this county. `nil` is every county.
    public var county: String?

    public init(text: String = "", county: String? = nil) {
        self.text = text
        self.county = county
    }

    /// Nothing typed and no county chosen.
    public var isEmpty: Bool { terms.isEmpty && county == nil }

    public func matches(_ water: Water) -> Bool {
        if let county, !water.counties.contains(county) { return false }
        let terms = self.terms
        guard !terms.isEmpty else { return true }
        let haystack = Self.fold(([water.name] + water.aliases + water.counties).joined(separator: " "))
        return terms.allSatisfy { haystack.contains($0) }
    }

    /// The matching waters, sorted by name.
    public func filter(_ waters: [Water]) -> [Water] {
        waters.filter(matches).sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    /// The counties these waters are in, sorted, each once. What a county
    /// filter offers, so it never offers a county with nothing in it.
    public static func counties(of waters: [Water]) -> [String] {
        Array(Set(waters.flatMap(\.counties))).sorted { $0.localizedStandardCompare($1) == .orderedAscending }
    }

    private var terms: [String] {
        Self.fold(text).split(whereSeparator: { $0.isWhitespace || $0 == "," }).map(String.init)
    }

    private static func fold(_ string: String) -> String {
        string.folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: Locale(identifier: "en_US_POSIX"))
    }
}
