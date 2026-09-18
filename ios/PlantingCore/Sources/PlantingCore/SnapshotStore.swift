import Foundation

/// Sidecar for the stored snapshot: the ETag we hold and the refresh ledger
/// the About screen shows. Never contains anything from the device.
public struct SnapshotMeta: Codable, Equatable, Sendable {
    public var etag: String?
    public var lastAttemptAt: Date?
    public var lastSuccessAt: Date?
    public var lastOutcome: String?
    public var lastError: String?
    public init(etag: String? = nil, lastAttemptAt: Date? = nil, lastSuccessAt: Date? = nil, lastOutcome: String? = nil, lastError: String? = nil) {
        self.etag = etag; self.lastAttemptAt = lastAttemptAt; self.lastSuccessAt = lastSuccessAt
        self.lastOutcome = lastOutcome; self.lastError = lastError
    }
}

public enum SnapshotOrigin: String, Sendable {
    case bundled
    case stored
}

public enum SnapshotStoreError: Error, Equatable, LocalizedError {
    case noUsableSnapshot(bundled: String?, stored: String?)
    case notNewer

    public var errorDescription: String? {
        switch self {
        case .noUsableSnapshot(let b, let s):
            return "No usable snapshot. Bundled: \(b ?? "missing"). Stored: \(s ?? "missing")."
        case .notNewer:
            return "The fetched snapshot is not newer than the one held."
        }
    }
}

/// Offline-first. Holds exactly one *last good* snapshot at all times:
///
/// * On load, the stored copy and the bundled copy are both decoded and the
///   one with the newer `generated_at` wins (an app update can ship a newer
///   bundle than what a device last fetched). A stored copy that fails to
///   decode is ignored, not deleted, and reported.
/// * `replace(with:)` decodes **before** writing and writes atomically, so a
///   truncated download or a contract change can never displace the last
///   good snapshot.
///
/// Not thread-safe by design: the app drives it from one actor.
public final class SnapshotStore {
    public let layout: AppStorageLayout
    public let bundledSnapshotURL: URL?
    private let decoder: SnapshotDecoder
    private let metaFile: JSONFileStore<SnapshotMeta>

    public private(set) var snapshot: Snapshot
    public private(set) var origin: SnapshotOrigin
    public private(set) var meta: SnapshotMeta
    /// Why the stored copy was not used, if it existed and was not.
    public private(set) var storedCopyProblem: String?

    public init(layout: AppStorageLayout, bundledSnapshotURL: URL?, decoder: SnapshotDecoder = SnapshotDecoder()) throws {
        self.layout = layout
        self.bundledSnapshotURL = bundledSnapshotURL
        self.decoder = decoder
        self.metaFile = JSONFileStore(url: layout.snapshotMetaFile)
        try layout.ensureDirectory()

        var bundled: Snapshot?
        var bundledProblem: String?
        if let url = bundledSnapshotURL {
            do { bundled = try decoder.decode(try Data(contentsOf: url)) }
            catch { bundledProblem = String(describing: error) }
        } else {
            bundledProblem = "no bundled snapshot URL"
        }

        var stored: Snapshot?
        var storedProblem: String?
        if FileManager.default.fileExists(atPath: layout.snapshotFile.path) {
            do { stored = try decoder.decode(try Data(contentsOf: layout.snapshotFile)) }
            catch { storedProblem = String(describing: error) }
        }

        switch (bundled, stored) {
        case (let b?, let s?):
            if s.generatedAt >= b.generatedAt { snapshot = s; origin = .stored } else { snapshot = b; origin = .bundled }
        case (let b?, nil):
            snapshot = b; origin = .bundled
        case (nil, let s?):
            snapshot = s; origin = .stored
        case (nil, nil):
            throw SnapshotStoreError.noUsableSnapshot(bundled: bundledProblem, stored: storedProblem)
        }
        storedCopyProblem = storedProblem
        meta = (try? metaFile.load()) ?? SnapshotMeta()
    }

    /// Decode, then write atomically, then swap. Throws and changes nothing if
    /// the bytes do not decode or are not newer than what is held.
    @discardableResult
    public func replace(with data: Data, etag: String?, now: Date = Date()) throws -> Snapshot {
        let candidate = try decoder.decode(data)
        guard candidate.generatedAt > snapshot.generatedAt || origin == .bundled else {
            throw SnapshotStoreError.notNewer
        }
        try data.write(to: layout.snapshotFile, options: [.atomic])
        snapshot = candidate
        origin = .stored
        storedCopyProblem = nil
        meta.etag = etag
        meta.lastAttemptAt = now
        meta.lastSuccessAt = now
        meta.lastOutcome = "updated"
        meta.lastError = nil
        try? metaFile.save(meta)
        return candidate
    }

    public func recordNotModified(now: Date = Date()) {
        meta.lastAttemptAt = now
        meta.lastSuccessAt = now
        meta.lastOutcome = "not modified"
        meta.lastError = nil
        try? metaFile.save(meta)
    }

    /// `meta.lastOutcome` after a failed check (see `SnapshotMeta.lastAttemptFailed`).
    public static let failedOutcome = "failed"

    public func recordFailure(_ message: String, now: Date = Date()) {
        meta.lastAttemptAt = now
        meta.lastOutcome = Self.failedOutcome
        meta.lastError = message
        try? metaFile.save(meta)
    }
}
