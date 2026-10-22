package com.chelseakr.cafishplanting.core

import java.time.Duration
import java.time.Instant

/**
 * "At most once per [interval]" for work done on each return to the
 * foreground (asking Google Play again what this account owns). Not thread
 * safe on its own; callers use it from one thread (the main thread).
 */
class ResumeThrottle(private val interval: Duration) {
    private var last: Instant? = null

    /** Records the work as done now, whether or not it was due (for example, a start-up query). */
    fun markRan(now: Instant) {
        last = now
    }

    /** `true` and records [now] when the work is due; `false` when it ran too recently. */
    fun tryRun(now: Instant): Boolean {
        val previous = last
        // A clock that moved back counts as due, as in RefreshThrottle.
        if (previous != null && !Duration.between(previous, now).isNegative && Duration.between(previous, now) < interval) return false
        last = now
        return true
    }
}

/**
 * Whether Android has stopped showing its notification prompt for this
 * install. The "asked" flag file lives in the app's files, which a
 * device-to-device transfer copies, so the flag records which install wrote
 * it ([installStamp], the package's first-install time on this device). A
 * flag from another install, or an older flag with no stamp, means this
 * install has never asked, and the prompt is shown.
 */
object NotificationAskMemory {
    fun flagContents(installStamp: String): String = installStamp

    /** [hasRuntimePermission] is false before Android 13, where there is no prompt to refuse. */
    fun refused(flag: String?, installStamp: String, hasRuntimePermission: Boolean, rationaleWanted: () -> Boolean): Boolean {
        if (!hasRuntimePermission) return false
        if (flag == null || flag.trim() != flagContents(installStamp)) return false
        // Asked on this install, and Android will not explain itself again: a permanent no.
        return !rationaleWanted()
    }
}
