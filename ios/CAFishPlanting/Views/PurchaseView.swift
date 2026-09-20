import SwiftUI
import StoreKit
import PlantingCore

/// The purchase sheet. Favoriting and browsing are always free (see
/// `FreeTier` in PlantingCore). It opens from About > "Unlock full access"
/// and from a tap on the locked Home Screen widget (`UnlockLink`), never as
/// an upsell on the favorite action itself.
struct PurchaseView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var purchases: PurchaseManager { environment.purchases }

    /// Centered at the usual sizes; ragged-right at the accessibility sizes,
    /// where a few words per line read more easily from a fixed left edge.
    private var textAlignment: TextAlignment {
        dynamicTypeSize.isAccessibilitySize ? .leading : .center
    }

    var body: some View {
        NavigationStack {
            // Scrolls, so at the largest text sizes nothing is cut off by
            // the sheet.
            ScrollView {
                VStack(alignment: dynamicTypeSize.isAccessibilitySize ? .leading : .center, spacing: 20) {
                    Image(systemName: purchases.isEntitled ? "checkmark.seal.fill" : "star.circle")
                        .font(.system(size: 48))
                        .foregroundStyle(purchases.isEntitled ? Color.green : Color.accentColor)
                        .accessibilityHidden(true)

                    if purchases.isEntitled {
                        Text("Full access unlocked")
                            .font(.title2.bold())
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Thank you. Every favorite now gets an alert when it's newly on the schedule, and the Favorite waters widget is unlocked: add it from your Home Screen or Lock Screen.")
                            .font(.subheadline)
                            .multilineTextAlignment(textAlignment)
                    } else {
                        Text("Unlock full access")
                            .font(.title2.bold())
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Browsing and favoriting are always free. Full access adds:")
                            .font(.subheadline)
                            .multilineTextAlignment(textAlignment)
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(Array(zip(FreeTier.fullAccessFeatures, ["bell.badge", "square.grid.2x2"])), id: \.0) { feature, symbol in
                                Label {
                                    Text(feature).fixedSize(horizontal: false, vertical: true)
                                } icon: {
                                    Image(systemName: symbol)
                                        .foregroundStyle(.tint)
                                        .accessibilityHidden(true)
                                }
                            }
                        }
                        .font(.subheadline)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Text("One payment, forever. No subscription, no account.")
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                            .multilineTextAlignment(textAlignment)

                        purchaseButton
                        restoreButton

                        if case .failed(let message) = purchases.uiState {
                            // Red on the symbol only: red text on white is below
                            // 4.5:1 at this size.
                            Label {
                                Text(message)
                            } icon: {
                                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                            }
                            .font(.footnote)
                            .multilineTextAlignment(textAlignment)
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel("Purchase error: \(message)")
                        }
                    }

                    Button(purchases.isEntitled ? "Done" : "Not now") { dismiss() }
                        .buttonStyle(.plain)
                        .padding(.top, 8)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: dynamicTypeSize.isAccessibilitySize ? .leading : .center)
            }
            .navigationTitle("Full access")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents(dynamicTypeSize.isAccessibilitySize ? [.large] : [.medium, .large])
        // Opaque, so text contrast doesn't depend on what the half-height
        // glass sheet happens to cover.
        .presentationBackground(Color(uiColor: .systemBackground))
    }

    @ViewBuilder
    private var purchaseButton: some View {
        Button {
            Task { await purchases.purchase() }
        } label: {
            HStack {
                if purchases.uiState == .purchasing {
                    ProgressView().tint(.white)
                }
                Text(purchaseLabel).frame(maxWidth: .infinity)
            }
        }
        .buttonStyle(.borderedProminent)
        .disabled(purchases.uiState == .purchasing || purchases.product == nil)
        .accessibilityHint("Shows the App Store payment sheet")
    }

    private var purchaseLabel: String {
        if let product = purchases.product {
            return "Unlock full access — \(product.displayPrice)"
        }
        return purchases.productLoadError == nil ? "Loading price…" : "Not available right now"
    }

    private var restoreButton: some View {
        Button {
            Task { await purchases.restorePurchases() }
        } label: {
            HStack {
                if purchases.uiState == .restoring { ProgressView() }
                Text("Restore purchases")
            }
        }
        .buttonStyle(.plain)
        .disabled(purchases.uiState == .purchasing || purchases.uiState == .restoring)
    }
}
