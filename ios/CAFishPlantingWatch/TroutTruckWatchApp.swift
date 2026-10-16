import SwiftUI
import UserNotifications

/// Trout Truck on Apple Watch: the phone's favorite waters, at a glance.
///
/// It shows only what the iPhone app sends (`WatchSync`), so it never
/// fetches anything, never checks a purchase, and never shows more than the
/// phone allows (`FreeTier.watchAllowed`, read on the phone).
@main
struct TroutTruckWatchApp: App {
    @State private var model = WatchModel.shared

    init() {
        // Before launch finishes, so a tap on an alert that launched the
        // app is delivered.
        WatchNotificationResponder.shared.install()
    }

    var body: some Scene {
        WindowGroup {
            WatchRootView()
                .environment(model)
                .tint(.troutTruckWatchGreen)
        }
    }
}

extension Color {
    /// The app's accent in dark mode (watchOS is always dark): the green
    /// the phone uses in dark mode.
    static let troutTruckWatchGreen = Color(red: 0x2E / 255, green: 0x9E / 255, blue: 0x68 / 255)
}
