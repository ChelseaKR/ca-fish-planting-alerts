# Changelog

All notable changes to Trout Truck (repository `ca-fish-planting-alerts`) are
recorded here. Format: [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
Versions will follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
once releases exist. No release has been tagged yet (#3).

"PR N" is a pull request in the original repository, which stays private.
This repository was republished with a new history on 2026-09-18
(`docs/adr/0014-republished-as-a-new-public-repository.md`).

## [Unreleased]

### Added

- A daily pipeline over CDFW's Fish Planting Schedule. It keeps an
  append-only history per water, publishes a schema-validated snapshot
  (`schema/snapshot.v1.json`) for the app, and builds a static site with a
  page and a subscribable `.ics` calendar for every water (PR 1).
- An iOS app (SwiftUI) over the same snapshot: favourite waters, background
  refresh, and a local notification when a favourite appears in a new week
  (PR 2). It also has a one-time StoreKit 2 purchase (PR 7), a first-run welcome
  screen (PR 8), and a way to share a water (PR 9). The app is not yet in the
  App Store.
- A curated species-name table, so one species is never split across two
  spellings (PR 6).
- Site: page titles and descriptions for search, a privacy page and a
  support page, and copy that says when the schedule was last checked (PR 14).
  The product is named Trout Truck (PR 16).
- Site: Google Analytics 4 on every page. It does not load when the browser
  sends Global Privacy Control or Do Not Track. The app still collects
  nothing (PR 20). An "Opt out of analytics" control in the footer is
  remembered on the device (PR 31).
- App: the About screen says the app is not affiliated with CDFW (PR 19).
- Site: a page for every county with a water on the schedule, and an index
  of them by CDFW region. Water pages link their county pages and the other
  waters in them. Pages carry schema.org structured data: breadcrumbs, the
  water as a place, and the schedule history as a dataset, but no events,
  because a plant is a scheduled week. There is a place for the Search
  Console verification tag, and the owner steps are in
  `docs/SEARCH-CONSOLE.md` (ADR 0013).
- A root `make verify` that runs every lint, type, test and security gate,
  and runs in CI (PR 18). CodeQL, workflow scanning, and a weekly scan of the
  full history for secrets (PR 21).

### Changed

- The pipeline records a well-formed schedule table with no rows as an empty
  week instead of failing the run (PR 4).
- App: the one-time purchase unlocks local notifications. Favourites and
  browsing are free, and there is no longer a cap on favourites (PR 12).
- Site: water page titles read "<water> (<county> County) <species> planting
  schedule", with the species from the data, so the catfish-only park lakes
  are no longer called trout waters. A water with nothing listed this week
  or later says so plainly, and says that this does not mean there are no
  fish (ADR 0013).

### Fixed

- The daily publish run had never succeeded, because the freshness check
  read CDFW's stated week start as "today". It now compares weeks. The same
  change stops a plant that ages off the page from being recorded as
  cancelled, and stops the run from crashing on a water whose rows have
  all aged off (PR 13).
- App: the shared Xcode scheme points at the right StoreKit configuration
  file (PR 24).
- App: it checks for a newer schedule on launch and on return to the
  foreground, at most every 6 hours (30 minutes after a failed check).
  Before, a fresh install showed the schedule bundled at build time until
  iOS ran the background task. Browse now says which week the schedule is
  for and how the last check went. A failed check or an ended week is said
  plainly, and the last good schedule stays on screen, labelled with its
  week (PR 37).
- App: the water screen and the share text say "Last scheduled for the week
  of …", not "Last planted …". CDFW publishes scheduled plants, which are
  subject to change, not confirmed ones (PR 37).

### Security

- The publish job pins every action to a commit, keeps no dependency cache,
  secret-scans the data it is about to commit, and opens an issue when a run
  fails (PR 21).
