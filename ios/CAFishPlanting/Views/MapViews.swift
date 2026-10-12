import SwiftUI
import MapKit
import CoreLocation
import PlantingCore

// Maps (DECISIONS 0026). Apple's MapKit draws the map; no third-party SDK.
// Only waters with a confident location get a pin (the snapshot's own);
// a stream's pin is marked approximate. "Near me" asks for the location
// only when it is used, When In Use only, takes one coarse fix, and works
// out distances on this device. The location is never stored or sent.

// MARK: - Near me

@MainActor
@Observable
final class NearMeLocator: NSObject, CLLocationManagerDelegate {
    enum State: Equatable {
        case idle
        case asking
        case locating
        case located(lat: Double, lon: Double)
        case denied
        case failed
    }

    private(set) var state: State = .idle
    private let manager = CLLocationManager()
    private var timeout: Task<Void, Never>?

    override init() {
        super.init()
        manager.delegate = self
        // Kilometer accuracy is plenty to sort waters by distance.
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    var needsPermission: Bool { manager.authorizationStatus == .notDetermined }

    /// Asks iOS for permission if it has never been asked, then waits for
    /// one fix and stops. Gives up after 20 seconds.
    func locate() {
        switch manager.authorizationStatus {
        case .notDetermined:
            state = .asking
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            state = .locating
            manager.startUpdatingLocation()
            timeout?.cancel()
            timeout = Task { [weak self] in
                try? await Task.sleep(for: .seconds(20))
                guard let self, !Task.isCancelled, self.state == .locating else { return }
                self.manager.stopUpdatingLocation()
                self.state = .failed
            }
        default:
            state = .denied
        }
    }

    private func finish(_ next: State) {
        timeout?.cancel()
        manager.stopUpdatingLocation()
        state = next
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            if self.state == .asking { self.locate() }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let c = locations.last?.coordinate else { return }
        Task { @MainActor in
            if self.state == .locating { self.finish(.located(lat: c.latitude, lon: c.longitude)) }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let code = (error as? CLError)?.code
        Task { @MainActor in
            // "Location unknown" is temporary: Core Location keeps trying,
            // and the 20-second limit decides when to give up.
            if code == .locationUnknown { return }
            self.finish(code == .denied ? .denied : .failed)
        }
    }
}

// MARK: - The Map tab

struct MapTabView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(AppRouter.self) private var router
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var locator = NearMeLocator()
    @State private var showingNearMe = false
    @State private var showingKey = false
    @State private var selection: Water.ID?

    private var splitLayout: Bool {
        horizontalSizeClass == .regular && !dynamicTypeSize.isAccessibilitySize
    }

    var body: some View {
        @Bindable var router = router
        if let snapshot = environment.snapshot {
            let pins = snapshot.mapPins
            if splitLayout {
                NavigationSplitView {
                    MappedWaterList(pins: pins, locator: locator, selection: $selection)
                        .navigationTitle("Waters")
                } detail: {
                    // Near me lives with the map, which is always on screen;
                    // the list column can be hidden (iPad portrait).
                    NavigationStack(path: $router.mapPath) {
                        mapScreen(snapshot: snapshot, pins: pins)
                            .navigationTitle("Map")
                            .navigationBarTitleDisplayMode(.inline)
                            .toolbar { nearMeButton }
                            .waterDestinations(in: snapshot, enabled: true)
                    }
                }
                .sheet(isPresented: $showingNearMe) { nearMeSheet(pins: pins) }
            } else {
                NavigationStack(path: $router.mapPath) {
                    mapScreen(snapshot: snapshot, pins: pins)
                        .navigationTitle("Map")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar { nearMeButton }
                        .waterDestinations(in: snapshot, enabled: true)
                }
                .sheet(isPresented: $showingNearMe) { nearMeSheet(pins: pins) }
            }
        } else {
            ContentUnavailableView("No schedule yet", systemImage: "map",
                                   description: Text("The map shows waters once the schedule has loaded."))
        }
    }

    @ToolbarContentBuilder
    private var nearMeButton: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            Button {
                showingKey = true
            } label: {
                Label("Map key", systemImage: "info.circle")
            }
        }
        ToolbarItem(placement: .primaryAction) {
            Button {
                showingNearMe = true
            } label: {
                Label("Near me", systemImage: "location")
            }
            .accessibilityHint("Lists the waters closest to you, worked out on this device")
        }
    }

    private func mapScreen(snapshot: Snapshot, pins: [WaterPin]) -> some View {
        ClusteredWaterMap(pins: pins, selection: $selection, opened: { router.mapPath = [$0] },
                          userLocation: locatedCoordinate)
            // The map ends above the caption, so no pin hides behind it.
            .safeAreaInset(edge: .bottom) {
                // At the accessibility sizes the caption would cover the
                // map; the Map key sheet says the same, in a list.
                if !dynamicTypeSize.isAccessibilitySize {
                    MapCaption(coverage: snapshot.mapCoverage)
                }
            }
            .sheet(isPresented: $showingKey) { MapKeySheet(coverage: snapshot.mapCoverage) }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Map of \(pins.count) waters with a location")
    }

    private var locatedCoordinate: CLLocationCoordinate2D? {
        if case let .located(lat, lon) = locator.state {
            return CLLocationCoordinate2D(latitude: lat, longitude: lon)
        }
        return nil
    }

    private func nearMeSheet(pins: [WaterPin]) -> some View {
        NearMeSheet(locator: locator, pins: pins) { id in
            showingNearMe = false
            selection = id
            router.mapPath = [id]
        }
    }
}

