import Foundation
import UserNotifications
import PlantingCore

/// The app's only interaction with `UserNotifications`: request permission
/// once, and schedule deterministic-identifier local notifications the OS
/// naturally dedupes. No categories, no actions, no badge, no server-sent
/// content — everything in the notification is built on-device from the
/// snapshot already on disk.
struct NotificationScheduler {
    let center: UNUserNotificationCenter
    init(center: UNUserNotificationCenter = .current()) { self.center = center }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await center.notificationSettings().authorizationStatus
    }

    /// Shows the system permission prompt. Call only after the app has
    /// already told the person, in its own words, what will and will not
    /// happen (see `FirstFavouriteExplainer` in `AppEnvironment`).
    @discardableResult
    func requestAuthorization() async -> Bool {
        (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
    }

    /// Schedules one local notification per planned water. A short fixed
    /// delay (not "now") avoids a UNTimeIntervalNotificationTrigger of 0,
    /// which UNUserNotificationCenter rejects.
    func schedule(_ notifications: [PlannedNotification]) async {
        for notification in notifications {
            let content = UNMutableNotificationContent()
            content.title = notification.title
            content.body = notification.body()
            content.sound = .default
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
            let request = UNNotificationRequest(identifier: notification.id, content: content, trigger: trigger)
            try? await center.add(request)
        }
    }
}
