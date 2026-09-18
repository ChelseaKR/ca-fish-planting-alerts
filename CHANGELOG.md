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
- Site: a page for every county with a water on the schedule, and an index
  of them by CDFW region. Water pages link their county pages and the other
  waters in them. Pages carry schema.org structured data: breadcrumbs, the
  water as a place, and the schedule history as a dataset, but no events,
  because a plant is a scheduled week. There is a place for the Search
  Console verification tag, and the owner steps are in
  `docs/SEARCH-CONSOLE.md` (ADR 0013).
- A root `make verify` that runs every lint, type, test and security gate,
  and runs in CI (#18). CodeQL, workflow scanning, and a weekly scan of the
  full history for secrets (#21).
- App: Favorites has search (name, a name CDFW used before, or county) and
  a county filter, swipe to remove, pull to refresh, and the schedule's
  week at the top. A favorite the schedule no longer lists is shown as
  such, and can be removed, instead of the list saying there are no
  favorites. Browse has a county filter within the chosen region, and its
  search matches every word typed and earlier names too.

### Changed

- The pipeline records a well-formed schedule table with no rows as an empty
  week instead of failing the run (#4).
- App: the one-time purchase unlocks local notifications. Favourites and
  browsing are free, and there is no longer a cap on favourites (#12).
- App: the screen before the notification permission prompt says, point
  by point, what an alert is (one per new week for a favorite, naming the
  week, never a day), that it is made on the device, that no other
  notifications come, and, before purchase, that alerts need full access.
  It scrolls at the largest text sizes. It shows only while iOS hasn't
  asked yet. About offers "Turn on notifications" while iOS hasn't asked,
  and "Open notification settings" once they're off, and re-reads the
  setting on return from Settings.
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
  all aged off (#13).
- App: the shared Xcode scheme points at the right StoreKit configuration
  file (#24).
- App: it checks for a newer schedule on launch and on return to the
  foreground, at most every 6 hours (30 minutes after a failed check).
  Before, a fresh install showed the schedule bundled at build time until
  iOS ran the background task. Browse now says which week the schedule is
  for and how the last check went. A failed check or an ended week is said
  plainly, and the last good schedule stays on screen, labelled with its
  week (#37).
- App: the water screen and the share text say "Last scheduled for the week
  of …", not "Last planted …". CDFW publishes scheduled plants, which are
  subject to change, not confirmed ones (#37).

### Security

- The publish job pins every action to a commit, keeps no dependency cache,
  secret-scans the data it is about to commit, and opens an issue when a run
  fails (#21).
