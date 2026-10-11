import Foundation

/// Whether the person has been through the introduction. A file in the app's
/// own directory, like favorites, rather than `UserDefaults`, so the app
/// still calls no required-reason API (`PrivacyInfo.xcprivacy`).
public struct OnboardingState: Codable, Equatable, Sendable {
    /// The introduction's version the person finished or skipped. A later
    /// version with something new to say raises `OnboardingCopy.version`.
    public var completedVersion: Int

    public init(completedVersion: Int = 0) { self.completedVersion = completedVersion }

    /// The introduction shows once, on a first launch. Someone updating from
    /// a version without it who already keeps favorites knows the app, so it
    /// doesn't stop them.
    public func shouldShow(hasFavorites: Bool, currentVersion: Int = OnboardingCopy.version) -> Bool {
        completedVersion < currentVersion && !hasFavorites
    }
}

extension AppStorageLayout {
    public var onboardingFile: URL { directory.appendingPathComponent("onboarding.json") }
}

/// A missing file means "not seen yet". A corrupt one reads the same, so the
/// worst a disk problem does is show the introduction once more.
public struct OnboardingStore: Sendable {
    let file: JSONFileStore<OnboardingState>
    public init(layout: AppStorageLayout) { file = JSONFileStore(url: layout.onboardingFile) }

    public func load() -> OnboardingState {
        (try? file.load()) ?? OnboardingState()
    }

    public func save(_ state: OnboardingState) throws {
        try file.save(state)
    }
}

/// The words of the introduction, kept apart from the view so a test can
/// hold them to the app's rules: a week, never a day; "scheduled", never
/// "stocked"; no price; and alerts named as part of full access.
public enum OnboardingCopy {
    /// Raise when a page says something a returning person should see.
    public static let version = 1

    public struct Page: Equatable, Identifiable, Sendable {
        public let id: String
        public let systemImage: String
        public let title: String
        public let body: String
        public let points: [String]
    }

    public static let pages: [Page] = [
        Page(id: "welcome",
             systemImage: "box.truck.fill",
             title: "Welcome to Trout Truck",
             body: "California's fish planting schedule from the Department of Fish and Wildlife, a week at a time.",
             points: [
                 "Every water on CDFW's weekly schedule",
                 "Each water's week-by-week history, which CDFW's own page doesn't keep",
             ]),
        Page(id: "browse",
             systemImage: "map.fill",
             title: "Find your waters",
             body: "Browse by region and county, or search by a water's name, a name CDFW used before, or its county.",
             points: [
                 "Waters on the current week's schedule are tagged This week",
                 "Pull down on a list to check for a newer schedule",
             ]),
        Page(id: "favorites",
             systemImage: "star.fill",
             title: "Star the waters you fish",
             body: "Favorites, browsing and history are free and unlimited.",
             points: [
                 "Full access, a one-time purchase, adds an alert when a favorite is newly on the schedule",
                 "It also adds a Favorite waters widget for your Home Screen and Lock Screen",
                 "Mute one water's alerts from the alert itself, and keep it as a favorite",
             ]),
        Page(id: "honest",
             systemImage: "calendar.badge.checkmark",
             title: "A week, never a day",
             body: "CDFW schedules plants by the week and says plans can change, so the app shows the week and says \"scheduled\".",
             points: [
                 "If the app can't check for a newer schedule, it says so and keeps the last one, labeled with its week",
                 "No account and no tracking. Favorites stay on this device",
             ]),
    ]
}
