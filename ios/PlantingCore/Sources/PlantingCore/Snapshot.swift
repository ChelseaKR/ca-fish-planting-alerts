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
    /// The newest version this app reads. It reads v1 too: a v1 file is
    /// California alone (`SnapshotDecoder`).
    public static let supportedSchemaVersion = 2
    public static let supportedSchemaVersions: Set<Int> = [1, 2]

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
    /// to agree with `waters[].plants`. Can legitimately be empty. In v2 it
    /// also holds the other states' day and week records in their own
    /// current weeks.
    public let thisWeek: [ThisWeekEntry]
    /// v1's coverage numbers. v2 has none, and none is made up.
    public let coverage: Coverage?
    /// Every state the snapshot carries, California first. `sourceWeek`,
    /// `source`, `attribution`, `license`, `regions` and `counties` above are
    /// California's, as they always were.
    public let states: [StateInfo]

    public init(schemaVersion: Int, generatedAt: Date, source: SourceInfo, sourceWeek: Week, attribution: Attribution, license: License, regions: [Region], counties: [County], species: [String], waters: [Water], thisWeek: [ThisWeekEntry], coverage: Coverage?, states: [StateInfo]? = nil) {
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
        self.states = states ?? [StateInfo.california(source: source, sourceWeek: sourceWeek, attribution: attribution, license: license, regions: regions, counties: counties, watersCount: waters.count)]
    }

    public func water(id: Water.ID) -> Water? { waters.first { $0.id == id } }

    public func waters(inRegion code: String) -> [Water] { waters.filter { $0.region == code } }

    public func region(code: String) -> Region? { regions.first { $0.code == code } }

    /// Regions that have at least one water, in `regions` order.
    public var regionsWithWaters: [Region] {
        let present = Set(waters.map(\.region))
        return regions.filter { present.contains($0.code) }
    }

    // MARK: States

    public func state(code: String) -> StateInfo? { states.first { $0.code == code } }

    public func state(of water: Water) -> StateInfo? { state(code: water.state) }

    public func waters(inState code: String) -> [Water] { waters.filter { $0.state == code } }

    /// The regions of one state that have a water, in the state's order.
    public func regionsWithWaters(inState code: String) -> [Region] {
        guard let state = state(code: code) else { return [] }
        let present = Set(waters(inState: code).map(\.region))
        return state.regions.filter { present.contains($0.code) }
    }

    /// What "this week" means for this water: its state's current week.
    public func currentWeek(for water: Water) -> Week {
        state(of: water)?.currentWeek ?? sourceWeek
    }

    /// The records the alert planner diffs for a favorite (`AlertPlanner`).
    /// A schedule: listed periods that have not ended before the state's
    /// current week. A report: reported stockings from `reportLookbackDays`
    /// before the current week on, because a report's records arrive after
    /// the fact (Michigan's by weeks).
    public func alertBasis(for water: Water) -> [Plant] {
        let week = currentWeek(for: water)
        switch water.semantics {
        case .schedule, .plan:
            return water.listedPlants(onOrAfter: week)
        case .report:
            let since = week.start.adding(days: -Self.reportLookbackDays)
            return water.plants.filter { $0.status == .reported && $0.week.start >= since }
        }
    }

    public static let reportLookbackDays = 120
}

/// What a state's records mean (`$defs/state/semantics`, schema v2).
public enum StateSemantics: String, Sendable, Equatable, Codable {
    /// The agency says when fish will be stocked, and plans can change.
    /// Say "scheduled".
    case schedule
    /// The agency reports stockings already done. Say "stocked".
    case report
    /// A once-a-year plan in the agency's own words (New York). Say
    /// "planned for"; nothing is ever inferred as removed from it.
    case plan
}

