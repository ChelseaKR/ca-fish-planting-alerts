#if DEBUG
import SwiftUI
import WidgetKit
import PlantingCore

/// Debug builds only: draws the complication in each size from the digest
/// the app holds, for screenshots (`TT_WATCH_GALLERY=1`). A watch face can't
/// be set up from the command line, so this is how the complication's
/// words are checked on a simulator. Release builds don't contain it.
struct ComplicationGallery: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        let entry = NextFavoriteEntry(date: Date(), digest: model.digest)
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                NextFavoriteView(entry: entry, family: .accessoryRectangular)
                    .frame(height: 64)
                HStack(spacing: 12) {
                    NextFavoriteView(entry: entry, family: .accessoryCircular)
                        .frame(width: 50, height: 50)
                    NextFavoriteView(entry: entry, family: .accessoryInline)
                        .font(.caption2)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 4)
        }
    }
}
#endif
