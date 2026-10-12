package com.chelseakr.cafishplanting.core

import kotlinx.serialization.Serializable
import java.time.Duration
import java.time.Instant

/**
 * When the app may ask Google Play for its in-app review card. The same
 * rules as the iOS rating lane (`ReviewPrompt.swift` on
 * feat/ratings-and-water-seo): asks only at the end of a task, never on the
 * first launch, never twice in one app version, at least 120 days apart and
 * at most 3 times in 365 days, and never over anything else on screen.
 * Google Play keeps its own, unpublished quota on top, and may show nothing.
 */
@Serializable
data class ReviewPromptState(
    val launchCount: Int = 0,
    val askedAt: List<@Serializable(with = InstantSerializer::class) Instant> = emptyList(),
    val askedVersions: List<String> = emptyList(),
)

enum class ReviewMoment {
    /** They opened a planting alert and then left that water's page. */
    READ_PLANTING_ALERT,

    /** They left a water's page, in a launch with at least one favorite. */
    FINISHED_WITH_WATER,
}

data class ReviewPromptPolicy(val minimumLaunches: Int = 3, val minimumDaysBetween: Int = 120, val maximumPerYear: Int = 3) {
    fun shouldAsk(moment: ReviewMoment, state: ReviewPromptState, hasFavorites: Boolean, appVersion: String, isBusy: Boolean, now: Instant): Boolean {
        if (isBusy || state.launchCount < 2) return false
        if (moment == ReviewMoment.FINISHED_WITH_WATER && (!hasFavorites || state.launchCount < minimumLaunches)) return false
        if (appVersion in state.askedVersions) return false
        val last = state.askedAt.maxOrNull()
        // A date after `now` (the clock moved back) is treated as recent.
        if (last != null && Duration.between(last, now) < Duration.ofDays(minimumDaysBetween.toLong())) return false
        return state.askedAt.count { Duration.between(it, now) < YEAR } < maximumPerYear
    }

    companion object {
        val STANDARD = ReviewPromptPolicy()
        val YEAR: Duration = Duration.ofDays(365)
    }
}

/** The state, the rules and the clock together. */
class ReviewPrompter(state: ReviewPromptState = ReviewPromptState(), val policy: ReviewPromptPolicy = ReviewPromptPolicy.STANDARD, private val now: () -> Instant = Instant::now) {
    var state: ReviewPromptState = state
        private set

    fun recordLaunch() {
        state = state.copy(launchCount = state.launchCount + 1)
    }

    /** `true` means ask now. The ask is recorded before it is made: Play never says whether it showed. */
    fun considerAsking(moment: ReviewMoment, hasFavorites: Boolean, appVersion: String, isBusy: Boolean): Boolean {
        val date = now()
        if (!policy.shouldAsk(moment, state, hasFavorites, appVersion, isBusy, date)) return false
        state = state.copy(
            askedAt = state.askedAt.filter { Duration.between(it, date) < ReviewPromptPolicy.YEAR } + date,
            askedVersions = if (appVersion in state.askedVersions) state.askedVersions else state.askedVersions + appVersion,
        )
        return true
    }
}

/** The About row that opens the app's Play Store page, where a person can rate it. */
object PlayStoreReviewLink {
    const val PACKAGE = "com.chelseakr.cafishplanting"
    const val MARKET_URL = "market://details?id=$PACKAGE"
    const val ROW_TITLE = "Rate Trout Truck"
    const val ROW_FOOTNOTE = "Opens Google Play, where you can rate the app or write a review."
}
