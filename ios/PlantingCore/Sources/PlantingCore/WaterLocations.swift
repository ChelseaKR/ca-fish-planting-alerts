import Foundation

// Water locations for the map (DECISIONS 0024 and 0026).
//
// They come from the snapshot itself: v2 carries `location` for every
// water the geocoder placed with confidence (exact, or picked by the owner),
// and `null` for the rest. A water with no location gets no pin. Only
// California has a location source today; another state's waters are
// pinned as soon as its snapshot entries carry one.

/// One water on the map.
public struct WaterPin: Equatable, Sendable, Identifiable {
    public let id: Water.ID
    public let name: String
    /// The state's postal code (`CA`, `TN`, …).
    public let state: String
    public let county: String
    public let location: GeoLocation
    /// Listed (or reported) for its state's own current week.
    public let isThisWeek: Bool

    public var isApproximate: Bool { location.isApproximate }
}

/// How many of a state's waters are on the map.
public struct MapCoverage: Equatable, Sendable, Identifiable {
    public let code: String
    public let name: String
    public let placed: Int
    public let total: Int
    public var id: String { code }
}

extension Snapshot {
    /// Waters in `thisWeek` (every state's own current week).
    public var thisWeekIDs: Set<Water.ID> { Set(thisWeek.map(\.waterID)) }

    /// A pin for every water with a location, by name; none for the rest.
    public var mapPins: [WaterPin] {
        let week = thisWeekIDs
        return waters.compactMap { w in
            w.location.map {
                WaterPin(id: w.id, name: w.name, state: w.state,
                         county: w.counties.first ?? w.towns.first ?? "",
                         location: $0, isThisWeek: week.contains(w.id))
            }
        }
        .sorted { ($0.name, $0.id) < ($1.name, $1.id) }
    }

    /// Per state, in the snapshot's order: how many waters have a pin.
    public var mapCoverage: [MapCoverage] {
        let known = states.isEmpty
            ? [(code: "CA", name: "California")]
            : states.map { (code: $0.code, name: $0.name) }
        return known.map { st in
            let mine = waters.filter { $0.state == st.code }
            return MapCoverage(code: st.code, name: st.name,
                               placed: mine.filter { $0.location != nil }.count,
                               total: mine.count)
        }
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
        case .waterbody:
            return "A point inside the lake."
        case nil:
            return "A point for this water."
        }
    }

    public static let attribution = "Location source: U.S. Geological Survey."
}
