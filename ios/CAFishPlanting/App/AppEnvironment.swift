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
    /// Whether this water's state is unlocked on this device.
    let isEntitled: Bool
    var id: Water.ID { water.id }
    var copy: NotificationPrimingCopy {
        NotificationPrimingCopy(waterName: water.name, isEntitled: isEntitled,
                                agencyShortName: water.agencyShortName, semantics: water.semantics)
    }
}

/// Which state Browse shows. A file like favorites, not `UserDefaults`, so
/// the app still calls no required-reason API (`PrivacyInfo.xcprivacy`).
struct BrowseChoice: Codable, Equatable {
    var state: String = "CA"
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
    /// The water's agency and what its records mean. California's by default.
    var agencyShortName: String = "CDFW"
    var semantics: StateSemantics = .schedule

    var headline: String {
        if let waterName { return "Get an alert when \(waterName) is on the schedule" }
        return "Get an alert when a favorite is on the schedule"
    }

    var points: [Point] {
        let which = waterName.map { "\($0) or another favorite" } ?? "one of your favorites"
        var points = [
            Point(systemImage: "calendar",
                  text: semantics == .report
                    ? "When \(agencyShortName)'s stocking report adds \(which), this device shows one alert, naming the day \(agencyShortName) gives."
                    : agencyShortName == "CDFW"
                    ? "When CDFW's weekly schedule adds a week for \(which), this device shows one alert. It names the week, never a day, and CDFW says plans can change."
                    : "When \(agencyShortName)'s schedule adds a date for \(which), this device shows one alert. It names the date as precisely as \(agencyShortName) gives it, and plans can change."),
            Point(systemImage: "iphone",
                  text: "Alerts are made on this device from the schedule it downloads. There is no account and no server, and nothing about you or your favorites leaves the device."),
            Point(systemImage: "bell.slash",
                  text: "No other notifications: no marketing, no reminders, no badges."),
        ]
        if !isEntitled {
            points.append(Point(systemImage: "lock",
                                text: "Alerts are part of full access, a one-time purchase for each state in About. If you allow notifications now, alerts start as soon as you unlock the state."))
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
    /// environment. Set once, in `App.init()`, so the background-refresh
    /// handler can reach it even on a cold background launch.
    static var shared: AppEnvironment?

    let bundleIdentifier = Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting"

    private(set) var loadError: String?
    private var store: SnapshotStore?
    private var favoritesStore: FavoritesStore?
    private var alertStateStore: AlertStateStore?
    private var mutedStore: MutedWatersStore?
    private var onboardingStore: OnboardingStore?
    private var reviewPromptStore: ReviewPromptStore?
    private var reviewPrompter = ReviewPrompter()
    private let refresher: SnapshotRefresher
    private let notifications: NotificationScheduler
    private let openThrottle: RefreshThrottle
    /// Writes what the Home Screen widget shows (`WidgetDigest`) to the App
    /// Group container. No network, and only when it changed.
    private let widgetBridge: WidgetBridge
    /// Sends the same digest to Apple Watch (`WatchSync`), and applies a
    /// mute the watch asks for. `nil` where there is no watch to talk to.
    private let watchBridge: WatchBridge?
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
    /// Favorites whose alerts are off. They stay favorites.
    private(set) var mutedWaters = MutedWaters()
    private(set) var onboarding = OnboardingState()
    private(set) var notificationAuthorization: UNAuthorizationStatus = .notDetermined
    /// The state Browse shows. California until the person picks another.
    private(set) var browseChoice = BrowseChoice()
    private var browseChoiceFile: JSONFileStore<BrowseChoice>?

    /// Goes up by one each time the app should ask iOS for its rating
    /// prompt. `RootTabView` watches it and calls `requestReview`, the only
    /// prompt there is (`ReviewPromptPolicy`).
    private(set) var reviewRequestCount = 0
    /// The water a tapped planting alert opened, until the person leaves it.
    private var waterOpenedFromAlert: Water.ID?
    let appVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"

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
    init(notificationCenter: UNUserNotificationCenter = .current(), purchases: PurchaseManager? = nil, refresher: SnapshotRefresher? = nil, openThrottle: RefreshThrottle = .foreground, widgetBridge: WidgetBridge? = nil, watchBridge: WatchBridge? = .shared) {
        self.notifications = NotificationScheduler(center: notificationCenter)
        self.refresher = refresher ?? SnapshotRefresher(session: SnapshotRefresher.makeSession())
        self.openThrottle = openThrottle
        self.widgetBridge = widgetBridge ?? WidgetBridge()
        self.watchBridge = watchBridge
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
            let mutedStore = MutedWatersStore(layout: layout)
            self.mutedStore = mutedStore
            self.mutedWaters = mutedStore.load()
            let onboardingStore = OnboardingStore(layout: layout)
            self.onboardingStore = onboardingStore
            self.onboarding = onboardingStore.load()
            let choiceFile = JSONFileStore<BrowseChoice>(url: layout.directory.appendingPathComponent("browse-state.json"))
            self.browseChoiceFile = choiceFile
            self.browseChoice = ((try? choiceFile.load()) ?? nil) ?? BrowseChoice()
            let reviewPromptStore = ReviewPromptStore(layout: layout)
            self.reviewPromptStore = reviewPromptStore
            self.reviewPrompter = ReviewPrompter(state: reviewPromptStore.load())
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
        // "Mute this water" tapped on the watch, if watchOS hands that
        // button to the watch app rather than to this one.
        self.watchBridge?.onMuteRequest = { [weak self] id in self?.setAlertsMuted(true, for: id) }
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
    /// place that flag is read. Apple Watch gets its own copy, gated the
    /// same way by `FreeTier.watchAllowed`, read only here too.
    func publishWidgetDigest() {
        guard let snapshot, let refreshMeta else { return }
        let entitled = purchases.entitledStates
        let digest = WidgetDigest(snapshot: snapshot, meta: refreshMeta, favorites: favorites.ids,
                                  locked: !FreeTier.widgetsAllowed(entitledStates: entitled),
                                  entitledStates: entitled)
        widgetBridge.publish(digest)
        let watchLocked = !FreeTier.watchAllowed(entitledStates: entitled)
        watchBridge?.publish(watchLocked == digest.locked ? digest
            : WidgetDigest(snapshot: snapshot, meta: refreshMeta, favorites: favorites.ids, locked: watchLocked,
                           entitledStates: entitled))
    }

    // MARK: States

    /// Each alert needs its own water's state's purchase (DECISIONS 0025): a
    /// California buyer gets no Tennessee alert, and the reverse. A water the
    /// snapshot no longer has is treated as California's, where every alert
    /// before states came from.
    nonisolated static func alertsToSchedule(_ planned: [PlannedNotification], in snapshot: Snapshot, entitledStates: Set<String>) -> [PlannedNotification] {
        planned.filter {
            FreeTier.notificationsAllowed(forState: snapshot.water(id: $0.waterID)?.state ?? "CA",
                                          entitledStates: entitledStates)
        }
    }

    /// The state Browse shows, if the snapshot still has it; else California.
    var browseState: String {
        snapshot?.state(code: browseChoice.state) == nil ? "CA" : browseChoice.state
    }

    func setBrowseState(_ code: String) {
        guard code != browseChoice.state else { return }
        browseChoice = BrowseChoice(state: code)
        try? browseChoiceFile?.save(browseChoice)
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
        setAlertsMuted(false, for: id)
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
                pendingNotificationExplainer = FirstFavoriteExplainer(water: water, isEntitled: purchases.isEntitled(state: water.state))
            }
        } else if !nowFavorited {
            alertState = AlertPlanner.pruning(alertState, unfavoriting: water.id)
            try? alertStateStore?.save(alertState)
            // Favoriting it again starts with alerts on.
            setAlertsMuted(false, for: water.id)
        }
    }

    // MARK: Muted alerts

    func alertsMuted(for id: Water.ID) -> Bool { mutedWaters.contains(id) }

    /// Turns one favorite's alerts off or back on. From the alert's "Mute
    /// this water" button (`NotificationResponder`) or the switch on the
    /// water's screen. The alert baseline keeps moving either way, so
    /// turning alerts back on never announces weeks that passed while muted.
    func setAlertsMuted(_ muted: Bool, for id: Water.ID) {
        guard muted != mutedWaters.contains(id) else { return }
        var updated = mutedWaters
        if muted { updated.mute(id) } else { updated.unmute(id) }
        mutedWaters = updated
        try? mutedStore?.save(updated)
    }

    /// The water's screen is open: its delivered alerts have been read.
    func clearDeliveredAlerts(for id: Water.ID) async {
        await notifications.removeDelivered(forWater: id)
    }

    // MARK: Introduction

    /// Whether the introduction shows over the app at launch.
    var shouldShowOnboarding: Bool {
        loadError == nil && onboarding.shouldShow(hasFavorites: !favorites.isEmpty)
    }

    /// Finished or skipped: it doesn't show again until a newer version.
    func completeOnboarding() {
        onboarding = OnboardingState(completedVersion: OnboardingCopy.version)
        try? onboardingStore?.save(onboarding)
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

    // MARK: Rating prompt

    /// The window came to the foreground: one launch, for
    /// `ReviewPromptPolicy.minimumLaunches`. Not called for a background
    /// launch by the refresh task.
    func recordForegroundLaunch() {
        guard reviewPromptStore != nil else { return }
        reviewPrompter.recordLaunch()
        try? reviewPromptStore?.save(reviewPrompter.state)
    }

    /// A tapped planting alert is opening this water (`NotificationResponder`).
    func notePlantingAlertOpened(_ id: Water.ID) {
        waterOpenedFromAlert = id
    }

    /// The person went back from a water's page: the end of a task, the only
    /// time the app may ask for a rating. `isBusy` is anything else on
    /// screen (a sheet, the introduction).
    func finishedWithWater(_ id: Water.ID, isBusy: Bool) {
        let fromAlert = waterOpenedFromAlert == id
        if fromAlert { waterOpenedFromAlert = nil }
        guard loadError == nil, reviewPromptStore != nil, ReviewPromptLaunchOverride.allowsAsking else { return }
        let busy = isBusy || isRefreshing || pendingNotificationExplainer != nil
        guard reviewPrompter.considerAsking(fromAlert ? .readPlantingAlert : .finishedWithWater,
                                            hasFavorites: !favorites.isEmpty, appVersion: appVersion,
                                            isBusy: busy) else { return }
        try? reviewPromptStore?.save(reviewPrompter.state)
        reviewRequestCount += 1
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
            // A muted water's baseline moved forward with the rest above;
            // only its alert is left out.
            let shown = Self.alertsToSchedule(mutedWaters.unmuted(plan.notifications), in: store.snapshot,
                                              entitledStates: purchases.entitledStates)
            if !shown.isEmpty {
                await notifications.schedule(shown)
            }
        }
        return outcome
    }
}

/// Debug builds show the system rating prompt on every request, which would
/// land in the middle of UI tests and screenshots. So a debug build never
/// asks unless launched with `-ReviewPrompt allow`. A release build always
/// follows `ReviewPromptPolicy`; TestFlight builds never show the prompt.
enum ReviewPromptLaunchOverride {
    static var allowsAsking: Bool {
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        guard let flag = arguments.firstIndex(of: "-ReviewPrompt"), flag + 1 < arguments.count else { return false }
        return arguments[flag + 1] == "allow"
        #else
        return true
        #endif
    }
}
