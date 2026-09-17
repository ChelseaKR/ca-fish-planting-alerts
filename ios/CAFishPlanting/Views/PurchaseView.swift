import SwiftUI
import StoreKit

/// The purchase sheet. Shown when a non-purchaser hits the free-tier cap
/// (see `FreeTier` in PlantingCore — a placeholder gate pending a real
/// free/paid decision) and reachable any time from About.
struct PurchaseView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    var contextMessage: String?

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
                    Text("Thank you — every water is favouritable and every favourite gets alerts.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                } else {
                    if let contextMessage {
                        Text(contextMessage)
                            .font(.body)
                            .multilineTextAlignment(.center)
                    }
                    Text("Unlock full access")
                        .font(.title2.bold())
                    Text("Favourite as many waters as you like and get an alert for every one of them. One payment, forever — no subscription, no account.")
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