/// The line under the map: how many waters are on it, and where the rest are.
private struct MapCaption: View {
    let coverage: [MapCoverage]

    /// "California: 232 of 387 waters have a location. Tennessee: no locations yet."
    private var line: String { Self.line(coverage) }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(line).fixedSize(horizontal: false, vertical: true)
            // Text in the primary color, only the symbols colored: the
            // accent green as text failed contrast at the largest sizes.
            HStack(spacing: 14) {
                MapLegendItem.thisWeek
                MapLegendItem.other
                MapLegendItem.stream
            }
            .font(.caption)
        }
        .font(.footnote)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal)
        .padding(.vertical, 8)
        // Solid, not a material: text over the map must keep its contrast.
        .background(Color(.systemBackground))
        .accessibilityElement(children: .combine)
    }

    static func line(_ coverage: [MapCoverage]) -> String {
        coverage.map { st in
            st.placed == 0
                ? "\(st.name): no locations yet."
                : "\(st.name): \(st.placed) of \(st.total) waters have a location."
        }
        .joined(separator: " ") + " The rest are in Browse, never guessed onto the map."
    }
}

/// The legend's three entries, shared by the caption and the Map key sheet.
enum MapLegendItem {
    static var thisWeek: some View { item("This week", symbol: "circle.fill", color: Color(ClusteredWaterMap.thisWeek)) }
    static var other: some View { item("Other waters", symbol: "circle.fill", color: Color(ClusteredWaterMap.otherWaters)) }
    static var stream: some View { item("Stream: approximate", symbol: "water.waves", color: .secondaryText) }

    private static func item(_ text: String, symbol: String, color: Color) -> some View {
        Label {
            Text(text)
        } icon: {
            Image(systemName: symbol).foregroundStyle(color)
        }
    }
}

/// Everything the caption says, as a scrolling list: from a toolbar button
/// at every size, and the only place it shows at the accessibility sizes,
/// where the caption would cover the map.
private struct MapKeySheet: View {
    let coverage: [MapCoverage]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(coverage) { st in
                        Text(st.placed == 0
                             ? "\(st.name): no locations yet."
                             : "\(st.name): \(st.placed) of \(st.total) waters have a location.")
                    }
                    Text("A water is on the map only when federal map data names exactly one water like it in its county. The rest are in Browse, never guessed onto the map.")
                        .foregroundStyle(.secondaryText)
                } header: {
                    SectionHeader("Waters on the map")
                }
                Section {
                    MapLegendItem.thisWeek
                    MapLegendItem.other
                    MapLegendItem.stream
                } header: {
                    SectionHeader("Pins")
                }
            }
            .navigationTitle("Map key")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}


