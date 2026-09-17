import Foundation

/// Where the app keeps its few files. Injected so tests use a temp directory.
public struct AppStorageLayout: Sendable {
    public let directory: URL

    public init(directory: URL) { self.directory = directory }

    public var snapshotFile: URL { directory.appendingPathComponent("snapshot.json") }
    public var snapshotMetaFile: URL { directory.appendingPathComponent("snapshot.meta.json") }
    public var favouritesFile: URL { directory.appendingPathComponent("favourites.json") }
    public var alertStateFile: URL { directory.appendingPathComponent("alert-state.json") }
    public var entitlementFile: URL { directory.appendingPathComponent("entitlement.json") }

    /// `~/Library/Application Support/<bundle id>/`, created if needed.
    public static func applicationSupport(bundleIdentifier: String, fileManager: FileManager = .default) throws -> AppStorageLayout {
        let base = try fileManager.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let dir = base.appendingPathComponent(bundleIdentifier, isDirectory: true)
        try fileManager.createDirectory(at: dir, withIntermediateDirectories: true)
        return AppStorageLayout(directory: dir)
    }

    public func ensureDirectory(fileManager: FileManager = .default) throws {
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
    }
}

/// One JSON file, written atomically. `load()` returns `nil` for a missing
/// file and throws for a corrupt one so the caller decides what absence means.
public struct JSONFileStore<Value: Codable>: Sendable {
    public let url: URL
    public init(url: URL) { self.url = url }

    public func load() throws -> Value? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(Value.self, from: data)
    }

    public func save(_ value: Value) throws {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        let data = try encoder.encode(value)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url, options: [.atomic])
    }

    public func remove() throws {
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
    }
}

/// Ordered, unique. Order is the order the user favourited in.
public struct Favourites: Codable, Equatable, Sendable {
    public private(set) var ids: [Water.ID]

    public init(ids: [Water.ID] = []) {
        var seen = Set<Water.ID>()
        self.ids = ids.filter { seen.insert($0).inserted }
    }

    public func contains(_ id: Water.ID) -> Bool { ids.contains(id) }

    public mutating func add(_ id: Water.ID) {
        if !ids.contains(id) { ids.append(id) }
    }

    public mutating func remove(_ id: Water.ID) {
        ids.removeAll { $0 == id }
    }

    /// Returns `true` if the id is now a favourite.
    @discardableResult
    public mutating func toggle(_ id: Water.ID) -> Bool {
        if contains(id) { remove(id); return false }
        add(id); return true
    }

    public var isEmpty: Bool { ids.isEmpty }
    public var count: Int { ids.count }
}

/// Persistence for favourites. A corrupt file reads as empty and is left in
/// place until the next successful save overwrites it.
public struct FavouritesStore: Sendable {
    let file: JSONFileStore<Favourites>
    public init(layout: AppStorageLayout) { file = JSONFileStore(url: layout.favouritesFile) }

    public func load() -> Favourites {
        (try? file.load()) ?? Favourites()
    }

    public func save(_ favourites: Favourites) throws {
        try file.save(favourites)
    }
}

public struct AlertStateStore: Sendable {
    let file: JSONFileStore<AlertState>
    public init(layout: AppStorageLayout) { file = JSONFileStore(url: layout.alertStateFile) }

    public func load() -> AlertState {
        (try? file.load()) ?? AlertState()
    }

    public func save(_ state: AlertState) throws {
        try file.save(state)
    }
}

/// The one-time purchase's local state. `Transaction.currentEntitlements`
/// (StoreKit, app target only — this package stays Foundation-only) is
/// always the source of truth; this on-disk cache exists only so the app
/// can show the right paywall/unlocked state instantly at launch instead
/// of waiting on an async StoreKit round trip first.
public struct PurchaseEntitlement: Codable, Equatable, Sendable {
    public var isPurchased: Bool
    public init(isPurchased: Bool = false) { self.isPurchased = isPurchased }
}

/// Persistence for the cached entitlement. A corrupt or missing file reads
/// as "not purchased" — never as "purchased" — so a disk problem can only
/// ever fail toward showing the paywall again, not toward a false unlock;
/// the next successful StoreKit entitlement check corrects it either way.
public struct EntitlementStore: Sendable {
    let file: JSONFileStore<PurchaseEntitlement>
    public init(layout: AppStorageLayout) { file = JSONFileStore(url: layout.entitlementFile) }

    public func load() -> PurchaseEntitlement {
        (try? file.load()) ?? PurchaseEntitlement()
    }

    public func save(_ entitlement: PurchaseEntitlement) throws {
        try file.save(entitlement)
    }
}
