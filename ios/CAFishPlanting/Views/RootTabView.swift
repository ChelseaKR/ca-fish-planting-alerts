import SwiftUI
import PlantingCore

struct RootTabView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(AppRouter.self) private var router
    /// Regular on iPad (full screen and the wider multitasking sizes) and on
    /// a Mac: Browse and Favorites become a list beside the water's page.
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// The list beside the water's page. Not at the accessibility text
    /// sizes, where the sidebar is too narrow for the words and the
    /// full-width iPhone layout reads better.
    private var showsListBesideWater: Bool {
        horizontalSizeClass == .regular && !dynamicTypeSize.isAccessibilitySize
    }

    var body: some View {
        if let error = environment.loadError {
            SnapshotUnavailableView(message: error)
        } else {
            @Bindable var router = router
            TabView(selection: $router.selectedTab) {
                Group {
                    if showsListBesideWater {
                        NavigationSplitView {
                            BrowseView(selection: selection($router.browsePath))
                        } detail: {
                            NavigationStack {
                                WaterDetailColumn(id: router.browsePath.last,
                                                  placeholder: "Choose a water from the list to see its schedule and history.")
                            }
                        }
                    } else {
                        NavigationStack(path: $router.browsePath) { BrowseView() }
                    }
                }
                .tabItem { Label("Browse", systemImage: "list.bullet") }
                .tag(AppRouter.Tab.browse)
                MapTabView()
                    .tabItem { Label("Map", systemImage: "map") }
                    .tag(AppRouter.Tab.map)
                Group {
                    if showsListBesideWater {
                        NavigationSplitView {
                            FavoritesView(selection: selection($router.favoritesPath))
                        } detail: {
                            NavigationStack {
                                WaterDetailColumn(id: router.favoritesPath.last,
                                                  placeholder: "Choose a favorite to see its schedule and history.")
                            }
                        }
                    } else {
                        NavigationStack(path: $router.favoritesPath) { FavoritesView() }
                    }
                }
                .tabItem { Label("Favorites", systemImage: "star") }
                .tag(AppRouter.Tab.favorites)
                NavigationStack { AboutView().readableWidth() }
                    .tabItem { Label("About", systemImage: "info.circle") }
                    .tag(AppRouter.Tab.about)
            }
            // A tapped alert or a widget link: open that water. `initial`
            // covers a request that arrived before this view existed (a
            // tap that launched the app).
            .onChange(of: router.pendingWaterID, initial: true) {
                router.openPending(in: environment.snapshot, isFavorite: environment.isFavorite)
            }
            .sheet(item: notificationExplainerBinding) { explainer in
                FirstFavoriteExplainerSheet(explainer: explainer)
            }
            // The locked widget's link. The same sheet About opens.
            .sheet(isPresented: $router.showingPurchase) {
                PurchaseView()
            }
            .fullScreenCover(isPresented: $router.showingOnboarding) {
                OnboardingView {
                    environment.completeOnboarding()
                    router.showingOnboarding = false
                }
            }
            // The introduction's end. iOS skips it when system haptics are off.
            .sensoryFeedback(.success, trigger: environment.onboarding.completedVersion)
            .onAppear {
                if OnboardingLaunchOverride.current?.show ?? environment.shouldShowOnboarding {
                    router.showingOnboarding = true
                }
            }
        }
    }

    /// A split view's selection over the tab's path, so the router opens a
    /// water the same way in both layouts: a path of one is the selection.
    private func selection(_ path: Binding<[Water.ID]>) -> Binding<Water.ID?> {
        Binding(get: { path.wrappedValue.last },
                set: { path.wrappedValue = $0.map { [$0] } ?? [] })
    }

    /// `@Observable` doesn't expose `Binding` the way `@Published` did;
    /// this adapts `pendingNotificationExplainer` for `.sheet(item:)`.
    private var notificationExplainerBinding: Binding<FirstFavoriteExplainer?> {
        Binding(
            get: { environment.pendingNotificationExplainer },
            set: { if $0 == nil { environment.dismissNotificationExplainer() } }
        )
    }
}