/// The sidebar at regular width: the nearest waters once located, otherwise
/// every mapped water by name. Choosing one centers the map on it.
private struct MappedWaterList: View {
    let pins: [WaterPin]
    let locator: NearMeLocator
    @Binding var selection: Water.ID?

    var body: some View {
        List(selection: $selection) {
            if case let .located(lat, lon) = locator.state {
                Section {
                    ForEach(NearMe.nearest(toLat: lat, lon: lon, pins: pins)) { result in
                        PinRow(pin: result.pin, distance: NearMe.milesText(result.meters)).tag(result.id)
                    }
                } header: {
                    SectionHeader("Nearest, in a straight line")
                }
            } else {
                Section {
                    ForEach(pins) { pin in PinRow(pin: pin, distance: nil).tag(pin.id) }
                } header: {
                    SectionHeader("Waters with a location")
                }
            }
        }
    }
}

private struct PinRow: View {
    let pin: WaterPin
    let distance: String?

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(pin.name)
                Text(detail).font(.caption).foregroundStyle(.secondaryText)
            }
            Spacer()
            if let distance {
                Text(distance).font(.subheadline).foregroundStyle(.secondaryText)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var detail: String {
        var parts = ["\(pin.county) County"]
        if pin.isThisWeek { parts.append("this week") }
        if pin.isApproximate { parts.append("approximate location") }
        return parts.joined(separator: " · ")
    }
}

/// What Near me says before iOS asks, and what it shows after.
private struct NearMeSheet: View {
    let locator: NearMeLocator
    let pins: [WaterPin]
    let open: (Water.ID) -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            content
                .navigationTitle("Near me")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                }
        }
        .task {
            if !locator.needsPermission, locator.state == .idle || locator.state == .failed {
                locator.locate()
            }
        }
    }

    @ViewBuilder private var content: some View {
        switch locator.state {
        case let .located(lat, lon):
            List {
                Section {
                    ForEach(NearMe.nearest(toLat: lat, lon: lon, pins: pins)) { result in
                        Button { open(result.id) } label: {
                            PinRow(pin: result.pin, distance: NearMe.milesText(result.meters))
                        }
                        .foregroundStyle(.primary)
                    }
                } header: {
                    // At the top, where it is read: the list can be long.
                    Text("Nearest first, in a straight line, not by road. Worked out on this device; your location is not saved or sent anywhere.")
                        .textCase(nil)
                        .foregroundStyle(.secondaryText)
                }
            }
        case .denied:
            ContentUnavailableView {
                Label("Location is off", systemImage: "location.slash")
            } description: {
                Text("Trout Truck can't see your location, so it can't sort waters by distance. The map, Browse and Favorites all work without it.")
            } actions: {
                Button("Open Settings") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                }
            }
        case .failed:
            ContentUnavailableView {
                Label("Couldn't find your location", systemImage: "location.slash")
            } description: {
                Text("Try again in a moment. The map works without it.")
            } actions: {
                Button("Try again") { locator.locate() }
            }
        case .asking, .locating:
            ProgressView("Finding waters near you…")
        case .idle:
            explainer
        }
    }

    /// Shown once, before iOS asks: what Near me does with the location.
    private var explainer: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Image(systemName: "location.circle")
                    .font(.largeTitle)
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)
                Text("Find waters near you")
                    .font(.title2.bold())
                    .accessibilityAddTraits(.isHeader)
                Text("Near me sorts the waters on the map by how far they are from you. iOS will ask to share your location while you use the app.")
                Text("Your location is used on this iPhone only. It isn't saved, and it isn't sent to the developer or anyone else.")
                Text("You can say no: the map, Browse and Favorites work the same without it.")
                    .foregroundStyle(.secondaryText)
                Button {
                    locator.locate()
                } label: {
                    Text("Continue").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                Button("Not now") { dismiss() }
                    .frame(maxWidth: .infinity)
            }
            .padding()
        }
    }
}

// MARK: - MapKit, clustered

