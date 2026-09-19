import Foundation
import WidgetKit
import PlantingCore

/// Hands the widget what it shows. The app writes a small digest of the
/// snapshot it already has (`WidgetDigest`) to the App Group container, and
/// asks WidgetKit to redraw only when that digest changed.
///
/// This adds no network request and sends nothing anywhere: the file stays
/// in a container only this app and its widget can read.
@MainActor
final class WidgetBridge {
    /// The widget's `kind` (`FavoriteWatersWidget.kind` in the extension).
    nonisolated static let widgetKind = "FavoriteWatersThisWeek"

    private let store: WidgetDigestStore?
    private let reload: () -> Void
    private var lastPublished: WidgetDigest?

    /// `store` is `nil` when this build has no App Group access; then
    /// publishing does nothing and the widget says to open the app.
    init(store: WidgetDigestStore? = WidgetDigestStore.appGroup(),
         reload: @escaping () -> Void = { WidgetCenter.shared.reloadTimelines(ofKind: WidgetBridge.widgetKind) }) {
        self.store = store
        self.reload = reload
        self.lastPublished = store?.load()
    }

    /// Writes the digest and redraws the widget, unless nothing changed.
    /// Returns whether it wrote.
    @discardableResult
    func publish(_ digest: WidgetDigest) -> Bool {
        guard let store, digest != lastPublished else { return false }
        do {
            try store.save(digest)
        } catch {
            // The widget keeps the last digest it could read, labeled with
            // its week. Nothing here may pretend the write worked.
            return false
        }
        lastPublished = digest
        reload()
        return true
    }
}
