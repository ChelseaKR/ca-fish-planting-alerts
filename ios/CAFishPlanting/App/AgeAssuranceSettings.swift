import AgeAssurance
import Foundation

/// App-store age assurance (Texas SB 2420, California AB 1043, Alabama
/// HB 161, Utah 13-76, Louisiana R.S. 51:1771). The app asks Apple for the
/// person's age range at launch, holds it in memory for the session, and
/// uses it for nothing: Trout Truck has no account, collects no data and
/// has nothing to gate. Asking is the duty; the answer is never stored,
/// sent, logged or shown.
///
/// The one per-app setting. `.recommended` is `requestPolicy:
/// .onlyWhenRequired` (decision D1 in the 2026-10-30 compliance report): ask
/// only when Apple says a law covers this person, so people outside the
/// covered states never see a sharing prompt. Change it here, nowhere else.
enum AppAgeAssurance {
    static let configuration: AgeAssuranceConfiguration = .recommended

    @MainActor
    static func makeSession() -> AgeAssuranceSession {
        AgeAssuranceSession(configuration: configuration, platform: platform)
    }

    private static var platform: AgeRangePlatform {
        #if canImport(DeclaredAgeRange)
        DeclaredAgeRangePlatform()
        #else
        UnsupportedAgeRangePlatform()
        #endif
    }
}
