import Foundation

public enum SnapshotDecodingError: Error, Equatable, LocalizedError {
    case unsupportedSchemaVersion(Int)
    case malformed(String)

    public var errorDescription: String? {
        switch self {
        case .unsupportedSchemaVersion(let v):
            return "Snapshot schema version \(v) is not supported (this app reads version \(Snapshot.supportedSchemaVersion))."
        case .malformed(let what):
            return "Snapshot is malformed: \(what)."
        }
    }
}

/// Strict decoder for `schema/snapshot.v1.json`. A contract violation throws
/// and the caller keeps the last good snapshot (see `SnapshotStore`). Unknown
/// JSON keys are ignored, matching `schema/README.md`'s reader contract.
public struct SnapshotDecoder: Sendable {
    public init() {}

    public func decode(_ data: Data) throws -> Snapshot {
        let dto: SnapshotDTO
        do {
            dto = try JSONDecoder().decode(SnapshotDTO.self, from: data)
        } catch let error as DecodingError {
            throw SnapshotDecodingError.malformed(Self.describe(error))
        }
        guard dto.schemaVersion == Snapshot.supportedSchemaVersion else {
            throw SnapshotDecodingError.unsupportedSchemaVersion(dto.schemaVersion)
        }

        let generatedAt = try Self.datetime(dto.generatedAt, field: "generated_at")
        let source = try Self.source(dto.source)
        let sourceWeek = try Self.week(dto.sourceWeek, field: "source_week")
        let attribution = try Self.attribution(dto.attribution)
        let license = try Self.license(dto.license)
        let regions = try dto.regions.map(Self.region)
        let counties = try dto.counties.map(Self.county)
        let species = Self.clean(dto.species)

        var seenIDs = Set<Water.ID>()
        var waters: [Water] = []
        waters.reserveCapacity(dto.waters.count)
        for w in dto.waters {
            let water = try Self.water(w)
            guard seenIDs.insert(water.id).inserted else {
                throw SnapshotDecodingError.malformed("duplicate water id \(water.id)")
            }
            waters.append(water)
        }

        let thisWeek = try dto.thisWeek.map { entry -> ThisWeekEntry in
            let id = entry.waterID.trimmingCharacters(in: .whitespaces)
            guard !id.isEmpty else { throw SnapshotDecodingError.malformed("this_week entry has an empty water_id") }
            let sp = entry.species.trimmingCharacters(in: .whitespaces)
            guard !sp.isEmpty else { throw SnapshotDecodingError.malformed("this_week entry \(id) has an empty species") }
            return ThisWeekEntry(waterID: id, species: sp)
        }

        let coverage = Coverage(
            watersThisWeek: dto.coverage.watersThisWeek, watersKnown: dto.coverage.watersKnown,
            watersWithHistory: dto.coverage.watersWithHistory, namesMatched: dto.coverage.namesMatched,
            namesSeen: dto.coverage.namesSeen, rowsParsed: dto.coverage.rowsParsed,
            weeksOfHistoryMin: dto.coverage.weeksOfHistoryMin, weeksOfHistoryMedian: dto.coverage.weeksOfHistoryMedian
        )

        return Snapshot(schemaVersion: dto.schemaVersion, generatedAt: generatedAt, source: source,
                        sourceWeek: sourceWeek, attribution: attribution, license: license,
                        regions: regions, counties: counties, species: species, waters: waters,
                        thisWeek: thisWeek, coverage: coverage)
    }

    // MARK: field builders

    static func source(_ dto: SourceDTO) throws -> SourceInfo {
        SourceInfo(
            name: dto.name,
            url: try url(dto.url, field: "source.url"),
            fetchedAt: try datetime(dto.fetchedAt, field: "source.fetched_at"),
            statedToday: try date(dto.statedToday, field: "source.stated_today"),
            statedPeriodStart: try date(dto.statedPeriod.start, field: "source.stated_period.start"),
            statedPeriodEnd: try date(dto.statedPeriod.end, field: "source.stated_period.end"),
            contentSHA256: dto.contentSHA256
        )
    }

    static func attribution(_ dto: AttributionDTO) throws -> Attribution {
        Attribution(text: dto.text, url: try url(dto.url, field: "attribution.url"))
    }

    static func license(_ dto: LicenseDTO) throws -> License {
        let sources = try dto.sources.map { s -> LicenseSource in
            guard let reuse = CommercialReuse(rawValue: s.commercialReuse) else {
                throw SnapshotDecodingError.malformed("license source \(s.name) has an unrecognized commercial_reuse: \(s.commercialReuse)")
            }
            return LicenseSource(name: s.name, url: try url(s.url, field: "licence.sources[\(s.name)].url"),
                                  termsURL: try url(s.termsURL, field: "licence.sources[\(s.name)].terms_url"),
                                  termsReadOn: try date(s.termsReadOn, field: "licence.sources[\(s.name)].terms_read_on"),
                                  commercialReuse: reuse, attributionRequired: s.attributionRequired)
        }
        return License(summary: dto.summary, sources: sources)
    }

