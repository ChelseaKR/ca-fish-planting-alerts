package com.chelseakr.cafishplanting

import android.annotation.SuppressLint
import android.content.Context
import com.chelseakr.cafishplanting.core.AlertPlanner
import com.chelseakr.cafishplanting.core.AlertState
import com.chelseakr.cafishplanting.core.AppStorageLayout
import com.chelseakr.cafishplanting.core.BrowseChoice
import com.chelseakr.cafishplanting.core.BundledSnapshot
import com.chelseakr.cafishplanting.core.Entitlements
import com.chelseakr.cafishplanting.core.Favorites
import com.chelseakr.cafishplanting.core.FreeTier
import com.chelseakr.cafishplanting.core.MutedWaters
import com.chelseakr.cafishplanting.core.OnboardingCopy
import com.chelseakr.cafishplanting.core.OnboardingState
import com.chelseakr.cafishplanting.core.PlainDate
import com.chelseakr.cafishplanting.core.ReminderPlanner
import com.chelseakr.cafishplanting.core.PurchaseEntitlement
import com.chelseakr.cafishplanting.core.RefreshOutcome
import com.chelseakr.cafishplanting.core.RefreshThrottle
import com.chelseakr.cafishplanting.core.ReviewMoment
import com.chelseakr.cafishplanting.core.ReviewPrompter
import com.chelseakr.cafishplanting.core.Snapshot
import com.chelseakr.cafishplanting.core.SnapshotFreshness
import com.chelseakr.cafishplanting.core.SnapshotMeta
import com.chelseakr.cafishplanting.core.SnapshotOrigin
import com.chelseakr.cafishplanting.core.SnapshotRefresher
import com.chelseakr.cafishplanting.core.SnapshotStore
import com.chelseakr.cafishplanting.core.Stores
import com.chelseakr.cafishplanting.core.Water
import com.chelseakr.cafishplanting.core.WidgetDigest
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.time.Instant
import java.time.LocalDate

/** Everything the screens show, in one value. */
data class AppState(
    /** True until the snapshot store has opened (or failed to), off the main thread. */
    val isLoading: Boolean = true,
    val loadError: String? = null,
    val snapshot: Snapshot? = null,
    val origin: SnapshotOrigin? = null,
    val meta: SnapshotMeta? = null,
    val isRefreshing: Boolean = false,
    val favorites: Favorites = Favorites(),
    val muted: MutedWaters = MutedWaters(),
    val entitlements: Entitlements = Entitlements(),
    val onboarding: OnboardingState = OnboardingState(),
    val notificationsAllowed: Boolean = false,
    /** Set when a water is favorited for the first time, before Android's permission prompt. */
    val primingFor: Water? = null,
    /** Which state Browse shows, as the person last picked it. */
    val browseChoice: BrowseChoice = BrowseChoice(),
) {
    /** Whether this state's full access is owned on this device (DECISIONS 0025). */
    fun isEntitled(state: String): Boolean = entitlements.owns(state)

    /** Any state unlocked: the widget and the general alert words. */
    val hasAnyAccess: Boolean get() = entitlements.hasAnyAccess

    /** The state Browse shows, if the snapshot still has it; else California. */
    val browseState: String get() = if (snapshot?.state(browseChoice.state) == null) "CA" else browseChoice.state

    fun freshness(now: Instant = Instant.now()): SnapshotFreshness? {
        val snapshot = snapshot ?: return null
        val origin = origin ?: return null
        val meta = meta ?: return null
        return SnapshotFreshness(snapshot, origin, meta, isRefreshing, now)
    }

    val shouldShowOnboarding: Boolean get() = loadError == null && onboarding.shouldShow(hasFavorites = !favorites.isEmpty)
}

/**
 * The app's one piece of shared state, the Android twin of the iOS app's
 * `AppEnvironment`: the snapshot, favorites, mutes, the alert baseline and
 * the purchase, and the refresh that ties them together. Used from the UI,
 * from WorkManager and from the mute receiver, so every change goes through
 * [lock] and is written to disk before it is published.
 */
