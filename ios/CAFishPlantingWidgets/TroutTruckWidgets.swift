import SwiftUI
import WidgetKit

/// The widget extension. One widget today; a bundle so another can be added
/// without changing the extension's entry point.
@main
struct TroutTruckWidgets: WidgetBundle {
    var body: some Widget {
        FavoriteWatersWidget()
    }
}
