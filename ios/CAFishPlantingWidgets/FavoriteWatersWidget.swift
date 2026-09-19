import SwiftUI
import WidgetKit
import PlantingCore

/// "This week at your favorite waters", on the Home Screen and the Lock
/// Screen.
///
/// It reads only the digest the app writes to the App Group container
/// (`WidgetDigestStore`). It never fetches anything: the app's snapshot GET
/// stays the only network request, and the widget shows what the app last
/// downloaded, labeled with its week.
struct FavoriteWatersWidget: Widget {
    /// Also in the app (`WidgetBridge`), which reloads this widget's
    /// timeline when the digest changes.
    static let kind = "FavoriteWatersThisWeek"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: Self.kind, provider: FavoriteWatersProvider()) { entry in
            FavoriteWatersView(entry: entry)
                .tint(.troutTruckGreen)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Favorite waters")
        .description("Which of your favorite waters are on CDFW's schedule this week. Part of full access.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .accessoryRectangular, .accessoryInline])
    }
}

struct FavoriteWatersEntry: TimelineEntry {
    let date: Date
    /// `nil` when the app hasn't written one yet, or it couldn't be read.
    let digest: WidgetDigest?
}

struct FavoriteWatersProvider: TimelineProvider {
    /// How often the widget re-reads the digest on its own, in case the app
    /// refreshed in the background. Reading a local file costs nothing on
    /// the network.
    static let rereadInterval: TimeInterval = 6 * 60 * 60

    func placeholder(in context: Context) -> FavoriteWatersEntry {
        FavoriteWatersEntry(date: Date(), digest: nil)
    }

    func getSnapshot(in context: Context, completion: @escaping (FavoriteWatersEntry) -> Void) {
        completion(FavoriteWatersEntry(date: Date(), digest: WidgetDigestStore.appGroup()?.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<FavoriteWatersEntry>) -> Void) {
        let now = Date()
        let digest = WidgetDigestStore.appGroup()?.load()
        var entries = [FavoriteWatersEntry(date: now, digest: digest)]
        // When the week ends, "this week" has to stop, even if the app
        // hasn't run since.
        if let digest, digest.staleAt > now {
            entries.append(FavoriteWatersEntry(date: digest.staleAt, digest: digest))
        }
        completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(Self.rereadInterval))))
    }
}

// MARK: - Views

struct FavoriteWatersView: View {
    @Environment(\.widgetFamily) private var environmentFamily
    let entry: FavoriteWatersEntry
    /// Set only to draw one size outside WidgetKit (a render check);
    /// otherwise the size WidgetKit asks for.
    var family: WidgetFamily?

    var body: some View {
        let family = self.family ?? environmentFamily
        switch family {
        case .accessoryInline:
            InlineView(entry: entry)
        case .accessoryRectangular:
            RectangularView(entry: entry)
        default:
            HomeScreenView(entry: entry, family: family, maxRows: Self.maxRows(family))
        }
    }

    static func maxRows(_ family: WidgetFamily) -> Int {
        switch family {
        case .systemSmall: return 3
        // Two rows of name and status fit the medium height with the
        // header and the footer; a third is cut off.
        case .systemMedium: return 2
        default: return 7
        }
    }
}

/// What to show when there are no favorites to list: said plainly, never as
/// "nothing scheduled".
private enum EmptyReason {
    case noDigest
    /// Before the purchase (`FreeTier.widgetsRequireFullAccess`). Carries
    /// the digest for its week, never for favorites (it has none).
    case locked(WidgetDigest)
    case noFavorites(WidgetDigest)
    case onlyMissingFavorites(WidgetDigest)

    init?(_ digest: WidgetDigest?) {
        guard let digest else { self = .noDigest; return }
        if digest.locked { self = .locked(digest); return }
        guard digest.favorites.isEmpty else { return nil }
        self = digest.missingFavorites > 0 ? .onlyMissingFavorites(digest) : .noFavorites(digest)
    }

