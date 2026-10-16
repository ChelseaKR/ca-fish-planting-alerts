import SwiftUI
import WidgetKit
import PlantingCore

/// The watch extension: one widget, for watch faces and the Smart Stack.
@main
struct TroutTruckWatchWidgets: WidgetBundle {
    var body: some Widget {
        NextFavoriteWidget()
    }
}

/// "Next favorite": the favorite water scheduled this week, or the one
/// scheduled soonest after it (`WidgetDigest.nextFavorite`).
///
/// It reads only the digest the watch app keeps in the watch's App Group
/// container, which the iPhone app sent (`WatchSync`). It never fetches
/// anything.
struct NextFavoriteWidget: Widget {
    static let kind = "NextFavoriteWater"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: Self.kind, provider: NextFavoriteProvider()) { entry in
            NextFavoriteView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("Next favorite")
        .description("Your favorite water on CDFW's schedule this week, or the next one scheduled. Part of full access.")
        .supportedFamilies([.accessoryRectangular, .accessoryCircular, .accessoryInline, .accessoryCorner])
    }
}

struct NextFavoriteProvider: TimelineProvider {
    /// Re-reads the local file this often, in case the phone sent a newer
    /// digest while the watch app wasn't running. No network.
    static let rereadInterval: TimeInterval = 6 * 60 * 60

    func placeholder(in context: Context) -> NextFavoriteEntry {
        NextFavoriteEntry(date: Date(), digest: nil)
    }

    func getSnapshot(in context: Context, completion: @escaping (NextFavoriteEntry) -> Void) {
        completion(NextFavoriteEntry(date: Date(), digest: WidgetDigestStore.appGroup()?.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<NextFavoriteEntry>) -> Void) {
        let now = Date()
        let digest = WidgetDigestStore.appGroup()?.load()
        var entries = [NextFavoriteEntry(date: now, digest: digest)]
        // "This week" has to stop when the week ends, app running or not.
        if let digest, digest.staleAt > now {
            entries.append(NextFavoriteEntry(date: digest.staleAt, digest: digest))
        }
        completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(Self.rereadInterval))))
    }
}
