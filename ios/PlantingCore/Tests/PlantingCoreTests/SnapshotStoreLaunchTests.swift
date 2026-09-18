import XCTest
@testable import PlantingCore

/// Launch reads the bundled snapshot only when it could win. The choice
/// itself never changes: the newer `generated_at` wins, and the stored copy
/// wins a tie.
final class SnapshotStoreLaunchTests: XCTestCase {
    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("launch-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    private func json(generatedAt: String) -> String {
        Fixture.minimalValid.replacingOccurrences(of: "\"generated_at\": \"2026-09-13T06:12:44Z\"", with: "\"generated_at\": \"\(generatedAt)\"")
    }

    private func write(_ json: String, to name: String) throws -> URL {
        let url = tempDir.appendingPathComponent(name)
        try Fixture.data(json).write(to: url)
        return url
    }

    func testTheFixtureCarriesGeneratedAtWhereThePeekLooks() throws {
        XCTAssertTrue(Fixture.minimalValid.contains("\"generated_at\": \"2026-09-13T06:12:44Z\""), "the fixture changed; update json(generatedAt:)")
        let url = try write(json(generatedAt: "2026-09-14T01:02:03Z"), to: "peek.json")
        XCTAssertEqual(SnapshotStore.peekGeneratedAt(url), ISO8601DateFormatter().date(from: "2026-09-14T01:02:03Z"))
    }

    /// The real bundled snapshot: the pipeline writes `generated_at` near
    /// the top, and the peek agrees with a full decode.
    func testThePeekAgreesWithAFullDecodeOfTheBundledSnapshot() throws {
        let data = try Fixture.bundledAppFixtureData()
        let url = tempDir.appendingPathComponent("bundled-real.json")
        try data.write(to: url)
        let full = try SnapshotDecoder().decode(data)
        XCTAssertEqual(SnapshotStore.peekGeneratedAt(url), full.generatedAt)
    }

    func testAStoredCopyAtLeastAsNewSkipsDecodingTheBundledOne() throws {
        let layout = AppStorageLayout(directory: tempDir.appendingPathComponent("store"))
        try layout.ensureDirectory()
        let bundled = try write(json(generatedAt: "2026-09-13T06:12:44Z"), to: "bundled.json")
        try Fixture.data(json(generatedAt: "2026-09-14T06:00:00Z")).write(to: layout.snapshotFile)

        let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        XCTAssertEqual(store.origin, .stored)
        XCTAssertFalse(store.decodedBundledCopy, "an older bundled copy can't win, so it isn't decoded")

        // A tie goes to the stored copy, as before.
        try Fixture.data(json(generatedAt: "2026-09-13T06:12:44Z")).write(to: layout.snapshotFile)
        let tie = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        XCTAssertEqual(tie.origin, .stored)
        XCTAssertFalse(tie.decodedBundledCopy)
    }

    /// An app update that ships a newer snapshot than the device downloaded.
    func testANewerBundledCopyIsDecodedAndWins() throws {
        let layout = AppStorageLayout(directory: tempDir.appendingPathComponent("store"))
        try layout.ensureDirectory()
        let bundled = try write(json(generatedAt: "2026-09-20T06:00:00Z"), to: "bundled.json")
        try Fixture.data(json(generatedAt: "2026-09-14T06:00:00Z")).write(to: layout.snapshotFile)

        let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        XCTAssertTrue(store.decodedBundledCopy)
        XCTAssertEqual(store.origin, .bundled)
        XCTAssertEqual(store.snapshot.generatedAt, ISO8601DateFormatter().date(from: "2026-09-20T06:00:00Z"))
    }

    /// A stored copy that doesn't decode can't be compared against, so the
    /// bundled one is decoded and used, and the problem is reported.
    func testABrokenStoredCopyFallsBackToTheBundledOne() throws {
        let layout = AppStorageLayout(directory: tempDir.appendingPathComponent("store"))
        try layout.ensureDirectory()
        let bundled = try write(json(generatedAt: "2026-09-13T06:12:44Z"), to: "bundled.json")
        try Data("{\"generated_at\": \"2026-12-31T00:00:00Z\", truncated".utf8).write(to: layout.snapshotFile)

        let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        XCTAssertTrue(store.decodedBundledCopy)
        XCTAssertEqual(store.origin, .bundled)
        XCTAssertNotNil(store.storedCopyProblem)
    }

    /// When the peek finds nothing, the whole file is decoded, as before.
    func testNoGeneratedAtNearTheTopMeansAFullDecode() throws {
        let layout = AppStorageLayout(directory: tempDir.appendingPathComponent("store"))
        try layout.ensureDirectory()
        let padding = String(repeating: " ", count: 600)
        let late = json(generatedAt: "2026-09-13T06:12:44Z").replacingOccurrences(of: "{\n", with: "{\n\(padding)", options: [], range: nil)
        let bundled = try write(late, to: "bundled.json")
        XCTAssertNil(SnapshotStore.peekGeneratedAt(bundled), "sanity check: generated_at is past the peeked bytes")
        try Fixture.data(json(generatedAt: "2026-09-14T06:00:00Z")).write(to: layout.snapshotFile)

        let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        XCTAssertTrue(store.decodedBundledCopy)
        XCTAssertEqual(store.origin, .stored, "the newer stored copy still wins")
    }
}
