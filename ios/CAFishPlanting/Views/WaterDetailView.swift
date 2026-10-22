import SwiftUI
import PlantingCore

struct WaterDetailView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let water: Water
    /// The water's own state's current week (`Snapshot.currentWeek(for:)`).
    let sourceWeek: Week
    @State private var showingPurchase = false

    private var state: StateInfo? { environment.snapshot?.state(of: water) }

    private var isFavorite: Bool { environment.isFavorite(water.id) }
    private var alertsMuted: Bool { environment.alertsMuted(for: water.id) }

    /// The alerts switch shows for a favorite once alerts can come (full
    /// access), and for a muted one whatever the purchase, so a mute can
    /// always be undone.
    private var showsAlertsSwitch: Bool {
        isFavorite && (environment.purchases.isEntitled(state: water.state) || alertsMuted)
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
                    if let note = water.monthsNote {
                        Text("\(water.agencyShortName) also lists this water by month: \(note). It writes each month as one letter, so \"M\" may be March or May, and says the dates vary through those months.")
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                    }
                    if let note = state?.recencyNote {
                        Text(note)
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                    }
                }
            }

            if isFavorite && !environment.purchases.isEntitled(state: water.state) && !alertsMuted, let state {
                Section {
                    Button("Unlock alerts for \(state.name)") { showingPurchase = true }
                        .accessibilityIdentifier("unlock-state")
                } footer: {
                    Text("Alerts and the widget for \(state.name) waters are a one-time purchase. Browsing and history stay free.")
                        .foregroundStyle(.secondaryText)
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
                         : water.state == "CA"
                         ? "An alert on this device when \(water.name) is newly on CDFW's weekly schedule."
                         : water.semantics == .plan
                         ? "An alert on this device when \(water.name) is in \(water.agencyShortName)'s spring plan, and a reminder when each planned period begins."
                         : water.semantics == .report
                         ? "An alert on this device when \(water.name) is new in \(water.agencyShortName)'s stocking report."
                         : "An alert on this device when \(water.name) is newly on \(water.agencyShortName)'s schedule.")
                        .foregroundStyle(.secondaryText)
                }
            }

            Section {
                Link(destination: water.cdfwMapURL) {
                    Label(water.state == "CA" ? "CDFW schedule for this water" : "\(water.agencyShortName) source for this water", systemImage: "link")
                }
                if let siteURL = SnapshotEndpoint.siteWaterURL(for: water) {
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
                SectionHeader(water.semantics == .report ? "Stocking history" : water.semantics == .plan ? "Stocking plans" : "Schedule history")
            }

            if water.state != "CA", let state {
                Section {
                    Text(state.attribution.text)
                    Text(state.disclaimer)
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                } header: {
                    SectionHeader("Source")
                }
            }
        }
        .sheet(isPresented: $showingPurchase) { PurchaseView(state: water.state) }
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
        ShareContent.message(for: water, siteURL: SnapshotEndpoint.siteWaterURL(for: water), sourceWeek: sourceWeek)
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
                // The pipeline's own label, verbatim: a week is never shown
                // as a day, and a month says its day isn't set.
                Text(plant.week.precision == .month ? "\(plant.week.label), day not set"
                     : plant.week.precision == .approximate ? "Planned for \(plant.week.label)"
                     : plant.week.label)
                Text(plant.count.map { "\(plant.species), \($0.formatted()) fish" } ?? plant.species)
                    .font(.caption).foregroundStyle(.secondaryText)
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