/// One state's source, terms and freshness (`$defs/state`, schema v2).
public struct StateInfo: Equatable, Sendable, Identifiable {
    public var id: String { code }
    public let code: String
    public let name: String
    public let agencyName: String
    public let agencyShortName: String
    public let agencyURL: URL
    public let semantics: StateSemantics
    public let datePrecisions: [DatePrecision]
    public let removalInference: Bool
    /// What "this week" means for this state.
    public let currentWeek: Week
    /// The civil date of the last good fetch, in the state's time zone.
    public let asOf: PlainDate
    public let newestRecord: Week?
    /// Shown next to the data when the source lags (Michigan).
    public let recencyNote: String?
    public let sourceName: String
    public let sourceURL: URL
    public let fetchedAt: Date
    public let lastModified: String?
    public let lastAttemptAt: Date
    public let lastSuccessAt: Date
    public let lastAttemptOK: Bool
    public let attribution: Attribution
    public let disclaimer: String
    public let license: License
    public let regions: [Region]
    public let counties: [County]
    public let watersCount: Int

    public init(code: String, name: String, agencyName: String, agencyShortName: String, agencyURL: URL, semantics: StateSemantics, datePrecisions: [DatePrecision], removalInference: Bool, currentWeek: Week, asOf: PlainDate, newestRecord: Week?, recencyNote: String?, sourceName: String, sourceURL: URL, fetchedAt: Date, lastModified: String?, lastAttemptAt: Date, lastSuccessAt: Date, lastAttemptOK: Bool, attribution: Attribution, disclaimer: String, license: License, regions: [Region], counties: [County], watersCount: Int) {
        self.code = code; self.name = name; self.agencyName = agencyName; self.agencyShortName = agencyShortName
        self.agencyURL = agencyURL; self.semantics = semantics; self.datePrecisions = datePrecisions
        self.removalInference = removalInference; self.currentWeek = currentWeek; self.asOf = asOf
        self.newestRecord = newestRecord; self.recencyNote = recencyNote; self.sourceName = sourceName
        self.sourceURL = sourceURL; self.fetchedAt = fetchedAt; self.lastModified = lastModified
        self.lastAttemptAt = lastAttemptAt; self.lastSuccessAt = lastSuccessAt; self.lastAttemptOK = lastAttemptOK
        self.attribution = attribution; self.disclaimer = disclaimer; self.license = license
        self.regions = regions; self.counties = counties; self.watersCount = watersCount
    }

    public static let californiaDisclaimer = "Trout Truck is independent and is not affiliated with or endorsed by CDFW. CDFW: \"all fish plants are subject to change depending on road, water, weather and operational conditions.\""

    /// California as a v1 file describes it.
    public static func california(source: SourceInfo, sourceWeek: Week, attribution: Attribution, license: License, regions: [Region], counties: [County], watersCount: Int) -> StateInfo {
        StateInfo(code: "CA", name: "California",
                  agencyName: "California Department of Fish and Wildlife", agencyShortName: "CDFW",
                  // From the file, never a second host in the app's source
                  // (`HostAllowlistTests`).
                  agencyURL: source.url,
                  semantics: .schedule, datePrecisions: [.week], removalInference: true,
                  currentWeek: sourceWeek, asOf: source.statedToday, newestRecord: nil, recencyNote: nil,
                  sourceName: source.name, sourceURL: source.url, fetchedAt: source.fetchedAt, lastModified: nil,
                  lastAttemptAt: source.fetchedAt, lastSuccessAt: source.fetchedAt, lastAttemptOK: true,
                  attribution: attribution, disclaimer: californiaDisclaimer, license: license,
                  regions: regions, counties: counties, watersCount: watersCount)
    }

