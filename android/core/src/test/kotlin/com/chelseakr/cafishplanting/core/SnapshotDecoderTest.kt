package com.chelseakr.cafishplanting.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class SnapshotDecoderTest {
    @Test fun decodesTheMinimalFixture() {
        val s = SnapshotDecoder.decode(TS.minimalValid)
        assertEquals("week of 2026-09-13", s.sourceWeek.label)
        val w = s.water("cdfw-1001")!!
        assertEquals("Lake Siskiyou", w.name)
        assertNull("absence stays absence", w.location)
        assertEquals(listOf("Trout"), w.lastListedSpecies)
        assertEquals(1, s.thisWeekWaterIDs.size)
    }

    @Test fun ignoresUnknownKeys() {
        val s = SnapshotDecoder.decode(TS.minimalValid.replaceFirst("{", """{ "a_new_field": [1, 2, 3],"""))
        assertEquals(1, s.waters.size)
    }

    @Test fun decodesTheBundledRealSnapshot() {
        val s = SnapshotDecoder.decode(TS.bundledSnapshot.readBytes())
        assertTrue(s.waters.count { it.state == "CA" } > 300)
        // A California water always has a week; another state's may have only month letters, never nothing.
        assertTrue(s.waters.filter { it.state == "CA" }.all { it.plants.isNotEmpty() })
        assertTrue(s.waters.all { it.plants.isNotEmpty() || it.monthsNote != null })
    }

    @Test fun refusesContractViolations() {
        val cases = mapOf(
            "schema version" to TS.minimalValid.replace("\"schema_version\": 1", "\"schema_version\": 3"),
            "a v1 body labeled v2" to TS.minimalValid.replace("\"schema_version\": 1", "\"schema_version\": 2"),
            "http url" to TS.minimalValid.replace("\"url\": \"https://nrm.dfg.ca.gov/FishPlants/\"", "\"url\": \"http://nrm.dfg.ca.gov/FishPlants/\""),
            "bad date" to TS.minimalValid.replace("\"stated_today\": \"2026-09-13\"", "\"stated_today\": \"2026-02-30\""),
            "a day not a week" to TS.minimalValid.replace("\"start\": \"2026-09-20\", \"end\": \"2026-09-26\"", "\"start\": \"2026-09-26\", \"end\": \"2026-09-20\""),
            "status" to TS.minimalValid.replaceFirst("\"status\": \"listed\"", "\"status\": \"stocked\""),
            "region" to TS.minimalValid.replace("\"code\": \"R1\"", "\"code\": \"R9\""),
            "water id" to TS.minimalValid.replace("\"id\": \"cdfw-1001\"", "\"id\": \"1001\""),
            "missing field" to TS.minimalValid.replace("\"generated_at\": \"2026-09-13T06:12:44Z\",", ""),
            "timestamp" to TS.minimalValid.replace("2026-09-13T06:12:44Z", "2026-09-13 06:12:44"),
            "truncated" to TS.minimalValid.substring(0, TS.minimalValid.length / 2),
        )
        for ((name, json) in cases) {
            assertTrue("negative control did not apply: $name", json != TS.minimalValid)
            assertThrows(name, SnapshotDecodingException::class.java) { SnapshotDecoder.decode(json) }
        }
    }
}
