package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration
import java.time.Instant

/** The iOS rating lane's rules (`ReviewPromptTests.swift`), case for case. */
class ReviewPromptTest {
    private val start = Instant.parse("2026-10-01T12:00:00Z")
    private var now = start
    private fun prompter(launches: Int) = ReviewPrompter(ReviewPromptState(launchCount = launches), now = { now })

    @Test fun theFirstLaunchNeverAsks() {
        val p = prompter(1)
        assertFalse(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.1.0", false))
        assertFalse(p.considerAsking(ReviewMoment.FINISHED_WITH_WATER, true, "1.1.0", false))
        assertTrue(p.state.askedAt.isEmpty())
    }

    @Test fun finishingWithAWaterAsksFromTheThirdLaunchAndOnlyWithAFavorite() {
        assertFalse(prompter(2).considerAsking(ReviewMoment.FINISHED_WITH_WATER, true, "1.1.0", false))
        assertFalse(prompter(3).considerAsking(ReviewMoment.FINISHED_WITH_WATER, false, "1.1.0", false))
        val p = prompter(3)
        assertTrue(p.considerAsking(ReviewMoment.FINISHED_WITH_WATER, true, "1.1.0", false))
        assertEquals(listOf(start), p.state.askedAt)
        assertEquals(listOf("1.1.0"), p.state.askedVersions)
    }

    @Test fun readingAnAlertAsksFromTheSecondLaunchButNeverWhenBusy() {
        assertFalse(prompter(2).considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.1.0", true))
        assertTrue(prompter(2).considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.1.0", false))
    }

    @Test fun oncePerVersion120DaysApartAndThreeAYear() {
        val p = prompter(5)
        assertTrue(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.1.0", false))
        assertFalse(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.1.0", false))
        assertFalse(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.2.0", false))
        now = start + Duration.ofDays(120)
        assertTrue(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.2.0", false))
        now = start + Duration.ofDays(240)
        assertTrue(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.3", false))
        now = start + Duration.ofDays(360)
        assertFalse("three in a year", p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.4", false))
        now = start + Duration.ofDays(366)
        assertTrue(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.4", false))
        assertEquals("asks older than a year are dropped", 3, p.state.askedAt.size)
    }

    @Test fun aClockSetBackTreatsTheLastAskAsRecent() {
        val p = prompter(5)
        assertTrue(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.1.0", false))
        now = start - Duration.ofDays(400)
        assertFalse(p.considerAsking(ReviewMoment.READ_PLANTING_ALERT, true, "1.2.0", false))
    }

    @Test fun theRowOffersNothingAndAsksNoQuestion() {
        for (text in listOf(PlayStoreReviewLink.ROW_TITLE, PlayStoreReviewLink.ROW_FOOTNOTE)) {
            for (banned in listOf("?", "free", "reward", "5 star", "love")) assertFalse(text.contains(banned, ignoreCase = true))
        }
        assertEquals("market://details?id=com.chelseakr.cafishplanting", PlayStoreReviewLink.MARKET_URL)
    }
}
