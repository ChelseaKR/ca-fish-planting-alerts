package com.chelseakr.cafishplanting.core

import java.time.DateTimeException
import java.time.LocalDate

/**
 * A calendar date with no time, an America/Los_Angeles civil date per
 * `schema/README.md`. The wire format is strict `YYYY-MM-DD`
 * (`$defs/date` in `schema/snapshot.v1.json`); anything else is refused.
 * Mirrors `PlainDate` in ios/PlantingCore.
 */
data class PlainDate(val year: Int, val month: Int, val day: Int) : Comparable<PlainDate> {
    val isoDate: String get() = "%04d-%02d-%02d".format(year, month, day)

    override fun toString(): String = isoDate

    override fun compareTo(other: PlainDate): Int =
        compareValuesBy(this, other, PlainDate::year, PlainDate::month, PlainDate::day)

    fun toLocalDate(): LocalDate = LocalDate.of(year, month, day)

    fun plusDays(days: Long): PlainDate = of(toLocalDate().plusDays(days))

    companion object {
        private val ISO = Regex("""^(\d{4})-(\d{2})-(\d{2})$""")

        /** `null` for anything that is not a real `YYYY-MM-DD` date. */
        fun parse(isoDate: String): PlainDate? {
            val match = ISO.matchEntire(isoDate) ?: return null
            val (y, m, d) = match.destructured
            return try {
                of(LocalDate.of(y.toInt(), m.toInt(), d.toInt()))
            } catch (_: DateTimeException) {
                null
            }
        }

        fun of(date: LocalDate): PlainDate = PlainDate(date.year, date.monthValue, date.dayOfMonth)
    }
}

/**
 * The unit of truth, matching `$defs/week`: CDFW publishes "week of <date>"
 * and nothing finer. [label] is the pipeline's own display string
 * ("week of YYYY-MM-DD") and is shown verbatim, never shortened to a day.
 */
data class Week(val start: PlainDate, val end: PlainDate, val label: String) : Comparable<Week> {
    override fun compareTo(other: Week): Int = start.compareTo(other.start)
}
