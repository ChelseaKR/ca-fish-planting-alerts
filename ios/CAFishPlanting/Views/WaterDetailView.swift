import SwiftUI
import PlantingCore

struct WaterDetailView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let water: Water
    let sourceWeek: Week

    private var isFavourite: Bool { environment.isFavourite(water.id) }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(water.countyLabel)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    lastScheduledLine
                    if !water.speciesSeen.isEmpty {
                        Text("Species seen: \(water.speciesSeen.joined(separator: ", "))")
                            .font(.subheadline)
                    }
                }
            }

            Section("Links") {
                Link(destination: water.cdfwMapURL) {
                    Label("CDFW schedule for this water", systemImage: "link")
                }
                if let siteURL = SnapshotEndpoint.siteWaterURL(slug: water.slug) {
                    Link(destination: siteURL) {
                        Label("Full history on the site", systemImage: "safari")
                    }
                }
            }

            Section("Schedule history") {
                if water.plants.isEmpty {
                    Text("No plants observed yet for this water.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(water.years, id: \.self) { year in
                        DisclosureGroup("\(String(year))") {
                            ForEach(water.plants(inYear: year).reversed(), id: \.self) { plant in
                                PlantRow(plant: plant)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(water.name)
        .navigationBarTitleDisplayMode(.large)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    if reduceMotion {
                        environment.toggleFavourite(water)
                    } else {
                        withAnimation(.snappy) { environment.toggleFavourite(water) }
                    }
                } label: {
                    Image(systemName: isFavourite ? "star.fill" : "star")
                }
                .accessibilityLabel(isFavourite ? "Remove \(water.name) from favourites" : "Add \(water.name) to favourites")
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                ShareLink(item: shareText, subject: Text(water.name)) {
                    Image(systemName: "square.and.arrow.up")
                }
                .accessibilityLabel("Share \(water.name)")
            }
        }
    }

    /// The real, grounded share message — see `ShareContent` in
    /// `PlantingCore` for what it does and doesn't claim.
    private var shareText: String {
        ShareContent.message(for: water, siteURL: SnapshotEndpoint.siteWaterURL(slug: water.slug), sourceWeek: sourceWeek)
    }

    /// "Last scheduled for the week of …": CDFW publishes scheduled plants
    /// at week-of granularity, never a confirmed plant or a day
    /// (`ScheduleWording`, shared with the share sheet).
    private var lastScheduledLine: some View {
        Text(ScheduleWording.lastScheduledLine(for: water, sourceWeek: sourceWeek))
            .font(.headline)
            .foregroundStyle(water.lastListedWeek == nil ? HierarchicalShapeStyle.secondary : .primary)
    }
}

private struct PlantRow: View {
    let plant: Plant

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                // Never a day — the pipeline's own label, verbatim.
                Text(plant.week.label)
                Text(plant.species).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if plant.status == .removed {
                Text("Schedule changed")
                    .font(.caption2)
                    .foregroundStyle(.orange)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(plant.status == .removed
            ? "\(plant.week.label), \(plant.species), later removed from the schedule"
            : "\(plant.week.label), \(plant.species)")
    }
}
