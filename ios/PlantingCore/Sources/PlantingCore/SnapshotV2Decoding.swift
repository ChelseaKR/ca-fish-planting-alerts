import Foundation

/// Decoder for `schema/snapshot.v2.json`: California plus every other state
/// with data. Unknown keys are ignored.
///
/// Two kinds of trouble are told apart (DECISIONS 0034):
///
/// * **A contract violation** (a missing field, a week labeled as a day, a
///   `reported` plant in a schedule state, California not first) throws,
///   and the caller keeps the last good snapshot, exactly like v1.
/// * **A vocabulary this build does not know** is left out, never thrown
///   on: a state whose `semantics` this build has no words for, a state
///   this build has no product for (`StateAccess`), a plant whose `status`
///   or `period.precision` is new. The pipeline may add a state or a value
///   before an app update ships; an install must keep refreshing through
///   that, not freeze on its last snapshot forever. What is left out is
///   counted in `Ignored`, and `this_week` entries for those waters are
///   dropped with them.
///
/// California's waters keep v1's ids (`cdfw-<id>`), so favorites, alert
/// baselines and the widget carry over. The `Snapshot`'s top-level
/// `sourceWeek`, `source`, `attribution`, `license`, `regions` and
/// `counties` are California's, so every screen that read them from v1
/// reads the same thing from v2.
enum SnapshotV2Decoding {
    /// What a decode left out, for tests and diagnostics.
    struct Ignored: Equatable {
        var states: [String] = []
        var waters: [Water.ID] = []
        var plants = 0
    }

    static func decode(_ data: Data) throws -> Snapshot {
        try decodeReporting(data).snapshot
    }

    static func decodeReporting(_ data: Data) throws -> (snapshot: Snapshot, ignored: Ignored) {
        let dto: SnapshotV2DTO
        do {
            dto = try JSONDecoder().decode(SnapshotV2DTO.self, from: data)
        } catch let error as DecodingError {
            throw SnapshotDecodingError.malformed(SnapshotDecoder.describe(error))
        }
        var ignored = Ignored()
        var states: [StateInfo] = []
        for d in dto.states {
            guard let st = try state(d) else {
                ignored.states.append(d.code)
                continue
            }
            states.append(st)
        }
        guard let ca = states.first(where: { $0.code == "CA" }), dto.states.first?.code == "CA" else {
            throw SnapshotDecodingError.malformed("a v2 snapshot must list California first")
        }
        guard Set(dto.states.map(\.code)).count == dto.states.count else {
            throw SnapshotDecodingError.malformed("a state is listed twice")
        }
        let byCode = Dictionary(uniqueKeysWithValues: states.map { ($0.code, $0) })
        let ignoredStates = Set(ignored.states)

        var seen = Set<Water.ID>()
        var dropped = Set<Water.ID>()
        var waters: [Water] = []
        waters.reserveCapacity(dto.waters.count)
        for w in dto.waters {
            let id = w.id.trimmingCharacters(in: .whitespaces)
            guard seen.insert(id).inserted else {
                throw SnapshotDecodingError.malformed("duplicate water id \(id)")
            }
            if ignoredStates.contains(w.state) {
                dropped.insert(id)
                ignored.waters.append(id)
                continue
            }
            guard let st = byCode[w.state] else {
                throw SnapshotDecodingError.malformed("water \(id) names a state the snapshot doesn't list: \(w.state)")
            }
            let decoded = try water(w, state: st)
            ignored.plants += decoded.ignoredPlants
            guard let water = decoded.water else {
                dropped.insert(id)
                ignored.waters.append(id)
                continue
            }
            waters.append(water)
        }
        // The pipeline never publishes a state without a water (DECISIONS
        // 0025), so a state left with none after its plants were ignored
        // goes too, rather than listing a count of waters this build can't show.
        let withWaters = Set(waters.map(\.state))
        for st in states where st.code != "CA" && !withWaters.contains(st.code) {
            ignored.states.append(st.code)
        }
        states.removeAll { $0.code != "CA" && !withWaters.contains($0.code) }
        var thisWeek: [ThisWeekEntry] = []
        for entry in dto.thisWeek {
            let id = entry.waterID.trimmingCharacters(in: .whitespaces)
            let sp = entry.species.trimmingCharacters(in: .whitespaces)
            if dropped.contains(id) { continue }
            guard seen.contains(id), !sp.isEmpty else {
                throw SnapshotDecodingError.malformed("this_week entry \(id) names no water or no species")
            }
            thisWeek.append(ThisWeekEntry(waterID: id, species: sp))
        }
        var species: [String] = []
        for w in waters { for p in w.plants where !species.contains(p.species) { species.append(p.species) } }

        let source = SourceInfo(name: ca.sourceName, url: ca.sourceURL, fetchedAt: ca.fetchedAt,
                                statedToday: ca.currentWeek.start,
                                statedPeriodStart: ca.currentWeek.start, statedPeriodEnd: ca.currentWeek.end,
                                contentSHA256: try dto.states[0].source.contentSHA256Checked())
        let snapshot = Snapshot(schemaVersion: 2,
                                generatedAt: try SnapshotDecoder.datetime(dto.generatedAt, field: "generated_at"),
                                source: source, sourceWeek: ca.currentWeek, attribution: ca.attribution,
                                license: ca.license, regions: ca.regions, counties: ca.counties,
                                species: species.sorted(), waters: waters, thisWeek: thisWeek,
                                coverage: nil, states: states)
        return (snapshot, ignored)
    }

