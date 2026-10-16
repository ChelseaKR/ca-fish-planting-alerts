package com.chelseakr.cafishplanting.core

import java.text.Collator
import java.text.Normalizer
import java.util.Locale

/**
 * Search and county filter over waters, as `WaterSearch.swift`. Typing
 * matches a water's name, any name CDFW has used for it, and its counties.
 * Case, accents and width don't matter, and every word typed must match.
 */
data class WaterSearch(val text: String = "", val county: String? = null) {
    val isEmpty: Boolean get() = terms.isEmpty() && county == null

    fun matches(water: Water): Boolean {
        if (county != null && county !in water.counties) return false
        val terms = terms
        if (terms.isEmpty()) return true
        val haystack = fold((listOf(water.name) + water.aliases + water.counties).joinToString(" "))
        return terms.all { haystack.contains(it) }
    }

    /** The matching waters, sorted by name. */
    fun filter(waters: List<Water>): List<Water> = waters.filter(::matches).sortedWith(compareBy(NameOrder) { it.name })

    private val terms: List<String>
        get() = fold(text).split(Regex("[\\s,]+")).filter { it.isNotEmpty() }

    companion object {
        /** The counties these waters are in, sorted, each once. */
        fun counties(waters: List<Water>): List<String> = waters.flatMap { it.counties }.distinct().sortedWith(NameOrder)

        fun fold(value: String): String =
            Normalizer.normalize(value, Normalizer.Form.NFKD).replace(Regex("\\p{Mn}+"), "").lowercase(Locale.ROOT)
    }
}

/**
 * Names in the order a person expects (Finder-like, as Swift's
 * `localizedStandardCompare`): case and accents set aside, and runs of
 * digits compared as numbers, so "Pond 2" comes before "Pond 10".
 */
object NameOrder : Comparator<String> {
    private val collator: Collator = Collator.getInstance(Locale.US).apply { strength = Collator.SECONDARY }
    private val chunk = Regex("\\d+|\\D+")

    override fun compare(a: String, b: String): Int {
        val left = chunk.findAll(a).map { it.value }.toList()
        val right = chunk.findAll(b).map { it.value }.toList()
        for (i in 0 until minOf(left.size, right.size)) {
            val x = left[i]
            val y = right[i]
            val result = if (x[0].isDigit() && y[0].isDigit()) {
                compareValuesBy(x, y, { it.trimStart('0').length }, { it.trimStart('0') })
            } else {
                collator.compare(x, y)
            }
            if (result != 0) return result
        }
        return left.size.compareTo(right.size).takeIf { it != 0 } ?: a.compareTo(b)
    }
}
