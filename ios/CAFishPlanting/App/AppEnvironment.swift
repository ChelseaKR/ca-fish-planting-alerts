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
    private let openThrottle: RefreshThrottle
    /// The one refresh running now, if any. Launch, return to the
    /// foreground and the background task can all ask at once; they share
    /// this task rather than racing two GETs into one `SnapshotStore`.
    private var inFlightRefresh: Task<RefreshOutcome, Never>?

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

    // Copies of the store's state, so SwiftUI sees a refresh land.
    // `SnapshotStore` is a plain class that Observation can't watch; these
    // are set from it after init and after every refresh (`syncFromStore`).
    private(set) var snapshot: Snapshot?
    private(set) var snapshotOrigin: SnapshotOrigin?
    private(set) var refreshMeta: SnapshotMeta?

    var isRefreshing: Bool { inFlightRefresh != nil }

    /// What to say about the schedule on screen: its week, whether that week
    /// is over, and how the last check went. `nil` only when no snapshot
    /// loaded at all (then `loadError` says why).
    func freshness(now: Date = Date()) -> SnapshotFreshness? {
        guard let snapshot, let snapshotOrigin, let refreshMeta else { return nil }
        return SnapshotFreshness(snapshot: snapshot, origin: snapshotOrigin, meta: refreshMeta, isChecking: isRefreshing, now: now)
    }

    /// Tests may inject a pre-built refresher (e.g. one wired to a mocked
    /// `URLSession` via `SnapshotRefresher.makeSession(protocolClasses:)`)
    /// to exercise `performBackgroundRefresh()` without a live network call.
    init(notificationCenter: UNUserNotificationCenter = .current(), purchases: PurchaseManager? = nil, refresher: SnapshotRefresher? = nil, openThrottle: RefreshThrottle = .foreground) {
        self.notifications = NotificationScheduler(center: notificationCenter)
        self.refresher = refresher ?? SnapshotRefresher(session: SnapshotRefresher.makeSession())
        self.openThrottle = openThrottle
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
        syncFromStore()
        Task { notificationAuthorization = await notifications.authorizationStatus() }
    }

    private func syncFromStore() {
        snapshot = store?.snapshot
        snapshotOrigin = store?.origin
        refreshMeta = store?.meta
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

    /// Launch and return to the foreground. Fetches the snapshot unless one
    /// is already being fetched or `openThrottle` says a check ran too
    /// recently (the background task's checks count too: they share
    /// `SnapshotMeta`). Returns `nil` when it skipped.
    ///
    /// Without this, a fresh install (and App Review) sees only the snapshot
    /// bundled at build time until iOS chooses to run the background task.
    /// It is the same single GET to the same host as the background task:
    /// no new destination and nothing sent about the device.
    @discardableResult
    func refreshIfDue(now: Date = Date()) async -> RefreshOutcome? {
        guard let store, inFlightRefresh == nil, openThrottle.isDue(meta: store.meta, now: now) else { return nil }
        return await refresh(now: now)
    }

    /// An unthrottled refresh (e.g. pull-to-refresh). Same path as the
    /// background task; the only difference is who called it.
    @discardableResult
    func refreshNow() async -> RefreshOutcome {
        await refresh(now: Date())
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
    func performBackgroundRefresh(now: Date = Date()) async -> RefreshOutcome {
        await refresh(now: now)
    }

    /// Joins the refresh already running, or starts one. Cancelling the
    /// caller (the background task's expiration handler) cancels the fetch.
    private func refresh(now: Date) async -> RefreshOutcome {
        let task: Task<RefreshOutcome, Never>
        if let inFlightRefresh {
            task = inFlightRefresh
        } else {
            task = Task { @MainActor in
                let outcome = await self.runRefresh(now: now)
                self.inFlightRefresh = nil
                return outcome
            }
            inFlightRefresh = task
        }
        return await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func runRefresh(now: Date) async -> RefreshOutcome {
        guard let store else { return .failed("no snapshot store") }
        let outcome = await refresher.refresh(into: store, now: now)
        // Whatever the outcome. A failure changes only the meta (the store
        // keeps the last good snapshot), and the screen must say so.
        syncFromStore()
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
