import Foundation
import Observation
import PlantingCore

/// Which tab is showing and which water is open in each. One place decides
/// where a water opens, so a tapped alert and a `trouttruck://water/<id>`
/// link (the Home Screen widget) land on the same screen.
///
/// A request can arrive before the UI exists: a tap on an alert that
/// launches the app reaches `NotificationResponder` before the first view
/// appears. It waits in `pendingWaterID` until `RootTabView` resolves it
/// against the snapshot.
@MainActor
@Observable
final class AppRouter {
    /// The one router the app uses. `NotificationResponder` is set up in
    /// `App.init()`, before any SwiftUI environment exists, so it reaches the
    /// router this way. Tests make their own.
    static let shared = AppRouter()

    enum Tab: Hashable {
        case browse
        case favorites
        case about
    }

    var selectedTab: Tab = .browse
    var browsePath: [Water.ID] = []
    var favoritesPath: [Water.ID] = []

    /// A water asked for by a tapped alert or a link, not opened yet.
    private(set) var pendingWaterID: Water.ID?

    /// Asks for a water to be opened as soon as the UI can.
    func request(waterID: Water.ID) {
        pendingWaterID = waterID
    }

    /// Handles a `trouttruck://water/<id>` link. Returns `false`, and asks
    /// for nothing, for any other URL.
    @discardableResult
    func handle(_ url: URL) -> Bool {
        guard let id = WaterLink.waterID(from: url) else { return false }
        request(waterID: id)
        return true
    }

    /// Opens the pending water, if any, and clears it.
    ///
    /// A favorite opens under Favorites, because every alert is for a
    /// favorite and that is where the person keeps it. Any other water opens
    /// under Browse. Either way it replaces what was open in that tab, so Back
    /// goes to the list.
    ///
    /// A water the snapshot doesn't have is never pushed: that would be a
    /// blank screen. The app opens on Favorites (for a favorite) or where it
    /// was, and returns `false`.
    @discardableResult
    func openPending(in snapshot: Snapshot?, isFavorite: (Water.ID) -> Bool) -> Bool {
        guard let id = pendingWaterID else { return false }
        pendingWaterID = nil
        let favorite = isFavorite(id)
        guard snapshot?.water(id: id) != nil else {
            if favorite { selectedTab = .favorites }
            return false
        }
        if favorite {
            selectedTab = .favorites
            favoritesPath = [id]
        } else {
            selectedTab = .browse
            browsePath = [id]
        }
        return true
    }
}
