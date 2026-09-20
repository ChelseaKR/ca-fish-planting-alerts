import SwiftUI
import BackgroundTasks

@main
struct CAFishPlantingApp: App {
    @State private var environment = AppEnvironment()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Must run before applicationDidFinishLaunching returns, so this
        // happens in the App's init rather than in a view's onAppear.
        //
        // Set shared here (not in the WindowGroup's .task) so the
        // background-refresh handler can reach it even if iOS launches the
        // app in the background without connecting a window scene.
        AppEnvironment.shared = environment
        BackgroundRefresh.register { await AppEnvironment.shared?.performBackgroundRefresh() ?? .failed("no environment") }
        // Also before launch finishes, so the tap on an alert that launched
        // the app is delivered and opens its water.
        NotificationResponder.shared.install()
    }

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(environment)
                .environment(AppRouter.shared)
                .onOpenURL { AppRouter.shared.handle($0) }
                .task {
                    await refreshOnOpen()
                }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                Task { await refreshOnOpen() }
            case .background:
                BackgroundRefresh.scheduleNextRefresh()
                // Leaving the app: make sure the widget shows what the app
                // shows (a purchase, for one, isn't a snapshot change).
                environment.publishWidgetDigest()
            default:
                break
            }
        }
    }

    /// Launch and each return to the foreground. `refreshIfDue` throttles
    /// it and joins a fetch already running, so launch firing both `.task`
    /// and `.active` costs one GET at most.
    private func refreshOnOpen() async {
        // App-hosted unit tests run inside this app. A live fetch here would
        // race them for the same Application Support directory, so they
        // drive `refreshIfDue` themselves against a mocked session.
        guard !Self.isHostingUnitTests else { return }
        await environment.refreshIfDue()
    }

    private static let isHostingUnitTests = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
}