    static let caRegionCodes = SnapshotDecoder.regionCodes

    /// One state, or nil when this build has no words or no product for it.
    static func state(_ d: StateDTO) throws -> StateInfo? {
        let code = d.code
        guard code.count == 2, code == code.uppercased() else {
            throw SnapshotDecodingError.malformed("state code is not two capitals: \(code)")
        }
        guard let semantics = StateSemantics(rawValue: d.semantics), StateAccess.isKnown(state: code) else {
            return nil
        }
        // A precision this build does not know is left out of the list; the
        // plants that use it are left out below, water by water.
        let precisions = d.datePrecisions.compactMap(DatePrecision.init(rawValue:))
        let regions = try d.regions.map { r -> Region in
            if code == "CA", !caRegionCodes.contains(r.code) {
                throw SnapshotDecodingError.malformed("region has an unrecognized code: \(r.code)")
            }
            return Region(code: r.code, name: r.name)
        }
        let license = License(summary: d.license.summary, sources: try d.license.sources.map { s in
            guard let reuse = CommercialReuse(rawValue: s.commercialReuse) else {
                throw SnapshotDecodingError.malformed("license source \(s.name) has an unrecognized commercial_reuse: \(s.commercialReuse)")
            }
            return LicenseSource(name: s.name, url: try SnapshotDecoder.url(s.url, field: "\(code).license.url"),
                                 termsURL: try SnapshotDecoder.url(s.termsURL, field: "\(code).license.terms_url"),
                                 termsReadOn: try SnapshotDecoder.date(s.termsReadOn, field: "\(code).license.terms_read_on"),
                                 commercialReuse: reuse, attributionRequired: s.attributionRequired,
                                 termsQuote: s.termsQuote)
        })
        return StateInfo(
            code: code, name: d.name, agencyName: d.agency.name, agencyShortName: d.agency.shortName,
            agencyURL: try SnapshotDecoder.url(d.agency.url, field: "\(code).agency.url"),
            semantics: semantics, datePrecisions: precisions, removalInference: d.removalInference,
            currentWeek: try SnapshotDecoder.week(d.currentWeek, field: "\(code).current_week"),
            asOf: try SnapshotDecoder.date(d.asOf, field: "\(code).as_of"),
            newestRecord: try d.newestRecord.flatMap { try period($0, field: "\(code).newest_record") },
            recencyNote: d.recencyNote,
            sourceName: d.source.name, sourceURL: try SnapshotDecoder.url(d.source.url, field: "\(code).source.url"),
            fetchedAt: try SnapshotDecoder.datetime(d.source.fetchedAt, field: "\(code).source.fetched_at"),
            lastModified: d.source.lastModified,
            lastAttemptAt: try SnapshotDecoder.datetime(d.checks.lastAttemptAt, field: "\(code).checks.last_attempt_at"),
            lastSuccessAt: try SnapshotDecoder.datetime(d.checks.lastSuccessAt, field: "\(code).checks.last_success_at"),
            lastAttemptOK: d.checks.lastAttemptOK,
            attribution: Attribution(text: d.attribution.text, url: try SnapshotDecoder.url(d.attribution.url, field: "\(code).attribution.url")),
            disclaimer: d.disclaimer, license: license, regions: regions,
            counties: d.counties.map { County(name: $0.name, region: $0.region ?? "") },
            watersCount: d.watersCount)
    }

