import SwiftUI
import BackgroundTasks

@main
struct CAFishPlantingApp: App {
    @State private var environment = AppEnvironment()
    @Environment(\.scenePhase) private var scenePhase

    init() {
        // Must run before applicationDidFinishLaunching returns, so this
        // happens in the App's init rather than in a view's onAppear.
        BackgroundRefresh.register { await AppEnvironment.shared?.performBackgroundRefresh() ?? .failed("no environment") }
    }

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(environment)
                .task {
                    AppEnvironment.shared = environment
                    await refreshOnOpen()
                }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                Task { await refreshOnOpen() }
            case .background:
                BackgroundRefresh.scheduleNextRefresh()
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
