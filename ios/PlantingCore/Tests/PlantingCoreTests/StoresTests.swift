import XCTest
@testable import PlantingCore

final class FavouritesTests: XCTestCase {
    func testAddRemoveToggleDeduplicates() {
        var f = Favourites()
        f.add("cdfw-1")
        f.add("cdfw-1")
        XCTAssertEqual(f.ids, ["cdfw-1"], "adding twice must not duplicate")
        XCTAssertTrue(f.contains("cdfw-1"))
        XCTAssertFalse(f.toggle("cdfw-1"))
        XCTAssertFalse(f.contains("cdfw-1"))
        XCTAssertTrue(f.toggle("cdfw-1"))
        XCTAssertTrue(f.contains("cdfw-1"))
    }

    func testInitDeduplicatesPreservingFirstOccurrenceOrder() {
        let f = Favourites(ids: ["a", "b", "a", "c", "b"])
        XCTAssertEqual(f.ids, ["a", "b", "c"])
    }
}

final class PersistenceTests: XCTestCase {
    var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("cafp-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    func testFavouritesRoundTripThroughDisk() throws {
        let layout = AppStorageLayout(directory: tempDir)
        let store = FavouritesStore(layout: layout)
        XCTAssertTrue(store.load().isEmpty, "no file yet = empty, not a crash")

        var f = store.load()
        f.add("cdfw-1"); f.add("cdfw-2")
        try store.save(f)

        let reloaded = store.load()
        XCTAssertEqual(reloaded.ids, ["cdfw-1", "cdfw-2"])
    }

    func testFavouritesCorruptFileReadsAsEmptyNotCrash() throws {
        let layout = AppStorageLayout(directory: tempDir)
        try "not json at all {{{".write(to: layout.favouritesFile, atomically: true, encoding: .utf8)
        let store = FavouritesStore(layout: layout)
        XCTAssertTrue(store.load().isEmpty, "a corrupt favourites file must read as empty, never crash the app")
    }

    func testAlertStateRoundTripThroughDisk() throws {
        let layout = AppStorageLayout(directory: tempDir)
        let store = AlertStateStore(layout: layout)
        var state = store.load()
        state.lastListed["cdfw-1"] = [PlantKey(weekStart: PlainDate(isoDate: "2026-09-13")!, species: "Trout")]
        try store.save(state)

        let reloaded = store.load()
        XCTAssertEqual(reloaded, state)
    }

    func testSnapshotStoreAtomicReplaceRejectsMalformedBytes() throws {
        let layout = AppStorageLayout(directory: tempDir)
        let bundled = tempDir.appendingPathComponent("bundled.json")
        try Fixture.data(Fixture.minimalValid).write(to: bundled)
        let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        let before = store.snapshot

        XCTAssertThrowsError(try store.replace(with: Data("not json".utf8), etag: "\"x\""))
        XCTAssertEqual(store.snapshot, before, "a bad download must never displace the last good snapshot")
        XCTAssertFalse(FileManager.default.fileExists(atPath: layout.snapshotFile.path), "nothing partial should ever be written to disk")
    }

    func testSnapshotStoreOffersBundledWhenNoStoredCopyExists() throws {
        let layout = AppStorageLayout(directory: tempDir)
        let bundled = tempDir.appendingPathComponent("bundled.json")
        try Fixture.data(Fixture.minimalValid).write(to: bundled)
        let store = try SnapshotStore(layout: layout, bundledSnapshotURL: bundled)
        XCTAssertEqual(store.origin, .bundled)
        XCTAssertEqual(store.snapshot.waters.count, 1)
    }

    func testSnapshotStoreThrowsWithNoUsableSnapshotAtAll() {
        let layout = AppStorageLayout(directory: tempDir)
        XCTAssertThrowsError(try SnapshotStore(layout: layout, bundledSnapshotURL: nil))
    }

    func testEntitlementDefaultsToNotPurchasedWithNoFile() throws {
        let layout = AppStorageLayout(directory: tempDir)
        let store = EntitlementStore(layout: layout)
        XCTAssertEqual(store.load(), PurchaseEntitlement(isPurchased: false))
    }

    func testEntitlementRoundTripsThroughDisk() throws {
        let layout = AppStorageLayout(directory: tempDir)
        let store = EntitlementStore(layout: layout)
        try store.save(PurchaseEntitlement(isPurchased: true))
        XCTAssertEqual(store.load(), PurchaseEntitlement(isPurchased: true))
    }

    func testEntitlementCorruptFileReadsAsNotPurchasedNotCrash() throws {
        let layout = AppStorageLayout(directory: tempDir)
        try "not json at all {{{".write(to: layout.entitlementFile, atomically: true, encoding: .utf8)
        let store = EntitlementStore(layout: layout)
        XCTAssertEqual(store.load(), PurchaseEntitlement(isPurchased: false), "a corrupt entitlement file must fail toward locked, never toward a free unlock")
    }
}

final class FreeTierTests: XCTestCase {
    func testEntitledHasNoLimit() {
        XCTAssertTrue(FreeTier.canAddFavourite(currentCount: FreeTier.maxFavourites, isEntitled: true))
        XCTAssertTrue(FreeTier.canAddFavourite(currentCount: 999, isEntitled: true))
    }

    func testNonPurchaserIsCappedAtMaxFavourites() {
        for count in 0..<FreeTier.maxFavourites {
            XCTAssertTrue(FreeTier.canAddFavourite(currentCount: count, isEntitled: false), "count \(count) should still be under the cap")
        }
        XCTAssertFalse(FreeTier.canAddFavourite(currentCount: FreeTier.maxFavourites, isEntitled: false))
        XCTAssertFalse(FreeTier.canAddFavourite(currentCount: FreeTier.maxFavourites + 1, isEntitled: false))
    }
}
