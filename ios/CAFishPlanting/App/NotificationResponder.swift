import Foundation
import UserNotifications
import PlantingCore

/// The `UNUserNotificationCenter` delegate. It does three things:
///
/// - A tap on an alert opens that water (`AppRouter`), from a cold launch
///   too. The alert carries only the water's ID (`WaterLink`).
/// - The alert's "Mute this water" button turns that water's alerts off
///   (`AppEnvironment.setAlertsMuted`) without opening the app. The water
///   stays a favorite.
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
        NotificationScheduler(center: center).registerCategories()
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        guard let id = WaterLink.waterID(fromNotificationUserInfo: response.notification.request.content.userInfo) else { return }
        switch response.actionIdentifier {
        case UNNotificationDefaultActionIdentifier:
            await MainActor.run { AppRouter.shared.request(waterID: id) }
        case PlantingAlertAction.muteIdentifier:
            // `AppEnvironment.shared` is set in `App.init()`, which runs
            // before this on a background launch too.
            await MainActor.run { AppEnvironment.shared?.setAlertsMuted(true, for: id) }
        default:
            break
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}