    /// A period at a precision this build knows, or nil for one it does not.
    /// A known precision whose label or bounds break the contract throws.
    static func period(_ d: PeriodV2DTO, field: String) throws -> Week? {
        guard let precision = DatePrecision(rawValue: d.precision) else { return nil }
        let start = try SnapshotDecoder.date(d.start, field: "\(field).start")
        let end = try SnapshotDecoder.date(d.end, field: "\(field).end")
        guard start <= end else { throw SnapshotDecodingError.malformed("\(field) has end before start") }
        switch precision {
        case .day:
            guard start == end, d.label == start.isoDate else {
                throw SnapshotDecodingError.malformed("\(field) is a day but reads \(d.label)")
            }
        case .week:
            guard d.label == "week of \(start.isoDate)" else {
                throw SnapshotDecodingError.malformed("\(field) is a week but reads \(d.label)")
            }
        case .month:
            guard start.day == 1, start.month == end.month, !d.label.contains("-") else {
                throw SnapshotDecodingError.malformed("\(field) is a month but reads \(d.label)")
            }
        case .approximate:
            // The agency's words and the year, verbatim: "April - third week, 2026".
            guard d.label.hasSuffix(", \(start.year)"), d.label.count > 6 else {
                throw SnapshotDecodingError.malformed("\(field) is approximate but reads \(d.label)")
            }
        }
        return Week(start: start, end: end, label: d.label, precision: precision)
    }

    /// One water, or nil when every plant used a vocabulary this build does
    /// not know and there is no months note to show instead.
    static func water(_ w: WaterV2DTO, state: StateInfo) throws -> (water: Water?, ignoredPlants: Int) {
        let id = w.id.trimmingCharacters(in: .whitespaces)
        var stockID = 0
        if state.code == "CA" {
            guard id.hasPrefix("cdfw-"), let n = Int(id.dropFirst("cdfw-".count)) else {
                throw SnapshotDecodingError.malformed("water id is not cdfw-<digits>: \(id)")
            }
            stockID = n
        } else if !id.hasPrefix("\(state.code.lowercased())-") {
            throw SnapshotDecodingError.malformed("water \(id) does not start with its state's code")
        }
        let name = w.name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { throw SnapshotDecodingError.malformed("water \(id) has an empty name") }
        let region = w.region ?? ""
        if state.code == "CA", !caRegionCodes.contains(region) {
            throw SnapshotDecodingError.malformed("water \(id) has an unrecognized region: \(region)")
        }
        var ignoredPlants = 0
        var plants: [Plant] = []
        for p in w.plants {
            guard let status = PlantStatus(rawValue: p.status),
                  let week = try period(p.period, field: "waters[\(id)].plants[].period") else {
                ignoredPlants += 1
                continue
            }
            let fits: Bool
            switch state.semantics {
            case .report: fits = status == .reported
            case .schedule: fits = status != .reported
            case .plan: fits = status == .listed
            }
            guard fits else {
                throw SnapshotDecodingError.malformed("waters[\(id)] has a \(p.status) plant in a \(state.semantics.rawValue) state")
            }
            let sp = p.species.trimmingCharacters(in: .whitespaces)
            guard !sp.isEmpty else { throw SnapshotDecodingError.malformed("waters[\(id)] has a plant with an empty species") }
            plants.append(Plant(week: week, species: sp, status: status,
                                firstObservedAt: try SnapshotDecoder.datetime(p.firstObservedAt, field: "waters[\(id)].plants[].first_observed_at"),
                                lastObservedAt: try SnapshotDecoder.datetime(p.lastObservedAt, field: "waters[\(id)].plants[].last_observed_at"),
                                count: p.count))
        }
        let monthsNote = w.monthsNote?.trimmingCharacters(in: .whitespaces)
        let hasNote = !(monthsNote ?? "").isEmpty
        if plants.isEmpty, !hasNote {
            // Nothing this build can show. An empty list in the file is a
            // contract violation; a list emptied by unknown vocabulary is not.
            guard ignoredPlants > 0 else {
                throw SnapshotDecodingError.malformed("water \(id) has no plants and no months note")
            }
            return (nil, ignoredPlants)
        }
        let water = Water(id: id, cdfwStockID: stockID, name: name, nameReviewed: w.nameStatus == "reviewed",
                          slug: w.slug, aliases: SnapshotDecoder.clean(w.aliases), counties: SnapshotDecoder.clean(w.counties),
                          region: region, cdfwMapURL: try SnapshotDecoder.url(w.sourceURL, field: "waters[\(id)].source_url"),
                          location: w.location.map { GeoLocation(lat: $0.lat, lon: $0.lon, source: $0.source) },
                          lastListedWeek: try w.lastPeriod.flatMap { try period($0, field: "waters[\(id)].last_period") },
                          plants: plants, state: state.code, semantics: state.semantics,
                          agencyShortName: state.agencyShortName, towns: SnapshotDecoder.clean(w.towns),
                          sitePath: w.sitePath, monthsNote: hasNote ? monthsNote : nil)
        return (water, ignoredPlants)
    }
}

