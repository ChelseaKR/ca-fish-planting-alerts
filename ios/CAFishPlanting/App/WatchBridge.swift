import Foundation
import WatchConnectivity
import PlantingCore

/// Hands Apple Watch the same small digest the widget reads (`WidgetDigest`),
/// and takes back the one thing the watch sends: a water to mute.
///
/// The digest travels as WatchConnectivity's application context
/// (`WatchSync`): only the latest one is kept, and the system delivers it
/// when the watch is in reach. Nothing goes through a server, and this adds
/// no network request. The phone builds the digest, locked unless
/// `FreeTier.watchAllowed`, so the watch can never show more than the phone
/// allows.
@MainActor
final class WatchBridge: NSObject {
    /// The app's one bridge. `WCSession.default` has one delegate, so there
    /// is one of these.
    static let shared = WatchBridge()

    private let session: WCSession?
    /// The newest digest, kept so it can be sent again when the session
    /// activates or the watch app is installed after the last change.
    private(set) var latest: WidgetDigest?
    private var lastSent: WidgetDigest?
    /// Applies a mute the watch asked for. Set by `AppEnvironment`.
    var onMuteRequest: (@MainActor (Water.ID) -> Void)?

    /// `session` is `nil` where WatchConnectivity isn't supported (iPad,
    /// Mac); then publishing does nothing.
    init(session: WCSession? = WCSession.isSupported() ? .default : nil) {
        self.session = session
        super.init()
        guard let session else { return }
        session.delegate = self
        session.activate()
    }

    /// Sends the digest to the watch if it changed and a watch app is
    /// there to receive it; otherwise keeps it for when one is.
    func publish(_ digest: WidgetDigest) {
        latest = digest
        sendLatestIfPossible()
    }

    private func sendLatestIfPossible() {
        guard let session, let latest, latest != lastSent,
              session.activationState == .activated, session.isPaired, session.isWatchAppInstalled,
              let context = try? WatchSync.applicationContext(for: latest)
        else { return }
        do {
            try session.updateApplicationContext(context)
            lastSent = latest
        } catch {
            // Not sent: the watch keeps the last digest it has, labeled
            // with its week. The next change or activation tries again.
        }
    }

    private func sessionChanged() {
        // A newly installed or re-paired watch has nothing yet.
        lastSent = nil
        sendLatestIfPossible()
    }

    /// A message from the watch. Internal so hosted tests can stand in for
    /// a paired watch, which the simulator test run doesn't have.
    func received(_ userInfo: [String: Any]) {
        guard let id = WatchSync.waterIDToMute(fromUserInfo: userInfo) else { return }
        onMuteRequest?(id)
    }
}

extension WatchBridge: WCSessionDelegate {
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        Task { @MainActor in self.sessionChanged() }
    }

    nonisolated func sessionWatchStateDidChange(_ session: WCSession) {
        Task { @MainActor in self.sessionChanged() }
    }

    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {}

    nonisolated func sessionDidDeactivate(_ session: WCSession) {
        // Switching to another watch: activate again for the new one.
        session.activate()
    }

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        Task { @MainActor in self.received(userInfo) }
    }
}
