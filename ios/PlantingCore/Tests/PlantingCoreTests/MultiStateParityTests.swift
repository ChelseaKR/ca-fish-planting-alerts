import XCTest
@testable import PlantingCore

/// The multi-state planner and widget fixtures
/// (`Fixtures/alert-planner-parity-states.json`, DECISIONS 0025). The Android
/// app's `MultiStateParityTest.kt` runs the same scenarios against the same
/// file, so both apps announce the same records with the same words, post
/// only the alerts each state's purchase allows, and list the same widget
/// rows.
///
/// The `expect` blocks were recorded from this planner. To re-record after a
/// deliberate change, run
/// `PARITY_RECORD=1 swift test --filter MultiStateParityTests`, review the
/// diff, and run the Android tests against it.
final class MultiStateParityTests: XCTestCase {
    private static var fixtures: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures")
    }

    func testEveryScenarioMatchesTheSharedExpectations() throws {
        let url = Self.fixtures.appendingPathComponent("alert-planner-parity-states.json")
        var doc = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let specs = try XCTUnwrap(doc["snapshots"] as? [String: [String: Any]])
        var snapshots: [String: Snapshot] = [:]
        for (name, spec) in specs {
            let file = try XCTUnwrap(spec["file"] as? String)
            snapshots[name] = try SnapshotDecoder().decode(Data(contentsOf: Self.fixtures.appendingPathComponent(file)))
        }
        let record = ProcessInfo.processInfo.environment["PARITY_RECORD"] == "1"
        var scenarios = try XCTUnwrap(doc["scenarios"] as? [[String: Any]])
        var checked = 0
        for s in scenarios.indices {
            let name = scenarios[s]["name"] as? String ?? "scenario \(s)"
            var state = AlertState(lastListed: try baseline(scenarios[s]["initial_state"] as? [String: Any] ?? [:]))
            var steps = try XCTUnwrap(scenarios[s]["steps"] as? [[String: Any]])
            for i in steps.indices {
                let step = steps[i]
                let actual: [String: Any]
                switch step["op"] as? String {
                case "seed":
                    let snap = try XCTUnwrap(snapshots[try XCTUnwrap(step["snapshot"] as? String)])
                    state = AlertPlanner.seeding(state, favoriting: try XCTUnwrap(step["water"] as? String), snapshot: snap)
                    actual = ["state": encode(state)]
                case "prune":
                    state = AlertPlanner.pruning(state, unfavoriting: try XCTUnwrap(step["water"] as? String))
                    actual = ["state": encode(state)]
                case "plan":
                    let snap = try XCTUnwrap(snapshots[try XCTUnwrap(step["snapshot"] as? String)])
                    let favorites = try XCTUnwrap(step["favorites"] as? [String])
                    let entitled = Set(try XCTUnwrap(step["entitled"] as? [String]))
                    let plan = AlertPlanner.plan(snapshot: snap, favorites: favorites, state: state)
                    state = plan.state
                    let muted = MutedWaters(ids: Set(step["muted"] as? [String] ?? []))
                    // The iOS app's rule (`AppEnvironment.alertsToSchedule`): each alert
                    // needs its water's state's purchase; a missing water counts as California.
                    let shown = muted.unmuted(plan.notifications).filter {
                        FreeTier.notificationsAllowed(forState: snap.water(id: $0.waterID)?.state ?? "CA", entitledStates: entitled)
                    }
                    actual = [
                        "notifications": plan.notifications.map(encode),
                        "shown": shown.map(\.id),
                        "state": encode(state),
                    ]
                case "widget":
                    let snap = try XCTUnwrap(snapshots[try XCTUnwrap(step["snapshot"] as? String)])
                    let entitled = Set(try XCTUnwrap(step["entitled"] as? [String]))
                    let now = try XCTUnwrap(ISO8601DateFormatter().date(from: try XCTUnwrap(step["now"] as? String)))
                    let meta = SnapshotMeta(lastAttemptAt: now, lastSuccessAt: now, lastOutcome: "updated")
                    let digest = WidgetDigest(snapshot: snap, meta: meta, favorites: try XCTUnwrap(step["favorites"] as? [String]),
                                              locked: !FreeTier.widgetsAllowed(entitledStates: entitled), entitledStates: entitled)
                    actual = [
                        "locked": digest.locked,
                        "favorites": digest.favoritesByStatus.map(\.id),
                        "status_lines": digest.favoritesByStatus.map { digest.statusLine(of: $0, at: now) },
                        "summary": digest.summary(at: now),
                        "favorites_in_other_states": digest.favoritesInOtherStates,
                        "missing_favorites": digest.missingFavorites,
                    ]
                default:
                    XCTFail("\(name): unknown op \(step["op"] ?? "nil")")
                    continue
                }
                if record {
                    steps[i]["expect"] = actual
                } else {
                    let expected = try XCTUnwrap(step["expect"] as? [String: Any], "\(name) step \(i) has no expect block; record it")
                    XCTAssertEqual(NSDictionary(dictionary: actual), NSDictionary(dictionary: expected), "\(name), step \(i)")
                    checked += 1
                }
            }
            scenarios[s]["steps"] = steps
        }
        if record {
            doc["scenarios"] = scenarios
            let data = try JSONSerialization.data(withJSONObject: doc, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
            try (data + Data("\n".utf8)).write(to: url)
        } else {
            XCTAssertGreaterThanOrEqual(checked, 18, "the fixture should exercise every scenario")
        }
    }

    // MARK: -

    private func baseline(_ json: [String: Any]) throws -> [Water.ID: Set<PlantKey>] {
        var result: [Water.ID: Set<PlantKey>] = [:]
        for (id, keys) in json {
            let rows = try XCTUnwrap(keys as? [[String]])
            result[id] = Set(try rows.map { row in
                let precision = row.count > 2 ? try XCTUnwrap(DatePrecision(rawValue: row[2])) : nil
                return PlantKey(weekStart: TS.date(row[0]), species: row[1], precision: precision)
            })
        }
        return result
    }

    private func encode(_ keys: [PlantKey]) -> [[String]] {
        keys.map { [$0.weekStart.isoDate, $0.species, ($0.precision ?? .week).rawValue] }
    }

    private func encode(_ state: AlertState) -> [String: Any] {
        state.lastListed.mapValues { keys in
            encode(keys.sorted { $0.weekStart == $1.weekStart ? $0.species < $1.species : $0.weekStart < $1.weekStart })
        }
    }

    private func encode(_ n: PlannedNotification) -> [String: Any] {
        ["id": n.id, "water_id": n.waterID, "title": n.title, "body": n.body(), "new_keys": encode(n.newKeys)]
    }
}