// MARK: - v2 wire DTOs

struct SnapshotV2DTO: Decodable {
    let generatedAt: String
    let states: [StateDTO]
    let waters: [WaterV2DTO]
    let thisWeek: [ThisWeekDTO]
    enum CodingKeys: String, CodingKey {
        case generatedAt = "generated_at", states, waters, thisWeek = "this_week"
    }
}

struct AgencyDTO: Decodable {
    let name: String
    let shortName: String
    let url: String
    enum CodingKeys: String, CodingKey { case name, shortName = "short_name", url }
}

struct StateSourceDTO: Decodable {
    let name: String
    let url: String
    let fetchedAt: String
    let contentSHA256: String
    let lastModified: String?
    enum CodingKeys: String, CodingKey {
        case name, url, fetchedAt = "fetched_at", contentSHA256 = "content_sha256", lastModified = "last_modified"
    }
    func contentSHA256Checked() throws -> String {
        guard contentSHA256.count == 64 else { throw SnapshotDecodingError.malformed("content_sha256 is not 64 hex digits") }
        return contentSHA256
    }
}

struct ChecksDTO: Decodable {
    let lastAttemptAt: String
    let lastSuccessAt: String
    let lastAttemptOK: Bool
    enum CodingKeys: String, CodingKey {
        case lastAttemptAt = "last_attempt_at", lastSuccessAt = "last_success_at", lastAttemptOK = "last_attempt_ok"
    }
}

struct LicenseSourceV2DTO: Decodable {
    let name: String
    let url: String
    let termsURL: String
    let termsReadOn: String
    let commercialReuse: String
    let attributionRequired: Bool
    let termsQuote: String?
    enum CodingKeys: String, CodingKey {
        case name, url, termsURL = "terms_url", termsReadOn = "terms_read_on"
        case commercialReuse = "commercial_reuse", attributionRequired = "attribution_required", termsQuote = "terms_quote"
    }
}

struct LicenseV2DTO: Decodable { let summary: String; let sources: [LicenseSourceV2DTO] }
struct CountyV2DTO: Decodable { let name: String; let region: String? }

struct PeriodV2DTO: Decodable { let precision: String; let start: String; let end: String; let label: String }

struct StateDTO: Decodable {
    let code: String
    let name: String
    let agency: AgencyDTO
    let semantics: String
    let datePrecisions: [String]
    let removalInference: Bool
    let currentWeek: WeekDTO
    let asOf: String
    let newestRecord: PeriodV2DTO?
    let recencyNote: String?
    let source: StateSourceDTO
    let checks: ChecksDTO
    let attribution: AttributionDTO
    let disclaimer: String
    let license: LicenseV2DTO
    let regions: [RegionDTO]
    let counties: [CountyV2DTO]
    let watersCount: Int
    enum CodingKeys: String, CodingKey {
        case code, name, agency, semantics, source, checks, attribution, disclaimer, license, regions, counties
        case datePrecisions = "date_precisions", removalInference = "removal_inference"
        case currentWeek = "current_week", asOf = "as_of", newestRecord = "newest_record"
        case recencyNote = "recency_note", watersCount = "waters_count"
    }
}

struct PlantV2DTO: Decodable {
    let period: PeriodV2DTO
    let species: String
    let status: String
    let count: Int?
    let firstObservedAt: String
    let lastObservedAt: String
    enum CodingKeys: String, CodingKey {
        case period, species, status, count
        case firstObservedAt = "first_observed_at", lastObservedAt = "last_observed_at"
    }
}

struct WaterV2DTO: Decodable {
    let id: String
    let state: String
    let name: String
    let nameStatus: String
    let slug: String
    let aliases: [String]?
    let counties: [String]
    let towns: [String]?
    let region: String?
    let sourceURL: String
    let sitePath: String?
    let location: LocationDTO?
    let lastPeriod: PeriodV2DTO?
    let monthsNote: String?
    let plants: [PlantV2DTO]
    enum CodingKeys: String, CodingKey {
        case id, state, name, slug, aliases, counties, towns, region, location, plants
        case nameStatus = "name_status", sourceURL = "source_url", sitePath = "site_path"
        case lastPeriod = "last_period", monthsNote = "months_note"
    }
}
