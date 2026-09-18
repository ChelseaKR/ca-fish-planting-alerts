import SwiftUI

struct RootTabView: View {
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        if let error = environment.loadError {
            SnapshotUnavailableView(message: error)
        } else {
            TabView {
                NavigationStack { BrowseView() }
                    .tabItem { Label("Browse", systemImage: "map") }
                NavigationStack { FavoritesView() }
                    .tabItem { Label("Favourites", systemImage: "star") }
                NavigationStack { AboutView() }
                    .tabItem { Label("About", systemImage: "info.circle") }
            }
            .sheet(item: notificationExplainerBinding) { explainer in
                FirstFavouriteExplainerSheet(explainer: explainer)
            }
        }
    }

    /// `@Observable` doesn't expose `Binding` the way `@Published` did;
    /// this adapts `pendingNotificationExplainer` for `.sheet(item:)`.
    private var notificationExplainerBinding: Binding<FirstFavouriteExplainer?> {
        Binding(
            get: { environment.pendingNotificationExplainer },
            set: { if $0 == nil { environment.dismissNotificationExplainer() } }
        )
    }
}

/// Shown once, the moment someone favourites their first water — before any
/// system permission prompt — stating plainly what will and won't happen.
private struct FirstFavouriteExplainerSheet: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    let explainer: FirstFavouriteExplainer

    var body: some View {
        NotificationPrimingView(copy: explainer.copy) {
            await environment.confirmNotificationExplainer()
            dismiss()
        } notNow: {
            environment.dismissNotificationExplainer()
            dismiss()
        }
    }
}

/// The screen before the system notification prompt: what an alert is, how
/// often one comes, and that it is made on this iPhone. It scrolls, so at
/// the largest text sizes nothing is cut off, and the buttons stay at the
/// bottom.
struct NotificationPrimingView: View {
    let copy: NotificationPrimingCopy
    let allow: () async -> Void
    let notNow: () -> Void
    @State private var isAsking = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Image(systemName: "bell.badge")
                        .font(.largeTitle)
                        .foregroundStyle(.tint)
                        .accessibilityHidden(true)
                    Text(copy.headline)
                        .font(.title2.bold())
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    ForEach(copy.points) { point in
                        Label {
                            Text(point.text)
                                .fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: point.systemImage)
                                .foregroundStyle(.tint)
                                .accessibilityHidden(true)
                        }
                        .font(.body)
                    }
                    Text(copy.footnote)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 12) {
                    Button {
                        isAsking = true
                        Task {
                            await allow()
                            isAsking = false
                        }
                    } label: {
                        Text("Allow notifications").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(isAsking)
                    .accessibilityHint("Shows the system permission prompt")

                    Button("Not now", action: notNow)
                        .frame(maxWidth: .infinity)
                        .disabled(isAsking)
                }
                .padding()
                .background(.bar)
            }
            .navigationTitle("Stay in the loop")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.large])
    }
}

struct SnapshotUnavailableView: View {
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .accessibilityHidden(true)
            Text("Can't load the stocking schedule")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
        }
        .padding()
        .accessibilityElement(children: .combine)
    }
}
