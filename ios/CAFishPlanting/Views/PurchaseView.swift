import SwiftUI
import StoreKit

/// The purchase sheet. Favouriting and browsing are always free (see
/// `FreeTier` in PlantingCore); this sheet is reachable only from About >
/// "Unlock full access", never as an upsell on the favourite action itself.
struct PurchaseView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss

    private var purchases: PurchaseManager { environment.purchases }

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Image(systemName: purchases.isEntitled ? "checkmark.seal.fill" : "star.circle")
                    .font(.system(size: 48))
                    .foregroundStyle(purchases.isEntitled ? Color.green : Color.accentColor)
                    .accessibilityHidden(true)

                if purchases.isEntitled {
                    Text("Full access unlocked")
                        .font(.title2.bold())
                    Text("Thank you — every favourite now gets a notification when its stocking schedule changes.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                } else {
                    Text("Unlock full access")
                        .font(.title2.bold())
                    Text("Favouriting and browsing are always free. Unlock full access to get a notification on this device whenever one of your favourites appears in CDFW's new weekly schedule. One payment, forever — no subscription, no account.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    purchaseButton
                    restoreButton

                    if case .failed(let message) = purchases.uiState {
                        Text(message)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                            .accessibilityLabel("Purchase error: \(message)")
                    }
                }

                Spacer()

                Button(purchases.isEntitled ? "Done" : "Not now") { dismiss() }
                    .buttonStyle(.plain)
            }
            .padding()
            .navigationTitle("Full access")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
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
