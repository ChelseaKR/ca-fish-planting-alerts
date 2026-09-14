import SwiftUI
import PlantingCore

struct FavoritesView: View {
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        Group {
            if let snapshot = environment.snapshot {
                let waters = environment.favourites.ids.compactMap(snapshot.water(id:))
                if waters.isEmpty {
                    ContentUnavailableView("No favourites yet", systemImage: "star",
                        description: Text("Star a water in Browse to get a local alert when it appears in a new week's schedule."))
                } else {
                    List(waters) { water in
                        NavigationLink(value: water.id) {
                            WaterRow(water: water, scheduledThisWeek: snapshot.thisWeek.contains { $0.waterID == water.id })
                        }
                    }
                    .navigationDestination(for: Water.ID.self) { id in
                        if let water = snapshot.water(id: id) { WaterDetailView(water: water) }
                    }
                }
            } else {
                SnapshotUnavailableView(message: "No stocking schedule is available yet.")
            }
        }
        .navigationTitle("Favourites")
    }
}
