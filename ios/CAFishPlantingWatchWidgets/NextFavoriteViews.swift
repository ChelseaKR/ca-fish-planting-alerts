import SwiftUI
import WidgetKit
import PlantingCore

/// One timeline entry: the digest as of `date`.
struct NextFavoriteEntry: TimelineEntry {
    let date: Date
    /// `nil` when the phone hasn't sent one yet.
    let digest: WidgetDigest?
}

/// The complication's words and marks, in every size. Also compiled into
/// the watch app, so a Debug-only gallery can draw them for screenshots.
struct NextFavoriteView: View {
    @Environment(\.widgetFamily) private var environmentFamily
    let entry: NextFavoriteEntry
    /// Set only to draw one size outside WidgetKit (the Debug gallery).
    var family: WidgetFamily?

    var body: some View {
        switch family ?? environmentFamily {
        case .accessoryCircular:
            CircularView(entry: entry)
        case .accessoryInline:
            InlineView(entry: entry)
        case .accessoryCorner:
            CornerView(entry: entry)
        default:
            RectangularView(entry: entry)
        }
    }
}

/// Where the complication stands, said plainly when there is no water to
/// name: never "nothing scheduled" for a missing or locked digest.
private enum Reading {
    case noDigest
    case locked(WidgetDigest)
    case noFavorites(WidgetDigest)
    /// Favorites, but none is listed for this week or later.
    case noneScheduled(WidgetDigest)
    case favorite(WidgetDigest, WidgetDigest.Favorite)

    init(_ digest: WidgetDigest?) {
        guard let digest else { self = .noDigest; return }
        if digest.locked { self = .locked(digest); return }
        if digest.favorites.isEmpty { self = .noFavorites(digest); return }
        if let next = digest.nextFavorite { self = .favorite(digest, next) } else { self = .noneScheduled(digest) }
    }

    var url: URL? {
        if case .favorite(_, let favorite) = self { return WaterLink.url(for: favorite.id) }
        return nil
    }
}

private struct RectangularView: View {
    let entry: NextFavoriteEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            switch Reading(entry.digest) {
            case .noDigest:
                title("Trout Truck")
                Text("Open Trout Truck on your iPhone")
                    .font(.caption).lineLimit(2)
            case .locked:
                title("Trout Truck")
                Text("Part of full access. Unlock it on your iPhone.")
                    .font(.caption).lineLimit(2)
            case .noFavorites:
                title("Trout Truck")
                Text("Star a water on your iPhone")
                    .font(.caption).lineLimit(2)
            case .noneScheduled(let digest):
                title(digest.isStale(at: entry.date) ? digest.week.label : "This week")
                Text("No favorite listed this week or later")
                    .font(.caption).lineLimit(2)
            case .favorite(let digest, let favorite):
                title(digest.isStale(at: entry.date) ? digest.week.label : "Trout Truck")
                Text(favorite.name)
                    .font(.headline)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(digest.shortStatus(of: favorite, at: entry.date))
                    .font(.caption)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .widgetURL(Reading(entry.digest).url)
    }

    private func title(_ text: String) -> some View {
        Label(text, systemImage: "fish.fill")
            .font(.caption2.weight(.semibold))
            .lineLimit(1)
            .minimumScaleFactor(0.7)
            .widgetAccentable()
    }
}

/// How many favorites are scheduled this week, under the fish. "ended"
/// once the week is over; a lock when locked; the fish alone with no
/// digest or no favorites, so a missing count never reads as zero.
private struct CircularView: View {
    let entry: NextFavoriteEntry

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            VStack(spacing: 0) {
                Image(systemName: symbol)
                    .font(.body.weight(.semibold))
                    .widgetAccentable()
                if let caption {
                    Text(caption)
                        .font(.system(.body, design: .rounded).weight(.bold))
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                }
            }
            .padding(3)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(entry.digest?.summary(at: entry.date) ?? WidgetDigest.watchNoDigestMessage)
        .widgetURL(Reading(entry.digest).url)
    }

    private var symbol: String {
        guard let digest = entry.digest else { return "fish" }
        if digest.locked { return "lock.fill" }
        return digest.isStale(at: entry.date) ? "calendar" : "fish.fill"
    }

    private var caption: String? {
        guard let digest = entry.digest, !digest.locked, !digest.favorites.isEmpty else { return nil }
        return digest.isStale(at: entry.date) ? "ended" : "\(digest.favoritesListedThisWeek)"
    }
}

private struct InlineView: View {
    let entry: NextFavoriteEntry

    var body: some View {
        switch Reading(entry.digest) {
        case .noDigest:
            Label("Open Trout Truck on iPhone", systemImage: "fish")
        case .locked:
            Label("Unlock on iPhone", systemImage: "lock")
        case .favorite(let digest, let favorite):
            if case .scheduledThisWeek = digest.status(of: favorite, at: entry.date) {
                Label("\(favorite.name) this week", systemImage: "fish.fill")
            } else {
                Label(digest.summary(at: entry.date), systemImage: "fish.fill")
            }
        case .noFavorites(let digest), .noneScheduled(let digest):
            Label(digest.summary(at: entry.date), systemImage: "fish.fill")
        }
    }
}

/// A corner: the fish, with the count of favorites scheduled this week
/// along the bezel.
private struct CornerView: View {
    let entry: NextFavoriteEntry

    var body: some View {
        Image(systemName: entry.digest?.locked == true ? "lock.fill" : "fish.fill")
            .font(.title3)
            .widgetAccentable()
            .widgetLabel(label)
            .accessibilityLabel(entry.digest?.summary(at: entry.date) ?? WidgetDigest.watchNoDigestMessage)
    }

    private var label: String {
        guard let digest = entry.digest else { return "Open on iPhone" }
        if digest.locked { return "Unlock on iPhone" }
        if digest.favorites.isEmpty { return "No favorites" }
        if digest.isStale(at: entry.date) { return "Week ended" }
        return "\(digest.favoritesListedThisWeek) this week"
    }
}
