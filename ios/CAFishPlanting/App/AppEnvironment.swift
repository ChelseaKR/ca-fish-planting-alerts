import Foundation
import Observation
import UserNotifications
import PlantingCore

/// What to tell the person before the system permission prompt appears —
/// deliverable #3's "a sentence that says what will and won't happen".
/// Shown on the first-ever favorite regardless of purchase status, so
/// permission is already granted by the moment someone unlocks full access
/// (see `FreeTier`) — `isEntitled` is carried through only so the copy
/// can say so accurately, rather than implying alerts start immediately
/// for a non-purchaser. The words are `NotificationPrimingCopy`.
struct FirstFavoriteExplainer: Identifiable {
    let water: Water
    let isEntitled: Bool
    var id: Water.ID { water.id }
    var copy: NotificationPrimingCopy { NotificationPrimingCopy(waterName: water.name, isEntitled: isEntitled) }
}

/// The words on the screen shown before the system notification prompt,
/// from a first favorite or from About. Kept apart from the view so a test
/// can read them: they say what an alert is, how often one comes, that it
/// is made on this device, and (for a non-purchaser) that alerts need full
/// access. They never name a price and never promise a day or a plant.
struct NotificationPrimingCopy: Equatable {
    struct Point: Equatable, Identifiable {
        let systemImage: String
        let text: String
        var id: String { systemImage }
    }

    /// The water just favorited, or `nil` when asked from About.
    let waterName: String?
    let isEntitled: Bool

    var headline: String {
        if let waterName { return "Get an alert when \(waterName) is on the schedule" }
        return "Get an alert when a favorite is on the schedule"
    }

    var points: [Point] {
        let which = waterName.map { "\($0) or another favorite" } ?? "one of your favorites"
        var points = [
            Point(systemImage: "calendar",
                  text: "When CDFW's weekly schedule adds a week for \(which), this iPhone shows one alert. It names the week, never a day, and CDFW says plans can change."),
            Point(systemImage: "iphone",
                  text: "Alerts are made on this iPhone from the schedule it downloads. There is no account and no server, and nothing about you or your favorites leaves the device."),
            Point(systemImage: "bell.slash",
                  text: "No other notifications: no marketing, no reminders, no badges."),
        ]
        if !isEntitled {
            points.append(Point(systemImage: "lock",
                                text: "Alerts are part of full access, a one-time purchase in About. If you allow notifications now, alerts start as soon as you unlock it."))
        }
        return points
    }

    var footnote: String { "Next, iOS asks for permission. You can change it any time in Settings." }
}

