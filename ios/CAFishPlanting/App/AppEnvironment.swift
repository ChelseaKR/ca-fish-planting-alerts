import Foundation
import Observation
import UserNotifications
import PlantingCore

/// What to tell the person before the system permission prompt appears —
/// deliverable #3's "a sentence that says what will and won't happen".
/// Shown on the first-ever favourite regardless of purchase status, so
/// permission is already granted by the moment someone unlocks full access
/// (see `FreeTier`) — `isEntitled` is carried through only so the sentence
/// can say so accurately, rather than implying alerts start immediately
/// for a non-purchaser.
struct FirstFavouriteExplainer: Identifiable {
    let water: Water
    let isEntitled: Bool
    var id: Water.ID { water.id }
    var sentence: String {
        let when = isEntitled ? "" : " — once you unlock full access —"
        return "If you allow notifications, this app will alert you on this device\(when) only when \(water.name) or another favourite you add appears in CDFW's new weekly schedule; it will not send any other notification, and nothing about you or your favourites ever leaves this device."
    }
}

/// The app's one shared piece of state. Owns the on-disk snapshot, the
/// favourites list, the alert baseline, and the network+notification
/// plumbing that touches them. A SwiftUI `@Observable` so views update
/// automatically; not thread-safe by design — always touched from the
/// main actor.
@MainActor
@Observable
final class AppEnvironment {
    /// Bridges the BGTaskScheduler launch handler (registered in
    /// `App.init()`, before any SwiftUI environment exists) to the live
    /// environment. Set once, from the `WindowGroup`'s root view.
    static var shared: AppEnvironment?

    let bundleIdentifier = Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting"

    private(set) var loadError: String?
    private var store: SnapshotStore?
    private var favouritesStore: FavouritesStore?
    private var alertStateStore: AlertStateStore?
    private let refresher: SnapshotRefresher
    private let notifications: NotificationScheduler

    /// The one-time purchase. `let`, not injected-per-call: it owns its
    /// own StoreKit listeners for the app's lifetime. Tests may inject a
    /// pre-built instance (e.g. one wired to an `SKTestSession`).
    let purchases: PurchaseManager

    private(set) var favourites = Favourites()
    private var alertState = AlertState()
    private(set) var notificationAuthorization: UNAuthorizationStatus = .notDetermined

    /// Set when a water is favourited for the first time ever. The view
    /// layer presents `sentence`, then calls `confirmNotificationExplainer()`
    /// or `dismissNotificationExplainer()`.
    var pendingNotificationExplainer: FirstFavouriteExplainer?

    var snapshot: Snapshot? { store?.snapshot }
    var snapshotOrigin: SnapshotOrigin? { store?.origin }
    var refreshMeta: SnapshotMeta? { store?.meta }

    /// Tests may inject a pre-built refresher (e.g. one wired to a mocked
    /// `URLSession` via `SnapshotRefresher.makeSession(protocolClasses:)`)
    /// to exercise `performBackgroundRefresh()` without a live network call.
    init(notificationCenter: UNUserNotificationCenter = .current(), purchases: PurchaseManager? = nil, refresher: SnapshotRefresher? = nil) {
        self.notifications = NotificationScheduler(center: notificationCenter)
        self.refresher = refresher ?? SnapshotRefresher(session: SnapshotRefresher.makeSession())
        var entitlementStore: EntitlementStore?
        do {
            let layout = try AppStorageLayout.applicationSupport(bundleIdentifier: bundleIdentifier)
            let bundledURL = Bundle.main.url(forResource: "snapshot", withExtension: "json")
            let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundledURL)
            self.store = store
            let favStore = FavouritesStore(layout: layout)
            let stateStore = AlertStateStore(layout: layout)
            self.favouritesStore = favStore
            self.alertStateStore = stateStore
            self.favourites = favStore.load()
            self.alertState = stateStore.load()
            entitlementStore = EntitlementStore(layout: layout)
        } catch {
            // Never fabricate a snapshot to paper over this: an honest
            // error screen (see AboutView / RootTabView) beats fake data.
            loadError = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
        }
        self.purchases = purchases ?? PurchaseManager(entitlementStore: entitlementStore)
        Task { notificationAuthorization = await notifications.authorizationStatus() }
    }

    // MARK: Favourites

    func isFavourite(_ id: Water.ID) -> Bool { favourites.contains(id) }

    /// Favouriting is never gated — every water may be favourited by
    /// anyone, purchaser or not (see `FreeTier`). What the one-time
    /// purchase unlocks is local notifications, not this.
    func toggleFavourite(_ water: Water) {
        let wasEmpty = favourites.isEmpty

        var updated = favourites
        let nowFavourited = updated.toggle(water.id)
        favourites = updated
        try? favouritesStore?.save(updated)

        if nowFavourited, let snapshot {
            alertState = AlertPlanner.seeding(alertState, favouriting: water.id, snapshot: snapshot)
            try? alertStateStore?.save(alertState)
            if wasEmpty {
                pendingNotificationExplainer = FirstFavouriteExplainer(water: water, isEntitled: purchases.isEntitled)
            }
        } else if !nowFavourited {
            alertState = AlertPlanner.pruning(alertState, unfavouriting: water.id)
            try? alertStateStore?.save(alertState)
        }
    }

    func confirmNotificationExplainer() async {
        guard pendingNotificationExplainer != nil else { return }
        pendingNotificationExplainer = nil
        let granted = await notifications.requestAuthorization()
        notificationAuthorization = granted ? .authorized : await notifications.authorizationStatus()
    }

    func dismissNotificationExplainer() {
        pendingNotificationExplainer = nil
    }

    // MARK: Refresh

    /// Foreground refresh (e.g. pull-to-refresh). Same path as the
    /// background task; the only difference is who called it.
    @discardableResult
    func refreshNow() async -> RefreshOutcome {
        await performBackgroundRefresh()
    }

    /// Entry point for `BGAppRefreshTask`. Refreshes the snapshot, replans
    /// alerts for every favourite against the (possibly) new snapshot, and
    /// — for a purchaser only (`FreeTier.notificationsAllowed`) — schedules
    /// any resulting local notifications. Safe to call with a stale or
    /// unusable store: it simply does nothing beyond the network attempt so
    /// the last good snapshot is never disturbed.
    ///
    /// The alert baseline itself is always replanned and saved, purchaser
    /// or not: it is bookkeeping ("what's already been seen"), not a
    /// notification, and keeping it current means a later purchase doesn't
    /// suddenly announce every listing change that happened while locked.
    func performBackgroundRefresh() async -> RefreshOutcome {
        guard let store else { return .failed("no snapshot store") }
        let outcome = await refresher.refresh(into: store, now: Date())
        if case .updated = outcome, !favourites.isEmpty {
            let plan = AlertPlanner.plan(snapshot: store.snapshot, favourites: favourites.ids, state: alertState)
            alertState = plan.state
            try? alertStateStore?.save(alertState)
            if !plan.notifications.isEmpty, FreeTier.notificationsAllowed(isEntitled: purchases.isEntitled) {
                await notifications.schedule(plan.notifications)
            }
        }
        return outcome
    }
}
