import Foundation

/// The unit of truth, matching `$defs/week` in `schema/snapshot.v1.json`
/// exactly: CDFW publishes "week of <date>" and nothing finer ("More
/// specific dates are not given to avoid focusing excess fishing activity
/// immediately after a plant"). `label` is the pipeline's own display string
/// ("week of YYYY-MM-DD") and is used verbatim — never reformatted, never
/// shortened to a single day, per `schema/README.md`: "Never shorten to a
/// single day."
public struct Week: Hashable, Comparable, Sendable, Codable {
    /// Always a Sunday.
    public let start: PlainDate
    /// Always `start + 6 days`, a Saturday.
    public let end: PlainDate
    /// "week of YYYY-MM-DD". Render this string directly; do not derive your own.
    public let label: String

    public init(start: PlainDate, end: PlainDate, label: String) {
        self.start = start; self.end = end; self.label = label
    }

    public static func < (lhs: Week, rhs: Week) -> Bool { lhs.start < rhs.start }
}
