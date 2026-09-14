import SwiftUI
import PlantingCore

struct BrowseView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var searchText = ""
    @State private var selectedRegion: String? // nil = all regions

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
        List {
            Section {
                Picker("Region", selection: $selectedRegion) {
                    Text("All regions").tag(String?.none)
                    ForEach(snapshot.regionsWithWaters) { region in
                        Text(region.name).tag(String?.some(region.code))
                    }
                }
                .pickerStyle(.menu)
                FreshnessRow(snapshot: snapshot, meta: environment.refreshMeta)
            }
            Section {
                if waters.isEmpty {
                    ContentUnavailableView.search(text: searchText)
                } else {
                    ForEach(waters) { water in
                        NavigationLink(value: water.id) {
                            WaterRow(water: water, scheduledThisWeek: thisWeekIDs.contains(water.id))
                        }
                    }
                }
            }
        }
        .navigationDestination(for: Water.ID.self) { id in
            if let water = snapshot.water(id: id) {
                WaterDetailView(water: water)
            }
        }
    }

    private func filtered(_ waters: [Water], thisWeekIDs: Set<Water.ID>) -> [Water] {
        var result = waters
        if let selectedRegion { result = result.filter { $0.region == selectedRegion } }
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !query.isEmpty {
            result = result.filter { water in
                water.name.localizedCaseInsensitiveContains(query)
                    || water.counties.contains { $0.localizedCaseInsensitiveContains(query) }
            }
        }
        return result.sorted { $0.name.localizedCompare($1.name) == .orderedAscending }
    }
}

struct WaterRow: View {
    let water: Water
    let scheduledThisWeek: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(water.name).font(.body)
                Text(water.countyLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if scheduledThisWeek {
                Text("This week")
                    .font(.caption2.weight(.semibold))
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(.tint.opacity(0.15), in: Capsule())
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(scheduledThisWeek ? "\(water.name), \(water.countyLabel), scheduled this week" : "\(water.name), \(water.countyLabel)")
    }
}

/// The offline-first promise made visible: which snapshot the app is
/// showing and how the last refresh went, never hidden behind "loading".
struct FreshnessRow: View {
    let snapshot: Snapshot
    let meta: SnapshotMeta?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Current schedule: \(snapshot.sourceWeek.label)")
                .font(.footnote.weight(.medium))
            if let outcome = meta?.lastOutcome, let attempt = meta?.lastAttemptAt {
                Text("Last refresh: \(outcome) — \(attempt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                Text("Not refreshed on this device yet — showing the schedule bundled with the app.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
