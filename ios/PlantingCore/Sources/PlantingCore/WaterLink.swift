import Foundation

/// The app's own link to one water's screen: `trouttruck://water/<water id>`.
///
/// A tapped alert and the Home Screen widget both open a water through this
/// one format, so they land on the same screen. It is not a web address:
/// opening it never makes a network request, and the only thing it can do is
/// show a water the app already has on this device.
public enum WaterLink {
    /// Registered in the app's `Info.plist` (`CFBundleURLTypes`).
    public static let scheme = "trouttruck"
    static let waterHost = "water"

    /// The key that carries the water's ID in a local notification's
    /// `userInfo`, so a tapped alert can open that water.
    public static let notificationWaterIDKey = "water_id"

    /// `trouttruck://water/cdfw-125`.
    public static func url(for id: Water.ID) -> URL {
        var components = URLComponents()
        components.scheme = scheme
        components.host = waterHost
        components.path = "/" + id
        // `id` is CDFW's own key (`cdfw-<number>`), so this can't fail for
        // a real water. `URLComponents` percent-encodes anything else.
        return components.url ?? URL(string: "\(scheme)://\(waterHost)")!
    }

    /// The water a link points to, or `nil` for anything that isn't one of
    /// this app's water links. Whether the water exists is for the caller
    /// to check against the snapshot.
    public static func waterID(from url: URL) -> Water.ID? {
        guard url.scheme?.lowercased() == scheme,
              url.host?.lowercased() == waterHost
        else { return nil }
        let parts = url.pathComponents.filter { $0 != "/" }
        guard parts.count == 1, let id = parts.first, !id.isEmpty else { return nil }
        return id
    }

    /// The water a tapped notification is about, from its `userInfo`.
    public static func waterID(fromNotificationUserInfo userInfo: [AnyHashable: Any]) -> Water.ID? {
        guard let id = userInfo[notificationWaterIDKey] as? String, !id.isEmpty else { return nil }
        return id
    }
}

/// The app's link to its purchase screen: `trouttruck://unlock`. The
/// widget's locked state uses it, so a tap goes straight to the one-time
/// purchase. Like `WaterLink`, it makes no network request.
public enum UnlockLink {
    static let host = "unlock"

    /// `trouttruck://unlock`.
    public static let url: URL = {
        var components = URLComponents()
        components.scheme = WaterLink.scheme
        components.host = host
        return components.url!
    }()

    /// Whether `url` is this link. Anything after the host is ignored.
    public static func matches(_ url: URL) -> Bool {
        url.scheme?.lowercased() == WaterLink.scheme && url.host?.lowercased() == host
    }
}

extension PlannedNotification {
    /// What the local notification carries so a tap can open this water.
    /// The water's ID only: it is CDFW's public key for the water, and
    /// nothing in it is about the person.
    public var userInfo: [AnyHashable: Any] { [WaterLink.notificationWaterIDKey: waterID] }
}
