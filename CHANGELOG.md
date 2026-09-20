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
- An iOS app (SwiftUI) over the same snapshot: favorite waters, background
  refresh, and a local notification when a favorite appears in a new week
  (PR 2). It also has a one-time StoreKit 2 purchase (PR 7), a first-run welcome
  screen (PR 8), and a way to share a water (PR 9). The app is not yet in the
  App Store.
- App: a Shortcuts and Siri action, "When is <water> scheduled in Trout
  Truck?", answered from the schedule already on the device: the week the
  water is next scheduled for (a week, never a day), or that it isn't on
  the schedule for that week or later and when it last was. It always
  names the schedule's week, says when that week has ended, and makes no
  network request.
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
- App: tapping an alert opens that water's screen, under Favorites, even
  when the tap launches the app. An alert that arrives while the app is
  open shows as a banner. A `trouttruck://water/<id>` link opens a water
  the same way, for the Home Screen widget. It makes no network request.
- Site: a page for every county with a water on the schedule, and an index
  of them by CDFW region. Water pages link their county pages and the other
  waters in them. Pages carry schema.org structured data: breadcrumbs, the
  water as a place, and the schedule history as a dataset, but no events,
  because a plant is a scheduled week. There is a place for the Search
  Console verification tag, and the owner steps are in
  `docs/SEARCH-CONSOLE.md` (ADR 0013).
- App: a Home Screen and Lock Screen widget, "Favorite waters": which of
  your favorites are on CDFW's schedule this week, a later week, or not
  listed, each with its week. It reads what the app already downloaded,
  through an App Group, and makes no network request. When the week ends
  it stops saying "this week", and a failed check or a missing schedule is
  said plainly. Tapping a water opens it. The widget is part of full
  access (DECISIONS 0015): before the purchase it says so, shows no
  favorites, and a tap opens the purchase screen. A purchase, a restore or
  a refund redraws it at once.
- A root `make verify` that runs every lint, type, test and security gate,
  and runs in CI (PR 18). CodeQL, workflow scanning, and a weekly scan of the
  full history for secrets (PR 21).
- App: Favorites has search (name, a name CDFW used before, or county) and
  a county filter, swipe to remove, pull to refresh, and the schedule's
  week at the top. A favorite the schedule no longer lists is shown as
  such, and can be removed, instead of the list saying there are no
  favorites. Browse has a county filter within the chosen region, and its
  search matches every word typed and earlier names too.

### Changed

- The pipeline records a well-formed schedule table with no rows as an empty
  week instead of failing the run (PR 4).
- App: the one-time purchase unlocks local notifications. Favorites and
  browsing are free, and there is no longer a cap on favorites (PR 12).
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
- App: the accent color is the icon's green (a lighter green in dark mode),
  instead of the default blue, and keeps 4.5:1 contrast in both. Adding
  or removing a favorite gives a haptic tap. Pull down on Browse to check
  for a newer schedule now. Launch no longer decodes the bundled 1 MB
  snapshot when the downloaded one is at least as new, which halves the
  decoding at launch once a schedule has been downloaded.
- App, site and docs use American English throughout: the tab and its
  buttons say "Favorites", About says "Data source and license", and the
  site's privacy and about pages use American spellings too. Saved favorites
  and the published snapshot are unaffected: the on-disk file
  (`favourites.json`) and the snapshot's `licence` field keep their original
  spelling. The screenshot `03-favourites.png` is now `03-favorites.png`.

### Fixed

- App: Product > Archive works. The shared scheme built both test targets
  for archiving, and in the Release configuration their `@testable` imports
  can't resolve, so every archive failed before signing was reached. The
  test targets are still built for testing, running and analysis.
- The daily publish run had never succeeded, because the freshness check
  read CDFW's stated week start as "today". It now compares weeks. The same
  change stops a plant that ages off the page from being recorded as
  canceled, and stops the run from crashing on a water whose rows have
  all aged off (PR 13).
- App: the shared Xcode scheme points at the right StoreKit configuration
  file (PR 24).
- App accessibility: at the largest text sizes a water's "This week" tag
  moves under its name instead of squeezing it, and the purchase sheet
  scrolls and wraps its title instead of cutting off. Text that was below
  4.5:1 contrast (the tag, "Schedule changed" in orange, "Unlocked" in
  green, a purchase error in red, the purchase sheet's gray body text over
  its see-through half-height background) now uses the label colors on an
  opaque sheet, with the color kept on the symbol. Gray text (county
  names, species, captions, footnotes, section headers) is darker: iOS's
  own gray measured 3.3:1 to 3.4:1 in light mode, and the app's grays now
  meet 4.5:1 on every background in light and dark mode without Increase
  Contrast, keeping primary, secondary and tertiary as distinct steps. An
  automated accessibility audit (`AccessibilityAuditUITests`) covers every
  main screen and the purchase sheet at the default size in light and
  dark mode and at the largest size, and fails on any contrast finding in
  the app's own text, "nearly passed" included. The smoke test no longer
  taps the Region row by mistake.
- App: it checks for a newer schedule on launch and on return to the
  foreground, at most every 6 hours (30 minutes after a failed check).
  Before, a fresh install showed the schedule bundled at build time until
  iOS ran the background task. Browse now says which week the schedule is
  for and how the last check went. A failed check or an ended week is said
  plainly, and the last good schedule stays on screen, labeled with its
  week (PR 37).
- App: the water screen and the share text say "Last scheduled for the week
  of …", not "Last planted …". CDFW publishes scheduled plants, which are
  subject to change, not confirmed ones (PR 37).
- A water CDFW drops from both its schedule table and its water picker no
  longer stops the daily run for every water. It is left out of that run's
  snapshot and site, its history is kept, and the run prints a warning that
  names it; it returns when CDFW lists it again. More than five at once
  refuses the run as a likely truncated page. Every refusal on the snapshot
  path (a water with no alias entry, a county with no region, a schema
  failure) is now one `run refused -- nothing published` line instead of a
  traceback. Not seen in production.

### Security

- The publish job pins every action to a commit, keeps no dependency cache,
  secret-scans the data it is about to commit, and opens an issue when a run
  fails (PR 21).
