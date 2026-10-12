import XCTest
@testable import PlantingCore

/// The alert planner's shared fixtures (`Fixtures/alert-planner-parity.json`).
/// The Android app's planner (`android/core`, `AlertPlannerParityTest.kt`)
/// runs the same scenarios against the same file, so both apps announce the
/// same weeks with the same words from the same snapshots.
///
/// The `expect` blocks were recorded from this planner. To re-record after a
/// deliberate change to the planner or the words, run
/// `PARITY_RECORD=1 swift test --filter AlertPlannerParityTests`, review the
/// diff, and run the Android tests against it.
final class AlertPlannerParityTests: XCTestCase {
    private static var fixtures: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures")
    }

    func testEveryScenarioMatchesTheSharedExpectations() throws {
        let url = Self.fixtures.appendingPathComponent("alert-planner-parity.json")
        var doc = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let snapshotSpecs = try XCTUnwrap(doc["snapshots"] as? [String: Any])
        var snapshots: [String: Snapshot] = [:]
        for (name, spec) in snapshotSpecs {
            snapshots[name] = try snapshot(from: XCTUnwrap(spec as? [String: Any]))
        }
        let record = ProcessInfo.processInfo.environment["PARITY_RECORD"] == "1"
        var scenarios = try XCTUnwrap(doc["scenarios"] as? [[String: Any]])
        var checked = 0
        for s in scenarios.indices {
            let name = scenarios[s]["name"] as? String ?? "scenario \(s)"
            var state = AlertState(lastListed: try baseline(from: scenarios[s]["initial_state"] as? [String: Any] ?? [:]))
            var steps = try XCTUnwrap(scenarios[s]["steps"] as? [[String: Any]])
            for i in steps.indices {
                let step = steps[i]
                let actual: [String: Any]
                switch step["op"] as? String {
                case "seed":
                    let water = try XCTUnwrap(step["water"] as? String)
                    let snap = try XCTUnwrap(snapshots[try XCTUnwrap(step["snapshot"] as? String)])
                    state = AlertPlanner.seeding(state, favoriting: water, snapshot: snap)
                    actual = ["state": encode(state)]
                case "prune":
                    state = AlertPlanner.pruning(state, unfavoriting: try XCTUnwrap(step["water"] as? String))
                    actual = ["state": encode(state)]
                case "plan":
                    let snap = try XCTUnwrap(snapshots[try XCTUnwrap(step["snapshot"] as? String)])
                    let favorites = try XCTUnwrap(step["favorites"] as? [String])
                    let plan = AlertPlanner.plan(snapshot: snap, favorites: favorites, state: state)
                    state = plan.state
                    let muted = MutedWaters(ids: Set(step["muted"] as? [String] ?? []))
                    actual = [
                        "notifications": plan.notifications.map(encode),
                        "shown": muted.unmuted(plan.notifications).map(\.id),
                        "state": encode(state),
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
            XCTAssertGreaterThan(checked, 20, "the fixture should exercise every scenario")
        }
    }

    // MARK: -

    private func snapshot(from spec: [String: Any]) throws -> Snapshot {
        if let file = spec["file"] as? String {
            return try SnapshotDecoder().decode(Data(contentsOf: Self.fixtures.appendingPathComponent(file)))
        }
        let waters = try XCTUnwrap(spec["waters"] as? [[String: Any]]).map { water -> Water in
            let plants = try XCTUnwrap(water["plants"] as? [[String: String]]).map { p in
                TS.plant(p["week"]!, species: p["species"]!, status: PlantStatus(rawValue: p["status"]!)!)
            }
            return TS.water(id: try XCTUnwrap(water["id"] as? String), name: try XCTUnwrap(water["name"] as? String), plants: plants)
        }
        return TS.snapshot(sourceWeek: try XCTUnwrap(spec["source_week"] as? String), waters: waters)
    }

    private func baseline(from json: [String: Any]) throws -> [Water.ID: Set<PlantKey>] {
        var result: [Water.ID: Set<PlantKey>] = [:]
        for (id, keys) in json {
            let pairs = try XCTUnwrap(keys as? [[String]])
            result[id] = Set(pairs.map { PlantKey(weekStart: TS.date($0[0]), species: $0[1]) })
        }
        return result
    }

    private func encode(_ keys: [PlantKey]) -> [[String]] {
        keys.map { [$0.weekStart.isoDate, $0.species] }
    }

    private func encode(_ state: AlertState) -> [String: Any] {
        state.lastListed.mapValues { keys in
            encode(keys.sorted { $0.weekStart == $1.weekStart ? $0.species < $1.species : $0.weekStart < $1.weekStart })
        }
    }

    private func encode(_ notification: PlannedNotification) -> [String: Any] {
        [
            "id": notification.id,
            "water_id": notification.waterID,
            "title": notification.title,
            "body": notification.body(),
            "new_keys": encode(notification.newKeys),
        ]
    }
}
