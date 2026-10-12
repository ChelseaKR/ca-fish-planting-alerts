# Decisions

> **Closed to new entries (2026-09-17).** New decisions go in `docs/adr/`,
> one file each; see `docs/adr/0000-record-architecture-decisions.md`.
> The entries below stay as they are and remain the record of those
> decisions. Numbers used here are never reused in `docs/adr/`.

## 0001 — Free static site + paid native app with local notifications (2026-09-13)

The site is the discovery surface (per-water pages rank for "<water> trout
stocking"); the app is the product. Alerts are **local notifications** from a
snapshot the app refreshes itself (BGAppRefreshTask), not server push: no APNs,
no device tokens, no accounts, no email. iOS decides when background refresh
runs, which is honest only because the source updates **weekly** — say so in
the app and the listing. Same architecture as the queer-tv-guide app; reuse it.

## 0002 — Data posture: none (2026-09-13)

Per DATA-GOVERNANCE-STANDARD §4a: "none". No analytics, no cookies, no
third-party script on the site; nothing collected by the app. Per-product
choice; revisit only with data.

**Superseded for the website by 0011** (2026-09-17): the site runs Google
Analytics 4. The app keeps this posture: nothing collected.

## 0011 — Website analytics: Google Analytics 4; the app still collects nothing (2026-09-17)

On 2026-09-17 the owner decided to put Google Analytics 4 on every public
site in the portfolio and to update each privacy page to match. She made
that call knowing it reverses 0002's "no tracking" for this product. This
entry replaces 0002 for the website only.

- **Scope: the website yes, the app no.** Every page the pipeline
  generates carries the GA4 tag. The iOS app is unchanged: no analytics, no
  SDK, `PrivacyInfo.xcprivacy` declares no collected data, and the App Store
  privacy label stays **Data Not Collected**. The app opens links to the
  site in the system browser (SwiftUI `Link`), not in an in-app web view,
  so the site's analytics are not data the app collects. An in-app web view
  showing the site would change that, so revisit the label before adding
  one.
- **Property:** GA4 property `554849409`, web stream measurement ID
  `G-ZYL3RMXCZF`. The ID appears in every page's HTML, so it is public and
  is committed as `GA4_MEASUREMENT_ID` in `pipeline/src/cfpa/site.py`
  rather than kept in a secret or a repository variable. Setting it to `""`
  removes the tag from every page and switches the about, privacy and
  support copy back to "nothing is collected".
- **Global Privacy Control and Do Not Track are honored.** When
  `navigator.globalPrivacyControl === true` or Do Not Track is on, nothing
  loads: no `dataLayer`, no request to Google, no cookie. The tag adds
  gtag.js by script after that check, never with a static `<script src>`.
- **Ads features are off.** The tag config sets
  `allow_google_signals: false` and
  `allow_ad_personalization_signals: false`, and Google signals are also
  disabled in the property. Consent Mode v2 defaults deny `ad_storage`,
  `ad_user_data` and `ad_personalization` everywhere, and deny
  `analytics_storage` in the EEA, the UK and Switzerland (granted
  elsewhere). There is no consent banner, so in those regions GA4 receives
  only cookieless measurements.
- **Retention:** 14 months, a property setting. The privacy page states it,
  so a change to the setting means a change to the page.
- **Copy:** the README and the about, privacy and support pages say the
  website uses Google Analytics and the app collects nothing. The page copy
  follows the configured ID, so neither state renders a false claim.

## 0003 — Paid up front, one price (2026-09-13, provisional)

**Settled by 0018 (2026-10-01):** the price model is the one 0007 built, a
free download with one $9.99 in-app purchase, not a price at download.

One-time purchase, no StoreKit, no subscription. The price is $9.99, one-time. [moved to private strategy notes]

**Superseded in part by 0007** — the app shipped with no purchase mechanism
at all (not even the App-Store-price-tier gate this decision assumed), which
is the actual blocker; 0007 keeps the $9.99 figure and "one-time, no
subscription" but replaces the mechanism with StoreKit.

## 0007 — Purchase mechanism: StoreKit 2 non-consumable, not App Store price tier (2026-09-15)

0003 said "no StoreKit" on the assumption that Apple's own paid-app price
tier — charge at download, App Store Connect gates it, no code — would be
the paywall. It never got built either way, so as of tonight's review the
app has **no purchase mechanism of any kind**: it can be downloaded and used
in full for free. That is the blocker this decision closes.

The paid-app-price-tier route is dropped in favor of **StoreKit 2**: a
single non-consumable in-app purchase, `com.chelseakr.cafishplanting.fullaccess`,
still $9.99, still one-time, still no subscription. Reasons:

- The app ships free to download and unlocks in-app — this is the standard,
  App-Review-expected shape for a "paid" iOS app in 2026; a bare download
  price is now the unusual path and StoreKit is the well-trodden one.
- StoreKit 2's `Transaction.currentEntitlements`/`Transaction.updates` gives
  restore-purchases and multi-device recovery "for free"; the price-tier
  route has no equivalent for a purely local, no-account app like this one.
- It is testable end-to-end without an App Store Connect record, via
  Xcode's local `.storekit` configuration file and `StoreKitTest.SKTestSession`
  — see `ios/CAFishPlanting/Configuration.storekit` and
  `ios/CAFishPlantingTests/PurchaseManagerTests.swift`.

What ships free vs. paid was never decided (see the "Not yet decided"
line in the top-level README and `docs/APP-STORE.md`'s "Known gaps").
Rather than guess at that scope, `PlantingCore/Sources/PlantingCore/FreeTier.swift`
gates a clearly-labeled placeholder — a cap on how many waters a
non-purchaser may favorite — so the StoreKit mechanism itself is complete
and real without inventing product scope that is Chelsea's call. Owner
follow-up: decide the real free/paid split and repoint `FreeTier` (or
delete it in favor of whatever the real gate turns out to be).

**Owner follow-up resolved by 0009** — favoriting is free and
unconstrained for everyone; the paid unlock is local notifications, not a
favorites cap. `FreeTier` is repointed accordingly, not deleted.

## 0004 — License before bytes (2026-09-13)

CDFW's terms are quoted verbatim in `docs/LICENSES-AND-ATTRIBUTION.md` before
any fetch, with the attribution the app and site must show. Unknown = not used.

## 0005 — The history is the asset (2026-09-13)

CDFW publishes the current week only. Keeping every week, forever, per water,
is what no one else offers and what makes "when was X last planted" answerable.
The pipeline never overwrites history; a stale or failed fetch never becomes a
"no plants this week" fact.

## 0017 — A water CDFW no longer lists is left out of the snapshot, not out of history (2026-09-19)

A snapshot entry needs a county. History stores none, so the pipeline reads
each water's counties from this run's table rows and then from CDFW's water
picker. A water with history that was in neither raised a `ValueError`. History
is append-only, so every later run hit the same error: the snapshot and site
for every water stopped updating until someone edited code, and the refusal
printed a raw traceback. CDFW has never been seen to drop a water from its
picker (about 895 waters, 385 with history); this was reproduced by editing a
fixture.

Now such a water is left out of that run's snapshot and site, and every other
water is published. Its records in `history.json` are untouched: never
deleted, and their status follows the normal rule. The run prints a
`cfpa: WARNING` block that names each water, its records on file and its newest
week, and under GitHub Actions a `::warning` annotation. The water comes back
by itself in the first run where CDFW lists it again. Leaving it out, rather
than keeping a page with remembered counties, means it is never published as
"nothing scheduled" when the truth is that CDFW does not list it: the app
already says "No longer in the schedule data" for a favorite the snapshot lacks
and keeps that favorite's alert baseline, so a return does not announce
plants it already had. The water's site page and calendar feed are not built
while it is left out. The exit status stays 0 on purpose: a non-zero exit would stop the
commit and deploy steps for every other water, which is the failure this fixes.

Refused, not left out: more than `snapshot.MAX_UNLISTED_WATERS` (5) waters in
one run, which looks like a truncated or reshaped page, not a retirement; a
water with history and no alias entry; a county with no region; a snapshot
that fails the schema. Each is now one `cfpa: run refused -- nothing
published:` line, not a traceback.

Conservative default, not the last word. The schema's description of `waters`
("every water with at least one observed plant") is not edited here and holds
except for the waters a run's warning names. Owner decisions left open: whether
the site and app should keep such a water with a label instead of omitting it
(which would mean remembering each water's last-seen counties, for example in
`aliases.json`); whether the limit of 5 is right; and whether a left-out water
should turn the run red or open an issue.

## 0006 — Name and domain: undecided
**Settled by 0010** (2026-09-17): the name is Trout Truck, and the site
stays on `github.io` for now.

## 0010 — Name: Trout Truck; domain stays on github.io for now (2026-09-17)

The product is **Trout Truck**. Anglers call the hatchery truck that
delivers planted trout "the trout truck", so the name uses words the
audience already uses for the thing the product tracks.

- **App Store:** a US App Store search on 2026-09-17 returned 0 apps using
  the name.
- **Trademark screen (2026-10-02): no conflict found.** The official USPTO
  trademark search (`https://tmsearch.uspto.gov/`, a word search typed into
  the search box), the US App Store search API, and the Justia,
  uspto.report and Trademarkia mirrors found no "TROUT TRUCK" mark and no
  app by that name. The nearest marks were TROUT EDGE (live, class 9,
  fishing apps, Fishing Culture LLC), TROUT TRICK (fishing lures) and
  TRUCK TRUCK (toy models). This is a screen, not legal advice; an
  attorney's clearance search is the standard next step for certainty.
- **Search terms stay next to the brand.** The name says neither
  "planting" nor "stocking", which are the words people search with, so
  page titles and meta descriptions keep that wording beside the name
  ("This week's CA trout planting schedule | Trout Truck"), and the App
  Store subtitle carries it (`CA trout stocking alerts`).
- **Domain: none yet.** The site stays at
  `https://chelseakr.github.io/ca-fish-planting-alerts/` with no CNAME. The
  owner may buy `trouttruck.com` later. If that happens, set
  `SITE_BASE_URL`, and the `github.io` URL becomes a 301 to the new domain
  (`schema/README.md`).
- **What does not change:** the repository name, the bundle identifier
  `com.chelseakr.cafishplanting`, the StoreKit product ID
  `com.chelseakr.cafishplanting.fullaccess`, the Xcode scheme and target
  names (`CAFishPlanting`), the snapshot URL, the pipeline's `User-Agent`,
  and the `.ics` event UIDs. Changing a UID would duplicate every event in
  a subscriber's calendar. Only the names people see change.
- **No uniqueness claims.** Other California stocking-alert apps exist,
  so no copy says "only",
  "first" or "the app for".

## 0008 — Zero parsed rows is a valid empty week, not a parse error (2026-09-14)

`parse_schedule_table` originally raised on any zero-row table body,
because the 54 weeks of real production data on hand (2025-09-14 to
2026-09-20) never once contained a genuinely empty statewide week -- so the
distinction from a broken/malformed fetch had never been exercised and
looked unsafe to assume. Confirmed live against production on 2026-09-14
by issuing a query (a specific `Params.StockingWaterID` with
`Params.PlantTimeFrame=2`, "Current-Future Plants") guaranteed to match
nothing: CDFW's own server still renders the full `#fishPlantsExternal`
table, with the exact expected `<thead>` and a present, empty `<tbody>` --
not a missing table, not an error page (captured response committed at
`pipeline/tests/fixtures/schedule-empty-week-2026-09-14.html`). Every
structural gate the parser already checks (table found, headers match
exactly, tbody found) still does the job of catching a broken fetch; only
the very last "zero `<tr>`" case was being over-conservative. That case now
returns `[]` instead of raising -- see `parse_schedule_table`'s docstring
for the reasoning kept next to the code.

This does not weaken decision 0005: a stale page is still caught
independently and earlier, in `fetch.py`'s own freshness check, before
`parse_schedule_table` ever sees the HTML.

## 0016 — Refuse a page that is not showing the full window (2026-09-19)

CDFW's Time Period control has three options: All Plants, Current-Future
Plants and Past Plants. Each is a different query with a different table.
`history.merge_observations` flips a listed plant to `removed` when its week
is inside the stated window and the plant is missing from the table, which is
only sound when the table is the whole window. The pipeline used to read the
window from the "All Plants (...)" label whichever option was checked, so a
"Current-Future Plants" response, like the real 2026-09-14 capture with zero
rows, would have flipped almost every earlier listed plant to `removed`, and
the site and the snapshot would have said nothing was scheduled. That has not
happened in production: the daily run asks for the default view, which has no
option checked and carries the whole year, and the 2026-09-14 response came
from a probe (decision 0008).

Now `fetch.extract_time_period_view` reads which option is checked, and
`cli.run` refuses the page unless it is "All Plants" or has no option checked
(what a plain GET returns today), before anything is parsed, merged or
written. A refusal is a non-zero exit with one `cfpa: run refused -- nothing
published:` line that names the checked option; history, aliases, the
snapshot and the site are untouched. A checked option this code does not
recognize, or more than one, is refused the same way.

Conservative default, not the last word. The owner may prefer the run to
continue and skip removal inference instead, or to accept the Current-Future
range for removals; that is a separate decision. Not built here: a
sanity check on how many removals one run may make, or on a zero-row table
with no option checked. Both need a threshold.

## 0009 — Free/paid split: notifications are the paid unlock, not favoriting (2026-09-17)

Resolves 0007's "owner follow-up" (decide the real free/paid split and
repoint `FreeTier` or delete it). The placeholder gate 0007 shipped — a cap
of 3 favorited waters for non-purchasers — is removed entirely.

- **Free, for everyone, no purchase required:** favoriting and browsing
  any water, with the same full lookup capability as the free website
  (0001) already gives anyone. This app's free tier must never be worse
  than the free site.
- **Paid (`com.chelseakr.cafishplanting.fullaccess`, still $9.99, still
  one-time — 0003/0007 unchanged on price and mechanism):** local push
  notifications when a favorited water's planting schedule changes.
  Without the purchase, favoriting still works fully; no local
  notification is ever scheduled or delivered for any favorited water.

Rationale: a website cannot push a native notification to someone's
phone — that is the one piece of value this app has that the free site
structurally cannot replicate, so it is the coherent thing to gate,
rather than gating a capability (favoriting) the free site already gives
away for nothing.

Implementation: `AlertPlanner` (the diff logic) and `NotificationScheduler`
(the `UNUserNotificationCenter` wrapper) already existed, fully built and
tested, wired into `AppEnvironment.performBackgroundRefresh()` — but
unconditionally, for every user, regardless of purchase. The only change
needed there was one entitlement check
(`FreeTier.notificationsAllowed(isEntitled:)`) immediately before
`notifications.schedule(...)`; the alert baseline itself is still always
replanned and saved for non-purchasers too, so a later purchase doesn't
suddenly announce every listing change that happened while locked.
`PlantingCore/Sources/PlantingCore/FreeTier.swift` is repointed at this
gate (`notificationsAllowed(isEntitled:)`) rather than a favorites cap;
`toggleFavorite` in `AppEnvironment` is no longer gated at all, and the
paywall sheet that used to interrupt the favorite action is removed —
`PurchaseView` is reachable only from About > "Unlock full access".

## 0015 — The widget is part of full access (2026-09-18)

The owner decided that the Home Screen and Lock Screen widget ("Favorite
waters") is part of full access, the same one-time purchase
(`com.chelseakr.cafishplanting.fullaccess`) that unlocks local
notifications (0009). Browsing, history and favoriting stay free for
everyone.

- Before the purchase the widget is honest about it: it says the widget is
  part of full access, shows the published schedule's week and how many
  waters it lists, shows no favorites and no made-up data, and a tap opens
  the purchase screen (`trouttruck://unlock`).
- After a purchase, a restore, or a purchase on another device, the widget
  lists the favorites at once. A refund locks it again.
- One flag carries the decision: `FreeTier.widgetsRequireFullAccess`.
- Everything that says what full access unlocks now names both alerts and
  the widget: the purchase screen, About, `docs/APP-STORE.md`,
  `docs/APP-STORE-LISTING.md` and the local StoreKit configuration.

## 0018 — First App Store release: as built, US only, version 1.0.0 (2026-10-01)

The owner decided three things before submission:

- **Price model: as built.** Free to download, with one non-consumable
  in-app purchase, Full Access (`com.chelseakr.cafishplanting.fullaccess`),
  at USD 9.99, one time, no subscription (0007, 0009, 0015). Browsing,
  history and favorites stay free. 0003's "paid up front" is settled in
  favor of this.
- **Storefronts: United States only.** The data is California's and the
  listing is English. With no EU storefront, App Store Connect needs no
  Digital Services Act trader declaration.
- **Version: 1.0.0.** `MARKETING_VERSION` is 1.0.0 in every target, with
  build 1. Every later upload raises `CURRENT_PROJECT_VERSION`. `make
  appstore` requires a `CHANGELOG.md` section for the current version, and
  the release workflow requires that section to carry a date.

Still the owner's: the trademark screen for "Trout Truck" (0010), the
support address, and moving the privacy policy off github.io (it stays
there for now). Update 2026-10-02: the trademark screen is done (0010) and
the support address is set (`SUPPORT_EMAIL`, `chelsea@chelseakr.com`).

## 0019 — A custom domain without breaking the snapshot URL (2026-10-05; proposed)

The site may move from `https://chelseakr.github.io/ca-fish-planting-alerts/`
to a domain of its own. The iOS app fetches
`https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json`, and
the builds already on phones and in review hard-code that URL, so it has to
keep working for as long as any of those builds is installed.

**What GitHub Pages does (measured 2026-10-05, not assumed).** When a
repository's Pages site has a custom domain, GitHub answers every github.io
URL of that site with a path-preserving `301` to the domain:
`https://chelseakr.github.io/womens-sports-calendar/some/deep/path.json`
returns `301` with `location: https://nexthomegame.com/some/deep/path.json`.
GitHub's docs describe the custom-domain setup, but not this redirect. A
site published by a GitHub Actions workflow ignores any `CNAME` file and
takes its domain from the Pages setting; a site published from a branch
takes it from the `CNAME` file on that branch. Google's Change of Address
tool works only on domain-level properties, never a path such as
`/ca-fish-planting-alerts/`, so it does not apply to this move.

**Two ways to move. The owner picks one.**

- **A. The custom domain goes on this repository.** It needs nothing beyond
  this change: set `SITE_BASE_URL` to `https://<domain>` and the domain in
  this repository's Pages settings. Every github.io URL, the snapshot
  included, becomes a real `301` to the same path on the domain.
  URLSession follows it. The cost: from then on, the app's snapshot works
  only while the domain stays registered, keeps its DNS and serves valid
  HTTPS. A domain that lapses sends every installed app to whoever holds
  it next.
- **B. The domain is served by a second repository, and this one keeps
  github.io (recommended).** This repository's Pages site never gets a
  custom domain. It keeps serving `snapshot/v1.json` and every
  `water/<slug>/feed.ics` byte for byte, and every page becomes a redirect
  page: `rel=canonical` to the new URL plus an instant
  `<meta http-equiv="refresh" content="0">`, which Google Search treats as a
  permanent redirect. The domain build, with its `CNAME`, is published by
  a second repository from a branch. The snapshot never depends on the
  domain. **Chosen by the owner on 2026-10-05**, with `trouttruck.com`.

**What `publish.yml` does under B.** With `SITE_BASE_URL` unset, nothing
new runs. Set, after the history commit: it pushes this run's domain build
as one fresh commit to the `gh-pages` branch of `DOMAIN_SITE_REPO` (a
repository variable), over SSH with a deploy key from the
`DOMAIN_SITE_DEPLOY_KEY` secret that can write to that repository only.
The key goes from the secret into `ssh-agent` on stdin and is never
written to disk, and github.com's host key is pinned. Then it polls
`<domain>/snapshot/v1.json` over HTTPS until it serves this run's
snapshot byte for byte (up to ten minutes), and only then uploads the
github.io site as this repository's Pages artifact. A domain that is not
serving fails the run there, and github.io keeps the last full site. The
second repository publishes from its branch, so the `CNAME` file in each
build keeps its custom domain set.

**What is built (both options).**

- One value, `SITE_BASE_URL`. Unset, the build is byte for byte what it
  was (measured by hashing the whole site built before and after from the
  same snapshot). Set to `https://<host>` at a host root that is not
  github.io (`site.custom_domain`), every canonical URL, `og:url`, piece of
  structured data, `sitemap.xml` entry, `robots.txt` line and calendar
  feed uses the domain, a `CNAME` file names it, and nothing in the build
  mentions github.io. A `SITE_BASE_URL` with a path stays a plain base URL,
  with no `CNAME`, as before.
- `cfpa --legacy-site-out DIR` (option B; `cfpa.legacy`) writes the
  github.io site from the domain build of the same run: the snapshot and
  feeds copied byte for byte, a redirect page for every page (the home
  page's keeps the Search Console tag), a `404.html` that sends any other
  old path to the same path on the domain, and a `sitemap.xml` of the old
  URLs. It refuses, writing nothing, without a custom domain or without a
  snapshot.

This supersedes 0010's "the `github.io` URL becomes a 301 to the new
domain", which holds under A only. The owner's steps are in the runbook
that came with this change.

## 0020 — iPhone, iPad, and Apple silicon Macs from the version after 1.0.0 (2026-10-11)

The owner decided on 2026-10-11 to make Trout Truck available on iPad and
on Apple silicon Macs. 1.0.0 (build 2) stays iPhone-only: it was already in
review, and nothing here changes it.

- **iPad.** Every target is `TARGETED_DEVICE_FAMILY = "1,2"`, and
  `make appstore` now requires that, where it used to require iPhone-only.
  At regular width (iPad full screen and the wider multitasking sizes),
  Browse and Favorites are a list beside the water's page
  (`NavigationSplitView`), not a stretched phone screen. About and a
  water's page keep their rows to a readable width. At compact width
  (iPhone, and iPad Slide Over or a narrow split) the app is the
  iPhone layout. So is iPad at the accessibility text sizes, where the
  list's column is too narrow for the words. The iPad turns to all four
  orientations, which iPad multitasking needs. iPhone stays portrait.
- **Pointer and keyboard.** Lists and buttons get the system pointer
  effects. At regular width a Refresh button with Command-R runs the same
  check as pull to refresh, which is awkward with a pointer.
- **Mac.** As "Designed for iPad": the iPad app, unchanged, on Apple
  silicon. No Mac Catalyst target. Alerts are local notifications, so on
  a Mac they go to the Mac's own Notification Center, where macOS shows an
  alert's buttons under Options. When the background refresh runs on a
  Mac is up to macOS. None of the Mac behavior is verified yet: running
  the app on a Mac needs the Mac registered for development, an owner
  step.
- **What the owner does in App Store Connect.** Mac availability is a
  checkbox under Pricing and Availability ("Make this app available on
  Mac"). A version that adds iPad needs iPad 13-inch screenshots before it
  can be submitted. Both are in `docs/app-store/OWNER-STEPS.md`.

## 0022 — A native Android app with the iOS app's features (2026-10-12; proposed)

The owner decided on 2026-10-12 that Trout Truck gets an Android app with
full parity with the iOS app. It lives in `android/` beside `ios/`.

- **Native, not a wrapper.** Kotlin, Jetpack Compose and Material 3. Two
  Gradle modules: `core`, plain Kotlin with the same rules as
  `ios/PlantingCore` (the strict snapshot decoder, the alert planner,
  freshness, search, the widget digest, the stores and the words the app
  shows), and `app`. Package name `com.chelseakr.cafishplanting`, the iOS
  bundle identifier's stem (0010).
- **California, from v1.** It reads
  `https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json`
  and nothing else, with the iOS app's request: one GET, `If-None-Match`, a
  fixed `User-Agent`, no cookies. v1 stays byte-compatible beside v2 (0025),
  so this app is California only until it gains states too. It ships its
  own committed v1 snapshot (`android/app/src/main/assets/snapshot.json`,
  refreshed by `android/scripts/sync-bundled-snapshot.sh`, which checks it
  against `schema/snapshot.v1.json`), since the iOS app now bundles v2.
- **Same rules.** A week, never a day, and "scheduled", never "stocked". No
  account, no analytics, no crash reporting, no server push. Alerts are
  local notifications that WorkManager's daily periodic refresh (and the
  refresh at launch and on swipe down) computes on the device. Favorites,
  mutes and the alert baseline are files on the device. Cloud backup is
  off; a device-to-device transfer carries them.
- **The alert planner is held to the Swift one.** Shared fixtures in
  `ios/PlantingCore/Tests/PlantingCoreTests/Fixtures/` (synthetic cases and
  two real-data excerpts) carry expectations recorded from the Swift
  planner. `AlertPlannerParityTests.swift` and `AlertPlannerParityTest.kt`
  both run every scenario and must produce the same alerts, ids, words and
  baselines.
- **Same free/paid boundary (0009, 0015).** Browsing, history and
  favorites are free and unlimited. One Google Play one-time in-app
  product, placeholder ID `fullaccess`, unlocks alerts and the home screen
  widget. Play Billing only; the app never links to another way to pay.
  The catalog and the entitlement are per product, so per-state products
  are new entries, not new code.
- **Platform words.** Android has a home screen widget (Glance) and no Lock
  Screen widget, so the copy says "home screen" where iOS says "Home Screen
  and Lock Screen", and "Swipe down" where iOS says "Pull down". Everything
  else in the introduction is the iOS app's California copy from before
  more states (0025), word for word, and a test pins it.
- **Review prompt.** Google Play's in-app review card, with the iOS rating
  lane's rules (feat/ratings-and-water-seo, not yet on main), and an About
  row that opens the app's Play Store page.
- **Not ported.** Shortcuts and Siri (`ScheduleIntents`) and the Apple
  Watch (0027) have no direct Android twin in this change.

Owner steps (Play Console app, in-app product, signing, Data safety,
listing, internal testing) are in `android/README.md`.

## 0024 — Water locations from federal public-domain data, never guessed (2026-10-12; proposed)

The owner approved maps on 2026-10-12. A map needs a point per water, and
every water in the snapshot has had `location: null`. The state's own
fishing map has coordinates, but its terms and robots.txt are unknown, so
under 0004 ("unknown = not used") it is not a source.

- **Sources.** USGS GNIS (names, classes, counties) and the USGS National
  Hydrography Dataset (lake polygons and stream lines, each tagged with its
  GNIS id), both U.S. Public Domain, with Census TIGER/Line county polygons
  to check that a point lies in the county CDFW lists. Each was downloaded
  once, by hand. Terms, quotes and robots.txt findings are in
  `docs/LICENSES-AND-ATTRIBUTION.md`.
- **Offline, not daily.** `cfpa-geocode` is run by hand and writes
  `pipeline/data/water_locations.json`, which is committed. The daily run
  only reads it. A new water gets no point until someone reruns it.
- **Three classes, no guessing.** `exact`: exactly one GNIS lake,
  reservoir, stream or canal with the water's name (or alias, or a
  mechanical variant of either: "Blue Lake Upper" is "Upper Blue Lake",
  "Pine Flat Reservoir" is "Pine Flat Lake") in the listed county.
  `ambiguous`: several; none is picked, all are listed for the owner.
  `none`: no feature, or the CDFW name is a reach of a stream ("Section 2",
  "below the dam"), which no federal dataset marks. Only `exact` and
  owner-resolved waters get a point.
- **Where the point goes.** A lake: the interior point of its NHD polygon
  farthest from shore (never the centroid, which can fall on land for a
  crescent-shaped reservoir); without a polygon, GNIS's own point. A
  stream: a vertex of its NHD line central to its course in the listed
  county, labeled approximate everywhere it is shown (`kind:
  stream_point`), because CDFW plants along a stream, not at a spot.
- **Owner overrides.** `pipeline/data/water_location_overrides.json`
  names a GNIS feature (or none) per water, with who decided, when and
  why. An override that points outside the listed county is an error.
- **v1 never changes.** Points go only into snapshot v2's
  `waters[].location` (`{lat, lon, source, kind, source_feature_id}`).
  `snapshot/v1.json` keeps `location: null` for installed 1.0 builds.
- **Attribution.** The about page carries "Source of water locations: U.S.
  Geological Survey, National Hydrography Dataset and Geographic Names
  Information System", and the Census Bureau acknowledgement its terms
  require.

## 0025 — More states, each a one-time purchase in the one app (2026-10-12)

**Context.**

On 2026-10-11 the owner decided to take Trout Truck beyond California:
"expand to more states, sold as per-state in-app purchases inside the one
app". Apple's App Review Guideline 4.3(a) asks for one app with in-app
purchases rather than an app per place. The first wave is Tennessee,
Massachusetts and Michigan; New York is optional and on hold. California
stays the base.

The research (`_agent-tools/remediate-2026-10-11/trout-truck-states/RESEARCH.md`)
found those three states' terms clear for reuse, and found that each
publishes something different:

| State | Agency | What it publishes | Precision | License (verbatim in `cfpa/states/*.py`) |
|---|---|---|---|---|
| TN | TWRA | A forward schedule for the year | day, week of a Sunday, or month | TN.gov Linking Policy: copy with attribution and no implied endorsement |
| MA | MassWildlife | A daily report of stockings done | day | The layer's item license: "Permission is granted to copy and use" |
| MI | Michigan DNR | A report of stockings done, weeks late | day | Public record, no restrictions; an indemnity clause |

**Decision.**

**One app, one product per state.** California's product stays the one
1.0 shipped, `com.chelseakr.cafishplanting.fullaccess`, unchanged in id,
price and meaning: alerts and the widget for California waters. Nobody who
bought it loses anything, and it is not repointed to "all states". Each
other state is its own non-consumable. Tennessee's is
`com.chelseakr.cafishplanting.state.tn` at USD 9.99, one time (confirmed by
the owner, 2026-10-12). `.state.ma` and `.state.mi` are placeholders, at a
placeholder $9.99, and are not created while those states are off. Browsing, every water's history and
favorites stay free in every state, as in California (0009). A state's
purchase unlocks alerts for that state's favorites and adds them to the
widget (0015); the widget unlocks with any state and counts, never shows,
favorites in states not bought.

**Snapshot v2 beside v1.** `snapshot/v1.json` is built exactly as before
and stays byte-compatible for installed 1.0 builds (a test pins it).
`snapshot/v2.json` (`schema/snapshot.v2.json`) carries every state, with
California derived from the finished v1 so the two can't disagree and its
water ids (`cdfw-<id>`) don't change. Each state says what its records mean
(`semantics`: a `schedule` says "scheduled", a `report` says "stocked") and
at what precision (`day`, `week`, `month`). Nothing is ever shown finer
than the agency gave it: a Tennessee "week of" is never a day, and its
"TBD 12/2026" is "December 2026, day not set". Tennessee's one-letter
month lists ("M, A, M, J, J, A, S") are ambiguous, so they are shown as
TWRA wrote them and never turned into dates.

**Removal inference stays with schedules** (0016). A Tennessee date that
vanishes from TWRA's file before it has passed becomes "schedule changed";
one that has passed has aged off. A report never infers a removal.

**Each state is isolated.** A state's fetch that fails or is refused keeps
its last good data; its `checks` say when it was last read and that the
newest check failed, and California and the other states carry on. A state
with no record is left out of v2 and the site, never shown empty.

**Robots** (the owner's rulings, 2026-10-12). The state fetchers read
`robots.txt` first, never follow a redirect, and never send a browser
User-Agent:

- an HTTP 200 `text/plain` file on the same host: its rules apply;
- an HTTP 404 (no file): "no rules", and the fetch may go ahead;
- anything else is off-limits, and nothing more on the host is requested:
  a 403, a redirect to a page that is not a robots file, any other 4xx, a
  5xx, a timeout, or a 200 that is not `text/plain`.

On 2026-10-12:

- `www.tn.gov/robots.txt`: 200, `Allow: /`. Tennessee is fetched daily.
- `services1.arcgis.com/robots.txt` (Massachusetts): **403**.
- `utility.arcgis.com/robots.txt` (Michigan): **301 to the arcgis.com home
  page**, not a robots file.

So Massachusetts and Michigan are built and tested against labeled
synthetic fixtures, but `ENABLED_STATES` is `("TN",)`: they are not
fetched, have no data, and do not appear in v2, the site or the app. Their
products exist in the StoreKit configuration only. The owner confirmed on
2026-10-12 that both stay off. Enabling either later needs its host to
serve a readable robots.txt (or none, a 404) and a first real fetch checked
against the field names in `ma.py` / `mi.py`, which come from the research
description, not from the layers.

**Site.** Every California URL is unchanged. Each other state gets
`/<code>/` and `/<code>/water/<slug>/`, plus `/states/`, all in the sitemap
with structured data (no `Event`; a period is not an event), "stocking"
first in titles, and the state's own attribution and disclaimer on every
page. California's pages gain one header link, "Other states", only when
another state has data.

**Consequences.**

- California's DECISIONS 0009 and 0015 hold per state. 0018's "one in-app
  purchase" becomes one per state; the price of California's is unchanged.
- Michigan's records lag by weeks, so Michigan's alerts say "stocked on
  <day>" with the lag note, never "this week's stocking".
- Michigan's snapshot carries 2021 onward (`mi.PUBLISH_SINCE`) to keep the
  app's download small; history keeps whatever was fetched.
- The App Store listing (name, subtitle "CA trout stocking alerts",
  screenshots) still says California. It changes when a state goes on sale.
- **Owner answers, 2026-10-12.** (1) Massachusetts and Michigan stay off: a
  robots.txt that answers 403, or redirects to a page that is not a robots
  file, is off-limits; a 404 counts as "no rules". (2) Tennessee is USD
  9.99, one time, product id `com.chelseakr.cafishplanting.state.tn`.
  Michigan's indemnity clause and species scope are moot while it is off.

## 0026 — Maps on the site and in the app, from confident locations only (2026-10-12; proposed)

The owner approved maps on 2026-10-12 ("make the app and site more
visual with maps"). 0024 gives each California water a point or none, and
0025's snapshot v2 carries it in `waters[].location`; this is how the point
is shown.

- **Only confident points.** A pin only for a water whose v2 `location` is
  set: for California, an `exact` geocoder match or one the owner resolved
  in `pipeline/data/water_location_overrides.json`. **Owner-resolved
  waters go on the map** (owner, 2026-10-12): an override is her deliberate
  pick, recorded with who, when and why. Ambiguous and unmatched waters get
  no pin, and their pages say "No map location" with the reason. A
  stream's point is drawn differently (a ring on the site, a wave glyph in
  the app) and called approximate wherever it appears.
- **State-aware.** The site's map and the app's Map tab pin every state's
  waters that carry a location, and say per state how many do. Only
  California has a location source today, so Tennessee says it has none yet
  rather than showing an empty promise. The site's tiles cover California
  only, so the build fails (`MapCoverageError`) on a located water outside
  them: a state's tiles are cut before its pins go on the site map. The
  app uses Apple Maps, which covers everywhere, and frames all pins.
- **One source of locations.** The site and the app both read v2. Snapshot
  v1 keeps `location: null` for installed 1.0 builds. The app's bundled
  snapshot is v2 and carries the same locations, so there is no separate
  bundled locations file.
- **Website: MapLibre GL JS with self-hosted tiles.** A Protomaps basemap
  cut to California at zoom 10 (18 MB, one PMTiles file), MapLibre GL JS
  6.11.2, PMTiles 4.5.0, the Protomaps style, fonts and sprites: all served
  from this site under `map/`. No Google, no other tile host, no tracker.
  Attribution "© OpenStreetMap contributors" (ODbL) is on every map and
  the about page. Versions and licenses: `map/licenses/README.md`.
- **The map loads only when asked, and both loads have a budget.** Pages
  carry one small first-party module, `map/map.js`, which shows a "Show
  map" button; page load, Lighthouse scores and Core Web Vitals are
  unchanged. The map's own download after the button (library, style,
  fonts, the first tiles) has its own budget, its measured size plus 10%
  (owner, 2026-10-12), checked by a scripted press of the button
  (`perf/README.md`). The tables on the page stay the full list and the
  text alternative; the map region is labeled, and keyboard pan and zoom
  work.
- **The privacy copy changes with it.** With maps, the site no longer says
  "no JavaScript runs"; it says what `map.js` does: nothing until pressed,
  then loads the map from this site, sets no cookie, stores nothing and
  sends nothing. Tests pin that only that exact same-origin module is
  exempt from the no-script checks.
- **App: MapKit, no SDK.** A Map tab with clustered pins (this week's in
  the accent color), a map and Directions (handed to Apple Maps) on each
  water's page, and an iPad layout with the list beside the map.
- **Near me: on the device, When In Use, only when tapped.** The app says
  what it will do before iOS asks, takes one coarse fix (kilometer
  accuracy), sorts waters by straight-line distance on the device, and
  never stores or sends the location. Everything works without it. The
  App Store answer stays "Data Not Collected": nothing leaves the device
  for the developer. MapKit loads map tiles from Apple, which is Apple's
  service; the About screen and privacy page now say so instead of "the
  only network request". The listing's own copy waits for the next
  listing revision (owner, 2026-10-12).

## 0027 — Apple Watch and a round Lock Screen widget, in full access (2026-10-12; proposed, pending owner)

The owner asked on 2026-10-12 for Apple Watch and Lock Screen extras, as
more reasons to buy the same one-time purchase. 1.0.0 (build 2) is in
review and doesn't change; this is for a later version.

- **A watch app, companion only.** `CAFishPlantingWatch`
  (`com.chelseakr.cafishplanting.watchkitapp`) lists the favorite waters,
  each with where it stands in the schedule's week: a "This week" tag when
  listed, otherwise its next scheduled week. A water's page adds its next
  and last scheduled weeks and the species listed this week. Nothing else:
  no browsing, no settings, no purchase screen.
- **A complication and Smart Stack widget**, "Next favorite"
  (`CAFishPlantingWatchWidgets`): the favorite listed this week, otherwise
  the one scheduled soonest after it, in the rectangular, circular, inline
  and corner families.
- **A round Lock Screen widget on the phone** (`accessoryCircular`): how
  many favorites are scheduled this week. The widget had the rectangular
  and inline Lock Screen sizes already.
- **Part of full access, per state (0025).** `FreeTier.watchRequiresFullAccess`
  is `true`, and `FreeTier.watchAllowed(entitledStates:)` is the widget's
  rule: any state's purchase unlocks the watch, which then lists only the
  favorites in states this device owns. Favorites in other states are
  counted and said ("2 favorites are in states not unlocked"), never shown.
  The phone decides, in one place (`AppEnvironment.publishWidgetDigest`),
  and sends the watch the same digest the widget reads. The watch never
  checks a purchase and never sees a product ID. A report state's water
  says "stocked" on the watch too (`ReportWording`), never "scheduled".
  Each state's purchase screen lists "<State> favorites on Apple Watch". Locked, the watch says the content is part of full access, bought
  in Trout Truck on the iPhone, and shows the published week and its count.
- **No new data path.** The digest travels phone to watch over
  WatchConnectivity's application context, with no server, no account and
  no network request. The watch sends back only a water ID to mute, when
  "Mute this water" is tapped on the wrist and watchOS gives that button
  to the watch app.
- **Listing copy.** Each in-app purchase's description and the promotional
  text name Apple Watch, as part of a state's purchase ("Alerts, widget,
  Watch: Tennessee waters").
- **Follow-up:** check "Mute this water" from the wrist on a paired iPhone
  and Apple Watch.
- **Not built:** a Control Center or Lock Screen control (iOS 18). It
  would only open the app, which the icon already does.
