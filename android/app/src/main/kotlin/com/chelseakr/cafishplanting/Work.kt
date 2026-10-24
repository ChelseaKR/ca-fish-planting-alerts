package com.chelseakr.cafishplanting

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.chelseakr.cafishplanting.core.PlannedReminder
import com.chelseakr.cafishplanting.core.RefreshOutcome
import com.chelseakr.cafishplanting.core.WidgetDigest
import com.chelseakr.cafishplanting.widget.FavoriteWatersWidget
import androidx.glance.appwidget.updateAll
import java.time.Duration
import java.time.Instant
import java.time.LocalTime
import java.time.ZoneId
import java.util.concurrent.TimeUnit

/**
 * The background refresh: WorkManager runs it about once a day when there
 * is a network, and Android decides exactly when, which is honest only
 * because the source is weekly (About says so). The same work as the iOS
 * app's `BGAppRefreshTask`: refresh, replan, and for a purchaser post alerts.
 */
class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = when (AppEnvironment.get(applicationContext).performBackgroundRefresh()) {
        RefreshOutcome.Updated, RefreshOutcome.NotModified -> Result.success()
        is RefreshOutcome.Failed -> Result.retry()
    }

    companion object {
        const val NAME = "snapshot-refresh"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<RefreshWorker>(24, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setInitialDelay(1, TimeUnit.HOURS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}

/**
 * Shows one planned-period reminder (New York) on the first day of its
 * period. The words travel in the work's input, so nothing is read or
 * fetched when it fires.
 */
class ReminderWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val id = inputData.getString(KEY_ID) ?: return Result.failure()
        val waterID = inputData.getString(KEY_WATER) ?: return Result.failure()
        val title = inputData.getString(KEY_TITLE) ?: return Result.failure()
        val body = inputData.getString(KEY_BODY) ?: return Result.failure()
        AppEnvironment.get(applicationContext).notifications.postReminder(id, waterID, title, body)
        return Result.success()
    }

    companion object {
        const val TAG = "planned-reminder"
        private const val KEY_ID = "id"
        private const val KEY_WATER = "water"
        private const val KEY_TITLE = "title"
        private const val KEY_BODY = "body"

        /** Local time of day a reminder shows, as on iOS. */
        val FIRE_TIME: LocalTime = LocalTime.of(9, 0)

        /**
         * Replaces every pending reminder with [reminders]: each shows at 9
         * a.m. local time on the first day of its period. A reminder whose
         * moment has passed is not scheduled.
         */
        fun replace(context: Context, reminders: List<PlannedReminder>, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault()) {
            val work = WorkManager.getInstance(context)
            work.cancelAllWorkByTag(TAG)
            for (r in reminders) {
                val fireAt = r.fireOn.toLocalDate().atTime(FIRE_TIME).atZone(zone).toInstant()
                val wait = Duration.between(now, fireAt)
                if (wait.isNegative) continue
                val request = OneTimeWorkRequestBuilder<ReminderWorker>()
                    .setInitialDelay(wait.toMillis(), TimeUnit.MILLISECONDS)
                    .addTag(TAG)
                    .setInputData(
                        Data.Builder()
                            .putString(KEY_ID, r.id).putString(KEY_WATER, r.waterID)
                            .putString(KEY_TITLE, r.title).putString(KEY_BODY, r.body)
                            .build(),
                    )
                    .build()
                work.enqueueUniqueWork(r.id, ExistingWorkPolicy.REPLACE, request)
            }
        }
    }
}

/** Redraws the widget. No network: it re-reads the digest file. */
class WidgetRedrawWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        FavoriteWatersWidget().updateAll(applicationContext)
        return Result.success()
    }
}

object WidgetUpdates {
    private const val STALE_NAME = "widget-week-ended"
    private const val NOW_NAME = "widget-redraw"

    /**
     * Redraws now, and again at midnight after the week's Saturday (Los
     * Angeles time), when "This week" has to stop even if the app hasn't run.
     */
    fun redraw(context: Context, digest: WidgetDigest) {
        val work = WorkManager.getInstance(context)
        work.enqueueUniqueWork(NOW_NAME, ExistingWorkPolicy.REPLACE, OneTimeWorkRequestBuilder<WidgetRedrawWorker>().build())
        val wait = Duration.between(Instant.now(), digest.staleAt)
        if (!wait.isNegative) {
            work.enqueueUniqueWork(
                STALE_NAME,
                ExistingWorkPolicy.REPLACE,
                OneTimeWorkRequestBuilder<WidgetRedrawWorker>().setInitialDelay(wait.toMillis() + 60_000, TimeUnit.MILLISECONDS).build(),
            )
        }
    }
}