    static func region(_ dto: RegionDTO) throws -> Region {
        guard Self.regionCodes.contains(dto.code) else {
            throw SnapshotDecodingError.malformed("region has an unrecognized code: \(dto.code)")
        }
        return Region(code: dto.code, name: dto.name)
    }

    static func county(_ dto: CountyDTO) throws -> County {
        guard Self.regionCodes.contains(dto.region) else {
            throw SnapshotDecodingError.malformed("county \(dto.name) has an unrecognized region: \(dto.region)")
        }
        return County(name: dto.name, region: dto.region)
    }

    static func water(_ w: WaterDTO) throws -> Water {
        let id = w.id.trimmingCharacters(in: .whitespaces)
        guard id.hasPrefix("cdfw-"), Int(id.dropFirst("cdfw-".count)) != nil else {
            throw SnapshotDecodingError.malformed("water id is not cdfw-<digits>: \(id)")
        }
        let name = w.name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { throw SnapshotDecodingError.malformed("water \(id) has an empty name") }
        let location = w.location.map { l -> GeoLocation in
            GeoLocation(lat: l.lat, lon: l.lon, source: l.source)
        }
        let lastListedWeek = try w.lastListedWeek.map { try week($0, field: "waters[\(id)].last_listed_week") }
        let plants = try w.plants.map { p -> Plant in
            guard let status = PlantStatus(rawValue: p.status) else {
                throw SnapshotDecodingError.malformed("waters[\(id)].plants has an unrecognized status: \(p.status)")
            }
            let sp = p.species.trimmingCharacters(in: .whitespaces)
            guard !sp.isEmpty else { throw SnapshotDecodingError.malformed("waters[\(id)] has a plant with an empty species") }
            return Plant(week: try week(p.week, field: "waters[\(id)].plants[].week"), species: sp, status: status,
                         firstObservedAt: try datetime(p.firstObservedAt, field: "waters[\(id)].plants[].first_observed_at"),
                         lastObservedAt: try datetime(p.lastObservedAt, field: "waters[\(id)].plants[].last_observed_at"))
        }
        guard !plants.isEmpty else { throw SnapshotDecodingError.malformed("water \(id) has no plants") }
        return Water(id: id, cdfwStockID: w.cdfwStockID, name: name, nameReviewed: w.nameStatus == "reviewed",
                     slug: w.slug, aliases: clean(w.aliases), counties: clean(w.counties), region: w.region,
                     cdfwMapURL: try url(w.cdfwMapURL, field: "waters[\(id)].cdfw_map_url"),
                     location: location, lastListedWeek: lastListedWeek, plants: plants)
    }

    static let regionCodes: Set<String> = ["R1", "R2", "R3", "R4", "R5", "R6"]

    // MARK: primitives

    static func clean(_ list: [String]?) -> [String] {
        (list ?? []).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
    }

    static func url(_ s: String, field: String) throws -> URL {
        guard let u = URL(string: s), let scheme = u.scheme?.lowercased(), scheme == "https", u.host != nil else {
            throw SnapshotDecodingError.malformed("\(field) is not an https URL: \(s)")
        }
        return u
    }

    static func date(_ s: String, field: String) throws -> PlainDate {
        guard let d = PlainDate(isoDate: s) else {
            throw SnapshotDecodingError.malformed("\(field) is not a YYYY-MM-DD date: \(s)")
        }
        return d
    }

    static func week(_ dto: WeekDTO, field: String) throws -> Week {
        let start = try date(dto.start, field: "\(field).start")
        let end = try date(dto.end, field: "\(field).end")
        guard start <= end else { throw SnapshotDecodingError.malformed("\(field) has end before start") }
        return Week(start: start, end: end, label: dto.label)
    }

