import SwiftUI
import PlantingCore

struct BrowseView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var searchText = ""
    @State private var selectedRegion: String? // nil = all regions
    @State private var selectedCounty: String? // nil = all counties

    var body: some View {
        Group {
            if let snapshot = environment.snapshot {
                content(for: snapshot)
            } else {
                SnapshotUnavailableView(message: "No stocking schedule is available yet.")
            }
        }
        .navigationTitle("Waters")
        .searchable(text: $searchText, prompt: "Water or county")
    }

    @ViewBuilder
    private func content(for snapshot: Snapshot) -> some View {
        let thisWeekIDs = Set(snapshot.thisWeek.map(\.waterID))
        let waters = filtered(snapshot.waters, thisWeekIDs: thisWeekIDs)
        let freshness = environment.freshness()
        List {
            Section {
                Picker("Region", selection: $selectedRegion) {
                    Text("All regions").tag(String?.none)
                    ForEach(snapshot.regionsWithWaters) { region in
                        Text(region.name).tag(String?.some(region.code))
                    }
                }
                .pickerStyle(.menu)
                // Only the counties that have a water in the chosen region.
                Picker("County", selection: $selectedCounty) {
                    Text("All counties").tag(String?.none)
                    ForEach(WaterSearch.counties(of: regionWaters(snapshot)), id: \.self) { county in
                        Text(county).tag(String?.some(county))
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: selectedRegion) { selectedCounty = nil }
                if let freshness {
                    FreshnessRow(freshness: freshness)
                }
            }
            Section {
                if waters.isEmpty {
                    ContentUnavailableView.search(text: searchText)
                } else {
                    ForEach(waters) { water in
                        NavigationLink(value: water.id) {
                            WaterRow(water: water, listed: thisWeekIDs.contains(water.id) ? freshness : nil)
                        }
                    }
                }
            }
        }
        .navigationDestination(for: Water.ID.self) { id in
            if let water = snapshot.water(id: id) {
                WaterDetailView(water: water, sourceWeek: snapshot.sourceWeek)
            }
        }
        // Pull down to check for a newer schedule now, past the throttle.
        // The freshness row above says how it went.
        .refreshable { await environment.refreshNow() }
    }

    private func regionWaters(_ snapshot: Snapshot) -> [Water] {
        guard let selectedRegion else { return snapshot.waters }
        return snapshot.waters(inRegion: selectedRegion)
    }

    /// Region, then county, then the search text: a water's name, any name
    /// CDFW has used for it, or its county (`WaterSearch`).
    private func filtered(_ waters: [Water], thisWeekIDs: Set<Water.ID>) -> [Water] {
        var result = waters
        if let selectedRegion { result = result.filter { $0.region == selectedRegion } }
        return WaterSearch(text: searchText, county: selectedCounty).filter(result)
    }
}

struct WaterRow: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let water: Water
    /// Set when the water is listed in the snapshot's week. The tag reads
    /// "This week" only while that week is current; once it has ended, it
    /// shows the week instead (`SnapshotFreshness.listedBadge`).
    let listed: SnapshotFreshness?

    var body: some View {
        // At the accessibility text sizes the tag goes under the name, so
        // neither is squeezed into a sliver or cut off.
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout())
        layout {
            VStack(alignment: .leading, spacing: 2) {
                Text(water.name).font(.body)
                Text(water.countyLabel)
                    .font(.caption)
                    .foregroundStyle(.secondaryText)
            }
            if !dynamicTypeSize.isAccessibilitySize {
                Spacer(minLength: 8)
            }
            if let listed {
                // Primary text on a tinted capsule: the tint alone is below
                // 4.5:1 on its own pale background at this size.
                Text(listed.listedBadge)
                    .font(.caption2.weight(.semibold))
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(.tint.opacity(0.18), in: Capsule())
                    .foregroundStyle(.primary)
                    .fixedSize()
                    .accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(listed.map { "\(water.name), \(water.countyLabel), \($0.listedPhrase)" } ?? "\(water.name), \(water.countyLabel)")
    }
}

/// The offline-first promise made visible: which week's schedule the app
/// is showing, whether that week is over, and how the last check for a newer
/// one went. A failed or stale check is said plainly and the last good
/// schedule stays on screen, labeled with its week; it is never replaced by
/// "nothing listed".
struct FreshnessRow: View {
    let freshness: SnapshotFreshness

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(freshness.headline)
                .font(.footnote.weight(.semibold))
            Text(freshness.summary)
                .font(.caption)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if freshness.isChecking {
                    ProgressView()
                        .controlSize(.mini)
                        .accessibilityHidden(true)
                } else if freshness.needsAttention {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                        .accessibilityHidden(true)
                }
                Text(freshness.detail)
            }
            .font(.caption2)
            .foregroundStyle(freshness.needsAttention ? Color.primary : Color.secondaryText)
            if let checked = freshness.lastSuccessfulCheck {
                let label = freshness.checkFailed ? "Last successful check" : "Last checked"
                Text("\(label) \(checked.formatted(.relative(presentation: .named)))")
                    .font(.caption2)
                    .foregroundStyle(.secondaryText)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
