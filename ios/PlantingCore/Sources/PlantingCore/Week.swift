import Foundation

/// How precisely an agency dates a record. California only ever gives a
/// week. Tennessee gives a day, the week of a Sunday, or a month with the
/// day not set yet. Massachusetts and Michigan report the day.
public enum DatePrecision: String, Hashable, Sendable, Codable {
    case day, week, month
}

/// The unit of truth: a period exactly as precise as the agency made it.
/// For California, as in `$defs/week` of `schema/snapshot.v1.json`: CDFW
/// publishes "week of <date>" and nothing finer ("More specific dates are
/// not given to avoid focusing excess fishing activity immediately after a
/// plant"). `label` is the pipeline's own display string and is used
/// verbatim, never reformatted and never shortened to a day: "week of
/// YYYY-MM-DD" for a week, "YYYY-MM-DD" for a day, "December 2026" for a
/// month (`$defs/period` in `schema/snapshot.v2.json`).
///
/// The type keeps its old name because a week is still what most records
/// are, and every stored alert baseline and widget digest already holds one.
public struct Week: Hashable, Comparable, Sendable, Codable {
    /// A week's Sunday, a day, or a month's first day.
    public let start: PlainDate
    /// A week's Saturday, the same day, or a month's last day.
    public let end: PlainDate
    /// Render this string directly; do not derive your own.
    public let label: String
    public let precision: DatePrecision

    public init(start: PlainDate, end: PlainDate, label: String, precision: DatePrecision = .week) {
        self.start = start; self.end = end; self.label = label; self.precision = precision
    }

    public static func < (lhs: Week, rhs: Week) -> Bool { lhs.start < rhs.start }

    /// The words that follow "scheduled for" or "last stocked": "the week of
    /// 2026-10-11", "2026-10-14", or "December 2026".
    public var phrase: String {
        precision == .week ? "the \(label)" : label
    }

    /// True when the period overlaps `other` (a state's current week).
    public func overlaps(_ other: Week) -> Bool { start <= other.end && end >= other.start }

    enum CodingKeys: String, CodingKey { case start, end, label, precision }

    /// A week stored before precision existed (an alert baseline or widget
    /// digest from an older build) reads as a week, which is what it was.
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        start = try c.decode(PlainDate.self, forKey: .start)
        end = try c.decode(PlainDate.self, forKey: .end)
        label = try c.decode(String.self, forKey: .label)
        precision = try c.decodeIfPresent(DatePrecision.self, forKey: .precision) ?? .week
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(start, forKey: .start)
        try c.encode(end, forKey: .end)
        try c.encode(label, forKey: .label)
        try c.encode(precision, forKey: .precision)
    }
}

extension PlainDate {
    /// This date moved by `days` (negative for earlier).
    public func adding(days: Int) -> PlainDate {
        let moved = Self.gregorianUTC.date(byAdding: .day, value: days, to: noonUTC)!
        let c = Self.gregorianUTC.dateComponents([.year, .month, .day], from: moved)
        return PlainDate(year: c.year!, month: c.month!, day: c.day!)
    }
}
