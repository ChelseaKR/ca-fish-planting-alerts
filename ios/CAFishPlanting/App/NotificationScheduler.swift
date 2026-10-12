import Foundation
import UserNotifications
import PlantingCore

/// The app's only scheduling of `UserNotifications`: request permission
/// once, and schedule deterministic-identifier local notifications the OS
/// naturally dedupes. One category with one button ("Mute this water",
/// `PlantingAlertAction`), no badge, no server-sent content — everything in
/// the notification is built on-device from the snapshot already on disk.
/// A tap or the button is handled by `NotificationResponder`.
struct NotificationScheduler {
    let center: UNUserNotificationCenter
    init(center: UNUserNotificationCenter = .current()) { self.center = center }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await center.notificationSettings().authorizationStatus
    }

    /// Shows the system permission prompt. Call only after the app has
    /// already told the person, in its own words, what will and will not
    /// happen (see `FirstFavoriteExplainer` in `AppEnvironment`).
    @discardableResult
    func requestAuthorization() async -> Bool {
        (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
    }

    /// Registers the planting alert's button. iOS keeps the set per
    /// install; call at every launch, from `App.init()`, so an alert that
    /// arrives after an update still has it.
    ///
    /// The button doesn't open the app (no `.foreground`): iOS runs the app
    /// in the background long enough for `NotificationResponder` to save the
    /// mute. It isn't `.destructive` either: the water stays a favorite.
    func registerCategories() {
        let mute = UNNotificationAction(identifier: PlantingAlertAction.muteIdentifier,
                                        title: PlantingAlertAction.muteTitle,
                                        options: [],
                                        icon: UNNotificationActionIcon(systemImageName: "bell.slash"))
        let category = UNNotificationCategory(identifier: PlantingAlertAction.categoryIdentifier,
                                              actions: [mute],
                                              intentIdentifiers: [],
                                              options: [])
        center.setNotificationCategories([category])
    }

    /// Clears the alerts already delivered for one water from Notification
    /// Center: its screen is open, so they have been read. Pending ones stay.
    func removeDelivered(forWater id: Water.ID) async {
        let delivered = await center.deliveredNotifications()
        let ids = delivered
            .filter { WaterLink.waterID(fromNotificationUserInfo: $0.request.content.userInfo) == id }
            .map(\.request.identifier)
        if !ids.isEmpty { center.removeDeliveredNotifications(withIdentifiers: ids) }
    }

    /// Schedules one local notification per planned water. A short fixed
    /// delay (not "now") avoids a UNTimeIntervalNotificationTrigger of 0,
    /// which UNUserNotificationCenter rejects.
    func schedule(_ notifications: [PlannedNotification]) async {
        for notification in notifications {
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
            let request = UNNotificationRequest(identifier: notification.id, content: Self.content(for: notification), trigger: trigger)
            try? await center.add(request)
        }
    }

    /// The alert for one water. It carries that water's ID so a tap opens
    /// it (`NotificationResponder`), and alerts for the same water group
    /// together in Notification Center.
    static func content(for notification: PlannedNotification) -> UNNotificationContent {
        let content = UNMutableNotificationContent()
        content.title = notification.title
        content.body = notification.body()
        content.sound = .default
        content.userInfo = notification.userInfo
        content.threadIdentifier = notification.waterID
        content.categoryIdentifier = PlantingAlertAction.categoryIdentifier
        return content
    }
}
