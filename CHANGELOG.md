# Changelog

All notable changes to Trout Truck (repository `ca-fish-planting-alerts`) are
recorded here. Format: [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
Versions will follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
once releases exist. No release has been tagged yet (#23).

## [Unreleased]

### Added

- A daily pipeline over CDFW's Fish Planting Schedule. It keeps an
  append-only history per water, publishes a schema-validated snapshot
  (`schema/snapshot.v1.json`) for the app, and builds a static site with a
  page and a subscribable `.ics` calendar for every water (#1).
- An iOS app (SwiftUI) over the same snapshot: favourite waters, background
  refresh, and a local notification when a favourite appears in a new week
  (#2). It also has a one-time StoreKit 2 purchase (#7), a first-run welcome
  screen (#8), and a way to share a water (#9). The app is not yet in the
  App Store.
- A curated species-name table, so one species is never split across two
  spellings (#6).
- Site: page titles and descriptions for search, a privacy page and a
  support page, and copy that says when the schedule was last checked (#14).
  The product is named Trout Truck (#16).
- Site: Google Analytics 4 on every page. It does not load when the browser
  sends Global Privacy Control or Do Not Track. The app still collects
  nothing (#20). An "Opt out of analytics" control in the footer is
  remembered on the device (#31).
- App: the About screen says the app is not affiliated with CDFW (#19).
- A root `make verify` that runs every lint, type, test and security gate,
  and runs in CI (#18). CodeQL, workflow scanning, and a weekly scan of the
  full history for secrets (#21).

### Changed

- The pipeline records a well-formed schedule table with no rows as an empty
  week instead of failing the run (#4).
- App: the one-time purchase unlocks local notifications. Favourites and
  browsing are free, and there is no longer a cap on favourites (#12).

### Fixed

- The daily publish run had never succeeded, because the freshness check
  read CDFW's stated week start as "today". It now compares weeks. The same
  change stops a plant that ages off the page from being recorded as
  cancelled, and stops the run from crashing on a water whose rows have
  all aged off (#13).
- App: the shared Xcode scheme points at the right StoreKit configuration
  file (#24).

### Security

- The publish job pins every action to a commit, keeps no dependency cache,
  secret-scans the data it is about to commit, and opens an issue when a run
  fails (#21).
