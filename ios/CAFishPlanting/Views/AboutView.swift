import SwiftUI
import UserNotifications
import PlantingCore

struct AboutView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(AppRouter.self) private var router
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var showingPurchaseSheet = false
    @State private var showingNotificationPriming = false
    @State private var showingStates = false

    var body: some View {
        List {
            Section {
                // Each unlocked state, named from the snapshot (DECISIONS 0049).
                ForEach(AboutCopy.unlockedLines(states: environment.snapshot?.states ?? [], entitled: environment.purchases.entitledStates), id: \.self) { line in
                    // Green on the seal only: green text on white is below 4.5:1.
                    Label {
                        Text(line)
                    } icon: {
                        Image(systemName: "checkmark.seal.fill").foregroundStyle(.green)
                    }
                }
                if !environment.purchases.isEntitled {
                    Text("Favoriting and browsing are free and unlimited. Full access adds an alert on this device when a favorite is newly on the schedule, and the Favorite waters widget for your Home Screen and Lock Screen.")
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                    Button("Unlock full access") { showingPurchaseSheet = true }
                }
                if (environment.snapshot?.states.count ?? 1) > 1 {
                    Text("Full access is a one-time purchase for each state. California's is the original purchase, and it stays what it was.")
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                    Button("States and full access") { showingStates = true }
                }
            } header: {
                SectionHeader("Full access")
            }

            Section {
                Text(AboutCopy.whatItDoes)
                Text(AboutCopy.california)
                if (environment.snapshot?.states.count ?? 1) > 1 {
                    Text(AboutCopy.otherStates)
                }
                Button("Show the introduction") { router.showingOnboarding = true }
            } header: {
                SectionHeader("What this app does")
            }

            Section {
                Text("Alerts are local notifications this app schedules on this device for full-access purchasers only — there is no server, no push service, and no account. \(AboutCopy.alertTiming)")
                Text("To stop one water's alerts and keep it as a favorite, touch and hold its alert and choose Mute this water, or use the switch on the water's page.")
                Text(AboutCopy.checking)
                Text("Notification status: \(authorizationDescription)")
                    .font(.footnote)
                    .foregroundStyle(.secondaryText)
                notificationAction
            } header: {
                SectionHeader("How alerts work")
            }

            Section {
                Link(AppStoreReviewLink.rowTitle, destination: AppStoreReviewLink.writeReviewURL)
                    .accessibilityHint("Opens the App Store")
                Text(AppStoreReviewLink.rowFootnote)
                    .font(.footnote)
                    .foregroundStyle(.secondaryText)
            } header: {
                SectionHeader("App Store")
            }

            Section {
                Text("Data collected by this app: none. No analytics, no crash reporting, no third-party SDKs, no accounts. Favorites and alert history stay on this device. The only network request this app ever makes is a plain, cookie-free fetch of the published stocking snapshot.")
            } header: {
                SectionHeader("Privacy")
            }

            if let snapshot = environment.snapshot {
                Section {
                    Text(AboutCopy.independence)
                }

                Section {
                    Text(snapshot.attribution.text)
                    Link("CDFW Fish Planting Schedule", destination: snapshot.attribution.url)
                    Text(snapshot.license.summary)
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                    ForEach(snapshot.license.sources) { source in
                        Link(source.name, destination: source.termsURL)
                            .font(.footnote)
                    }
                } header: {
                    SectionHeader("\(AboutCopy.dataSourceHeader(stateName: snapshot.state(code: "CA")?.name ?? "California"))")
                }

                ForEach(snapshot.states.filter { $0.code != "CA" }) { state in
                    Section {
                        Text(state.attribution.text)
                        Text(state.disclaimer)
                        Link(state.sourceName, destination: state.attribution.url)
                        Text(state.license.summary)
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                        ForEach(state.license.sources) { source in
                            Link(source.name, destination: source.termsURL)
                                .font(.footnote)
                        }
                    } header: {
                        SectionHeader("\(AboutCopy.dataSourceHeader(stateName: state.name))")
                    }
                }

                Section {
                    LabeledContent("Schedule week", value: snapshot.sourceWeek.label)
                    LabeledContent("Built", value: snapshot.generatedAt.formatted(date: .abbreviated, time: .shortened))
                    if let originLabel {
                        LabeledContent("Source", value: originLabel)
                    }
                    if let freshness = environment.freshness() {
                        Text(freshness.detail)
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                    }
                } header: {
                    SectionHeader("This snapshot")
                }
            }
        }
        .navigationTitle("About")
        .sheet(isPresented: $showingPurchaseSheet) {
            PurchaseView()
        }
        .sheet(isPresented: $showingStates) {
            StatesView()
        }
        .sheet(isPresented: $showingNotificationPriming) {
            NotificationPrimingView(copy: NotificationPrimingCopy(waterName: nil, isEntitled: environment.purchases.hasAnyAccess)) {
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
