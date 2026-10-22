package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.time.Instant

class WidgetDigestTest {
    @get:Rule val tmp = TemporaryFolder()

    private val snapshot = TS.snapshot(
        "2026-09-13",
        listOf(
            TS.water("cdfw-1", "Listed Lake", listOf(TS.plant("2026-09-13", "Rainbow trout"), TS.plant("2026-09-13", "Brown trout"))),
            TS.water("cdfw-2", "Later Lake", listOf(TS.plant("2026-08-30"), TS.plant("2026-09-27"))),
            TS.water("cdfw-3", "Quiet Lake", listOf(TS.plant("2026-08-30"))),
        ),
        listOf(ThisWeekEntry("cdfw-1", "Rainbow trout")),
    )
    private val during = Instant.parse("2026-09-16T12:00:00Z")
    private val after = Instant.parse("2026-09-21T12:00:00Z")

    @Test fun eachFavoriteSaysWhichWeekAndTheLockedOneShowsNone() {
        val d = WidgetDigest.build(snapshot, SnapshotMeta(), listOf("cdfw-3", "cdfw-2", "cdfw-gone", "cdfw-1"), locked = false)
        assertEquals(1, d.missingFavorites)
        assertEquals(listOf("cdfw-1", "cdfw-2", "cdfw-3"), d.favoritesByStatus.map { it.id })
        val byID = d.favorites.associateBy { it.id }
        assertEquals("Scheduled this week: Rainbow trout, Brown trout", d.statusLine(byID.getValue("cdfw-1"), during))
        assertEquals("Scheduled for the week of 2026-09-13: Rainbow trout, Brown trout", d.statusLine(byID.getValue("cdfw-1"), after))
        assertEquals("Next scheduled for the week of 2026-09-27", d.statusLine(byID.getValue("cdfw-2"), during))
        assertEquals(
            "Not listed for the week of 2026-09-13. Last scheduled for the week of 2026-08-30",
            d.statusLine(byID.getValue("cdfw-3"), during),
        )
        assertEquals("This week", d.headline(during))
        assertEquals("Schedule for the week of 2026-09-13", d.headline(after))
        assertEquals("1 favorite scheduled this week", d.summary(during))
        assertNull(d.emptyMessage())
        assertEquals(Instant.parse("2026-09-20T07:00:00Z"), d.staleAt)

        val locked = WidgetDigest.build(snapshot, SnapshotMeta(), listOf("cdfw-1"), locked = true)
        assertTrue(locked.favorites.isEmpty())
        assertEquals("This widget is part of full access, a one-time purchase in Trout Truck.", locked.emptyMessage())
        assertEquals("1 water is listed for the week of 2026-09-13.", locked.scheduleContext())
    }

    @Test fun savesOnlyWhenChangedAndReadsOtherVersionsAsMissing() {
        val layout = AppStorageLayout(tmp.newFolder())
        val d = WidgetDigest.build(snapshot, SnapshotMeta(), listOf("cdfw-1"), locked = false)
        assertTrue(WidgetDigest.save(layout, d))
        assertFalse(WidgetDigest.save(layout, d))
        assertEquals(d, WidgetDigest.load(layout))
        val written = layout.widgetDigestFile.readText()
        val other = written.replace("\"version\": ${WidgetDigest.CURRENT_VERSION}", "\"version\": 99")
        assertNotEquals("the version swap must land", written, other)
        layout.widgetDigestFile.writeText(other)
        assertNull(WidgetDigest.load(layout))
    }
}
