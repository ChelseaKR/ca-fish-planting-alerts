package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The same cases as `FeedbackMailTests.swift`. */
class FeedbackMailTest {
    @Test fun theSubjectCarriesTheVersionAndPlatform() {
        assertEquals("Trout Truck 1.2.0 for Android", FeedbackMail.subject("1.2.0", "Android"))
        assertEquals(
            "mailto:chelsea@chelseakr.com?subject=Trout%20Truck%201.2.0%20for%20Android",
            FeedbackMail.url("1.2.0", "Android"),
        )
    }

    @Test fun aMissingVersionIsLeftOutNeverShownAsAValue() {
        for (missing in listOf(null, "", "  ")) {
            val subject = FeedbackMail.subject(missing, "Android")
            assertEquals("Trout Truck for Android", subject)
            assertFalse(subject.contains("null") || subject.contains("unknown"))
        }
    }

    @Test fun spacesAreNeverPlusSigns() {
        val url = FeedbackMail.url("1.0.0 (7)", "Android")
        assertFalse(url.contains("+"))
        assertTrue(url.endsWith("subject=Trout%20Truck%201.0.0%20%287%29%20for%20Android"))
    }

    @Test fun theFootnoteNamesTheAddressSoItWorksWithoutAnEmailApp() {
        assertTrue(FeedbackMail.ROW_FOOTNOTE.contains(FeedbackMail.ADDRESS))
        assertEquals("Write to the developer", FeedbackMail.ROW_TITLE)
        assertEquals("Questions and corrections", FeedbackMail.SECTION_HEADER)
    }
}
