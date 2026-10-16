import Foundation
import UserNotifications
import PlantingCore

/// Planting alerts are the phone's local notifications; watchOS shows them
/// on the wrist when the phone is locked. This registers the same category
/// as the phone (`PlantingAlertAction`), so "Mute this water" shows on the
/// watch too, and handles what watchOS hands the watch app:
///
/// - a tap on the alert opens that water here;
/// - "Mute this water" asks the phone to mute it (`WatchModel.requestMute`),
///   which applies it the same way as the phone's own button.
///
/// The watch schedules nothing and asks for no permission.
final class WatchNotificationResponder: NSObject, UNUserNotificationCenterDelegate {
    static let shared = WatchNotificationResponder()

    func install(on center: UNUserNotificationCenter = .current()) {
        center.delegate = self
        let mute = UNNotificationAction(identifier: PlantingAlertAction.muteIdentifier,
                                        title: PlantingAlertAction.muteTitle, options: [])
        center.setNotificationCategories([
            UNNotificationCategory(identifier: PlantingAlertAction.categoryIdentifier, actions: [mute], intentIdentifiers: []),
        ])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        guard let id = WaterLink.waterID(fromNotificationUserInfo: response.notification.request.content.userInfo) else { return }
        switch response.actionIdentifier {
        case UNNotificationDefaultActionIdentifier:
            await MainActor.run { WatchModel.shared.openWaterID = id }
        case PlantingAlertAction.muteIdentifier:
            await MainActor.run { WatchModel.shared.requestMute(id) }
        default:
            break
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}
