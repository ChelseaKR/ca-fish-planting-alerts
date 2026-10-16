package com.chelseakr.cafishplanting

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.net.toUri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.chelseakr.cafishplanting.core.PlannedNotification
import com.chelseakr.cafishplanting.core.PlantingAlertAction
import com.chelseakr.cafishplanting.core.WaterLink

/**
 * The app's only notifications: one local alert per water a refresh found
 * newly scheduled, built on this device from the snapshot it downloaded.
 * One channel, one button ("Mute this water"), no badge, nothing from a
 * server. The iOS twin is `NotificationScheduler`.
 */
class Notifications(private val context: Context) {
    private val manager = NotificationManagerCompat.from(context)

    fun createChannel() {
        val channel = NotificationChannel(CHANNEL_ID, context.getString(R.string.channel_alerts_name), NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = context.getString(R.string.channel_alerts_description)
            setShowBadge(false)
        }
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    /** Notifications are on for this app (and, on Android 13+, the permission is granted). */
    fun allowed(): Boolean = manager.areNotificationsEnabled() &&
        (Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)

    /**
     * Whether the priming sheet should show on a first favorite: only while
     * Android would still show its prompt (Android 13+, not yet granted).
     * The activity also checks it hasn't been refused for good.
     */
    fun shouldAsk(): Boolean = Build.VERSION.SDK_INT >= 33 && !allowed()

    fun post(n: PlannedNotification) {
        if (!allowed()) return
        val open = PendingIntent.getActivity(
            context,
            n.id.hashCode(),
            Intent(Intent.ACTION_VIEW, WaterLink.url(n.waterID).toUri(), context, MainActivity::class.java)
                .putExtra(EXTRA_FROM_ALERT, true),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val mute = PendingIntent.getBroadcast(
            context,
            n.id.hashCode(),
            Intent(context, MuteReceiver::class.java)
                .setAction(ACTION_MUTE)
                .putExtra(WaterLink.NOTIFICATION_WATER_ID_KEY, n.waterID)
                .putExtra(EXTRA_TAG, n.id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_trout)
            .setContentTitle(n.title)
            .setContentText(n.body())
            .setStyle(NotificationCompat.BigTextStyle().bigText(n.body()))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setGroup(n.waterID)
            .addAction(NotificationCompat.Action.Builder(R.drawable.ic_bell_off, PlantingAlertAction.MUTE_TITLE, mute).build())
            .addExtras(android.os.Bundle().apply { putString(WaterLink.NOTIFICATION_WATER_ID_KEY, n.waterID) })
            .build()
        try {
            // The tag is the planner's deterministic id, so posting one evaluation twice shows one alert.
            manager.notify(n.id, NOTIFICATION_ID, notification)
        } catch (_: SecurityException) {
            // Permission withdrawn between the check and the post: nothing to show.
        }
    }

    /** The water's page is open: its delivered alerts have been read. */
    fun clearDelivered(waterID: String) {
        val system = context.getSystemService(NotificationManager::class.java)
        system.activeNotifications
            .filter { it.notification.extras.getString(WaterLink.NOTIFICATION_WATER_ID_KEY) == waterID }
            .forEach { manager.cancel(it.tag, it.id) }
    }

    fun cancel(tag: String) = manager.cancel(tag, NOTIFICATION_ID)

    companion object {
        const val CHANNEL_ID = "planting-alerts"
        const val NOTIFICATION_ID = 1
        const val ACTION_MUTE = "com.chelseakr.cafishplanting.action.MUTE"
        const val EXTRA_TAG = "tag"
        const val EXTRA_FROM_ALERT = "from_alert"
    }
}
