import Foundation
import AppIntents
import PlantingCore

// Shortcuts and Siri: "When is <water> scheduled in Trout Truck?"
//
// The answer comes from the schedule already on this iPhone
// (`ScheduleAnswer`). Asking makes no network request, sends nothing, and
// needs no purchase: it is the same lookup Browse gives everyone.

/// What an intent can read: the app's own snapshot and favorites, on this
/// device. The running app's copy when there is one, otherwise the files the
/// app keeps, read the same way the app reads them at launch.
@MainActor
enum IntentData {
    static func snapshot() -> Snapshot? {
        if let snapshot = AppEnvironment.shared?.snapshot { return snapshot }
        guard let layout = layout() else { return nil }
        let bundled = Bundle.main.url(forResource: "snapshot", withExtension: "json")
        return try? SnapshotStore(layout: layout, bundledSnapshotURL: bundled).snapshot
    }

    static func favoriteIDs() -> [Water.ID] {
        if let environment = AppEnvironment.shared { return environment.favorites.ids }
        guard let layout = layout() else { return [] }
        return FavoritesStore(layout: layout).load().ids
    }

    private static func layout() -> AppStorageLayout? {
        try? AppStorageLayout.applicationSupport(bundleIdentifier: Bundle.main.bundleIdentifier ?? "com.chelseakr.cafishplanting")
    }
}

struct WaterEntity: AppEntity {
    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Water")
    static let defaultQuery = WaterEntityQuery()

    let id: Water.ID
    let name: String
    let countyLabel: String

    init(_ water: Water) {
        id = water.id
        name = water.name
        countyLabel = water.countyLabel
    }

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)", subtitle: "\(countyLabel)")
    }
}

struct WaterEntityQuery: EntityStringQuery {
    /// Enough to pick from, without listing all ~400 waters.
    static let maxResults = 50

    func entities(for identifiers: [WaterEntity.ID]) async throws -> [WaterEntity] {
        await MainActor.run {
            let snapshot = IntentData.snapshot()
            return identifiers.compactMap { snapshot?.water(id: $0).map(WaterEntity.init) }
        }
    }

    /// A water's name, a name CDFW used before, or its county. Every word
    /// typed has to match.
    func entities(matching string: String) async throws -> [WaterEntity] {
        await MainActor.run {
            Self.matching(string, in: IntentData.snapshot()?.waters ?? []).map(WaterEntity.init)
        }
    }

    /// Favorites first, in the order they were added; with none, the waters
    /// listed for the schedule's week.
    func suggestedEntities() async throws -> [WaterEntity] {
        await MainActor.run {
            guard let snapshot = IntentData.snapshot() else { return [] }
            let favorites = IntentData.favoriteIDs().compactMap(snapshot.water(id:))
            if !favorites.isEmpty { return favorites.map(WaterEntity.init) }
            var seen = Set<Water.ID>()
            let listed = snapshot.thisWeek.map(\.waterID).filter { seen.insert($0).inserted }
            return listed.compactMap(snapshot.water(id:)).map(WaterEntity.init)
        }
    }

    static func matching(_ string: String, in waters: [Water]) -> [Water] {
        func fold(_ s: String) -> String { s.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil) }
        let terms = fold(string).split(whereSeparator: \.isWhitespace).map(String.init)
        guard !terms.isEmpty else { return [] }
        let found = waters.filter { water in
            let haystack = fold(([water.name] + water.aliases + water.counties).joined(separator: " "))
            return terms.allSatisfy(haystack.contains)
        }
        return Array(found.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }.prefix(maxResults))
    }
}

/// "When is <water> scheduled next?" Answers from the schedule on this
/// iPhone, and always names that schedule's week.
struct NextScheduledWeekIntent: AppIntent {
    static let title: LocalizedStringResource = "Next Scheduled Week"
    static let description = IntentDescription("Says the next week CDFW's schedule lists a water for, from the schedule already on this iPhone. CDFW gives the week, not the day.")

    @Parameter(title: "Water", requestValueDialog: "Which water?")
    var water: WaterEntity

    static var parameterSummary: some ParameterSummary {
        Summary("When is \(\.$water) scheduled next?")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let text = Self.answer(waterID: water.id, name: water.name, snapshot: IntentData.snapshot(), now: Date())
        return .result(value: text, dialog: "\(text)")
    }

    /// Separate from `perform()` so a test can read it.
    static func answer(waterID: Water.ID, name: String, snapshot: Snapshot?, now: Date) -> String {
        guard let snapshot, let water = snapshot.water(id: waterID) else {
            return "Trout Truck doesn't have \(name) in the schedule on this iPhone. Open Trout Truck to check for a newer one."
        }
        return ScheduleAnswer.nextScheduled(for: water, in: snapshot, now: now)
    }
}

struct TroutTruckShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: NextScheduledWeekIntent(),
            phrases: [
                "When is \(\.$water) scheduled in \(.applicationName)",
                "When is \(\.$water) next scheduled in \(.applicationName)",
                "Next scheduled week in \(.applicationName)",
            ],
            shortTitle: "Next Scheduled Week",
            systemImageName: "calendar"
        )
    }
}
