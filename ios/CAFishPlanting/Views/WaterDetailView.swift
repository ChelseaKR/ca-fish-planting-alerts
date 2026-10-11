import SwiftUI
import PlantingCore

struct WaterDetailView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let water: Water
    let sourceWeek: Week

    private var isFavorite: Bool { environment.isFavorite(water.id) }
    private var alertsMuted: Bool { environment.alertsMuted(for: water.id) }

    /// The alerts switch shows for a favorite once alerts can come (full
    /// access), and for a muted one whatever the purchase, so a mute can
    /// always be undone.
    private var showsAlertsSwitch: Bool {
        isFavorite && (environment.purchases.isEntitled || alertsMuted)
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text(water.countyLabel)
                        .font(.subheadline)
                        .foregroundStyle(.secondaryText)
                    lastScheduledLine
                    if !water.speciesSeen.isEmpty {
                        Text("Species seen: \(water.speciesSeen.joined(separator: ", "))")
                            .font(.subheadline)
                    }
                }
            }

            if showsAlertsSwitch {
                Section {
                    Toggle(isOn: Binding(get: { !alertsMuted },
                                         set: { environment.setAlertsMuted(!$0, for: water.id) })) {
                        Label("Alerts for this water", systemImage: alertsMuted ? "bell.slash" : "bell")
                    }
                    .sensoryFeedback(.selection, trigger: alertsMuted)
                } header: {
                    SectionHeader("Alerts")
                } footer: {
                    Text(alertsMuted
                         ? "Muted. \(water.name) stays in Favorites and the widget, with no alert when it is newly on the schedule."
                         : "An alert on this device when \(water.name) is newly on CDFW's weekly schedule.")
                        .foregroundStyle(.secondaryText)
                }
            }

            Section {
                Link(destination: water.cdfwMapURL) {
                    Label("CDFW schedule for this water", systemImage: "link")
                }
                if let siteURL = SnapshotEndpoint.siteWaterURL(slug: water.slug) {
                    Link(destination: siteURL) {
                        Label("Full history on the site", systemImage: "safari")
                    }
                }
            } header: {
                SectionHeader("Links")
            }

            Section {
                if water.plants.isEmpty {
                    Text("No plants observed yet for this water.")
                        .foregroundStyle(.secondaryText)
                } else {
                    ForEach(water.years, id: \.self) { year in
                        DisclosureGroup("\(String(year))") {
                            ForEach(water.plants(inYear: year).reversed(), id: \.self) { plant in
                                PlantRow(plant: plant)
                            }
                        }
                    }
                }
            } header: {
                SectionHeader("Schedule history")
            }
        }
        .navigationTitle(water.name)
        .navigationBarTitleDisplayMode(.large)
        // Opened, from an alert or anywhere else: its alerts in Notification
        // Center have been read.
        .task(id: water.id) { await environment.clearDeliveredAlerts(for: water.id) }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    if reduceMotion {
                        environment.toggleFavorite(water)
                    } else {
                        withAnimation(.snappy) { environment.toggleFavorite(water) }
                    }
                } label: {
                    Image(systemName: isFavorite ? "star.fill" : "star")
                }
                // A firmer tap for adding a favorite than for removing one.
                // iOS skips it when system haptics are off.
                .sensoryFeedback(trigger: isFavorite) { _, nowFavorite in
                    nowFavorite ? .success : .selection
                }
                .accessibilityLabel(isFavorite ? "Remove \(water.name) from favorites" : "Add \(water.name) to favorites")
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
            .foregroundStyle(water.lastListedWeek == nil ? Color.secondaryText : Color.primary)
    }
}

private struct PlantRow: View {
    let plant: Plant

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                // Never a day — the pipeline's own label, verbatim.
                Text(plant.week.label)
                Text(plant.species).font(.caption).foregroundStyle(.secondaryText)
            }
            Spacer()
            if plant.status == .removed {
                // Words plus a symbol, in a color that keeps 4.5:1 in light
                // and dark mode; orange text on white doesn't.
                Label("Schedule changed", systemImage: "arrow.uturn.backward.circle")
                    .font(.caption2)
                    .foregroundStyle(.secondaryText)
                    .labelStyle(.titleAndIcon)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(plant.status == .removed
            ? "\(plant.week.label), \(plant.species), later removed from the schedule"
            : "\(plant.week.label), \(plant.species)")
    }
}
