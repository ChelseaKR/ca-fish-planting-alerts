package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.time.Instant

/**
 * New York (DECISIONS 0034): a once-a-year spring plan in the agency's own
 * words, the same cases as the New York half of `StatesWave2Tests.swift`,
 * against the same pinned fixture (real pipeline output trimmed to a few
 * waters per state). The fixture's states are at the week of 2026-10-18,
 * after New York's spring plan; tests that need the plan ahead of them move
 * New York's current week to March by string substitution, as Swift does.
 */
class NewYorkTest {
    private val text: String by lazy { File(TS.swiftFixtures, "v2-wave2.json").readText() }
    private val snapshot: Snapshot by lazy { SnapshotDecoder.decode(text.toByteArray()) }

    private fun decode(raw: String): Snapshot = SnapshotDecoder.decode(raw.toByteArray())

    /** [raw] with the first [old] after [marker] replaced; fails, rather than changing nothing, when either is missing. */
    private fun replaceAfter(raw: String, marker: String, old: String, new: String): String {
        val from = raw.indexOf(marker)
        assertTrue("marker $marker must be in the fixture", from >= 0)
        val at = raw.indexOf(old, from)
        assertTrue("$old must follow $marker", at >= 0)
        return raw.substring(0, at) + new + raw.substring(at + old.length)
    }

    private val inMarch: Snapshot by lazy {
        var raw = text
        for ((old, new) in listOf(
            "\"start\": \"2026-10-18\"" to "\"start\": \"2026-03-01\"",
            "\"end\": \"2026-10-24\"" to "\"end\": \"2026-03-07\"",
            "\"label\": \"week of 2026-10-18\"" to "\"label\": \"week of 2026-03-01\"",
        )) raw = replaceAfter(raw, "\"code\": \"NY\"", old, new)
        val s = decode(raw)
        assertEquals("the move must land", "week of 2026-03-01", s.state("NY")?.currentWeek?.label)
        assertEquals("and touch New York alone", "week of 2026-10-18", s.state("TN")?.currentWeek?.label)
        s
    }

    private val july5 = Week(PlainDate(2026, 7, 5), PlainDate(2026, 7, 11), "week of 2026-07-05")
    private val genesee = "ny-allegany-amity-genesee-river"
    private val crandall = "ny-cattaraugus-ashford-crandall-pond"

    // The decoder

    @Test fun newYorkDecodesAsAPlanInTheAgencysWords() {
        val s = snapshot
        assertEquals(listOf("CA", "MA", "MI", "NY", "TN"), s.states.map { it.code })
        val ny = s.state("NY")!!
        assertEquals(StateSemantics.PLAN, ny.semantics)
        assertEquals(listOf(DatePrecision.APPROXIMATE), ny.datePrecisions)
        assertEquals("Spring stocking plan", ny.kindLabel)
        assertFalse(ny.removalInference)
        val waters = s.watersInState("NY")
        assertEquals(5, waters.size)
        for (plant in waters.flatMap { it.plants }) {
            assertEquals(DatePrecision.APPROXIMATE, plant.week.precision)
            assertEquals(PlantStatus.LISTED, plant.status)
            assertTrue(plant.week.label, plant.week.label.endsWith(", 2026"))
        }
        assertTrue(waters.all { it.semantics == StateSemantics.PLAN && it.agencyShortName == "NYS DEC" })
        // Nothing was left out: every state in the file is one this build sells.
        for (state in s.states) assertNotNull(state.code, StateProducts.productID(state.code))
        val decoded = SnapshotDecoder.decodeReporting(text.toByteArray())
        assertTrue(decoded.ignored.toString(), decoded.ignored.isEmpty)
    }

    @Test fun theOtherStatesInTheSameFileAreUnchanged() {
        val s = snapshot
        assertEquals(StateSemantics.REPORT, s.state("MI")?.semantics)
        assertEquals(StateSemantics.REPORT, s.state("MA")?.semantics)
        assertEquals(StateSemantics.SCHEDULE, s.state("TN")?.semantics)
        assertEquals("Shutesbury", s.water("ma-34103-272")?.countyLabel)
    }

