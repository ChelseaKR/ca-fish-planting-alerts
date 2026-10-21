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

- An open-data page at `/data/` and CSV and JSON files under `/data/v1/` (current schedule and weekly history for California, and for Tennessee in its own files), with a data dictionary, written by the site build from `snapshot/v2.json`. Linked from the footer and the about page. The page states the source and terms (CDFW Conditions of Use) and adds no license of its own; choosing one is the owner's call (`DATASET_LICENSE_URL`).

- Region pages at `/region/<slug>/` for each CDFW region that has a water
  (Northern, North Central, Bay Delta, Central, South Coast, Inland Deserts),
  named with CDFW's own labels: the waters scheduled this week and the week
  after, the region's counties, per-water calendar feeds, a breadcrumb, a
  sitemap entry, and links from the home page, the county index and each
  county page. `tests/test_site_region.py`.
- Species pages at `/species/trout/` and `/species/catfish/`, one for each
  species with a listed plant in the data: the waters CDFW has scheduled for
  this week and for next week, by CDFW region with county and water links, a
  unique title and description, a canonical URL, a breadcrumb, `CollectionPage`
  structured data (no new schema.org type) and sitemap entries. Linked from the
  home page and `/county/`. `tests/test_site_species.py` pins each rule with
  negative controls.
- Share cards: link previews now show a 1200x630 card (`og:image`,
  `twitter:card=summary_large_image`, alt text) drawn at build time by
  `pipeline/src/cfpa/share_cards.py`, one per kind of page (home, county,
  water, region, species, and state when other states are built). Each carries the site name, a title that says "scheduled",
  never "stocked", and the date CDFW's schedule was last checked. Five to six PNGs
  of about 28 KB, not one per page. Pillow is the new dependency; its bundled
  font is the only font used and none is fetched. Replaces the 600x600 icon
  as the preview image (`assets/social-card.png` is no longer published).
- Amazon Associates gear links on California water pages (DECISIONS 0029):
  four generic Amazon search links per water under "Gear for this water", each
  `rel="sponsored nofollow noopener"` and tagged `trouttruck-20` from one
  constant, with Amazon's disclosure, a plain affiliate sentence and a note that
  the links are Trout Truck's and CDFW does not endorse them or Amazon beside
  them; a "Gear links" section on the privacy page. On the website alone: none in the
  iOS app, the other pages, the data or the feeds, and no added tracking.
  `tests/test_site_affiliate.py` pins each rule with negative controls.
- A "What to bring" guide at `/gear/` (DECISIONS 0030): a seasonal packing
  list for anglers, with a link to CDFW's license page and Amazon search links
  per category (tagged, `rel="sponsored nofollow noopener"`, disclosed before
  the first link and after the last). Linked from each water page's gear block
  and the footer. Website only; `tests/test_site_gear_guide.py` pins the rules.
- Launch readiness for the App Store (DECISIONS 0028): the website's App
  Store surfaces follow one committed value, `APP_STORE_LIVE_DEFAULT`, which
  stays `False` until launch day; a test fails if the banner, badge, links,
  `MobileApplication` data and click event ever disagree; the event
  `app_store_click` (placement, link type) replaces `app_store_badge_click`
  and obeys the same privacy rules; `scripts/preflight_app_store_live.py`
  checks the listing before the flip; `docs/LAUNCH-CHECKLIST.md` lists the
  steps.
- Search and sharing markup from a 2026-10-19 audit: every page carries
  `og:image`, `twitter:image`, `twitter:title` and `twitter:description`; the
  support page carries a `FAQPage` that matches its visible questions and
  answers; and, once `APP_STORE_LIVE` is on, the home and support pages carry
  a `MobileApplication`. The home title is shorter (docs/adr/0013, addendum).

- Water locations for maps, from public-domain USGS data (GNIS and the
  National Hydrography Dataset), matched by name and county and never
  guessed: a water with several same-name candidates, or none, has no
  location. `cfpa-geocode` builds `pipeline/data/water_locations.json`
  offline; the owner can settle ambiguous waters in
  `pipeline/data/water_location_overrides.json`. Snapshot v1 is unchanged.
  The about page credits the USGS and the Census Bureau (DECISIONS 0024).
