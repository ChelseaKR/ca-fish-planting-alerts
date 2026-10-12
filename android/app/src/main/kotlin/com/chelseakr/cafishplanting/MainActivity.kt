package com.chelseakr.cafishplanting

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.chelseakr.cafishplanting.core.WaterLink
import com.chelseakr.cafishplanting.ui.AppRoot
import com.chelseakr.cafishplanting.ui.TroutTruckTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val app get() = application as TroutTruckApplication

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val env = AppEnvironment.get(this)
        if (savedInstanceState == null) {
            handle(intent)
            env.recordForegroundLaunch()
            if (env.state.value.shouldShowOnboarding) app.router.setOnboarding(true)
        }
        setContent {
            TroutTruckTheme {
                AppRoot(env = env, router = app.router, purchases = app.purchases, activity = this)
            }
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                env.refreshNotificationPermission()
                // Launch and each return to the foreground, at most every 6 hours (30 minutes after a failure).
                env.refreshIfDue()
            }
        }
        lifecycleScope.launch {
            env.reviewRequests.drop(1).collect {
                // After the back animation, so the card doesn't land on it.
                delay(1000)
                InAppReview.request(this@MainActivity)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    private fun handle(intent: Intent?) {
        val url = intent?.data?.toString() ?: return
        if (intent.getBooleanExtra(Notifications.EXTRA_FROM_ALERT, false)) {
            WaterLink.waterID(url)?.let { AppEnvironment.get(this).notePlantingAlertOpened(it) }
        }
        app.router.handle(url)
    }
}
