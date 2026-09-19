import Foundation

// The snapshot contract as the app expects it, mirroring
// `schema/snapshot.v1.json` (schema_version 1) field-for-field. Owned by
// `schema/` (the pipeline lane) — this file must be reconciled against that
// schema whenever it changes. Unknown top-level or nested JSON keys are
// ignored by design (`schema/README.md`: "readers must ignore unknown
// fields"), so an additive schema change never breaks decoding.
//
// Absence is modeled, never defaulted: `location` is `nil` unless a
// licensed source supplied it; `last_listed_week` is `nil` when every
// observed plant is in the future. Never rendered as zero or "none planted".
//
// Granularity: every planting is a `Week` (Sunday..Saturday). There is no
// day anywhere in this model.

public struct Snapshot: Equatable, Sendable {
    public static let supportedSchemaVersion = 1

    public let schemaVersion: Int
    /// When the pipeline built this file (UTC).
    public let generatedAt: Date
    public let source: SourceInfo
    /// The CDFW week containing `source.statedToday`. "This week" everywhere
    /// in the app means this, not the device's clock.
    public let sourceWeek: Week
    public let attribution: Attribution
    public let license: License
    public let regions: [Region]
    public let counties: [County]
    /// Every species string ever observed, verbatim from CDFW.
    public let species: [String]
    public let waters: [Water]
    /// Convenience index of listed plants for `sourceWeek`, pipeline-tested
    /// to agree with `waters[].plants`. Can legitimately be empty.
    public let thisWeek: [ThisWeekEntry]
    public let coverage: Coverage

    public init(schemaVersion: Int, generatedAt: Date, source: SourceInfo, sourceWeek: Week, attribution: Attribution, license: License, regions: [Region], counties: [County], species: [String], waters: [Water], thisWeek: [ThisWeekEntry], coverage: Coverage) {
        self.schemaVersion = schemaVersion
        self.generatedAt = generatedAt
        self.source = source
        self.sourceWeek = sourceWeek
        self.attribution = attribution
        self.license = license
        self.regions = regions
        self.counties = counties
        self.species = species
        self.waters = waters
        self.thisWeek = thisWeek
        self.coverage = coverage
    }

    public func water(id: Water.ID) -> Water? { waters.first { $0.id == id } }

    public func waters(inRegion code: String) -> [Water] { waters.filter { $0.region == code } }

    public func region(code: String) -> Region? { regions.first { $0.code == code } }

    /// Regions that have at least one water, in `regions` order.
    public var regionsWithWaters: [Region] {
        let present = Set(waters.map(\.region))
        return regions.filter { present.contains($0.code) }
    }
}

public struct SourceInfo: Equatable, Sendable {
    public let name: String
    public let url: URL
    public let fetchedAt: Date
    /// The date the CDFW page itself said was "today". Freshness is judged
    /// from this, not from HTTP headers or the device clock.
    public let statedToday: PlainDate
    public let statedPeriodStart: PlainDate
    public let statedPeriodEnd: PlainDate
    public let contentSHA256: String
    public init(name: String, url: URL, fetchedAt: Date, statedToday: PlainDate, statedPeriodStart: PlainDate, statedPeriodEnd: PlainDate, contentSHA256: String) {
        self.name = name; self.url = url; self.fetchedAt = fetchedAt
        self.statedToday = statedToday
        self.statedPeriodStart = statedPeriodStart; self.statedPeriodEnd = statedPeriodEnd
        self.contentSHA256 = contentSHA256
    }
}

/// Shown verbatim wherever data from the snapshot is displayed — the About
/// screen and, per DECISIONS, nowhere it could be missed.
public struct Attribution: Equatable, Sendable {
    public let text: String
    public let url: URL
    public init(text: String, url: URL) { self.text = text; self.url = url }
}

public enum CommercialReuse: String, Sendable, Equatable { case permitted, notPermitted = "not-permitted", unknown }

public struct LicenseSource: Equatable, Sendable, Identifiable {
    public var id: String { name + url.absoluteString }
    public let name: String
    public let url: URL
    public let termsURL: URL
    public let termsReadOn: PlainDate
    public let commercialReuse: CommercialReuse
    public let attributionRequired: Bool
    public init(name: String, url: URL, termsURL: URL, termsReadOn: PlainDate, commercialReuse: CommercialReuse, attributionRequired: Bool) {
        self.name = name; self.url = url; self.termsURL = termsURL; self.termsReadOn = termsReadOn
        self.commercialReuse = commercialReuse; self.attributionRequired = attributionRequired
    }
}

public struct License: Equatable, Sendable {
    public let summary: String
    public let sources: [LicenseSource]
    public init(summary: String, sources: [LicenseSource]) { self.summary = summary; self.sources = sources }
}

public struct Region: Equatable, Sendable, Identifiable {
    public var id: String { code }
    public let code: String
    public let name: String
    public init(code: String, name: String) { self.code = code; self.name = name }
}

public struct County: Equatable, Sendable, Identifiable {
    public var id: String { name }
    public let name: String
    public let region: String
    public init(name: String, region: String) { self.name = name; self.region = region }
}

