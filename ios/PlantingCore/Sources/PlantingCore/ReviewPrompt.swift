import Foundation

/// When the app may ask iOS to show its rating prompt
/// (`AppStore.requestReview`, app target only: this package stays
/// Foundation-only).
///
/// Apple's rules (App Review Guideline 5.6.1) shape all of it: the system
/// prompt is the only one, nothing comes before it that asks whether the
/// person likes the app, and nothing is offered for a rating. iOS itself
/// shows the prompt at most three times in 365 days and may show it fewer
/// times or never; the app keeps its own, stricter count on top of that.
///
/// A file in the app's own directory, like favorites and the introduction,
/// rather than `UserDefaults`, so the app still calls no required-reason API
/// (`PrivacyInfo.xcprivacy`). Nothing in it leaves the device.
public struct ReviewPromptState: Codable, Equatable, Sendable {
    /// Times the app came to the foreground with its window showing. A
    /// launch in the background (the refresh task) doesn't count.
    public var launchCount: Int
    /// When the app asked, newest last. Older than a year is dropped.
    public var askedAt: [Date]
    /// The app versions (`CFBundleShortVersionString`) it has asked in.
    public var askedVersions: [String]

    public init(launchCount: Int = 0, askedAt: [Date] = [], askedVersions: [String] = []) {
        self.launchCount = launchCount
        self.askedAt = askedAt
        self.askedVersions = askedVersions
    }
}

/// The good moments the app may ask after. Both come at the end of
/// something the person did, never in the middle of it: the app asks when
/// they leave a water's page, not while it is open.
///
/// Neither depends on which state's purchase the person owns (DECISIONS
/// 0025, 0028): an alert only exists for a state they unlocked, whichever
/// it is, and a favorite in any state counts.
public enum ReviewMoment: Equatable, Sendable {
    /// They opened a planting alert and then left that water's page.
    case readPlantingAlert
    /// They left a water's page, in a launch with at least one favorite in
    /// any state.
    case finishedWithWater
}

/// The rules, apart from the clock and the file so a test can drive them.
public struct ReviewPromptPolicy: Equatable, Sendable {
    /// Launches before a `finishedWithWater` moment may ask. The first
    /// launch never asks, whatever the moment.
    public var minimumLaunches: Int
    /// Days between two asks.
    public var minimumDaysBetween: Int
    /// Asks in any 365 days. iOS's own cap is three; this one also counts
    /// asks iOS chose not to show.
    public var maximumPerYear: Int

    public init(minimumLaunches: Int = 3, minimumDaysBetween: Int = 120, maximumPerYear: Int = 3) {
        self.minimumLaunches = minimumLaunches
        self.minimumDaysBetween = minimumDaysBetween
        self.maximumPerYear = maximumPerYear
    }

    public static let standard = ReviewPromptPolicy()

    static let day: TimeInterval = 24 * 60 * 60
    static let year: TimeInterval = 365 * day

    /// Whether this moment may ask. `isBusy` is anything else on screen or
    /// under way (the introduction, a sheet, the notification explainer):
    /// the prompt never lands on top of it.
    public func shouldAsk(_ moment: ReviewMoment, state: ReviewPromptState, hasFavorites: Bool,
                          appVersion: String, isBusy: Bool, now: Date) -> Bool {
        guard !isBusy, state.launchCount >= 2 else { return false }
        switch moment {
        case .readPlantingAlert:
            break
        case .finishedWithWater:
            guard hasFavorites, state.launchCount >= minimumLaunches else { return false }
        }
        guard !state.askedVersions.contains(appVersion) else { return false }
        if let last = state.askedAt.max(),
           now.timeIntervalSince(last) < TimeInterval(minimumDaysBetween) * Self.day {
            // Also true when `last` is after `now` (the clock moved back):
            // a date the app can't place is treated as recent.
            return false
        }
        let inLastYear = state.askedAt.filter { now.timeIntervalSince($0) < Self.year }
        return inLastYear.count < maximumPerYear
    }
}

/// The state, the rules and the clock together. The app holds one; a test
/// injects the clock and starts from any counts it likes.
public struct ReviewPrompter: Sendable {
    public private(set) var state: ReviewPromptState
    public let policy: ReviewPromptPolicy
    private let now: @Sendable () -> Date

    public init(state: ReviewPromptState = ReviewPromptState(), policy: ReviewPromptPolicy = .standard,
                now: @escaping @Sendable () -> Date = { Date() }) {
        self.state = state
        self.policy = policy
        self.now = now
    }

    public mutating func recordLaunch() {
        state.launchCount += 1
    }

    /// `true` means: ask now. The ask is recorded before it is made, because
    /// iOS never says whether it showed the prompt.
    public mutating func considerAsking(_ moment: ReviewMoment, hasFavorites: Bool, appVersion: String,
                                        isBusy: Bool) -> Bool {
        let date = now()
        guard policy.shouldAsk(moment, state: state, hasFavorites: hasFavorites, appVersion: appVersion,
                               isBusy: isBusy, now: date) else { return false }
        state.askedAt = state.askedAt.filter { date.timeIntervalSince($0) < ReviewPromptPolicy.year } + [date]
        if !state.askedVersions.contains(appVersion) { state.askedVersions.append(appVersion) }
        return true
    }
}

extension AppStorageLayout {
    public var reviewPromptFile: URL { directory.appendingPathComponent("review-prompt.json") }
}

/// A missing or corrupt file reads as a fresh state. The worst that does is
/// count launches from zero again, which only delays an ask; iOS's own cap
/// still holds.
public struct ReviewPromptStore: Sendable {
    let file: JSONFileStore<ReviewPromptState>
    public init(layout: AppStorageLayout) { file = JSONFileStore(url: layout.reviewPromptFile) }

    public func load() -> ReviewPromptState {
        (try? file.load()) ?? ReviewPromptState()
    }

    public func save(_ state: ReviewPromptState) throws {
        try file.save(state)
    }
}

/// The "Rate Trout Truck" row in About: the App Store's write-a-review page
/// for this app. Opened by the system (the App Store), never fetched by the
/// app itself.
public enum AppStoreReviewLink {
    public static let appID = "6818637427"
    public static let host = "apps.apple.com"
    public static let writeReviewURL = URL(string: "https://apps.apple.com/app/id6818637427?action=write-review")!
    public static let rowTitle = "Rate Trout Truck"
    public static let rowFootnote = "Opens the App Store, where you can rate the app or write a review."
}
