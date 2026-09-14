import Foundation

/// The one host this app ever talks to. `HostAllowlistTests` scans the
/// Swift source tree and fails if any other host is referenced from code.
///
/// From `schema/README.md` (the pipeline lane, commit 1b1d0eb): "The domain
/// is undecided (DECISIONS 0006). When a custom domain is set, the
/// `github.io` URL becomes a 301 to it, so **follow redirects**." URLSession
/// follows redirects for a plain GET by default, so no code change is
/// needed when that happens — only this constant, if the path also moves.
public enum SnapshotEndpoint {
    public static let url = URL(string: "https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json")!
    public static var host: String { url.host! }

    /// The per-water site page. `schema/README.md` defines the path
    /// convention (`waters[].slug` → `/water/<slug>/`) but the schema
    /// carries no per-water site URL field, so this is derived from the
    /// snapshot endpoint's own origin rather than a second hardcoded host —
    /// the app never references any host besides `host` above. If the
    /// pipeline/site lane later adds an explicit `site_url` to the schema,
    /// prefer that field over this derivation.
    public static func siteWaterURL(slug: String) -> URL? {
        var components = URLComponents()
        components.scheme = url.scheme
        components.host = url.host
        components.port = url.port
        components.path = "/ca-fish-planting-alerts/water/\(slug)/"
        return components.url
    }
}
