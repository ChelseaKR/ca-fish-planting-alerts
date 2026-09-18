import SwiftUI
import PlantingCore

struct FavoritesView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var search = WaterSearch()

    var body: some View {
        Group {
            if let snapshot = environment.snapshot {
                content(for: snapshot)
            } else {
                SnapshotUnavailableView(message: "No stocking schedule is available yet.")
            }
        }
        .navigationTitle("Favourites")
    }

    @ViewBuilder
    private func content(for snapshot: Snapshot) -> some View {
        let ids = environment.favourites.ids
        let present = ids.compactMap(snapshot.water(id:))
        // Favorites the snapshot no longer has (a water CDFW dropped). Said
        // plainly, never folded into "no favorites".
        let missing = ids.filter { snapshot.water(id: $0) == nil }
        if present.isEmpty && missing.isEmpty {
            ContentUnavailableView {
                Label("No favorite waters yet", systemImage: "star")
            } description: {
                Text(emptyDescription)
            }
        } else {
            list(snapshot: snapshot, present: present, missing: missing)
        }
    }

    private var emptyDescription: String {
        let alerts = environment.purchases.isEntitled
            ? "You'll get an alert when one appears in a new week's schedule."
            : "With full access, you also get an alert when one appears in a new week's schedule."
        return "Tap the star on any water in Browse to keep its schedule here. \(alerts)"
    }

    private func list(snapshot: Snapshot, present: [Water], missing: [Water.ID]) -> some View {
        let thisWeekIDs = Set(snapshot.thisWeek.map(\.waterID))
        let freshness = environment.freshness()
        let counties = WaterSearch.counties(of: present)
        // A county chosen earlier that no favorite is in any more.
        let activeSearch = WaterSearch(text: search.text, county: search.county.flatMap { counties.contains($0) ? $0 : nil })
        let shown = activeSearch.filter(present)
        return List {
            if let freshness {
                Section {
                    FreshnessRow(freshness: freshness)
                }
            }
            Section {
                if shown.isEmpty && !present.isEmpty {
                    noMatches(activeSearch)
                } else {
                    ForEach(shown) { water in
                        NavigationLink(value: water.id) {
                            WaterRow(water: water, listed: thisWeekIDs.contains(water.id) ? freshness : nil)
                        }
                        .swipeActions {
                            Button(role: .destructive) {
                                environment.toggleFavourite(water)
                            } label: {
                                Label("Remove", systemImage: "star.slash")
                            }
                        }
                    }
                }
            } header: {
                if activeSearch.county != nil || !activeSearch.text.isEmpty {
                    Text(shown.count == 1 ? "1 of \(present.count) favorites" : "\(shown.count) of \(present.count) favorites")
                }
            }
            if !missing.isEmpty && activeSearch.isEmpty {
                Section {
                    ForEach(missing, id: \.self) { id in
                        MissingFavoriteRow(id: id)
                            .swipeActions {
                                Button(role: .destructive) {
                                    environment.removeFavorite(id)
                                } label: {
                                    Label("Remove", systemImage: "star.slash")
                                }
                            }
                    }
                } header: {
                    Text("Not in this schedule")
                } footer: {
                    Text("This schedule no longer lists these favorites. CDFW may have renamed or dropped the water. Swipe to remove one.")
                }
            }
        }
        .navigationDestination(for: Water.ID.self) { id in
            if let water = snapshot.water(id: id) { WaterDetailView(water: water) }
        }
        .searchable(text: $search.text, prompt: "Favorite water or county")
        .toolbar {
            if counties.count > 1 {
                ToolbarItem(placement: .topBarTrailing) {
                    countyMenu(counties, selection: activeSearch.county)
                }
            }
        }
        .refreshable { await environment.refreshNow() }
    }

    private func countyMenu(_ counties: [String], selection: String?) -> some View {
        Menu {
            Picker("County", selection: $search.county) {
                Text("All counties").tag(String?.none)
                ForEach(counties, id: \.self) { county in
                    Text(county).tag(String?.some(county))
                }
            }
        } label: {
            Label(selection.map { "County: \($0)" } ?? "Filter by county",
                  systemImage: selection == nil ? "line.3.horizontal.decrease.circle" : "line.3.horizontal.decrease.circle.fill")
        }
    }

    @ViewBuilder
    private func noMatches(_ activeSearch: WaterSearch) -> some View {
        if activeSearch.text.trimmingCharacters(in: .whitespaces).isEmpty, let county = activeSearch.county {
            ContentUnavailableView("No favorites in \(county)", systemImage: "line.3.horizontal.decrease.circle",
                                   description: Text("Choose All counties to see every favorite."))
        } else {
            ContentUnavailableView.search(text: activeSearch.text)
        }
    }
}

/// A favorite the snapshot doesn't have. Its name isn't known any more, so
/// it shows CDFW's own number for the water rather than a guess.
private struct MissingFavoriteRow: View {
    let id: Water.ID

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
            Text("No longer in the schedule data")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private var title: String {
        let prefix = "cdfw-"
        guard id.hasPrefix(prefix) else { return "A favorite water (\(id))" }
        return "CDFW water \(id.dropFirst(prefix.count))"
    }
}
