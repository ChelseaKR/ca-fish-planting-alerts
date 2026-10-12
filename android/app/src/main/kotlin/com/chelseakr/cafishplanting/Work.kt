package com.chelseakr.cafishplanting

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.chelseakr.cafishplanting.core.RefreshOutcome
import com.chelseakr.cafishplanting.core.WidgetDigest
import com.chelseakr.cafishplanting.widget.FavoriteWatersWidget
import androidx.glance.appwidget.updateAll
import java.time.Duration
import java.time.Instant
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
