import SwiftUI
import PlantingCore

/// The watch app's one screen: the favorites, each with where it stands in
/// the schedule's week. Every line names its week, as on the phone.
struct WatchRootView: View {
    @Environment(WatchModel.self) private var model
    @State private var path: [String] = []

    var body: some View {
        #if DEBUG
        if ProcessInfo.processInfo.environment["TT_WATCH_GALLERY"] == "1" {
            ComplicationGallery()
        } else {
            stack
        }
        #else
        stack
        #endif
    }

    private var stack: some View {
        NavigationStack(path: $path) {
            content
                .navigationTitle("Trout Truck")
                .navigationDestination(for: String.self) { id in
                    if let digest = model.digest, let favorite = digest.favorites.first(where: { $0.id == id }) {
                        FavoriteDetailView(digest: digest, favorite: favorite)
                    } else {
                        // An alert for a water the phone hasn't sent:
                        // said plainly, never a blank page.
                        MessageView(symbol: "fish", message: "Open this water in Trout Truck on your iPhone.")
                    }
                }
        }
        // A tap on an alert can set this before the view exists (a cold
        // launch), so read it on appear too, not only on change.
        .onAppear { openRequestedWater() }
        .onChange(of: model.openWaterID) { _, _ in openRequestedWater() }
    }

    private func openRequestedWater() {
        guard let id = model.openWaterID else { return }
        path = [id]
        model.openWaterID = nil
    }

    @ViewBuilder
    private var content: some View {
        TimelineView(.everyMinute) { context in
            if let digest = model.digest {
                if digest.locked {
                    LockedView(digest: digest)
                } else if digest.favorites.isEmpty, let other = digest.otherStatesLine {
                    MessageView(symbol: "lock.fill", message: other, footnote: digest.subheadline(at: context.date))
                } else if digest.favorites.isEmpty {
                    MessageView(symbol: "star",
                                message: digest.missingFavorites > 0
                                    ? "Your favorite waters aren't in this week's schedule data. Open Trout Truck on your iPhone to check them."
                                    : "Star a water in Trout Truck on your iPhone to see its schedule here.",
                                footnote: digest.subheadline(at: context.date))
                } else {
                    FavoritesList(digest: digest, now: context.date)
                }
            } else {
                MessageView(symbol: "iphone", message: WidgetDigest.watchNoDigestMessage)
            }
        }
    }
}

private struct FavoritesList: View {
    let digest: WidgetDigest
    let now: Date

    var body: some View {
        List {
            Section {
                ForEach(digest.favoritesByStatus) { favorite in
                    NavigationLink(value: favorite.id) {
                        FavoriteRow(digest: digest, favorite: favorite, now: now)
                    }
                }
            } header: {
                Text(digest.headline(at: now))
                    .textCase(nil)
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(digest.subheadline(at: now))
                    if let other = digest.otherStatesLine {
                        Text(other)
                    }
                    if digest.missingFavorites > 0 {
                        Text(digest.missingFavorites == 1
                             ? "1 favorite isn't in this schedule. Open Trout Truck on your iPhone to check it."
                             : "\(digest.missingFavorites) favorites aren't in this schedule. Open Trout Truck on your iPhone to check them.")
                    }
                }
            }
        }
    }
}

private struct FavoriteRow: View {
    let digest: WidgetDigest
    let favorite: WidgetDigest.Favorite
    let now: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(favorite.name)
                .font(.headline)
                .lineLimit(2)
            if case .scheduledThisWeek = digest.status(of: favorite, at: now) {
                Text(favorite.isReport ? ReportWording.stockedThisWeekTag : "This week")
                    .font(.caption2.weight(.semibold))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(Capsule().fill(Color.accentColor.opacity(0.3)))
            } else {
                Text(digest.shortStatus(of: favorite, at: now))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(favorite.name): \(digest.statusLine(of: favorite, at: now))")
    }
}

struct FavoriteDetailView: View {
    let digest: WidgetDigest
    let favorite: WidgetDigest.Favorite

    var body: some View {
        TimelineView(.everyMinute) { context in
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text(favorite.name)
                        .font(.headline)
                    Text(favorite.countyLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Divider()
                    Text(digest.statusLine(of: favorite, at: context.date))
                        .font(.body)
                    if let next = digest.nextScheduledLine(of: favorite) {
                        Text(next)
                            .font(.footnote)
                    }
                    if let last = digest.lastScheduledLine(of: favorite) {
                        Text(last)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Text(digest.subheadline(at: context.date))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.top, 4)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .navigationTitle("Water")
    }
}

/// Before the purchase: what the locked widget says, and where to unlock.
/// The schedule's week and its count are the published schedule, not
/// anyone's favorites.
private struct LockedView: View {
    let digest: WidgetDigest

    var body: some View {
        let count = digest.watersListed
        MessageView(symbol: "lock.fill",
                    message: WidgetDigest.watchLockedMessage,
                    footnote: "\(count == 1 ? "1 water is" : "\(count) waters are") listed for the \(digest.week.label).")
    }
}

private struct MessageView: View {
    let symbol: String
    let message: String
    var footnote: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Image(systemName: symbol)
                    .font(.title2)
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)
                Text(message)
                    .font(.footnote)
                    .multilineTextAlignment(.center)
                if let footnote {
                    Text(footnote)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
            }
            .frame(maxWidth: .infinity)
        }
    }
}