class AppEnvironment(
    private val context: Context,
    private val refresher: SnapshotRefresher,
    private val throttle: RefreshThrottle = RefreshThrottle.FOREGROUND,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val lock = Mutex()
    private val layout = AppStorageLayout(File(context.filesDir, "trout-truck"))
    private val stores = Stores(layout)
    private var store: SnapshotStore? = null
    private val loader = SnapshotLoader(scope, Dispatchers.Default) {
        SnapshotStore(layout, BundledSnapshot { context.assets.open("snapshot.json") })
    }

    /** Completes once the load's result is in [state]; the store, or `null` when it failed to open. */
    private val loaded = CompletableDeferred<SnapshotStore?>()
    private var alertState = AlertState()
    private var inFlight: CompletableDeferred<RefreshOutcome>? = null
    private val reviewPrompter: ReviewPrompter
    private var waterOpenedFromAlert: String? = null

    val notifications = Notifications(context)
    val appVersion: String = BuildConfig.VERSION_NAME

    private val _state = MutableStateFlow(AppState())
    val state: StateFlow<AppState> = _state

    /** Goes up by one each time the app should ask Google Play for its review card. */
    private val _reviewRequests = MutableStateFlow(0)
    val reviewRequests: StateFlow<Int> = _reviewRequests

    init {
        // The small stores are read here; the snapshot opens on [loader], off the main thread.
        alertState = stores.loadAlertState()
        reviewPrompter = ReviewPrompter(stores.loadReviewPrompt())
        _state.value = AppState(
            favorites = stores.loadFavorites(),
            muted = stores.loadMuted(),
            entitlements = stores.loadEntitlement().entitlements,
            onboarding = stores.loadOnboarding(),
            notificationsAllowed = notifications.allowed(),
            browseChoice = stores.loadBrowseChoice(),
        )
        scope.launch {
            val outcome = loader.await()
            lock.withLock {
                when (outcome) {
                    is SnapshotLoad.Ready -> store = outcome.store
                    // Never a made-up snapshot: an honest error screen instead.
                    is SnapshotLoad.Failed -> _state.update { it.copy(loadError = outcome.message) }
                    SnapshotLoad.Loading -> error("the loader completed while still loading")
                }
                _state.update { it.copy(isLoading = false) }
                syncFromStore()
            }
            loaded.complete(store)
        }
    }

    val storageLayout: AppStorageLayout get() = layout

    private fun syncFromStore() {
        val s = store
        _state.update { it.copy(snapshot = s?.snapshot, origin = s?.origin, meta = s?.meta) }
        publishWidgetDigest()
        replanReminders()
    }

    /**
     * Replaces the pending planned-period reminders (New York) with the ones
     * the current favorites, purchases and mutes call for. Runs after a
     * refresh and after any of those change, as `replanReminders` on iOS.
     */
    fun replanReminders(now: Instant = Instant.now()) {
        val st = _state.value
        val snapshot = st.snapshot ?: return
        val local = LocalDate.now(java.time.ZoneId.systemDefault())
        val reminders = ReminderPlanner.reminders(
            snapshot = snapshot,
            favorites = st.favorites.ids,
            entitledStates = st.entitlements.entitledStates,
            muted = st.favorites.ids.filter { st.muted.contains(it) }.toSet(),
            today = PlainDate.of(local),
        )
        ReminderWorker.replace(context, reminders, now)
    }

    /**
     * Hands the widget the snapshot's week at the current favorites. Whether
     * it may list them is [FreeTier.widgetsAllowed], read only here.
     */
    fun publishWidgetDigest() {
        val st = _state.value
        val snapshot = st.snapshot ?: return
        val meta = st.meta ?: return
        val entitled = st.entitlements.entitledStates
        val digest = WidgetDigest.build(
            snapshot, meta, st.favorites.ids,
            locked = !FreeTier.widgetsAllowed(entitled), entitledStates = entitled,
        )
        if (WidgetDigest.save(layout, digest)) WidgetUpdates.redraw(context, digest)
    }

    // Favorites

    /** Favoriting is never gated: everyone may favorite every water (FreeTier). */
    fun toggleFavorite(water: Water) = scope.launch {
        // Seeding a new favorite's baseline needs the snapshot.
        loaded.await()
        lock.withLock {
            val st = _state.value
            val wasEmpty = st.favorites.isEmpty
            val (updated, nowFavorite) = st.favorites.toggled(water.id)
            stores.saveFavorites(updated)
            var muted = st.muted
            if (nowFavorite && st.snapshot != null) {
                alertState = AlertPlanner.seeding(alertState, water.id, st.snapshot)
            } else if (!nowFavorite) {
                alertState = AlertPlanner.pruning(alertState, water.id)
                // Favoriting it again starts with alerts on.
                muted = muted.unmuting(water.id)
                stores.saveMuted(muted)
            }
            stores.saveAlertState(alertState)
            val prime = nowFavorite && wasEmpty && notifications.shouldAsk()
            _state.update { it.copy(favorites = updated, muted = muted, primingFor = if (prime) water else it.primingFor) }
        }
        publishWidgetDigest()
        replanReminders()
    }

    /** For a favorite the snapshot no longer has. */
    fun removeFavorite(id: String) = scope.launch {
        lock.withLock {
            val st = _state.value
            if (!st.favorites.contains(id)) return@withLock
            val updated = st.favorites.removing(id)
            stores.saveFavorites(updated)
            alertState = AlertPlanner.pruning(alertState, id)
            stores.saveAlertState(alertState)
            val muted = st.muted.unmuting(id)
            stores.saveMuted(muted)
            _state.update { it.copy(favorites = updated, muted = muted) }
        }
        publishWidgetDigest()
        replanReminders()
    }

    // Mutes

    /** From the alert's "Mute this water" or the switch on the water's page. The baseline keeps moving either way. */
    suspend fun setMuted(muted: Boolean, id: String) = lock.withLock {
        val current = _state.value.muted
        if (current.contains(id) == muted) return@withLock
        val updated = if (muted) current.muting(id) else current.unmuting(id)
        stores.saveMuted(updated)
        _state.update { it.copy(muted = updated) }
        replanReminders()
    }

    fun setMutedAsync(muted: Boolean, id: String) = scope.launch { setMuted(muted, id) }

    // Notifications

    fun dismissPriming() = _state.update { it.copy(primingFor = null) }

    fun refreshNotificationPermission() = _state.update { it.copy(notificationsAllowed = notifications.allowed()) }

    // Purchase

    /** Google Play's answer is the truth; the cache only avoids a locked flash at launch. */
    fun setEntitlements(entitlements: Entitlements) {
        if (_state.value.entitlements == entitlements) return
        stores.saveEntitlement(PurchaseEntitlement.of(entitlements))
        _state.update { it.copy(entitlements = entitlements) }
        // The widget is part of full access: a purchase or a refund redraws it straight away.
        publishWidgetDigest()
        // A New York purchase, restore or refund changes which planned periods this device reminds about.
        replanReminders()
    }

    // States

    /** Browse shows this state from now on, and after a relaunch. */
    fun setBrowseState(code: String) {
        val choice = BrowseChoice(code)
        if (_state.value.browseChoice == choice) return
        stores.saveBrowseChoice(choice)
        _state.update { it.copy(browseChoice = choice) }
    }

    // Introduction

    fun completeOnboarding() {
        val done = OnboardingState(OnboardingCopy.VERSION)
        stores.saveOnboarding(done)
        _state.update { it.copy(onboarding = done) }
    }

    // Rating prompt

    fun recordForegroundLaunch() = scope.launch {
        lock.withLock {
            reviewPrompter.recordLaunch()
            stores.saveReviewPrompt(reviewPrompter.state)
        }
    }

    fun notePlantingAlertOpened(id: String) {
        waterOpenedFromAlert = id
    }

    /** The person went back from a water's page: the end of a task, the only time the app may ask for a review. */
    fun finishedWithWater(id: String, isBusy: Boolean) = scope.launch {
        lock.withLock {
            val fromAlert = waterOpenedFromAlert == id
            if (fromAlert) waterOpenedFromAlert = null
            val st = _state.value
            if (st.loadError != null || !ReviewLaunchOverride.allowsAsking(context)) return@withLock
            val busy = isBusy || st.isRefreshing || st.primingFor != null
            val moment = if (fromAlert) ReviewMoment.READ_PLANTING_ALERT else ReviewMoment.FINISHED_WITH_WATER
            if (!reviewPrompter.considerAsking(moment, !st.favorites.isEmpty, appVersion, busy)) return@withLock
            stores.saveReviewPrompt(reviewPrompter.state)
            _reviewRequests.update { it + 1 }
        }
    }

    // Refresh

    /** Launch and return to the foreground: fetches unless a check ran too recently. `null` when it skipped. */
    suspend fun refreshIfDue(now: Instant = Instant.now()): RefreshOutcome? {
        val s = loaded.await() ?: return null
        if (inFlight == null && !throttle.isDue(s.meta, now)) return null
        return refresh(now)
    }

    /** Swipe down to refresh, past the throttle. */
    suspend fun refreshNow(): RefreshOutcome = refresh(Instant.now())

    /** WorkManager's periodic work. */
    suspend fun performBackgroundRefresh(): RefreshOutcome = refresh(Instant.now())

    /** Joins the refresh already running, or starts one, so two callers never race two GETs. */
    private suspend fun refresh(now: Instant): RefreshOutcome {
        val (deferred, owner) = synchronized(this) {
            inFlight?.let { it to false } ?: CompletableDeferred<RefreshOutcome>().also { inFlight = it }.let { it to true }
        }
        if (!owner) return deferred.await()
        _state.update { it.copy(isRefreshing = true) }
        val outcome = try {
            runRefresh(now)
        } catch (e: Exception) {
            RefreshOutcome.Failed(e.message ?: e.toString())
        } finally {
            synchronized(this) { inFlight = null }
            _state.update { it.copy(isRefreshing = false) }
        }
        deferred.complete(outcome)
        return outcome
    }

    private suspend fun runRefresh(now: Instant): RefreshOutcome {
        val s = loaded.await() ?: return RefreshOutcome.Failed("no snapshot store")
        val outcome = withContext(Dispatchers.IO) { refresher.refresh(s, now) }
        // Whatever the outcome: a failure changes only the ledger, and the screen must say so.
        syncFromStore()
        val shown = lock.withLock {
            val st = _state.value
            if (outcome != RefreshOutcome.Updated || st.favorites.isEmpty) return@withLock emptyList()
            // The baseline moves forward for everyone, purchaser or not, so a later
            // purchase doesn't announce what changed while locked.
            val plan = AlertPlanner.plan(s.snapshot, st.favorites.ids, alertState)
            alertState = plan.state
            stores.saveAlertState(alertState)
            // A muted water's baseline moved forward with the rest; only its alert is left out.
            // Each alert needs its own water's state's purchase (DECISIONS 0025).
            FreeTier.alertsToPost(st.muted.unmuted(plan.notifications), s.snapshot, st.entitlements.entitledStates)
        }
        shown.forEach(notifications::post)
        return outcome
    }

    companion object {
        // Holds only the application context, never an activity, so it outlives nothing it shouldn't.
        @SuppressLint("StaticFieldLeak")
        @Volatile
        private var instance: AppEnvironment? = null

        fun get(context: Context): AppEnvironment = instance ?: synchronized(this) {
            instance ?: AppEnvironment(context.applicationContext, SnapshotRefresher(DebugHooks.transport(context.applicationContext)))
                .also { instance = it }
        }
    }
}
