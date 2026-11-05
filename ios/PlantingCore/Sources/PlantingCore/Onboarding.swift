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
/// hold them to the app's rules: never a day; never "stocked"; no price;
/// alerts named as part of full access; and no state taken as the default
/// (DECISIONS 0049).
public enum OnboardingCopy {
    /// Raise when a page says something a returning person should see.
    public static let version = 2

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
             body: "Trout stocking schedules and reports from state wildlife agencies, each shown the way the agency publishes it.",
             points: [
                 "Schedules, stocking reports and plans, in each agency's own words",
                 "Each water's history, which the agencies' own pages don't keep",
             ]),
        Page(id: "browse",
             systemImage: "map.fill",
             title: "Find your waters",
             body: "Pick a state, then browse by region and county, or search by a water's name, a name the agency used before, or its county.",
             points: [
                 "California waters on the current week's schedule are tagged This week",
                 "Pull down on a list to check for a newer schedule",
             ]),
        Page(id: "favorites",
             systemImage: "star.fill",
             title: "Star the waters you fish",
             body: "Favorites, browsing and history are free and unlimited, in each state.",
             points: [
                 "Full access is a one-time purchase for each state. It adds an alert when a favorite there is newly on the agency's schedule or in its stocking report",
                 "It also adds that state's favorites to a Favorite waters widget for your Home Screen and Lock Screen",
                 "Mute one water's alerts from the alert itself, and keep it as a favorite",
             ]),
        Page(id: "honest",
             systemImage: "calendar.badge.checkmark",
             title: "Never more precise than the agency",
             body: "California schedules plants by the week. Other states report stockings after they happen, or publish a spring plan. The app shows exactly what each agency gives, and says \"scheduled\", \"stocked\" or \"planned\" as it does.",
             points: [
                 "If the app can't check a state's source, it says so and keeps the last data it has, labeled with how current it is",
                 "No account needed. Favorites stay on this device",
             ]),
    ]
}
