package com.chelseakr.cafishplanting.core

/**
 * About's "Write to the developer" row: a `mailto:` link with the app's
 * version in the subject, so a report says which build it came from. The
 * iOS twin is `FeedbackMail.swift`, word for word (DECISIONS 0057).
 *
 * The address is the one `/support/` shows. Opening it hands off to the
 * person's email app; the app itself sends nothing.
 */
object FeedbackMail {
    const val ADDRESS = "chelsea@chelseakr.com"
    const val SECTION_HEADER = "Questions and corrections"
    const val ROW_TITLE = "Write to the developer"
    const val ROW_FOOTNOTE =
        "Opens your email app, addressed to $ADDRESS, with the app version in the subject. If a date looks wrong, say which water."

    /** "Trout Truck 1.2.0 for Android", or "Trout Truck for Android" when the build carries no version. */
    fun subject(version: String?, platform: String): String {
        val v = version?.trim().orEmpty()
        return if (v.isEmpty()) "Trout Truck for $platform" else "Trout Truck $v for $platform"
    }

    fun url(version: String?, platform: String): String = "mailto:$ADDRESS?subject=${encode(subject(version, platform))}"

    /** RFC 3986 percent-encoding (a space is %20, never "+", which mail apps show literally). */
    internal fun encode(text: String): String = buildString {
        for (byte in text.toByteArray(Charsets.UTF_8)) {
            val c = byte.toInt() and 0xFF
            val ch = c.toChar()
            if (ch in 'A'..'Z' || ch in 'a'..'z' || ch in '0'..'9' || ch in "-._~") append(ch) else append("%%%02X".format(c))
        }
    }
}