public struct GeoLocation: Equatable, Sendable {
    public let lat: Double
    public let lon: Double
    /// The licensed dataset the point came from. Never a guess.
    public let source: String
    public init(lat: Double, lon: Double, source: String) { self.lat = lat; self.lon = lon; self.source = source }
}

public enum PlantStatus: String, Sendable, Equatable, Codable { case listed, removed }

public struct Plant: Hashable, Sendable {
    public let week: Week
    public let species: String
    public let status: PlantStatus
    public let firstObservedAt: Date
    public let lastObservedAt: Date

    public init(week: Week, species: String, status: PlantStatus, firstObservedAt: Date, lastObservedAt: Date) {
        self.week = week; self.species = species; self.status = status
        self.firstObservedAt = firstObservedAt; self.lastObservedAt = lastObservedAt
    }

    // Equality/hashing over the identity CDFW gives a plant, so re-fetches
    // that only refresh observation timestamps compare equal.
    public static func == (lhs: Plant, rhs: Plant) -> Bool {
        lhs.week == rhs.week && lhs.species == rhs.species && lhs.status == rhs.status
    }
    public func hash(into hasher: inout Hasher) {
        hasher.combine(week); hasher.combine(species); hasher.combine(status)
    }
}

public struct ThisWeekEntry: Equatable, Sendable {
    public let waterID: Water.ID
    public let species: String
    public init(waterID: Water.ID, species: String) { self.waterID = waterID; self.species = species }
}

public struct Water: Equatable, Sendable, Identifiable {
    public typealias ID = String

    /// `cdfw-<StockingWaterID>` — CDFW's own key. Stable; names are not keys.
    public let id: ID
    public let cdfwStockID: Int
    public let name: String
    public let nameReviewed: Bool
    /// Site path segment: `/water/<slug>/`.
    public let slug: String
    public let aliases: [String]
    public let counties: [String]
    /// Region of the first listed county.
    public let region: String
    public let cdfwMapURL: URL
    public let location: GeoLocation?
    /// Newest week with status "listed" that is not in the future. `nil` if
    /// every observed plant is in the future.
    public let lastListedWeek: Week?
    /// Every (week, species) ever observed, oldest first.
    public let plants: [Plant]

    public init(id: ID, cdfwStockID: Int, name: String, nameReviewed: Bool, slug: String, aliases: [String], counties: [String], region: String, cdfwMapURL: URL, location: GeoLocation?, lastListedWeek: Week?, plants: [Plant]) {
        self.id = id; self.cdfwStockID = cdfwStockID; self.name = name; self.nameReviewed = nameReviewed
        self.slug = slug; self.aliases = aliases; self.counties = counties; self.region = region
        self.cdfwMapURL = cdfwMapURL; self.location = location; self.lastListedWeek = lastListedWeek
        self.plants = plants.sorted { $0.week < $1.week }
    }

    /// Listed plants at or after `week`, oldest first — the set the alert
    /// planner diffs against a stored baseline.
    public func listedPlants(onOrAfter week: Week) -> [Plant] {
        plants.filter { $0.status == .listed && $0.week >= week }
    }

    public func plants(inYear year: Int) -> [Plant] { plants.filter { $0.week.start.year == year } }

    /// Distinct species across the kept history, most recently observed first.
    public var speciesSeen: [String] {
        var seen: [String] = []
        for plant in plants.reversed() where !seen.contains(plant.species) { seen.append(plant.species) }
        return seen
    }

    /// Distinct species actually listed in `lastListedWeek`, in the order
    /// first observed. Empty when `lastListedWeek` is `nil` (nothing has
    /// ever been listed for a non-future week) — never a guess, and never
    /// falls back to `speciesSeen`, which can include species from other
    /// weeks or from `removed` plants that never happened.
    public var lastListedSpecies: [String] {
        guard let lastListedWeek else { return [] }
        var seen: [String] = []
        for plant in plants where plant.week == lastListedWeek && plant.status == .listed {
            if !seen.contains(plant.species) { seen.append(plant.species) }
        }
        return seen
    }

    public var years: [Int] { Array(Set(plants.map { $0.week.start.year })).sorted(by: >) }

    public var countyLabel: String {
        counties.isEmpty ? "County not stated" : counties.joined(separator: ", ")
    }
}

public struct Coverage: Equatable, Sendable {
    public let watersThisWeek: Int
    public let watersKnown: Int
    public let watersWithHistory: Int
    public let namesMatched: Int
    public let namesSeen: Int
    public let rowsParsed: Int
    public let weeksOfHistoryMin: Int
    public let weeksOfHistoryMedian: Double
    public init(watersThisWeek: Int, watersKnown: Int, watersWithHistory: Int, namesMatched: Int, namesSeen: Int, rowsParsed: Int, weeksOfHistoryMin: Int, weeksOfHistoryMedian: Double) {
        self.watersThisWeek = watersThisWeek; self.watersKnown = watersKnown; self.watersWithHistory = watersWithHistory
        self.namesMatched = namesMatched; self.namesSeen = namesSeen; self.rowsParsed = rowsParsed
        self.weeksOfHistoryMin = weeksOfHistoryMin; self.weeksOfHistoryMedian = weeksOfHistoryMedian
    }
}