    var message: String {
        switch self {
        case .noDigest:
            return "Open Trout Truck to load the schedule here."
        case .locked:
            return "This widget is part of full access, a one-time purchase in Trout Truck."
        case .noFavorites:
            return "Star a water in Trout Truck to see its schedule here."
        case .onlyMissingFavorites:
            return "Your favorite waters aren't in this week's schedule data. Open Trout Truck to check them."
        }
    }

    /// A true line about the schedule itself, when there is one. The
    /// locked widget shows it too: it is the published schedule, not a
    /// preview of anyone's favorites.
    func context(at now: Date) -> String? {
        switch self {
        case .noFavorites(let digest), .onlyMissingFavorites(let digest), .locked(let digest):
            let count = digest.watersListed
            let waters = count == 1 ? "1 water is" : "\(count) waters are"
            return "\(waters) listed for the \(digest.week.label)."
        case .noDigest:
            return nil
        }
    }

    /// What a tap does, when it isn't just "open the app".
    var action: String? {
        switch self {
        case .locked: return "Tap to unlock"
        case .noDigest, .noFavorites, .onlyMissingFavorites: return nil
        }
    }
}

private struct HomeScreenView: View {
    let entry: FavoriteWatersEntry
    let family: WidgetFamily
    let maxRows: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            header
            if let reason = EmptyReason(entry.digest) {
                Text(reason.message)
                    .font(.footnote)
                    .fixedSize(horizontal: false, vertical: true)
                if let action = reason.action {
                    Label(action, systemImage: "lock.open")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.tint)
                }
                if family != .systemSmall, let context = reason.context(at: entry.date) {
                    Text(context)
                        .font(.caption2)
                        .foregroundStyle(.secondaryText)
                }
                Spacer(minLength: 0)
            } else if let digest = entry.digest {
                rows(digest)
                Spacer(minLength: 0)
                footer(digest)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .widgetURL(defaultURL)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 1) {
            Label {
                Text(headerTitle)
                    .font(.headline)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            } icon: {
                Image(systemName: "fish.fill")
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)
            }
            if let digest = entry.digest, !digest.locked, family != .systemSmall {
                Text(digest.subheadline(at: entry.date))
                    .font(.caption2)
                    .foregroundStyle(digest.isStale(at: entry.date) || digest.lastCheckFailed ? Color.primary : Color.secondaryText)
                    .lineLimit(2)
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// "This week", or the week once it has ended. The small widget has no
    /// room for the week's label in its header, so it says the week ended
    /// and its footer names the week.
    private var headerTitle: String {
        guard let digest = entry.digest, !digest.locked else { return "Trout Truck" }
        if family == .systemSmall, digest.isStale(at: entry.date) { return "Week ended" }
        return digest.headline(at: entry.date)
    }

    @ViewBuilder
    private func rows(_ digest: WidgetDigest) -> some View {
        ForEach(digest.favoritesByStatus.prefix(maxRows)) { favorite in
            if family == .systemSmall {
                SmallRow(digest: digest, favorite: favorite, now: entry.date)
            } else {
                Link(destination: WaterLink.url(for: favorite.id)) {
                    Row(digest: digest, favorite: favorite, now: entry.date)
                }
            }
        }
    }

    @ViewBuilder
    private func footer(_ digest: WidgetDigest) -> some View {
        let hidden = max(0, digest.favorites.count - maxRows) + digest.missingFavorites
        if family == .systemSmall {
            Text(digest.summary(at: entry.date))
                .font(.caption2)
                .foregroundStyle(.secondaryText)
                .lineLimit(2)
        } else if hidden > 0 {
            Text(hidden == 1 ? "1 more favorite in the app" : "\(hidden) more favorites in the app")
                .font(.caption2)
                .foregroundStyle(.secondaryText)
        }
    }

    /// Before the purchase, every size opens the purchase screen. After
    /// it, the small widget is one tap target, the first favorite shown,
    /// and the others link each row. Without a digest, a tap just opens
    /// the app.
    private var defaultURL: URL? {
        if entry.digest?.locked == true { return UnlockLink.url }
        guard family == .systemSmall, let first = entry.digest?.favoritesByStatus.first else { return nil }
        return WaterLink.url(for: first.id)
    }
}

/// A status mark that doesn't rely on color: a filled check for listed, a
/// calendar for a later week, a dash for not listed.
private struct StatusMark: View {
    let status: WidgetDigest.Status

