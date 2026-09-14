import Foundation

public enum RefreshOutcome: Equatable, Sendable {
    case updated
    case notModified
    case failed(String)
}

/// The app's entire network surface: one plain GET of the snapshot URL with
/// `If-None-Match`. No cookies, no cache, no credentials, no identifiers, no
/// other hosts. The session is ephemeral so nothing persists between runs.
public struct SnapshotRefresher: Sendable {
    public static let maximumBodyBytes = 32 * 1024 * 1024

    public let session: URLSession
    public let endpoint: URL

    public init(session: URLSession, endpoint: URL = SnapshotEndpoint.url) {
        self.session = session
        self.endpoint = endpoint
    }

    /// `protocolClasses` exists so tests can intercept without a network.
    public static func makeSession(protocolClasses: [AnyClass]? = nil) -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil
        config.httpCookieAcceptPolicy = .never
        config.httpShouldSetCookies = false
        config.urlCache = nil
        config.urlCredentialStorage = nil
        config.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        config.waitsForConnectivity = false
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 120
        config.httpAdditionalHeaders = nil
        if let protocolClasses { config.protocolClasses = protocolClasses }
        return URLSession(configuration: config)
    }

    /// Pure, so the headers can be asserted.
    public func makeRequest(etag: String?) -> URLRequest {
        var request = URLRequest(url: endpoint)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.httpShouldHandleCookies = false
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        // A fixed UA with no version, device, or locale: CFNetwork's default
        // would otherwise append the framework build.
        request.setValue("CAFishPlanting", forHTTPHeaderField: "User-Agent")
        if let etag { request.setValue(etag, forHTTPHeaderField: "If-None-Match") }
        return request
    }

    @discardableResult
    public func refresh(into store: SnapshotStore, now: Date = Date()) async -> RefreshOutcome {
        precondition(endpoint.host == SnapshotEndpoint.host, "refresh is only ever against the snapshot host")
        let request = makeRequest(etag: store.meta.etag)
        let data: Data
        let response: HTTPURLResponse
        do {
            let (d, r) = try await session.data(for: request)
            guard let http = r as? HTTPURLResponse else {
                store.recordFailure("not an HTTP response", now: now)
                return .failed("not an HTTP response")
            }
            data = d
            response = http
        } catch {
            let message = (error as NSError).localizedDescription
            store.recordFailure(message, now: now)
            return .failed(message)
        }

        switch response.statusCode {
        case 304:
            store.recordNotModified(now: now)
            return .notModified
        case 200:
            guard data.count <= Self.maximumBodyBytes else {
                let message = "body too large: \(data.count) bytes"
                store.recordFailure(message, now: now)
                return .failed(message)
            }
            let etag = response.value(forHTTPHeaderField: "ETag")
            do {
                try store.replace(with: data, etag: etag, now: now)
                return .updated
            } catch SnapshotStoreError.notNewer {
                store.recordNotModified(now: now)
                return .notModified
            } catch {
                let message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
                store.recordFailure(message, now: now)
                return .failed(message)
            }
        default:
            let message = "HTTP \(response.statusCode)"
            store.recordFailure(message, now: now)
            return .failed(message)
        }
    }
}
