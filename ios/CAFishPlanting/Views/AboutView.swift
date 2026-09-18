import SwiftUI
import UserNotifications
import PlantingCore

struct AboutView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var showingPurchaseSheet = false

    var body: some View {
        List {
            Section("Full access") {
                if environment.purchases.isEntitled {
                    Label("Unlocked", systemImage: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                } else {
                    Text("Favouriting and browsing are free and unlimited. Unlock full access to get a notification on this device whenever a favourite's stocking schedule changes.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Button("Unlock full access") { showingPurchaseSheet = true }
                }
            }

            Section("What this app does") {
                Text("Favourite any California water for free and browse its full stocking history. With full access, also get a notification on this device when a favourite appears in the California Department of Fish and Wildlife's weekly stocking schedule.")
                Text("CDFW publishes the week a plant is scheduled, not the day, and all plants are subject to change. This app always shows a week, never a day, and says \"scheduled\" rather than \"stocked\".")
            }

            Section("How alerts work") {
                Text("Alerts are local notifications this app schedules on this device for full-access purchasers only — there is no server, no push service, and no account. iOS decides when the app is allowed to refresh in the background, and the schedule itself is weekly, so an alert arrives within the week a water is added, not the minute it is.")
                Text("Notification status: \(authorizationDescription)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Privacy") {
                Text("Data collected by this app: none. No analytics, no crash reporting, no third-party SDKs, no accounts. Favourites and alert history stay on this device. The only network request this app ever makes is a plain, cookie-free fetch of the published stocking snapshot.")
            }

            if let snapshot = environment.snapshot {
                Section("Data source and licence") {
                    Text(snapshot.attribution.text)
                    Text("This app is independent. It is not affiliated with or endorsed by the California Department of Fish and Wildlife.")
                    Link("CDFW Fish Planting Schedule", destination: snapshot.attribution.url)
                    Text(snapshot.licence.summary)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    ForEach(snapshot.licence.sources) { source in
                        Link(source.name, destination: source.termsURL)
                            .font(.footnote)
                    }
                }

                Section("This snapshot") {
                    LabeledContent("Current schedule week", value: snapshot.sourceWeek.label)
                    LabeledContent("Built", value: snapshot.generatedAt.formatted(date: .abbreviated, time: .shortened))
                    if let originLabel {
                        LabeledContent("Source", value: originLabel)
                    }
                }
            }
        }
        .navigationTitle("About")
        .sheet(isPresented: $showingPurchaseSheet) {
            PurchaseView()
        }
    }

    private var authorizationDescription: String {
        switch environment.notificationAuthorization {
        case .authorized, .provisional, .ephemeral: return "on"
        case .denied: return "off (change in Settings to receive alerts)"
        case .notDetermined: return "not yet asked — favourite a water to enable"
        @unknown default: return "unknown"
        }
    }

    private var originLabel: String? {
        switch environment.snapshotOrigin {
        case .bundled: return "Bundled with the app"
        case .stored: return "Refreshed on this device"
        case nil: return nil
        }
    }
}