    var body: some View {
        Image(systemName: symbol)
            .foregroundStyle(isScheduled ? AnyShapeStyle(.tint) : AnyShapeStyle(Color.secondaryText))
            .accessibilityHidden(true)
    }

    private var isScheduled: Bool {
        switch status {
        case .scheduledThisWeek, .scheduledForEndedWeek: return true
        case .scheduledLater, .notListed: return false
        }
    }

    private var symbol: String {
        switch status {
        case .scheduledThisWeek, .scheduledForEndedWeek: return "checkmark.circle.fill"
        case .scheduledLater: return "calendar"
        case .notListed: return "minus.circle"
        }
    }
}

private struct Row: View {
    let digest: WidgetDigest
    let favorite: WidgetDigest.Favorite
    let now: Date

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            StatusMark(status: digest.status(of: favorite, at: now))
            VStack(alignment: .leading, spacing: 0) {
                Text(favorite.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text(digest.statusLine(of: favorite, at: now))
                    .font(.caption2)
                    .foregroundStyle(Color.secondaryText)
                    .lineLimit(1)
            }
        }
        // A row is a Link, which would tint its text; tinted secondary text
        // is too faint to read on the widget background.
        .foregroundStyle(Color.primary)
        .accessibilityElement(children: .combine)
    }
}

private struct SmallRow: View {
    let digest: WidgetDigest
    let favorite: WidgetDigest.Favorite
    let now: Date

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            StatusMark(status: digest.status(of: favorite, at: now))
            Text(favorite.name)
                .font(.caption.weight(.semibold))
                .lineLimit(1)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(favorite.name): \(digest.statusLine(of: favorite, at: now))")
    }
}

private struct RectangularView: View {
    let entry: FavoriteWatersEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let reason = EmptyReason(entry.digest) {
                Text("Trout Truck")
                    .font(.headline)
                    .widgetAccentable()
                Text(reason.action == nil ? reason.message : "Part of full access. Tap to unlock.")
                    .font(.caption)
                    .lineLimit(2)
            } else if let digest = entry.digest {
                // The week the words below are about: "This week", or the
                // week itself once it has ended.
                Text(digest.isStale(at: entry.date) ? digest.week.label : "This week")
                    .font(.headline)
                    .widgetAccentable()
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                ForEach(digest.favoritesByStatus.prefix(2)) { favorite in
                    HStack(spacing: 4) {
                        Text(favorite.name)
                            .lineLimit(1)
                        Spacer(minLength: 2)
                        Text(shortStatus(digest, favorite))
                            .fixedSize()
                    }
                    .font(.caption)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(favorite.name): \(digest.statusLine(of: favorite, at: entry.date))")
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetURL(entry.digest?.locked == true
            ? UnlockLink.url
            : entry.digest?.favoritesByStatus.first.map { WaterLink.url(for: $0.id) })
    }

    /// Relative to the headline's week, which the line above names.
    private func shortStatus(_ digest: WidgetDigest, _ favorite: WidgetDigest.Favorite) -> String {
        switch digest.status(of: favorite, at: entry.date) {
        case .scheduledThisWeek, .scheduledForEndedWeek: return "scheduled"
        case .scheduledLater: return "later"
        case .notListed: return "not listed"
        }
    }
}

private struct InlineView: View {
    let entry: FavoriteWatersEntry

    var body: some View {
        if let digest = entry.digest, digest.locked {
            Label(digest.summary(at: entry.date), systemImage: "lock")
                .widgetURL(UnlockLink.url)
        } else if let digest = entry.digest {
            Label(digest.summary(at: entry.date), systemImage: "fish.fill")
        } else {
            Label("Open Trout Truck to load the schedule", systemImage: "fish")
        }
    }
}

extension ShapeStyle where Self == Color {
    /// The app's accent (its icon's green, lighter in dark mode), so the
    /// widget's checks and links match the app. The extension has no asset
    /// catalog of its own, so without this it would be the default blue.
    static var troutTruckGreen: Color {
        Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(rgb: 0x2E9E68) : UIColor(rgb: 0x0F784B) })
    }
}