- More states, each a one-time purchase in the one app (DECISIONS 0025).
  Tennessee's trout stocking schedule from TWRA is on the site and in the
  app, with each date as precise as TWRA gives it: a day, the week of a
  Sunday, or a month with the day not set. Browsing and history are free in
  every state; alerts and the widget are a purchase per state. California's
  Full Access is unchanged, so buyers keep everything they have.
  Massachusetts and Michigan are built but not fetched: their data hosts'
  robots.txt files could not be read.
- `snapshot/v2.json` and `schema/snapshot.v2.json`: every state, what its
  records mean (a schedule or a report) and their precision.
  `snapshot/v1.json` is unchanged for installed 1.0 builds.
- Site: `/states/`, a hub page per state and a page per water under
  `/<state>/water/<slug>/`. Every California URL is unchanged.
- App: a state picker in Browse, a States screen with each state's
  purchase, restore, and per-state alerts and widget.

- A four-page introduction on first launch: what the app is, finding
  waters, favorites and what full access adds, and why it says a week and
  "scheduled". Swipe or tap Continue, or skip it. About can show it again.
- "Mute this water" on a planting alert turns that water's alerts off
  without opening the app. The water stays a favorite. Turn its alerts back
  on with the Alerts switch on its page or a swipe in Favorites.
- Opening a water clears its alerts from Notification Center.
- Haptics when a pull to refresh finishes (a warning if the check failed)
  and when full access unlocks.
- iPad. At full width, Browse and Favorites show the list beside the
  water's page, with the search field always at the top of the list, and a
  Refresh button (Command-R). The iPhone layout is used in Slide Over,
  narrow splits and at the accessibility text sizes. The full-access sheet
  opens at full height. The iPad turns to every orientation.
- Trout Truck on Apple Watch, part of full access: your favorite waters
  with a "This week" tag or their next scheduled week, each water's next
  and last scheduled weeks, and a "Next favorite" complication for watch
  faces and the Smart Stack. It shows what the iPhone app sends, so it
  needs the iPhone app and makes no network request. "Mute this water"
  works from an alert on the watch too.
- The app may ask for an App Store rating with iOS's own prompt, and only
  when someone goes back from a water's page: after opening a planting
  alert, or from the third launch on with at least one favorite. Never on
  the first launch, never over another screen, at most once per app
  version, 120 days apart and three times a year. Nothing is offered for a
  rating. Any state's alerts and favorites count; nothing depends on which
  state was bought. About has a "Rate Trout Truck" row that opens the App
  Store's review page (DECISIONS 0035).
- A round Lock Screen size for the Favorite waters widget: how many of
  your favorites are scheduled this week.
- A California water page with nothing on CDFW's schedule this week or later
  now lists the other waters in its counties that are scheduled, each with
  its week, and links the county page. It is built from the snapshot alone,
  and the page's sitemap `lastmod` moves when one of those waters changes.

### Fixed

- County pages keep past and upcoming scheduled weeks apart: a new "Scheduled
  for later weeks" table lists each water and week after the current one, and
  the history table reports each water's latest week through the current week,
  so a later week no longer hides a current plant.
- Tennessee (and other non-California) pages judge "this week" and the
  upcoming window against the build date, not the date of the last good fetch.
  The freshness line now says when the failed check ran, which read is the last
  good one, and the range of dates in the data.
- The release workflow's preflight no longer fails on the first release.
  With no earlier `v*` tags its list of earlier builds is empty, and the
  macOS runner's bash 3.2 treated that empty list as an unbound variable
  under `set -u`. The workflow checks now reject that pattern in any
  `run:` step.

## [1.0.0] - 2026-10-02

The first App Store release of Trout Truck for iPhone: version 1.0.0,
build 2, free to download in the United States.

Build 2 removes the device name from the Shortcuts description after App Store processing rejected build 1 (ITMS-90626).

Trout Truck shows the California Department of Fish and Wildlife's fish
planting schedule on your iPhone, a week at a time. Browse every water on
the schedule by region and county, or search by name, an earlier name or
county, and see which waters are scheduled for the current week. Each
water has its week-by-week history of scheduled plants. Favorite the
waters you fish; favorites, browsing and history are free. The schedule
lists the week a plant is scheduled for, never a day, and CDFW notes that
plants are subject to change, so the app says "scheduled", not "planted".

