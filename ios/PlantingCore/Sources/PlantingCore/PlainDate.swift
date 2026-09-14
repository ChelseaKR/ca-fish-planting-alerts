import Foundation

/// A calendar date with no time component, America/Los_Angeles civil date
/// per `schema/README.md`. Wire format is strict `YYYY-MM-DD`
/// (`$defs/date` in `schema/snapshot.v1.json`); this type refuses anything else.
public struct PlainDate: Hashable, Comparable, Sendable, Codable, CustomStringConvertible {
    public let year: Int
    public let month: Int
    public let day: Int

    public init?(isoDate: String) {
        let parts = isoDate.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3,
              parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
              let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]),
              (1...12).contains(m), (1...31).contains(d)
        else { return nil }
        var comps = DateComponents()
        comps.calendar = Self.gregorianUTC
        comps.year = y; comps.month = m; comps.day = d
        guard comps.isValidDate else { return nil }
        self.year = y; self.month = m; self.day = d
    }

    public init(year: Int, month: Int, day: Int) {
        self.year = year; self.month = month; self.day = day
    }

    public var isoDate: String { String(format: "%04d-%02d-%02d", year, month, day) }
    public var description: String { isoDate }

    /// Noon UTC on this date — for formatting only, chosen so no timezone
    /// conversion can push the date to the adjacent day.
    public var noonUTC: Date {
        var comps = DateComponents()
        comps.year = year; comps.month = month; comps.day = day; comps.hour = 12
        return Self.gregorianUTC.date(from: comps)!
    }

    public static func < (lhs: PlainDate, rhs: PlainDate) -> Bool {
        (lhs.year, lhs.month, lhs.day) < (rhs.year, rhs.month, rhs.day)
    }

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        guard let value = PlainDate(isoDate: raw) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "not a YYYY-MM-DD date: \(raw)"))
        }
        self = value
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(isoDate)
    }

    /// "Sep 14, 2026" in the given locale.
    public func formatted(locale: Locale = .current) -> String {
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.setLocalizedDateFormatFromTemplate("MMMdyyyy")
        return formatter.string(from: noonUTC)
    }

    static let gregorianUTC: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()
}
