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
    /// The state this sheet sells. California's is the original Full Access.
    var state: String = "CA"

    private var purchases: PurchaseManager { environment.purchases }
    private var info: StateInfo? { environment.snapshot?.state(code: state) }
    private var isCalifornia: Bool { state == "CA" }
    private var stateName: String { info?.name ?? (isCalifornia ? "California" : state) }
    private var unlocked: Bool { purchases.isEntitled(state: state) }

    /// California keeps its words (`FreeTier.fullAccessFeatures`, which the
    /// App Store copy is checked against); another state names itself.
    private var features: [String] {
        guard !isCalifornia, let info else { return FreeTier.fullAccessFeatures }
        return FreeTier.stateFeatures(stateName: info.name, agencyShortName: info.agencyShortName, semantics: info.semantics)
    }

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
                    Image(systemName: unlocked ? "checkmark.seal.fill" : "star.circle")
                        .font(.system(size: 48))
                        .foregroundStyle(unlocked ? Color.green : Color.accentColor)
                        .accessibilityHidden(true)

                    if unlocked && !isCalifornia {
                        Text("\(stateName) unlocked")
                            .font(.title2.bold())
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Thank you. Your \(stateName) favorites now get alerts, and they show in the Favorite waters widget.")
                            .font(.subheadline)
                            .multilineTextAlignment(textAlignment)
                    } else if unlocked {
                        Text("Full access unlocked")
                            .font(.title2.bold())
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Thank you. Every favorite now gets an alert when it's newly on the schedule, and the Favorite waters widget is unlocked: add it from your Home Screen or Lock Screen.")
                            .font(.subheadline)
                            .multilineTextAlignment(textAlignment)
                    } else {
                        Text(isCalifornia ? "Unlock full access" : "Unlock \(stateName)")
                            .font(.title2.bold())
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(isCalifornia
                             ? "Browsing and favoriting are always free. Full access for California adds:"
                             : "Browsing, history and favorites in \(stateName) are always free. \(stateName) full access adds:")
                            .font(.subheadline)
                            .multilineTextAlignment(textAlignment)
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(Array(zip(features, ["bell.badge", "square.grid.2x2", "applewatch"])), id: \.0) { feature, symbol in
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
                        Text(PaywallCopy.terms(stateName: stateName))
                            .font(.footnote)
                            .foregroundStyle(.secondaryText)
                            .multilineTextAlignment(textAlignment)
                            .fixedSize(horizontal: false, vertical: true)

                        // How current this state's data is, before the buy
                        // button: a failed check is said here too, not only
                        // on Browse (PaywallCopy).
                        if let info {
                            freshness(info)
                        }

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

                    Button(unlocked ? "Done" : "Not now") { dismiss() }
                        .buttonStyle(.plain)
                        .padding(.top, 8)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: dynamicTypeSize.isAccessibilitySize ? .leading : .center)
            }
            .navigationTitle(isCalifornia ? "Full access" : stateName)
            .navigationBarTitleDisplayMode(.inline)
        }
        // Half height on iPhone. Not on iPad (or a Mac), where iPadOS 26
        // makes the medium detent a short card that hides the buy button
        // below its edge. The idiom, not the size class: inside a sheet on
        // iPad the size class is compact.
        .presentationDetents(dynamicTypeSize.isAccessibilitySize || UIDevice.current.userInterfaceIdiom == .pad ? [.large] : [.medium, .large])
        // The unlock landing, from a purchase or a restore. iOS skips it when
        // system haptics are off.
        .sensoryFeedback(.success, trigger: unlocked) { wasEntitled, isEntitled in !wasEntitled && isEntitled }
        // Opaque, so text contrast doesn't depend on what the half-height
        // glass sheet happens to cover.
        .presentationBackground(Color(uiColor: .systemBackground))
    }

    @ViewBuilder
    private func freshness(_ info: StateInfo) -> some View {
        VStack(alignment: dynamicTypeSize.isAccessibilitySize ? .leading : .center, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if !info.lastAttemptOK {
                    // Orange on the symbol only, as on Browse.
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                        .accessibilityHidden(true)
                }
                Text(PaywallCopy.freshness(info))
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let note = info.recencyNote {
                Text(note).fixedSize(horizontal: false, vertical: true)
            }
        }
        .font(.footnote)
        .foregroundStyle(info.lastAttemptOK ? Color.secondaryText : Color.primary)
        .multilineTextAlignment(textAlignment)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("purchase-freshness")
    }

    @ViewBuilder
    private var purchaseButton: some View {
        Button {
            Task { await purchases.purchase(state: state) }
        } label: {
            HStack {
                if purchases.uiState == .purchasing {
                    ProgressView().tint(.white)
                }
                Text(purchaseLabel).frame(maxWidth: .infinity)
            }
        }
        .buttonStyle(.borderedProminent)
        .tint(.prominentButtonFill)
        .foregroundStyle(.white)
        .disabled(purchases.uiState == .purchasing || purchases.product(forState: state) == nil)
        .accessibilityHint("Shows the App Store payment sheet")
    }

    private var purchaseLabel: String {
        if let product = purchases.product(forState: state) {
            return isCalifornia ? "Unlock full access — \(product.displayPrice)" : "Unlock \(stateName) — \(product.displayPrice)"
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