final class WaterAnnotation: NSObject, MKAnnotation {
    let pin: WaterPin
    let coordinate: CLLocationCoordinate2D
    var title: String? { pin.name }
    var subtitle: String? {
        var parts = ["\(pin.county) County"]
        if pin.isThisWeek { parts.append("Scheduled this week") }
        if pin.isApproximate { parts.append("Approximate: on the stream") }
        return parts.joined(separator: " · ")
    }

    init(pin: WaterPin) {
        self.pin = pin
        self.coordinate = CLLocationCoordinate2D(latitude: pin.location.lat, longitude: pin.location.lon)
    }
}

/// MKMapView, because SwiftUI's `Map` has no clustering. Pins cluster as
/// the map zooms out; a pin's callout opens the water's page.
struct ClusteredWaterMap: UIViewRepresentable {
    let pins: [WaterPin]
    @Binding var selection: Water.ID?
    let opened: (Water.ID) -> Void
    let userLocation: CLLocationCoordinate2D?

    /// Pins and clusters that are not this week's. MapKit draws the count
    /// and glyph in white; this gray keeps them at about 6.7:1 (the system
    /// gray was 3.3:1, below WCAG's 4.5:1, in the accessibility audit).
    static let otherWaters = UIColor(white: 0.36, alpha: 1)

    /// This week's pins and clusters: the accent green of light mode in both
    /// modes (#0F784B, 5.5:1 under MapKit's white glyph). The dark-mode
    /// accent (#2E9E68) is only 3.4:1 there, which the accessibility audit
    /// flagged on cluster counts.
    static let thisWeek = UIColor(red: 0x0F / 255, green: 0x78 / 255, blue: 0x4B / 255, alpha: 1)

    static let california = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 37.3, longitude: -119.4),
        span: MKCoordinateSpan(latitudeDelta: 10.5, longitudeDelta: 10.5))

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        // Every pin in view, whatever states they are in; California when
        // there are none.
        if pins.isEmpty {
            map.setRegion(Self.california, animated: false)
        } else {
            let rect = pins.reduce(MKMapRect.null) { rect, pin in
                let point = MKMapPoint(CLLocationCoordinate2D(latitude: pin.location.lat, longitude: pin.location.lon))
                return rect.union(MKMapRect(x: point.x, y: point.y, width: 0, height: 0))
            }
            map.setVisibleMapRect(rect, edgePadding: UIEdgeInsets(top: 40, left: 40, bottom: 40, right: 40), animated: false)
        }
        map.pointOfInterestFilter = .excludingAll
        map.register(MKMarkerAnnotationView.self,
                     forAnnotationViewWithReuseIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier)
        map.register(MKMarkerAnnotationView.self,
                     forAnnotationViewWithReuseIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier)
        map.addAnnotations(pins.map(WaterAnnotation.init))
        return map
    }

    func updateUIView(_ map: MKMapView, context: Context) {
        context.coordinator.parent = self
        let current = map.annotations.compactMap { $0 as? WaterAnnotation }
        if current.map(\.pin) != pins {
            map.removeAnnotations(current)
            map.addAnnotations(pins.map(WaterAnnotation.init))
        }
        // The blue dot only after Near me found a location, never before.
        map.showsUserLocation = userLocation != nil
        if let userLocation, context.coordinator.centeredOnUser != userLocation.latitude {
            context.coordinator.centeredOnUser = userLocation.latitude
            map.setRegion(MKCoordinateRegion(center: userLocation, latitudinalMeters: 120_000,
                                             longitudinalMeters: 120_000), animated: true)
        }
        if let selection, context.coordinator.lastSelection != selection,
           let a = map.annotations.compactMap({ $0 as? WaterAnnotation }).first(where: { $0.pin.id == selection }) {
            context.coordinator.lastSelection = selection
            map.setRegion(MKCoordinateRegion(center: a.coordinate, latitudinalMeters: 30_000,
                                             longitudinalMeters: 30_000), animated: true)
            map.selectAnnotation(a, animated: true)
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var parent: ClusteredWaterMap
        var centeredOnUser: Double?
        var lastSelection: Water.ID?

        init(_ parent: ClusteredWaterMap) { self.parent = parent }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if let cluster = annotation as? MKClusterAnnotation {
                let view = mapView.dequeueReusableAnnotationView(
                    withIdentifier: MKMapViewDefaultClusterAnnotationViewReuseIdentifier, for: cluster)
                if let marker = view as? MKMarkerAnnotationView {
                    let thisWeek = cluster.memberAnnotations.contains { ($0 as? WaterAnnotation)?.pin.isThisWeek == true }
                    marker.markerTintColor = thisWeek ? ClusteredWaterMap.thisWeek : ClusteredWaterMap.otherWaters
                    marker.glyphText = "\(cluster.memberAnnotations.count)"
                    marker.accessibilityLabel = "\(cluster.memberAnnotations.count) waters"
                }
                return view
            }
            guard let water = annotation as? WaterAnnotation else { return nil }
            let view = mapView.dequeueReusableAnnotationView(
                withIdentifier: MKMapViewDefaultAnnotationViewReuseIdentifier, for: water)
            guard let marker = view as? MKMarkerAnnotationView else { return view }
            marker.clusteringIdentifier = "water"
            marker.canShowCallout = true
            marker.markerTintColor = water.pin.isThisWeek ? ClusteredWaterMap.thisWeek : ClusteredWaterMap.otherWaters
            // A stream's point is approximate: a wave, not a drop.
            marker.glyphImage = UIImage(systemName: water.pin.isApproximate ? "water.waves" : "drop.fill")
            marker.displayPriority = water.pin.isThisWeek ? .defaultHigh : .defaultLow
            let open = UIButton(type: .detailDisclosure)
            open.accessibilityLabel = "Open \(water.pin.name)"
            marker.rightCalloutAccessoryView = open
            marker.accessibilityLabel = [water.title, water.subtitle].compactMap { $0 }.joined(separator: ", ")
            return marker
        }

        func mapView(_ mapView: MKMapView, annotationView view: MKAnnotationView,
                     calloutAccessoryControlTapped control: UIControl) {
            guard let water = view.annotation as? WaterAnnotation else { return }
            parent.opened(water.pin.id)
        }
    }
}