An optional one-time purchase, Full Access ($9.99), adds a local
notification when a favorite appears on a new week's schedule, and a Home
Screen and Lock Screen widget for your favorites. The app checks for a
newer schedule on launch and in the background, says which week it is
showing and when it last checked, and keeps the last good schedule on
screen when a check fails. It also has a Shortcuts and Siri action, a way
to share a water, and support for VoiceOver, Dynamic Type and dark mode.
Trout Truck collects no data, has no accounts and shows no ads. It is not
affiliated with or endorsed by CDFW.

The detailed list below covers the app, the website and the data pipeline
behind both.

### Added

- `make appstore` (part of `make verify`): an App Store readiness check
  for the iOS app. It fails on version or build-number drift between the
  app and widget, a target that isn't iPhone-only, the wrong team ID, a
  missing export-compliance flag or launch screen, a privacy manifest that
  declares tracking or collected data, a required-reason API the code calls
  without declaring it, a non-Apple import in shipped code, a push
  entitlement, or an incomplete or translucent app icon (#3).
- `ios-release` workflow: dispatched with a signed `vX.Y.Z` tag on the tip of
  `main`, it verifies the tag against `.github/allowed_signers`, builds only
  the commit it was dispatched from (and refuses a tag on any other), checks
  the tag matches
  `MARKETING_VERSION` with a higher build number and a CHANGELOG section,
  tests and archives the app unsigned, reads the version back out of the
  built app, and drafts a GitHub Release. It never signs or uploads (#3).
- `docs/app-store/OWNER-STEPS.md`: the one ordered list of owner steps to
  App Store submission. The listing file gains the App Privacy reasoning
  per Apple data category and the age-rating answers, and the screenshot
  script can make an optional 6.5" set (`SCREENSHOT_CLASS=6.5`) and
  refuses a bundled snapshot more than 7 days old, because the app now
  refreshes on launch and would show a different week from the one the
  script picked its waters from.
- The iOS app's version is 1.0.0 (build 1) for the first App Store release,
  free to download with the $9.99 in-app purchase as built, United States
  only (DECISIONS 0018). `make appstore` requires a CHANGELOG section for
  the app's version, and the release workflow requires it to be dated.
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

- The vendored portfolio standards in `docs/standards/` move from v3.0.0 to
  v3.0.1, replaced as one set from the signed tag. v3.0.1 is a patch release
  (re-verified stamps, text corrections, and tooling fixes) with no control,
  threshold, or gate change.
- The vendored portfolio standards in `docs/standards/` move from v2.0.0 to
  v3.0.0, replaced as one set. v3.0.0 re-verifies the three documents whose
  quarterly recheck had lapsed and adds the advisory Discovery and Adoption
  standard.
- The App Store screenshot script also filters Browse by the chosen
  region's county with the most waters on the week's schedule. Browse
  lists waters alphabetically, and on 2026-10-02 none of Northern Region's
  scheduled waters were on its first screen, so the first screenshot would
  have shown no "This week" badge.
- Site: a water page's planting history says "Scheduled" and "Schedule
  changed" where it printed the raw values "listed" and "removed", the words
  the app uses. A page that shows a changed week explains it in a sentence:
  CDFW listed that week earlier and later removed it from its schedule. The
  snapshot and the history keep their values.
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

- Site: a catfish-only water's calendar feed is named "<water> catfish
  planting schedule", and a water with both species "trout and catfish
  planting schedule", to match its page. It said "trout" for every water.
  Only the calendar's display name changes: each feed's address and every
  event's ID stay the same, so nothing duplicates in a subscribed calendar.
- App: Product > Archive works. The shared scheme built both test targets
  for archiving, and in the Release configuration their `@testable` imports
  can't resolve, so every archive failed before signing was reached. The
  test targets are still built for testing, running and analysis.
- The daily publish run had never succeeded, because the freshness check
  read CDFW's stated week start as "today". It now compares weeks. The same
  change stops a plant that ages off the page from being recorded as
  canceled, and stops the run from crashing on a water whose rows have
  all aged off (PR 13).
- The daily run refuses a CDFW page that is showing its "Current-Future
  Plants" or "Past Plants" view instead of the full window. Before, a
  Current-Future response (the real 2026-09-14 capture has zero rows) would
  have marked almost every earlier listed plant `removed` and published a
  snapshot saying nothing is scheduled. The run now stops with a
  `run refused -- nothing published` line that names the view, and history,
  the snapshot and the site are untouched. The daily run's own request is
  unaffected. Not seen in production.
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
