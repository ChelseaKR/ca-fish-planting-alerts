package com.chelseakr.cafishplanting.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
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
 * How precisely an agency dates a record (`DatePrecision.swift`). California
 * only ever gives a week. Tennessee gives a day, the week of a Sunday, or a
 * month with the day not set yet. Massachusetts and Michigan report the day.
 * New York gives its own words for when ([APPROXIMATE]).
 */
@Serializable
enum class DatePrecision(val wire: String) {
    @SerialName("day") DAY("day"),
    @SerialName("week") WEEK("week"),
    @SerialName("month") MONTH("month"),

    /**
     * The agency's own words for when, verbatim (New York: "April - third
     * week, 2026", "Spring, 2026"). Never shown or treated as a date.
     */
    @SerialName("approximate") APPROXIMATE("approximate"),
    ;

    companion object {
        fun fromWire(value: String): DatePrecision? = entries.firstOrNull { it.wire == value }
    }
}

/**
 * The unit of truth: a period exactly as precise as the agency made it, as
 * `Week.swift`. For California, `$defs/week`: CDFW publishes "week of <date>"
 * and nothing finer. [label] is the pipeline's own display string and is
 * shown verbatim, never reformatted and never shortened to a day: "week of
 * YYYY-MM-DD" for a week, "YYYY-MM-DD" for a day, "December 2026" for a
 * month (`$defs/period` in `schema/snapshot.v2.json`).
 *
 * The type keeps its name because a week is still what most records are.
 */
data class Week(
    /** A week's Sunday, a day, or a month's first day. */
    val start: PlainDate,
    /** A week's Saturday, the same day, or a month's last day. */
    val end: PlainDate,
    val label: String,
    val precision: DatePrecision = DatePrecision.WEEK,
) : Comparable<Week> {
    override fun compareTo(other: Week): Int = start.compareTo(other.start)

    /** The words after "scheduled for" or "last stocked": "the week of 2026-10-11", "2026-10-14", "December 2026". */
    val phrase: String get() = if (precision == DatePrecision.WEEK) "the $label" else label

    /** Days the period spans, counting both ends. */
    val spanDays: Int get() = (end.toLocalDate().toEpochDay() - start.toLocalDate().toEpochDay()).toInt() + 1

    /** True when the period overlaps [other] (a state's current week). */
    fun overlaps(other: Week): Boolean = start <= other.end && end >= other.start
}
