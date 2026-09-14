import Foundation
import BackgroundTasks
import PlantingCore

/// The app's `BGAppRefreshTask` plumbing. iOS decides when this actually
/// runs — typically not more than a few times a day, and never precisely —
/// which is honest here only because the source updates weekly (see
/// `AboutView`, and `docs/APP-STORE.md`'s 2.5.4 justification).
enum BackgroundRefresh {
    static let taskIdentifier = "com.chelseakr.cafishplanting.refresh"

    /// Call once, in `App.init()`, before the app finishes launching.
    static func register(_ work: @escaping @Sendable () async -> RefreshOutcome) {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: taskIdentifier, using: nil) { task in
            guard let refreshTask = task as? BGAppRefreshTask else { task.setTaskCompleted(success: false); return }
            handle(refreshTask, work: work)
        }
    }

    private static func handle(_ task: BGAppRefreshTask, work: @escaping @Sendable () async -> RefreshOutcome) {
        // Always queue the next run before doing anything else, so a crash
        // or an expiration mid-refresh doesn't strand the app with no
        // future refresh scheduled.
        scheduleNextRefresh()

        let runningWork = Task {
            let outcome = await work()
            switch outcome {
            case .updated, .notModified: task.setTaskCompleted(success: true)
            case .failed: task.setTaskCompleted(success: false)
            }
        }
        task.expirationHandler = { runningWork.cancel() }
    }

    /// The source is weekly; refreshing roughly once a day is enough to
    /// land an alert "within the week, not the minute" without polling a
    /// static file needlessly. iOS may run it later than requested, or not
    /// at all in a given day — see `AboutView`.
    static func scheduleNextRefresh(earliestIn seconds: TimeInterval = 24 * 60 * 60) {
        let request = BGAppRefreshTaskRequest(identifier: taskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: seconds)
        try? BGTaskScheduler.shared.submit(request)
    }
}