    /// `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` per `$defs/datetime`, with a
    /// tolerant fallback for fractional seconds so a future additive change
    /// (an ISO 8601 detail, not a contract break) does not hard-fail reads.
    static func datetime(_ s: String, field: String) throws -> Date {
        if let d = strictUTCFormatter.date(from: s) { return d }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: s) { return d }
        throw SnapshotDecodingError.malformed("\(field) is not an RFC 3339 UTC timestamp: \(s)")
    }

    static let strictUTCFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'Z'"
        return f
    }()

    static func describe(_ error: DecodingError) -> String {
        func path(_ ctx: DecodingError.Context) -> String { ctx.codingPath.map(\.stringValue).joined(separator: ".") }
        switch error {
        case .keyNotFound(let key, let ctx): return "missing \(path(ctx)).\(key.stringValue)"
        case .typeMismatch(_, let ctx): return "wrong type at \(path(ctx)): \(ctx.debugDescription)"
        case .valueNotFound(_, let ctx): return "null at \(path(ctx))"
        case .dataCorrupted(let ctx): return ctx.debugDescription
        @unknown default: return String(describing: error)
        }
    }
}

// MARK: - Wire DTOs (private to decoding; the public model is `Snapshot`)

struct SnapshotDTO: Decodable {
    let schemaVersion: Int
    let generatedAt: String
    let source: SourceDTO
    let sourceWeek: WeekDTO
    let attribution: AttributionDTO
    let license: LicenseDTO
    let regions: [RegionDTO]
    let counties: [CountyDTO]
    let species: [String]
    let waters: [WaterDTO]
    let thisWeek: [ThisWeekDTO]
    let coverage: CoverageDTO

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version", generatedAt = "generated_at", source
        case sourceWeek = "source_week", attribution, regions, counties, species, waters
        // Published snapshot field name: spelling kept so every v1 file still decodes.
        case license = "licence"
        case thisWeek = "this_week", coverage
    }
}

struct SourceDTO: Decodable {
    let name: String
    let url: String
    let fetchedAt: String
    let statedToday: String
    let statedPeriod: PeriodDTO
    let contentSHA256: String
    enum CodingKeys: String, CodingKey {
        case name, url
        case fetchedAt = "fetched_at", statedToday = "stated_today", statedPeriod = "stated_period"
        case contentSHA256 = "content_sha256"
    }
}

struct PeriodDTO: Decodable { let start: String; let end: String }

struct WeekDTO: Decodable { let start: String; let end: String; let label: String }

struct AttributionDTO: Decodable { let text: String; let url: String }

struct LicenseDTO: Decodable { let summary: String; let sources: [LicenseSourceDTO] }

struct LicenseSourceDTO: Decodable {
    let name: String
    let url: String
    let termsURL: String
    let termsReadOn: String
    let commercialReuse: String
    let attributionRequired: Bool
    enum CodingKeys: String, CodingKey {
        case name, url
        case termsURL = "terms_url", termsReadOn = "terms_read_on"
        case commercialReuse = "commercial_reuse", attributionRequired = "attribution_required"
    }
}

struct RegionDTO: Decodable { let code: String; let name: String }
struct CountyDTO: Decodable { let name: String; let region: String }

struct LocationDTO: Decodable { let lat: Double; let lon: Double; let source: String }

struct PlantDTO: Decodable {
    let week: WeekDTO
    let species: String
    let status: String
    let firstObservedAt: String
    let lastObservedAt: String
    enum CodingKeys: String, CodingKey {
        case week, species, status
        case firstObservedAt = "first_observed_at", lastObservedAt = "last_observed_at"
    }
}

struct WaterDTO: Decodable {
    let id: String
    let cdfwStockID: Int
    let name: String
    let nameStatus: String
    let slug: String
    let aliases: [String]?
    let counties: [String]
    let region: String
    let cdfwMapURL: String
    let location: LocationDTO?
    let lastListedWeek: WeekDTO?
    let plants: [PlantDTO]
    enum CodingKeys: String, CodingKey {
        case id, name, slug, aliases, counties, region, location, plants
        case cdfwStockID = "cdfw_stock_id", nameStatus = "name_status"
        case cdfwMapURL = "cdfw_map_url", lastListedWeek = "last_listed_week"
    }
}

struct ThisWeekDTO: Decodable {
    let waterID: String
    let species: String
    enum CodingKeys: String, CodingKey { case waterID = "water_id", species }
}

struct CoverageDTO: Decodable {
    let watersThisWeek: Int
    let watersKnown: Int
    let watersWithHistory: Int
    let namesMatched: Int
    let namesSeen: Int
    let rowsParsed: Int
    let weeksOfHistoryMin: Int
    let weeksOfHistoryMedian: Double
    enum CodingKeys: String, CodingKey {
        case watersThisWeek = "waters_this_week", watersKnown = "waters_known"
        case watersWithHistory = "waters_with_history", namesMatched = "names_matched"
        case namesSeen = "names_seen", rowsParsed = "rows_parsed"
        case weeksOfHistoryMin = "weeks_of_history_min", weeksOfHistoryMedian = "weeks_of_history_median"
    }
}