/// The app's one shared piece of state. Owns the on-disk snapshot, the
/// favorites list, the alert baseline, and the network+notification
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
    private var favoritesStore: FavoritesStore?
    private var alertStateStore: AlertStateStore?
    private let refresher: SnapshotRefresher
    private let notifications: NotificationScheduler
    private let openThrottle: RefreshThrottle
    /// Writes what the Home Screen widget shows (`WidgetDigest`) to the App
    /// Group container. No network, and only when it changed.
    private let widgetBridge: WidgetBridge
    /// The one refresh running now, if any. Launch, return to the
    /// foreground and the background task can all ask at once; they share
    /// this task rather than racing two GETs into one `SnapshotStore`.
    private var inFlightRefresh: Task<RefreshOutcome, Never>?

    /// The one-time purchase. `let`, not injected-per-call: it owns its
    /// own StoreKit listeners for the app's lifetime. Tests may inject a
    /// pre-built instance (e.g. one wired to an `SKTestSession`).
    let purchases: PurchaseManager

    /// Every change reaches the widget, whichever path made it.
    private(set) var favorites = Favorites() {
        didSet { publishWidgetDigest() }
    }
    private var alertState = AlertState()
    private(set) var notificationAuthorization: UNAuthorizationStatus = .notDetermined

    /// Set when a water is favorited for the first time ever. The view
    /// layer presents `copy`, then calls `confirmNotificationExplainer()`
    /// or `dismissNotificationExplainer()`.
    var pendingNotificationExplainer: FirstFavoriteExplainer?

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
    init(notificationCenter: UNUserNotificationCenter = .current(), purchases: PurchaseManager? = nil, refresher: SnapshotRefresher? = nil, openThrottle: RefreshThrottle = .foreground, widgetBridge: WidgetBridge? = nil) {
        self.notifications = NotificationScheduler(center: notificationCenter)
        self.refresher = refresher ?? SnapshotRefresher(session: SnapshotRefresher.makeSession())
        self.openThrottle = openThrottle
        self.widgetBridge = widgetBridge ?? WidgetBridge()
        var entitlementStore: EntitlementStore?
        do {
            let layout = try AppStorageLayout.applicationSupport(bundleIdentifier: bundleIdentifier)
            let bundledURL = Bundle.main.url(forResource: "snapshot", withExtension: "json")
            let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundledURL)
            self.store = store
            let favStore = FavoritesStore(layout: layout)
            let stateStore = AlertStateStore(layout: layout)
            self.favoritesStore = favStore
            self.alertStateStore = stateStore
            self.favorites = favStore.load()
            self.alertState = stateStore.load()
            entitlementStore = EntitlementStore(layout: layout)
        } catch {
            // Never fabricate a snapshot to paper over this: an honest
            // error screen (see AboutView / RootTabView) beats fake data.
            loadError = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
        }
        self.purchases = purchases ?? PurchaseManager(entitlementStore: entitlementStore)
        // The widget is part of full access: a purchase, a restore or a
        // refund redraws it straight away.
        self.purchases.onEntitlementChange = { [weak self] _ in self?.publishWidgetDigest() }
        syncFromStore()
        Task { notificationAuthorization = await notifications.authorizationStatus() }
    }

    private func syncFromStore() {
        snapshot = store?.snapshot
        snapshotOrigin = store?.origin
        refreshMeta = store?.meta
        publishWidgetDigest()
    }

    /// Hands the widget the snapshot's week at the current favorites. Runs
    /// after every refresh (the background task's too) and every change to
    /// `favorites`; `WidgetBridge` skips the write when nothing changed. Whether
    /// the widget may list favorites is `FreeTier.widgetsAllowed`, the one
    /// place that flag is read.
    func publishWidgetDigest() {
        guard let snapshot, let refreshMeta else { return }
        let digest = WidgetDigest(snapshot: snapshot, meta: refreshMeta, favorites: favorites.ids,
                                  locked: !FreeTier.widgetsAllowed(isEntitled: purchases.isEntitled))
        widgetBridge.publish(digest)
    }

    // MARK: Favorites

    func isFavorite(_ id: Water.ID) -> Bool { favorites.contains(id) }

    /// Removes a favorite by its ID alone. For a favorite the snapshot no
    /// longer has, so there is no `Water` to toggle.
    func removeFavorite(_ id: Water.ID) {
        guard favorites.contains(id) else { return }
        var updated = favorites
        updated.remove(id)
        favorites = updated
        try? favoritesStore?.save(updated)
        alertState = AlertPlanner.pruning(alertState, unfavoriting: id)
        try? alertStateStore?.save(alertState)
    }

    /// Favoriting is never gated — every water may be favorited by
    /// anyone, purchaser or not (see `FreeTier`). What the one-time
    /// purchase unlocks is local notifications, not this.
    func toggleFavorite(_ water: Water) {
        let wasEmpty = favorites.isEmpty

        var updated = favorites
        let nowFavorited = updated.toggle(water.id)
        favorites = updated
        try? favoritesStore?.save(updated)

        if nowFavorited, let snapshot {
            alertState = AlertPlanner.seeding(alertState, favoriting: water.id, snapshot: snapshot)
            try? alertStateStore?.save(alertState)
            if Self.shouldPrimeNotifications(favoritesWereEmpty: wasEmpty, authorization: notificationAuthorization) {
                pendingNotificationExplainer = FirstFavoriteExplainer(water: water, isEntitled: purchases.isEntitled)
            }
        } else if !nowFavorited {
            alertState = AlertPlanner.pruning(alertState, unfavoriting: water.id)
            try? alertStateStore?.save(alertState)
        }
    }

    /// The priming screen shows on the first favorite, and only while iOS
    /// hasn't asked yet. Once the person has allowed or declined, the system
    /// prompt never shows again, so the screen would promise a prompt that
    /// doesn't come (About offers Settings instead).
    nonisolated static func shouldPrimeNotifications(favoritesWereEmpty: Bool, authorization: UNAuthorizationStatus) -> Bool {
        favoritesWereEmpty && authorization == .notDetermined
    }

    func confirmNotificationExplainer() async {
        guard pendingNotificationExplainer != nil else { return }
        pendingNotificationExplainer = nil
        await requestNotificationAuthorization()
    }

    /// Shows the system prompt. Call only from the priming screen, after the
    /// app has said in its own words what alerts are (`NotificationPrimingCopy`).
    func requestNotificationAuthorization() async {
        let granted = await notifications.requestAuthorization()
        notificationAuthorization = granted ? .authorized : await notifications.authorizationStatus()
    }

    /// Re-reads the setting, which the person can change in Settings while
    /// the app is in the background.
    func refreshNotificationAuthorization() async {
        notificationAuthorization = await notifications.authorizationStatus()
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
    /// alerts for every favorite against the (possibly) new snapshot, and
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

    /// Joins the refresh already running, or starts one. Canceling the
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
        if case .updated = outcome, !favorites.isEmpty {
            let plan = AlertPlanner.plan(snapshot: store.snapshot, favorites: favorites.ids, state: alertState)
            alertState = plan.state
            try? alertStateStore?.save(alertState)
            if !plan.notifications.isEmpty, FreeTier.notificationsAllowed(isEntitled: purchases.isEntitled) {
                await notifications.schedule(plan.notifications)
            }
        }
        return outcome
    }
}