/// The detail column of a split view: the chosen water's page, or a
/// prompt to choose one. A water the snapshot doesn't have shows the prompt,
/// never a blank page.
struct WaterDetailColumn: View {
    @Environment(AppEnvironment.self) private var environment
    let id: Water.ID?
    let placeholder: String

    var body: some View {
        if let id, let snapshot = environment.snapshot, let water = snapshot.water(id: id) {
            WaterDetailView(water: water, sourceWeek: snapshot.currentWeek(for: water))
                .readableWidth()
                .id(id)
        } else {
            ContentUnavailableView {
                Label("No water chosen", systemImage: "fish")
            } description: {
                Text(placeholder).foregroundStyle(.secondaryText)
            }
        }
    }
}

/// Keeps a list's rows to a readable width on a wide screen (iPad
/// landscape, a Mac window) instead of stretching them edge to edge. No
/// change at compact width.
struct ReadableWidth: ViewModifier {
    static let maximum: CGFloat = 720
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    func body(content: Content) -> some View {
        GeometryReader { geometry in
            content.contentMargins(.horizontal,
                                   horizontalSizeClass == .regular ? max(0, (geometry.size.width - Self.maximum) / 2) : 0,
                                   for: .scrollContent)
        }
    }
}

extension View {
    func readableWidth() -> some View { modifier(ReadableWidth()) }
}

/// UI tests choose whether the introduction shows, whatever an earlier run
/// left on the simulator: `-UITestOnboarding show` or `skip`. Debug builds
/// only; a release build always decides from what is on the device.
enum OnboardingLaunchOverride {
    case show, skip

    var show: Bool { self == .show }

    static var current: OnboardingLaunchOverride? {
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        guard let flag = arguments.firstIndex(of: "-UITestOnboarding"), flag + 1 < arguments.count else { return nil }
        switch arguments[flag + 1] {
        case "show": return .show
        case "skip": return .skip
        default: return nil
        }
        #else
        return nil
        #endif
    }
}

/// Shown once, the moment someone favorites their first water — before any
/// system permission prompt — stating plainly what will and won't happen.
private struct FirstFavoriteExplainerSheet: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss
    let explainer: FirstFavoriteExplainer

    var body: some View {
        NotificationPrimingView(copy: explainer.copy) {
            await environment.confirmNotificationExplainer()
            dismiss()
        } notNow: {
            environment.dismissNotificationExplainer()
            dismiss()
        }
    }
}

/// The screen before the system notification prompt: what an alert is, how
/// often one comes, and that it is made on this iPhone. It scrolls, so at
/// the largest text sizes nothing is cut off, and the buttons stay at the
/// bottom.
struct NotificationPrimingView: View {
    let copy: NotificationPrimingCopy
    let allow: () async -> Void
    let notNow: () -> Void
    @State private var isAsking = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Image(systemName: "bell.badge")
                        .font(.largeTitle)
                        .foregroundStyle(.tint)
                        .accessibilityHidden(true)
                    Text(copy.headline)
                        .font(.title2.bold())
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    ForEach(copy.points) { point in
                        Label {
                            Text(point.text)
                                .fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: point.systemImage)
                                .foregroundStyle(.tint)
                                .accessibilityHidden(true)
                        }
                        .font(.body)
                    }
                    Text(copy.footnote)
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 12) {
                    Button {
                        isAsking = true
                        Task {
                            await allow()
                            isAsking = false
                        }
                    } label: {
                        Text("Allow notifications").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(isAsking)
                    .accessibilityHint("Shows the system permission prompt")

                    Button("Not now", action: notNow)
                        .frame(maxWidth: .infinity)
                        .disabled(isAsking)
                }
                .padding()
                .background(.bar)
            }
            .navigationTitle("Stay in the loop")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.large])
    }
}

struct SnapshotUnavailableView: View {
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .accessibilityHidden(true)
            Text("Can't load the stocking schedule")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(.secondaryText)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
        }
        .padding()
        .accessibilityElement(children: .combine)
    }
}
