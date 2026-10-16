package com.chelseakr.cafishplanting

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.chelseakr.cafishplanting.core.WaterLink
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * "Mute this water", without opening the app. Saves the mute, then clears
 * that alert. The water stays a favorite; only its alerts stop.
 */
class MuteReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Notifications.ACTION_MUTE) return
        val id = intent.getStringExtra(WaterLink.NOTIFICATION_WATER_ID_KEY) ?: return
        val tag = intent.getStringExtra(Notifications.EXTRA_TAG)
        val pending = goAsync()
        CoroutineScope(Dispatchers.Default).launch {
            try {
                val env = AppEnvironment.get(context)
                env.setMuted(true, id)
                if (tag != null) env.notifications.cancel(tag)
            } finally {
                pending.finish()
            }
        }
    }
}
