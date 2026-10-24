package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The purchase sheet's words for every state (DECISIONS 0025), the same
 * cases as `PaywallCopyTests.swift` against the same pinned fixture: honest
 * about what the purchase adds and costs, no urgency, and plain about a
 * state whose source has stopped answering, before the buy button.
 */
class PaywallCopyTest {
    private val text: String by lazy { File(TS.swiftFixtures, "v2-wave2.json").readText() }

    private fun state(code: String, raw: String = text): StateInfo =
        requireNotNull(SnapshotDecoder.decode(raw.toByteArray()).state(code)) { "$code must be in the fixture" }

    /** Every line the sheet can show for every state in the fixture. */
    private fun everyLine(raw: String): List<String> {
        val snapshot = SnapshotDecoder.decode(raw.toByteArray())
        val lines = FreeTier.fullAccessFeatures.toMutableList()
        for (s in snapshot.states) {
            lines += FreeTier.stateFeatures(s.name, s.agencyShortName, s.semantics)
            lines += PaywallCopy.terms(s.name)
            lines += PaywallCopy.freshness(s)
        }
        return lines
    }

    @Test fun termsSayOnePaymentPerStateWithNoSubscriptionAndHowToRestore() {
        assertEquals(
            "One payment for Tennessee. No subscription and no account. Each state is its own purchase, " +
                "and Restore purchases brings it back on a new device.",
            PaywallCopy.terms("Tennessee"),
        )
    }

    @Test fun freshnessNamesTheAgencyAndTheDateOfTheLastGoodRead() {
        val tn = state("TN")
        assertTrue("sanity check: the fixture's Tennessee check succeeded", tn.lastAttemptOK)
        assertEquals(
            "Latest update read from TWRA: Sep 13, 2026. Alerts follow TWRA's own page and are never more current than it is.",
            PaywallCopy.freshness(tn),
        )
        assertEquals(
            "Latest update read from NYS DEC: Sep 13, 2026. Alerts follow NYS DEC's own page and are never more current than it is.",
            PaywallCopy.freshness(state("NY")),
        )
    }

    /** Tennessee's real source refused the pipeline from 2026-10-15 on (issue #97). A buyer must see that on the sheet itself. */
    @Test fun aFailedCheckIsSaidBeforeTheBuyButton() {
        val marker = text.indexOf("\"code\": \"TN\"")
        assertTrue("TN must be in the fixture", marker >= 0)
        val flag = text.indexOf("\"last_attempt_ok\": true", marker)
        assertTrue("the TN entry must carry last_attempt_ok, or this sabotage would change nothing", flag >= 0)
        val sabotaged = text.substring(0, flag) + "\"last_attempt_ok\": false" + text.substring(flag + "\"last_attempt_ok\": true".length)
        val tn = state("TN", sabotaged)
        assertFalse("the sabotage must actually apply", tn.lastAttemptOK)
        assertEquals(
            "Trout Truck's newest check of TWRA failed, so what you see is still the update read on Sep 13, 2026. " +
                "Alerts for Tennessee resume when TWRA's page can be read again.",
            PaywallCopy.freshness(tn),
        )
        // The other states are untouched.
        assertTrue(state("NY", sabotaged).lastAttemptOK)
    }

    @Test fun noLineOnTheSheetUsesUrgencyOrAPromiseTheDataCannotKeep() {
        val lines = everyLine(text)
        assertTrue("every state's lines must be checked", lines.size >= 2 + 5 * 4)
        for (line in lines) {
            val words = line.lowercase()
            for (banned in PaywallCopy.bannedWords) {
                val pattern = Regex("\\b${Regex.escape(banned)}\\b")
                assertFalse("\"$banned\" must not appear on the purchase sheet: $line", pattern.containsMatchIn(words))
            }
        }
    }

    /** Negative control: the check above would catch the footnote the sheet had before. */
    @Test fun negativeControlTheOldFootnoteWouldFail() {
        val old = "One payment, forever, for this state. No subscription, no account. Each state is its own purchase."
        assertTrue(PaywallCopy.bannedWords.any { Regex("\\b${Regex.escape(it)}\\b").containsMatchIn(old.lowercase()) })
        assertNotEquals(old, PaywallCopy.terms("New York"))
    }
}
