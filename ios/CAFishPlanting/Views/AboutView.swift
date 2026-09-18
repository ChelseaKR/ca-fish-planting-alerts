import SwiftUI
import UserNotifications
import PlantingCore

struct AboutView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var showingPurchaseSheet = false
    @State private var showingNotificationPriming = false

    var body: some View {
        List {
            Section("Full access") {
                if environment.purchases.isEntitled {
                    // Green on the seal only: green text on white is below 4.5:1.
                    Label {
                        Text("Unlocked")
                    } icon: {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(.green)
                    }
                } else {
                    Text("Favouriting and browsing are free and unlimited. Unlock full access to get a notification on this device whenever a favourite's stocking schedule changes.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Button("Unlock full access") { showingPurchaseSheet = true }
                }
            }

            Section("What this app does") {
                Text("Favourite any California water for free and browse its full schedule history. With full access, also get a notification on this device when a favourite appears in the California Department of Fish and Wildlife's weekly stocking schedule.")
                Text("CDFW publishes the week a plant is scheduled, not the day, and all plants are subject to change. This app always shows a week, never a day, and says \"scheduled\" rather than \"stocked\".")
            }

            Section("How alerts work") {
                Text("Alerts are local notifications this app schedules on this device for full-access purchasers only — there is no server, no push service, and no account. iOS decides when the app is allowed to refresh in the background, and the schedule itself is weekly, so an alert arrives within the week a water is added, not the minute it is.")
                Text("The app also checks for a newer schedule when you open it, at most every few hours. If it can't, it says so and keeps showing the last schedule it has, with that schedule's week.")
                Text("Notification status: \(authorizationDescription)")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                notificationAction
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
                    LabeledContent("Schedule week", value: snapshot.sourceWeek.label)
                    LabeledContent("Built", value: snapshot.generatedAt.formatted(date: .abbreviated, time: .shortened))
                    if let originLabel {
                        LabeledContent("Source", value: originLabel)
                    }
                    if let freshness = environment.freshness() {
                        Text(freshness.detail)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("About")
        .sheet(isPresented: $showingPurchaseSheet) {
            PurchaseView()
        }
        .sheet(isPresented: $showingNotificationPriming) {
            NotificationPrimingView(copy: NotificationPrimingCopy(waterName: nil, isEntitled: environment.purchases.isEntitled)) {
                await environment.requestNotificationAuthorization()
                showingNotificationPriming = false
            } notNow: {
                showingNotificationPriming = false
            }
        }
        // The setting can change in Settings while the app is away.
        .task { await environment.refreshNotificationAuthorization() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                Task { await environment.refreshNotificationAuthorization() }
            }
        }
    }

    /// A way forward from each state: ask (with the priming screen first)
    /// while iOS hasn't asked, or go to Settings once notifications are off.
    /// Once they're off, the system prompt never shows again, so a button
    /// that asked would do nothing.
    @ViewBuilder
    private var notificationAction: some View {
        switch environment.notificationAuthorization {
        case .notDetermined:
            Button("Turn on notifications") { showingNotificationPriming = true }
                .accessibilityHint("Explains alerts, then shows the system permission prompt")
        case .denied:
            Button("Open notification settings") {
                if let url = URL(string: UIApplication.openNotificationSettingsURLString) {
                    openURL(url)
                }
            }
            .accessibilityHint("Opens this app's notification settings")
        default:
            EmptyView()
        }
    }

    private var authorizationDescription: String {
        switch environment.notificationAuthorization {
        case .authorized, .provisional, .ephemeral: return "on"
        case .denied: return "off (change in Settings to receive alerts)"
        case .notDetermined: return "not yet asked"
        @unknown default: return "unknown"
        }
    }

    private var originLabel: String? {
        switch environment.snapshotOrigin {
        case .bundled: return "Bundled with the app"
        case .stored: return "Downloaded on this device"
        case nil: return nil
        }
    }
}
