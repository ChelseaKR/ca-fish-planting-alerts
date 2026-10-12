package com.chelseakr.cafishplanting

import android.app.Activity
import com.google.android.play.core.review.ReviewManagerFactory

/**
 * Google Play's in-app review card, the only prompt there is. Play decides
 * whether to show it and never says; the app's own rules
 * (`ReviewPromptPolicy`) decide when it may ask.
 */
object InAppReview {
    fun request(activity: Activity) {
        val manager = ReviewManagerFactory.create(activity)
        manager.requestReviewFlow().addOnCompleteListener { task ->
            if (task.isSuccessful) manager.launchReviewFlow(activity, task.result)
        }
    }
}
