import Foundation
import Observation
import WatchConnectivity
import WidgetKit
import PlantingCore

/// What the watch knows: the digest the phone last sent.
///
/// The phone sends it as WatchConnectivity's application context
/// (`WatchSync`). This keeps it in the watch's own App Group container, so
/// the complication reads the same file (`WidgetDigestStore`), and redraws
/// the complication when it changes. Nothing here makes a network request.
@MainActor
@Observable
final class WatchModel: NSObject {
    static let shared = WatchModel()

    /// `nil` until the phone has sent one; the watch then says to open
    /// Trout Truck on the iPhone, never "nothing scheduled".
    private(set) var digest: WidgetDigest?
    /// A water to show, from a tapped alert.
    var openWaterID: String?

    @ObservationIgnored private let store: WidgetDigestStore?
    @ObservationIgnored private let session: WCSession?

    init(store: WidgetDigestStore? = WidgetDigestStore.appGroup(),
         session: WCSession? = WCSession.isSupported() ? .default : nil) {
        self.store = store
        self.session = session
        super.init()
        digest = store?.load()
        #if DEBUG
        // Screenshots and UI checks only: draw a digest a test wrote to a
        // file, built from the real bundled snapshot (NOTES.md). Never in
        // a release build.
        if let path = ProcessInfo.processInfo.environment["TT_WATCH_DIGEST_FILE"],
           let digest = WidgetDigestStore(directory: URL(fileURLWithPath: path).deletingLastPathComponent()).load() {
            self.digest = digest
            try? store?.save(digest)
        }
        openWaterID = ProcessInfo.processInfo.environment["TT_WATCH_OPEN_WATER"]
        #endif
        guard let session else { return }
        session.delegate = self
        session.activate()
    }

    private func receive(_ context: [String: Any]) {
        guard let received = WatchSync.digest(fromApplicationContext: context), received != digest else { return }
        digest = received
        try? store?.save(received)
        WidgetCenter.shared.reloadAllTimelines()
    }

    /// "Mute this water" tapped on the watch. The phone owns the mute list,
    /// so the watch asks it; WatchConnectivity queues the request until the
    /// phone is in reach.
    func requestMute(_ id: String) {
        guard let session, session.activationState == .activated else { return }
        session.transferUserInfo(WatchSync.muteRequest(for: id))
    }
}

extension WatchModel: WCSessionDelegate {
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        let context = session.receivedApplicationContext
        Task { @MainActor in self.receive(context) }
    }

    nonisolated func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        Task { @MainActor in self.receive(applicationContext) }
    }
}
