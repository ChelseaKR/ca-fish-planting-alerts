import XCTest
@testable import PlantingCore

/// Deliverable #5: "A test that fails if any host other than the snapshot
/// host appears in the source tree." Scoped to the app's own *production*
/// Swift source (where a network call could originate) — not test fixtures,
/// which legitimately reference CDFW's own host as sample data, and not the
/// standard `http://www.apple.com/DTDs/...` plist DOCTYPE boilerplate, which
/// is never fetched.
final class HostAllowlistTests: XCTestCase {
    func testOnlyTheSnapshotHostAppearsInProductionSource() throws {
        let hosts = try hostsReferenced(under: productionSourceDirectories())
        let unexpected = hosts.subtracting([SnapshotEndpoint.host])
        XCTAssertTrue(unexpected.isEmpty, "found a host other than \(SnapshotEndpoint.host) in app source: \(unexpected.sorted())")
        XCTAssertTrue(hosts.contains(SnapshotEndpoint.host), "sanity check: the scan should at least find the snapshot host itself")
    }

    // MARK: -

    private func iosRoot() throws -> URL {
        // .../ios/CAFishPlantingTests/HostAllowlistTests.swift -> .../ios
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
    }

    private func productionSourceDirectories() throws -> [URL] {
        let ios = try iosRoot()
        return [
            ios.appendingPathComponent("PlantingCore/Sources"),
            ios.appendingPathComponent("CAFishPlanting/App"),
            ios.appendingPathComponent("CAFishPlanting/Views"),
        ]
    }

    private func hostsReferenced(under directories: [URL]) throws -> Set<String> {
        let pattern = try NSRegularExpression(pattern: #"https?://([A-Za-z0-9.-]+)"#)
        var hosts = Set<String>()
        for directory in directories {
            guard let enumerator = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: nil) else { continue }
            for case let file as URL in enumerator where file.pathExtension == "swift" {
                let text = try String(contentsOf: file, encoding: .utf8)
                let range = NSRange(text.startIndex..., in: text)
                for match in pattern.matches(in: text, range: range) {
                    guard let hostRange = Range(match.range(at: 1), in: text) else { continue }
                    hosts.insert(String(text[hostRange]))
                }
            }
        }
        return hosts
    }
}
