package com.chelseakr.cafishplanting

import android.os.Build
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalView

/**
 * The same moments as the iOS app's `sensoryFeedback`: a firm tap for a
 * success (a favorite added, a refresh that worked, the unlock, the end of
 * the introduction), a warning for a failed refresh, and a light tick for a
 * selection (a favorite removed, a page turned, the alerts switch). Through
 * `View.performHapticFeedback`, so Android skips them when touch feedback is
 * off in Settings.
 */
class Haptics(private val view: View) {
    fun success() = view.performHapticFeedback(if (Build.VERSION.SDK_INT >= 30) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.VIRTUAL_KEY)

    fun warning() = view.performHapticFeedback(if (Build.VERSION.SDK_INT >= 30) HapticFeedbackConstants.REJECT else HapticFeedbackConstants.LONG_PRESS)

    fun selection() = view.performHapticFeedback(if (Build.VERSION.SDK_INT >= 27) HapticFeedbackConstants.KEYBOARD_TAP else HapticFeedbackConstants.VIRTUAL_KEY)
}

@Composable
fun rememberHaptics(): Haptics {
    val view = LocalView.current
    return remember(view) { Haptics(view) }
}
