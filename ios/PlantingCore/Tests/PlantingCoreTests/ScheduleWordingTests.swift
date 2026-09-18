import XCTest
@testable import PlantingCore

/// The wording rule (`schema/README.md`): CDFW publishes the week a plant is
/// *scheduled*, which is subject to change. Never say "stocked", never say
/// "planted on", never render a plant as a single day; say "scheduled" or
/// "listed for the week of …".
final class ScheduleWordingTests: XCTestCase {
    func testLastScheduledLineNamesAWeekAndSaysScheduled() {
        let water = TS.water(id: "cdfw-1", plants: [TS.plant("2026-08-30"), TS.plant("2026-09-06")])
        XCTAssertEqual(ScheduleWording.lastScheduledLine(for: water), "Last scheduled for the week of 2026-09-06")
    }

    func testAWaterWithNoListedWeekNeverGetsOne() {
        let water = TS.water(id: "cdfw-2", plants: [TS.plant("2026-09-20", status: .removed)])
        XCTAssertNil(water.lastListedWeek)
        XCTAssertEqual(ScheduleWording.lastScheduledLine(for: water), ScheduleWording.noScheduledWeekYet)
        XCTAssertFalse(ScheduleWording.noScheduledWeekYet.contains("week of"), "no week exists to name")
    }

    /// Every string literal in the app's own source: the SwiftUI views, the
    /// app target and PlantingCore. A label that says "planted" or "stocked"
    /// claims a plant CDFW only scheduled. Quoting the word to say the app
    /// doesn't use it (`says \"scheduled\" rather than \"stocked\"`) is allowed.
    func testNoLabelInTheAppClaimsAConfirmedPlant() throws {
        let offending = try literals().filter { Self.claimsAConfirmedPlant($0.text) }
        XCTAssertEqual(offending.map { "\($0.file): \($0.text)" }, [])
    }

    /// Negative control for the scan above: it must see the app's own copy
    /// (or it would pass on an empty tree) and must flag the label this
    /// change replaced.
    func testTheWordingScanSeesTheAppAndCatchesTheOldLabel() throws {
        let all = try literals()
        XCTAssertTrue(all.contains { $0.file == "WaterDetailView.swift" }, "the scan must read the app's views")
        XCTAssertTrue(all.contains { $0.text.contains("scheduled") }, "the scan must see real copy")
        XCTAssertTrue(Self.claimsAConfirmedPlant("Last planted \\(last.label)"))
        XCTAssertTrue(Self.claimsAConfirmedPlant("Not yet planted in the schedule this app has observed"))
        XCTAssertTrue(Self.claimsAConfirmedPlant("Stocked on Sep 14"))
        XCTAssertFalse(Self.claimsAConfirmedPlant("says \\\"scheduled\\\" rather than \\\"stocked\\\"."))
        XCTAssertFalse(Self.claimsAConfirmedPlant("CA fish planting alerts"))
    }

    // MARK: -

    static func claimsAConfirmedPlant(_ literal: String) -> Bool {
        // Drop quoted mentions of the words themselves: \"stocked\".
        let unquoted = literal.replacingOccurrences(of: #"\\"[A-Za-z ]+\\""#, with: "", options: .regularExpression)
        return unquoted.range(of: #"\b(planted|stocked)\b"#, options: [.regularExpression, .caseInsensitive]) != nil
    }

    private struct Literal { let file: String; let text: String }

    private func literals() throws -> [Literal] {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // PlantingCoreTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // PlantingCore
            .deletingLastPathComponent() // ios
        let directories = ["CAFishPlanting/Views", "CAFishPlanting/App", "PlantingCore/Sources"].map { ios.appendingPathComponent($0) }
        // One-line Swift string literals, escapes included.
        let pattern = try NSRegularExpression(pattern: #""((?:[^"\\\n]|\\.)*)""#)
        var found: [Literal] = []
        for directory in directories {
            guard let files = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: nil) else {
                XCTFail("missing source directory \(directory.path)")
                continue
            }
            for case let file as URL in files where file.pathExtension == "swift" {
                let source = try String(contentsOf: file, encoding: .utf8)
                for line in source.components(separatedBy: .newlines) {
                    let code = line.trimmingCharacters(in: .whitespaces)
                    if code.hasPrefix("//") { continue } // comments may discuss the rule
                    let range = NSRange(code.startIndex..., in: code)
                    for match in pattern.matches(in: code, range: range) {
                        guard let r = Range(match.range(at: 1), in: code) else { continue }
                        found.append(Literal(file: file.lastPathComponent, text: String(code[r])))
                    }
                }
            }
        }
        return found
    }
}
