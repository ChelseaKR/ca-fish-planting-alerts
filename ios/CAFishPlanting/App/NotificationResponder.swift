import Foundation
import UserNotifications
import PlantingCore

/// The `UNUserNotificationCenter` delegate. It does two things:
///
/// - A tap on an alert opens that water (`AppRouter`), from a cold launch
///   too. The alert carries only the water's ID (`WaterLink`).
/// - An alert that arrives while the app is open still shows as a banner.
///   Without a delegate, iOS files it silently in Notification Center.
///
/// It never schedules anything and never asks for permission: those stay in
/// `NotificationScheduler`, behind the paid unlock (`FreeTier`).
final class NotificationResponder: NSObject, UNUserNotificationCenterDelegate {
    /// `UNUserNotificationCenter.delegate` is weak; this keeps the one
    /// responder alive for the app's lifetime.
    static let shared = NotificationResponder()

    /// Call once, from `App.init()`. Apple requires the delegate to be set
    /// before the app finishes launching, or the tap that launched the app
    /// is never delivered.
    func install(on center: UNUserNotificationCenter = .current()) {
        center.delegate = self
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        guard response.actionIdentifier == UNNotificationDefaultActionIdentifier,
              let id = WaterLink.waterID(fromNotificationUserInfo: response.notification.request.content.userInfo)
        else { return }
        await MainActor.run { AppRouter.shared.request(waterID: id) }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}
