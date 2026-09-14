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
                .task { AppEnvironment.shared = environment }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background {
                BackgroundRefresh.scheduleNextRefresh()
            }
        }
    }
}