    @Test fun newYorksProductIsItsOwnAndCaliforniasIsUnchanged() {
        assertEquals("state_ny", StateProducts.productID("NY"))
        assertEquals("com.chelseakr.cafishplanting.state.ny", StateProducts.appStoreProductIDsByState["NY"])
        assertEquals("fullaccess", StateProducts.productID("CA"))
        assertEquals("state_tn", StateProducts.productID("TN"))
        assertEquals("state_ma", StateProducts.productID("MA"))
        assertEquals("state_mi", StateProducts.productID("MI"))
        assertEquals(setOf("fullaccess", "state_tn", "state_ma", "state_mi", "state_ny"), StateProducts.allProductIDs)
        assertEquals(setOf("NY"), StateProducts.entitledStates(setOf("state_ny")))
        assertTrue(StateProducts.isKnown("NY"))
        assertFalse(StateProducts.isKnown("OR"))
        // The same ids on both stores, state for state.
        assertEquals(StateProducts.productIDsByState.keys, StateProducts.appStoreProductIDsByState.keys)
        for ((state, play) in StateProducts.productIDsByState) {
            val store = StateProducts.appStoreProductIDsByState.getValue(state)
            assertTrue("$state: $play vs $store", store.endsWith(if (state == "CA") ".fullaccess" else ".state.${state.lowercase()}"))
            assertEquals(state, if (state == "CA") play.removePrefix("fullaccess").let { "CA" } else play.removePrefix("state_").uppercase())
        }
    }

    // Words

    @Test fun aPlanSaysPlannedForInTheAgencysWordsNeverADate() {
        val s = inMarch
        val water = s.water(genesee)!!
        val line = ScheduleWording.lastScheduledLine(water, s.currentWeek(water))
        assertEquals("Planned for March - third week, 2026", line)
        assertFalse("never a date: $line", line.contains("2026-0"))
        assertEquals("Planned for March - third week, 2026", ScheduleWording.nextScheduledLine(water, s.currentWeek(water)))
        assertFalse(line.lowercase().contains("scheduled"))
    }

    @Test fun aPlanWaterWithNothingAheadSaysSoHonestly() {
        val water = snapshot.water(crandall)!!
        assertNull(ScheduleWording.nextScheduledLine(water, july5))
        assertEquals("Last planned for Mid April, 2026", ScheduleWording.lastScheduledLine(water, july5))
    }

    @Test fun thePurchaseSheetAndThePrimingSheetSpeakOfAPlan() {
        assertEquals(
            listOf(
                "A reminder on this device when a New York favorite's planned stocking period begins, in NYS DEC's own words",
                "New York favorites in the Favorite waters widget",
            ),
            FreeTier.stateFeatures("New York", "NYS DEC", StateSemantics.PLAN),
        )
        val priming = NotificationPrimingCopy("Crandall Pond", false, "NYS DEC", StateSemantics.PLAN)
        val words = priming.points.map { it.text }
        assertTrue(words.toString(), words[0].startsWith("When NYS DEC's spring plan lists Crandall Pond or another favorite"))
        assertTrue(words[0].contains("a reminder when each planned period begins"))
        assertEquals("No other notifications: no marketing and no badges.", words[2])
        // The other semantics keep their words.
        assertEquals(
            "No other notifications: no marketing, no reminders, no badges.",
            NotificationPrimingCopy("X", true, "TWRA", StateSemantics.SCHEDULE).points[2].text,
        )
    }

    // Alerts

    @Test fun aPlanAlertSaysPlannedAndNeverScheduledOrStocked() {
        val s = inMarch
        val plan = AlertPlanner.plan(s, listOf(crandall), AlertState())
        val n = plan.notifications.single()
        assertEquals("Crandall Pond is in the stocking plan", n.title)
        assertEquals(
            "Planned for Mid April, 2026 (Rainbow Trout), in NYS DEC's own words. A plan, not a date, and not a confirmed stocking.",
            n.body(),
        )
        assertTrue("planned again: nothing new", AlertPlanner.plan(s, listOf(crandall), plan.state).notifications.isEmpty())
    }