// MARK: - A water's page

/// The Location section of a water's page: a small map and Directions, or
/// a plain "no location" line. Never a guessed pin.
struct WaterLocationSection: View {
    let water: Water
    let location: GeoLocation?

    var body: some View {
        Section {
            if let location {
                let coordinate = CLLocationCoordinate2D(latitude: location.lat, longitude: location.lon)
                Map(initialPosition: .region(MKCoordinateRegion(center: coordinate,
                                                                latitudinalMeters: location.isApproximate ? 12_000 : 6_000,
                                                                longitudinalMeters: location.isApproximate ? 12_000 : 6_000)),
                    interactionModes: []) {
                    Marker(water.name, systemImage: location.isApproximate ? "water.waves" : "drop.fill",
                           coordinate: coordinate)
                }
                .frame(height: 180)
                .listRowInsets(EdgeInsets())
                .accessibilityLabel(location.isApproximate
                                    ? "Map showing an approximate point on \(water.name)"
                                    : "Map showing \(water.name)")
                Text(LocationWording.summary(location))
                    .font(.subheadline)
                Button {
                    openDirections(to: coordinate)
                } label: {
                    Label(location.isApproximate ? "Directions to this point" : "Directions",
                          systemImage: "car")
                }
                .accessibilityHint("Opens Apple Maps")
            } else {
                Text(LocationWording.summary(nil))
                    .font(.subheadline)
                    .foregroundStyle(.secondaryText)
            }
        } header: {
            SectionHeader("Location")
        } footer: {
            if location != nil {
                Text(LocationWording.attribution).foregroundStyle(.secondaryText)
            }
        }
    }

    private func openDirections(to coordinate: CLLocationCoordinate2D) {
        let item = MKMapItem(placemark: MKPlacemark(coordinate: coordinate))
        item.name = water.name
        item.openInMaps(launchOptions: [MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving])
    }
}
