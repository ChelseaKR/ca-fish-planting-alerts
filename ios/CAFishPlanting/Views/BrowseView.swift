import SwiftUI
import PlantingCore

struct BrowseView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    /// Set in a split view (iPad, Mac): a tapped row selects its water for
    /// the detail column instead of pushing it.
    var selection: Binding<Water.ID?>? = nil
    @State private var searchText = ""
    @State private var selectedRegion: String? // nil = all regions
    @State private var selectedCounty: String? // nil = all counties
    @State private var refreshFeedback: RefreshFeedback?

    var body: some View {
        Group {
            if let snapshot = environment.snapshot {
                content(for: snapshot)
            } else {
                SnapshotUnavailableView(message: "No stocking schedule is available yet.")
            }
        }
        .navigationTitle("Waters")
        .searchable(text: $searchText, placement: .splitAware(selection), prompt: "Water or county")
    }

    @ViewBuilder
    private func content(for snapshot: Snapshot) -> some View {
        let thisWeekIDs = Set(snapshot.thisWeek.map(\.waterID))
        let waters = filtered(snapshot.waters, thisWeekIDs: thisWeekIDs)
        let freshness = environment.freshness()
        SelectableList(selection: selection) {
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
        .waterDestinations(in: snapshot, enabled: selection == nil)
        .toolbar { RefreshToolbarButton(shown: horizontalSizeClass == .regular) { refreshFeedback = RefreshFeedback(await environment.refreshNow()) } }
        // Pull down to check for a newer schedule now, past the throttle.
        // The freshness row above says how it went, and a tap says it too.
        .refreshable { refreshFeedback = RefreshFeedback(await environment.refreshNow()) }
        .sensoryFeedback(trigger: refreshFeedback) { _, feedback in feedback?.haptic }
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
    /// A favorite whose alerts are off (`MutedWaters`). Shown in Favorites.
    var alertsMuted = false

    var body: some View {
        // At the accessibility text sizes the tag goes under the name, so
        // neither is squeezed into a sliver or cut off.
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 6))
            : AnyLayout(HStackLayout())
        layout {
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(water.name).font(.body)
                    if alertsMuted {
                        Image(systemName: "bell.slash")
                            .font(.caption)
                            .foregroundStyle(.secondaryText)
                            .accessibilityHidden(true)
                    }
                }
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
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        var parts = [water.name, water.countyLabel]
        if let listed { parts.append(listed.listedPhrase) }
        if alertsMuted { parts.append("alerts muted") }
        return parts.joined(separator: ", ")
    }
}

/// A `List` that keeps a selection when it has one (a split view's
/// sidebar), and a plain one otherwise (a navigation stack).
struct SelectableList<Content: View>: View {
    let selection: Binding<Water.ID?>?
    @ViewBuilder let content: () -> Content

    var body: some View {
        if let selection {
            List(selection: selection, content: content)
        } else {
            List(content: content)
        }
    }
}

extension SearchFieldPlacement {
    /// In a split view's list column, a search field that always shows at
    /// the top of the list. Left to itself (`.automatic`, or `.sidebar`),
    /// iPadOS 26 shows no search field there at all until it is revealed,
    /// which UI tests measured on 2026-10-11. The stack layout keeps the
    /// system's placement.
    static func splitAware(_ selection: Binding<Water.ID?>?) -> SearchFieldPlacement {
        selection == nil ? .automatic : .navigationBarDrawer(displayMode: .always)
    }
}

extension View {
    /// A water's page pushed onto the stack, in the stack layout only. In a
    /// split view the detail column shows the selection instead.
    @ViewBuilder
    func waterDestinations(in snapshot: Snapshot, enabled: Bool) -> some View {
        if enabled {
            navigationDestination(for: Water.ID.self) { id in
                if let water = snapshot.water(id: id) {
                    WaterDetailView(water: water, sourceWeek: snapshot.sourceWeek)
                }
            }
        } else {
            self
        }
    }
}

/// A Refresh button with Command-R, at regular width (iPad, Mac), where a
/// pointer or a keyboard makes pull to refresh awkward. It runs the same
/// unthrottled check as pull to refresh.
struct RefreshToolbarButton: ToolbarContent {
    let shown: Bool
    let refresh: () async -> Void
    @State private var isRefreshing = false

    var body: some ToolbarContent {
        if shown {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    isRefreshing = true
                    Task {
                        await refresh()
                        isRefreshing = false
                    }
                } label: {
                    Label("Check for a newer schedule", systemImage: "arrow.clockwise")
                }
                .disabled(isRefreshing)
                .keyboardShortcut("r", modifiers: .command)
            }
        }
    }
}

/// What a pull to refresh ended in, for its haptic: a success tap when the
/// check reached the schedule (new or unchanged), a warning when it failed.
/// Each refresh is a new value, so two in a row both play.
struct RefreshFeedback: Equatable {
    let failed: Bool
    private let id = UUID()

    init(_ outcome: RefreshOutcome) {
        if case .failed = outcome { failed = true } else { failed = false }
    }

    var haptic: SensoryFeedback { failed ? .warning : .success }
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