    @Test fun anApproximateKeyKeepsTheAgencysWordsThroughAStoredBaseline() {
        val key = PlantKey(snapshot.water(crandall)!!.plants.first())
        assertEquals(DatePrecision.APPROXIMATE, key.precision)
        assertEquals("Mid April, 2026", key.phrase)
        val stored = kotlinx.serialization.json.Json.encodeToString(PlantKey.serializer(), key)
        assertEquals(key, kotlinx.serialization.json.Json.decodeFromString(PlantKey.serializer(), stored))
        // A baseline written before New York has no text and reads as it did.
        val old = kotlinx.serialization.json.Json.decodeFromString(
            PlantKey.serializer(), "{\"weekStart\":\"2026-12-01\",\"species\":\"Rainbow Trout\",\"precision\":\"month\"}",
        )
        assertNull(old.text)
        assertEquals("December 2026", old.phrase)
    }

    // Reminders

    @Test fun remindersOnlyForTightPlannedPeriodsInBoughtStatesAndNotMuted() {
        val s = snapshot
        val today = PlainDate(2026, 2, 1)
        val reminders = ReminderPlanner.reminders(s, listOf(genesee), setOf("NY"), emptySet(), today)
        assertEquals(
            listOf("March - third week, 2026", "April - first week, 2026", "April - third week, 2026", "May - first week, 2026"),
            reminders.map { it.periodLabel },
        )
        assertEquals(listOf("Brown Trout", "Rainbow Trout"), reminders.first().species)
        assertEquals(PlainDate(2026, 3, 15), reminders.first().fireOn)
        for (r in reminders) {
            assertEquals("Genesee River: planned stocking period", r.title)
            assertTrue(r.body, r.body.startsWith("NYS DEC plans to stock Genesee River in ${r.periodLabel}"))
            assertTrue(r.body, r.body.endsWith("A plan in NYS DEC's own words, not a date and not a confirmed stocking."))
            assertTrue(r.id.startsWith(PlannedReminder.ID_PREFIX))
            val period = s.water(genesee)!!.plants.first { it.week.start == r.fireOn }.week
            assertTrue(period.spanDays <= ReminderPlanner.MAX_SPAN_DAYS)
        }
        assertEquals(
            "ids are deterministic, so a replan replaces rather than duplicates",
            reminders.map { it.id }, ReminderPlanner.reminders(s, listOf(genesee), setOf("NY"), emptySet(), today).map { it.id },
        )
        assertTrue("a reminder needs New York's purchase", ReminderPlanner.reminders(s, listOf(genesee), setOf("CA", "TN"), emptySet(), today).isEmpty())
        assertTrue("a muted favorite gets none", ReminderPlanner.reminders(s, listOf(genesee), setOf("NY"), setOf(genesee), today).isEmpty())
        assertTrue("none for a period that has begun", ReminderPlanner.reminders(s, listOf(genesee), setOf("NY"), emptySet(), PlainDate(2026, 12, 31)).isEmpty())
        assertTrue("nor for the day it begins", ReminderPlanner.reminders(s, listOf(genesee), setOf("NY"), emptySet(), PlainDate(2026, 5, 1)).isEmpty())
    }

    @Test fun springAndATwoMonthRangeAreTooLooseToRemindAbout() {
        val today = PlainDate(2026, 1, 1)
        for (id in listOf("ny-albany-berne-thompsons-lake", "ny-albany-city-of-albany-six-mile-waterworks")) {
            val water = snapshot.water(id)!!
            assertTrue(id, water.plants.all { it.week.spanDays > ReminderPlanner.MAX_SPAN_DAYS })
            assertTrue(id, ReminderPlanner.reminders(snapshot, listOf(id), setOf("NY"), emptySet(), today).isEmpty())
        }
        // The control: a tight period in the same state does remind.
        assertEquals(
            listOf("Mid April, 2026"),
            ReminderPlanner.reminders(snapshot, listOf(crandall), setOf("NY"), emptySet(), today).map { it.periodLabel },
        )
    }

