import Foundation

// Water locations for the map (DECISIONS 0024 and 0025).
//
// Snapshot v1, which this app reads, carries `location: null` for every
// water, and must stay that way for installed 1.0 builds. So the app ships
// its own copy of the confident locations, `water-locations.json`, built
// from `pipeline/data/water_locations.json` by
// `ios/scripts/sync-water-locations.sh`. Only `exact` and owner-resolved
// waters are in it: an ambiguous or unmatched water has no entry and gets
// no pin. When a snapshot does carry a location (v2), that one wins.

public struct WaterLocationTable: Equatable, Sendable {
    public static let schema = "cfpa-app-water-locations-v1"

    public let generatedOn: String
    public let locations: [Water.ID: GeoLocation]

    public init(generatedOn: String, locations: [Water.ID: GeoLocation]) {
        self.generatedOn = generatedOn
        self.locations = locations
    }

    public static let empty = WaterLocationTable(generatedOn: "", locations: [:])

    public enum DecodeError: Error, Equatable {
        case wrongSchema(String)
        case outOfRange(Water.ID)
    }

    private struct DTO: Decodable {
        let schema: String
        let generated_on: String
        let locations: [String: Entry]
        struct Entry: Decodable {
            let lat: Double
            let lon: Double
            let source: String
            let kind: String
        }
    }

    public static func decode(_ data: Data) throws -> WaterLocationTable {
        let dto = try JSONDecoder().decode(DTO.self, from: data)
        guard dto.schema == schema else { throw DecodeError.wrongSchema(dto.schema) }
        var out: [Water.ID: GeoLocation] = [:]
        for (id, e) in dto.locations {
            // California, generously. A point outside it is a bug, not a pin.
            guard (32.0...42.5).contains(e.lat), (-125.0 ... -114.0).contains(e.lon) else {
                throw DecodeError.outOfRange(id)
            }
            out[id] = GeoLocation(lat: e.lat, lon: e.lon, source: e.source,
                                  kind: GeoLocation.Kind(rawValue: e.kind))
        }
        return WaterLocationTable(generatedOn: dto.generated_on, locations: out)
    }

    /// The snapshot's own location if it has one, else this table's.
    public func location(for water: Water) -> GeoLocation? {
        water.location ?? locations[water.id]
    }
}

/// One water on the map.
public struct WaterPin: Equatable, Sendable, Identifiable {
    public let id: Water.ID
    public let name: String
    public let county: String
    public let location: GeoLocation
    /// Listed for the snapshot's own current week.
    public let isThisWeek: Bool

    public var isApproximate: Bool { location.isApproximate }
}

extension Snapshot {
    /// Waters listed for `sourceWeek`.
    public var thisWeekIDs: Set<Water.ID> { Set(thisWeek.map(\.waterID)) }

    /// A pin for every water with a location, by name; none for the rest.
    public func mapPins(_ table: WaterLocationTable) -> [WaterPin] {
        let week = thisWeekIDs
        return waters.compactMap { w in
            table.location(for: w).map {
                WaterPin(id: w.id, name: w.name, county: w.counties.first ?? "",
                       location: $0, isThisWeek: week.contains(w.id))
            }
        }
        .sorted { ($0.name, $0.id) < ($1.name, $1.id) }
    }
}

/// "Near me", worked out on the device. The location never leaves it.
public enum NearMe {
    public struct Result: Equatable, Sendable, Identifiable {
        public let pin: WaterPin
        /// Straight-line distance, not by road.
        public let meters: Double
        public var id: Water.ID { pin.id }
    }

    /// Great-circle distance in meters (haversine, mean Earth radius).
    public static func meters(fromLat lat1: Double, lon lon1: Double,
                              toLat lat2: Double, lon lon2: Double) -> Double {
        let r = 6_371_008.8
        let p1 = lat1 * .pi / 180, p2 = lat2 * .pi / 180
        let dp = (lat2 - lat1) * .pi / 180, dl = (lon2 - lon1) * .pi / 180
        let a = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2)
        return 2 * r * atan2(a.squareRoot(), (1 - a).squareRoot())
    }

    /// The closest `limit` pins to a point, nearest first.
    public static func nearest(toLat lat: Double, lon: Double, pins: [WaterPin],
                               limit: Int = 25) -> [Result] {
        pins.map { Result(pin: $0, meters: meters(fromLat: lat, lon: lon,
                                                  toLat: $0.location.lat, lon: $0.location.lon)) }
            .sorted { ($0.meters, $0.pin.name) < ($1.meters, $1.pin.name) }
            .prefix(max(0, limit))
            .map { $0 }
    }

    /// "0.4 mi", "12 mi", "130 mi": US miles, straight line.
    public static func milesText(_ meters: Double) -> String {
        let miles = meters / 1_609.344
        if miles < 10 { return String(format: "%.1f mi", miles) }
        return "\(Int(miles.rounded())) mi"
    }
}

/// What a water's page says about where it is.
public enum LocationWording {
    public static func summary(_ location: GeoLocation?) -> String {
        guard let location else {
            return "No map location. Federal map data doesn't name exactly one water like this in its county, or the name is a stretch of a stream, so it isn't placed on a map rather than guessed."
        }
        switch location.kind {
        case .streamPoint:
            return "Approximate: a point on the stream. CDFW plants along a stream and doesn't say where."
        case .namedPoint:
            return "The point the U.S. Geological Survey gives for this lake."
        case .waterbody, nil:
            return "A point inside the lake."
        }
    }

    public static let attribution = "Location source: U.S. Geological Survey."
}
