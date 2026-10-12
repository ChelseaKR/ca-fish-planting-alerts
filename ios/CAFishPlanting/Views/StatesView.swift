import SwiftUI
import PlantingCore

/// The state picker (docs/adr/0021): every state in the snapshot, what its
/// agency publishes, and whether this device has its full access. Browsing
/// and history are free everywhere; each state's alerts and widget are a
/// one-time purchase. California's is the original Full Access, so anyone
/// who bought it before states sees California as unlocked here.
struct StatesView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    @State private var purchasing: PurchaseTarget?

    private struct PurchaseTarget: Identifiable { let id: String }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Browsing, every water's history and favorites are free in every state. Alerts and the widget are a one-time purchase for each state.")
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                }
                if let snapshot = environment.snapshot {
                    ForEach(snapshot.states) { state in
                        Section {
                            row(state)
                        }
                    }
                }
                Section {
                    Button("Restore purchases") { Task { await environment.purchases.restorePurchases() } }
                        .disabled(environment.purchases.uiState == .restoring)
                }
            }
            .navigationTitle("States")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .sheet(item: $purchasing) { target in PurchaseView(state: target.id) }
        }
    }

    @ViewBuilder
    private func row(_ state: StateInfo) -> some View {
        let unlocked = environment.purchases.isEntitled(state: state.code)
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(state.name).font(.headline)
                Spacer()
                if unlocked {
                    Label("Unlocked", systemImage: "checkmark.seal.fill")
                        .labelStyle(.titleAndIcon)
                        .font(.caption.weight(.semibold))
                }
            }
            Text("\(state.agencyName): \(state.kindLabel.lowercased()), \(state.watersCount) waters")
                .font(.caption)
                .foregroundStyle(.secondaryText)
            if state.code == "CA" {
                Text("California full access is the original one-time purchase.")
                    .font(.caption)
                    .foregroundStyle(.secondaryText)
            }
        }
        .accessibilityElement(children: .combine)
        Button("Browse \(state.name)") {
            environment.setBrowseState(state.code)
            dismiss()
        }
        if !unlocked {
            Button {
                purchasing = PurchaseTarget(id: state.code)
            } label: {
                if let product = environment.purchases.product(forState: state.code) {
                    Text("Unlock alerts and widget — \(product.displayPrice)")
                } else {
                    Text("Unlock alerts and widget")
                }
            }
            .accessibilityIdentifier("unlock-\(state.code.lowercased())")
        }
    }
}