    @Test fun aReminderNeedsOnlyItsOwnStatesPurchase() {
        val tn = "tn-monroe-tellico-river"
        val today = PlainDate(2026, 1, 1)
        val reminders = ReminderPlanner.reminders(snapshot, listOf(tn, crandall), setOf("NY"), emptySet(), today)
        assertEquals("a Tennessee favorite never gets a plan reminder", listOf(crandall), reminders.map { it.waterID })
        assertTrue(FreeTier.notificationsAllowed("NY", setOf("NY")))
        assertFalse(FreeTier.notificationsAllowed("NY", setOf("CA", "TN", "MI", "MA")))
        // Even bought, a schedule state's favorite gets no plan reminder.
        assertTrue(ReminderPlanner.reminders(snapshot, listOf(tn), setOf("NY", "TN"), emptySet(), today).isEmpty())
    }

    // The widget

    @Test fun theWidgetSaysPlannedForAPlanFavorite() {
        val s = inMarch
        val meta = SnapshotMeta(lastAttemptAt = Instant.now(), lastSuccessAt = Instant.now(), lastOutcome = "updated")
        val spring = "ny-albany-berne-thompsons-lake"
        val digest = WidgetDigest.build(s, meta, listOf(spring, genesee), locked = false, entitledStates = setOf("NY"))
        assertEquals(3, digest.version)
        val now = Instant.parse("2026-03-01T00:00:00Z")
        val ahead = digest.favorites.first { it.id == genesee }
        assertTrue(ahead.isPlan)
        assertEquals("Planned for March - third week, 2026", digest.statusLine(ahead, now))
        // "Spring" began on March 1: it overlaps the current week, but the
        // agency's words never read as "this week", and nothing is ahead.
        val begun = digest.favorites.first { it.id == spring }
        assertFalse(begun.isListedThisWeek)
        assertEquals("No planned period ahead. Last planned for Spring, 2026", digest.statusLine(begun, now))
        for (line in listOf(digest.statusLine(ahead, now), digest.statusLine(begun, now))) {
            assertFalse(line, line.lowercase().contains("scheduled"))
        }
    }

    // Negative controls: the contract still holds

    @Test fun negativeControlAReportedPlantInAPlanStateIsRefused() {
        val broken = replaceAfter(text, "\"state\": \"NY\"", "\"status\": \"listed\"", "\"status\": \"reported\"")
        assertNotEquals("the sabotage must land", text, broken)
        val e = runCatching { decode(broken) }.exceptionOrNull()
        assertTrue("$e", e is SnapshotDecodingException)
        assertTrue(e?.message, e!!.message!!.contains("plan state"))
    }

    @Test fun negativeControlAnApproximateLabelWithoutItsYearIsRefused() {
        val broken = text.replace("\"label\": \"Mid April, 2026\"", "\"label\": \"Mid April\"")
        assertNotEquals("the sabotage must land", text, broken)
        val e = runCatching { decode(broken) }.exceptionOrNull()
        assertTrue("$e", e is SnapshotDecodingException)
        assertTrue(e?.message, e!!.message!!.contains("is approximate but reads"))
    }

    @Test fun negativeControlAPlanStateWithNoProductHereIsStillLeftOutWhole() {
        // The same fixture with New York renamed to a code this build sells nothing for.
        val renamed = text.replace("\"NY\"", "\"XX\"").replace("\"ny-", "\"xx-")
        assertNotEquals("the sabotage must land", text, renamed)
        assertFalse(StateProducts.isKnown("XX"))
        val decoded = SnapshotDecoder.decodeReporting(renamed.toByteArray())
        assertEquals(listOf("XX"), decoded.ignored.states)
        assertEquals(5, decoded.ignored.waters.size)
        assertTrue(decoded.snapshot.waters.none { it.state == "XX" })
        assertEquals(listOf("CA", "MA", "MI", "TN"), decoded.snapshot.states.map { it.code })
    }

    @Test fun negativeControlAnApproximatePeriodIsNeverTakenForAWeek() {
        // A week must read "week of <start>"; an agency's words in its place are refused for a schedule state.
        val broken = replaceAfter(text, "\"id\": \"tn-greene-dillard-ponds\"", "\"label\": \"week of 2026-10-18\"", "\"label\": \"April - third week, 2026\"")
        assertNotEquals("the sabotage must land", text, broken)
        val e = runCatching { decode(broken) }.exceptionOrNull()
        assertTrue("$e", e is SnapshotDecodingException)
        assertTrue(e?.message, e!!.message!!.contains("is a week but reads"))
    }
}