    /// "Schedule" or "Stocking report", for a list of states.
    public var kindLabel: String {
        switch semantics {
        case .schedule: return "Stocking schedule"
        case .report: return "Stocking report"
        case .plan: return "Spring stocking plan"
        }
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
    /// The license clause, verbatim (v2). nil from a v1 file.
    public let termsQuote: String?
    public init(name: String, url: URL, termsURL: URL, termsReadOn: PlainDate, commercialReuse: CommercialReuse, attributionRequired: Bool, termsQuote: String? = nil) {
        self.name = name; self.url = url; self.termsURL = termsURL; self.termsReadOn = termsReadOn
        self.commercialReuse = commercialReuse; self.attributionRequired = attributionRequired
        self.termsQuote = termsQuote
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

/// `listed` and `removed` belong to a schedule; `reported` to a report
/// (a stocking the agency says it did).
public enum PlantStatus: String, Sendable, Equatable, Codable { case listed, removed, reported }

public struct Plant: Hashable, Sendable {
    /// The period, at the agency's precision (`week.precision`).
    public let week: Week
    public let species: String
    public let status: PlantStatus
    public let firstObservedAt: Date
    public let lastObservedAt: Date
    /// How many fish, when the agency says (Michigan). Never guessed.
    public let count: Int?

    public init(week: Week, species: String, status: PlantStatus, firstObservedAt: Date, lastObservedAt: Date, count: Int? = nil) {
        self.week = week; self.species = species; self.status = status
        self.firstObservedAt = firstObservedAt; self.lastObservedAt = lastObservedAt
        self.count = count
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

    /// `cdfw-<StockingWaterID>` — CDFW's own key — for California, so a
    /// favorite made from a v1 file is the same water in v2. `tn-…`, `ma-…`,
    /// `mi-…` elsewhere. Stable; names are not keys.
    public let id: ID
    /// CDFW's stock ID for California; 0 for a water in another state.
    public let cdfwStockID: Int
    public let name: String
    public let nameReviewed: Bool
    /// Site path segment: `/water/<slug>/`.
    public let slug: String
    public let aliases: [String]
    public let counties: [String]
    /// Region of the first listed county.
    /// The region code, or "" for a state that has none.
    public let region: String
    /// The agency's page for this water (CDFW's map link in California).
    public let cdfwMapURL: URL
    public let location: GeoLocation?
    /// Newest week with status "listed" that is not in the future. `nil` if
    /// every observed plant is in the future.
    public let lastListedWeek: Week?
    /// Every (week, species) ever observed, oldest first.
    public let plants: [Plant]
    /// The state's postal code ("CA" for every v1 water).
    public let state: String
    /// What this water's records mean, from its state.
    public let semantics: StateSemantics
    /// The agency's short name ("CDFW", "TWRA"), for the words on screen.
    public let agencyShortName: String
    /// Massachusetts reports a town, not a county.
    public let towns: [String]
    /// The water's page, from the site root (`site_path`, v2). nil from v1,
    /// where it is always `/water/<slug>/`.
    public let sitePath: String?
    /// Tennessee's month letters, verbatim (`months_note`). Never dates.
    public let monthsNote: String?

    public init(id: ID, cdfwStockID: Int, name: String, nameReviewed: Bool, slug: String, aliases: [String], counties: [String], region: String, cdfwMapURL: URL, location: GeoLocation?, lastListedWeek: Week?, plants: [Plant], state: String = "CA", semantics: StateSemantics = .schedule, agencyShortName: String = "CDFW", towns: [String] = [], sitePath: String? = nil, monthsNote: String? = nil) {
        self.id = id; self.cdfwStockID = cdfwStockID; self.name = name; self.nameReviewed = nameReviewed
        self.slug = slug; self.aliases = aliases; self.counties = counties; self.region = region
        self.cdfwMapURL = cdfwMapURL; self.location = location; self.lastListedWeek = lastListedWeek
        self.plants = plants.sorted { $0.week < $1.week }
        self.state = state; self.semantics = semantics; self.agencyShortName = agencyShortName
        self.towns = towns; self.sitePath = sitePath; self.monthsNote = monthsNote
    }

    /// Listed plants whose period has not ended before `week` starts, oldest
    /// first — the set the alert planner diffs for a schedule. For
    /// California's aligned weeks this is "at or after `week`", as it was.
    public func listedPlants(onOrAfter week: Week) -> [Plant] {
        plants.filter { $0.status == .listed && $0.week.end >= week.start }
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
        for plant in plants where plant.week == lastListedWeek && plant.status != .removed {
            if !seen.contains(plant.species) { seen.append(plant.species) }
        }
        return seen
    }

    public var years: [Int] { Array(Set(plants.map { $0.week.start.year })).sorted(by: >) }

    public var countyLabel: String {
        if !counties.isEmpty { return counties.joined(separator: ", ") }
        if !towns.isEmpty { return towns.joined(separator: ", ") }
        return "County not stated"
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
