import SwiftUI
import PlantingCore

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
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                Image(systemName: "bell.badge")
                    .font(.largeTitle)
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)
                Text(explainer.sentence)
                    .font(.body)
                Text("You can change this any time in Settings.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    Task {
                        await environment.confirmNotificationExplainer()
                        dismiss()
                    }
                } label: {
                    Text("Allow notifications").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .accessibilityHint("Shows the system permission prompt")

                Button("Not now") {
                    environment.dismissNotificationExplainer()
                    dismiss()
                }
                .buttonStyle(.plain)
                .frame(maxWidth: .infinity)
            }
            .padding()
            .navigationTitle("Stay in the loop")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium])
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
