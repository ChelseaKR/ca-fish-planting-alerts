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
- **Every state, from v2 (0025).** It reads
  `https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v2.json`
  with the iOS app's request: one GET, `If-None-Match`, a fixed
  `User-Agent`, no cookies. Only when v2 isn't there (HTTP 404 or 410) does
  it make one more GET, of `snapshot/v1.json`, California alone; the decoder
  reads both. It ships its own committed v2 snapshot
  (`android/app/src/main/assets/snapshot.json`, refreshed by
  `android/scripts/sync-bundled-snapshot.sh`, which checks it against
  `schema/snapshot.v2.json`), so each app controls when its file changes.
- **Same rules.** A week, never a day, and "scheduled", never "stocked". No
  account, no analytics, no crash reporting, no server push. Alerts are
  local notifications that WorkManager's daily periodic refresh (and the
  refresh at launch and on swipe down) computes on the device. Favorites,
  mutes and the alert baseline are files on the device. Cloud backup is
  off; a device-to-device transfer carries them.
- **The alert planner is held to the Swift one.** Shared fixtures in
  `ios/PlantingCore/Tests/PlantingCoreTests/Fixtures/` carry expectations
  recorded from the Swift planner. `alert-planner-parity.json` (synthetic
  cases and two real-data excerpts) is California's;
  `alert-planner-parity-states.json` runs every state of the v2 fixture,
  with each state's purchase deciding which alerts may be posted and which
  favorites the widget lists. `AlertPlannerParityTests.swift`,
  `MultiStateParityTests.swift` and their Kotlin twins run every scenario
  and must produce the same alerts, ids, words, baselines and widget rows.
- **Same free/paid boundary, per state (0009, 0015, 0025).** Browsing,
  history and favorites are free and unlimited in every state. Each state
  is one Google Play one-time product that unlocks alerts for that state's
  favorites and lists them in the home screen widget; the widget unlocks
  with any state and counts, never shows, favorites in states not bought.
  California's is `fullaccess`, unchanged. Tennessee's is `state_tn`,
  Massachusetts' `state_ma`, Michigan's `state_mi` and New York's
  `state_ny` (added 2026-10-24, with New York's `plan` semantics,
  `approximate` precision and reminders, as 0034), each USD 9.99. A Play
  product ID already belongs to this one app, so these drop the
  package-name prefix the App Store IDs carry; `StateProducts` in `core`
  records the mapping, and a test checks it against `StateAccess.swift`.
  Play Billing only; the app never links to another way to pay.
- **Platform words.** Android has a home screen widget (Glance) and no Lock
  Screen widget, so the copy says "home screen" where iOS says "Home Screen
  and Lock Screen", and "Swipe down" where iOS says "Pull down". Everything
  else in the introduction is the iOS copy, with more states (0025), word
  for word, which a test checks against `Onboarding.swift`.
- **Review prompt.** Google Play's in-app review card, with the iOS rating
  lane's rules (0035), and an About row that opens the app's Play Store
  page.
- **Not ported.** Shortcuts and Siri (`ScheduleIntents`) and the Apple
  Watch (0027) have no direct Android twin in this change.

Owner steps (Play Console app, in-app products, signing, Data safety,
listing, internal testing) are in `android/README.md`. The v2, per-state
and introduction bullets above were updated on 2026-10-12 when the Android
app gained the states of 0025.

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

### Addendum 2026-10-20: the map link, "closest to me" and a hand review

- **Where the points show.** A water page with a point has a "View on
  map" link to OpenStreetMap (a plain link with `rel="noopener noreferrer"`;
  nothing is embedded and nothing loads from a map service until a reader
  clicks), the coordinates, and the source. A stream's point is labeled
  approximate. The about page says how many California waters have a point
  right now, and credits the USGS, which asks for
  acknowledgment and does not require it.
- **`geo` in structured data** only when the point is inside the water
  (`waterbody` or `named_point`) and the page prints the same numbers. A
  stream point (`stream_point`) gets none: a stream is not at one place.
  `tests/test_site_seo.py` and `tests/test_site_water_map.py` fail otherwise.
- **"Closest to me"** on the home page: `assets/closest.js` (first-party,
  about 6 KB, idle until a button is pressed) and `assets/water-coords.json`
  (slug to latitude, longitude, kind, built from the same committed file).
  The browser asks for the location only after the press; the script reads
  the static file with a plain GET that carries no location, sorts in memory,
  and stores and sends nothing. Without JavaScript the section stays hidden
  and the lists are unchanged. This is the one script on the site besides the
  GA4 tag (0011), so the about and privacy copy that said "no JavaScript runs"
  now names it, and the privacy page has a "Your location and map links"
  section.
- **Hand review, 2026-10-20.** Every `exact` match was re-read against the
  GNIS file (published 2026-09-29). One was wrong: GNIS lists two streams
  named North Fork Willow Creek in Madera County (feature ids 264220 and
  267078), and the geocoder had counted only the one
  with NHD flowlines. CDFW 501572 is now `ambiguous` with no point, the
  geocoder keeps a flowline-less same-name stream as a candidate, and
  `hand_review` in `water_locations.json` records it. No other `exact` water
  has a second same-name lake, reservoir, stream or canal in its listed
  counties. The nine other `ambiguous` waters and the 146 `none` waters are
  unchanged and need the owner (`water_location_overrides.json`).
- **Terms, read again 2026-10-20.** `usgs.gov/information-policies-and-instructions/copyrights-and-credits`:
  "USGS-authored or produced data and information are considered to be in the
  U.S. Public Domain" and "we ask that proper credit be given". The file
  metadata `DomesticNames_CA_Text.xml` (pubdate 20260929): use constraints
  "None. Acknowledgment of the U.S. Geological Survey would be appreciated for
  products derived from these data."

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

## 0028 — The website's App Store launch is one reviewed value, and clicks are measured (2026-10-19)

The app (1.0.0, build 2) is waiting for Apple's review. The website already
had a switch for the App Store surfaces (`APP_STORE_LIVE`, ADR 0013), but it
was a repository variable, so turning it on left no reviewed change and no
test that the surfaces moved together.

- **One committed value.** `APP_STORE_LIVE_DEFAULT` in
  `pipeline/src/cfpa/site.py` is `False` until launch day, when a one-line
  pull request makes it `True`. The `APP_STORE_LIVE` variable still wins when
  set to `true` or `false`, so it doubles as an off switch that needs no code
  change. An unknown value still refuses the run.
- **One flag, every surface.** `APP_STORE_URL` no longer links the app by
  itself; it changes the address while the switch is on and does nothing
  while it is off.
  `cfpa.launch_check.surface_problems` reads a built site and reports any
  surface (banner, badge, install links, `MobileApplication` data, click
  event, badge file, "not yet" sentence) that disagrees with the flag. The
  tests and `scripts/preflight_app_store_live.py` both use it.
- **Click measurement on the website.** One event, `app_store_click`, with
  `placement` (home, support, about, water), `link_type` (badge, link) and
  `link_url`, sent through the existing GA4 tag. It obeys the same Global
  Privacy Control, Do Not Track, footer opt-out and consent rules as every
  other event, because it is inside the same guard. It replaces
  `app_store_badge_click`, which never shipped because the switch was off.
  The privacy page describes it when the switch is on.
- **The app is unchanged.** It still has no analytics (0011). Installs are
  read in App Store Connect (Sources, Web Referrer), not on the website.
- **Owner steps** (they need her Google login) are in
  `docs/LAUNCH-CHECKLIST.md`: mark the event as a key event and register its
  two parameters as custom dimensions, after the event has arrived.


## 0029 — Amazon Associates gear links on the website's water pages (2026-10-20)

The owner opened an Amazon Associates account on 2026-10-19 with the store
ID `trouttruck-20`. Affiliate links are allowed when they are plain and
visibly disclosed. Amazon closes an account that has not made 3 qualifying
sales within 180 days, which is about 2027-04-17; if there are none by then
the links come out in one edit (delete `GEAR_CATEGORIES` and the block in
`water.html.jinja`).

- **Where.** A short "Gear for this water" block on each California water
  page, and a "Gear links" section on the privacy page. **The website, never the app.**
  The iOS app has no web view and never shows these links; the report-state
  pages, the home, county, support and about pages carry none. The about
  page's privacy note mentions them in a sentence. (0039, 2026-10-23, adds
  California county pages and other states' water pages.)
- **Why search links.** Each link is `https://www.amazon.com/s?k=<terms>&tag=trouttruck-20`,
  a search for a generic category (trout rod and reel combo, trout lure and
  tackle assortment, fishing waders, landing net for trout). A search has no
  product to go out of stock or change price, so the page never states a
  price, rating, image or "best" claim, and nothing about a product can be
  wrong. The data has no lake-or-stream field, so every water gets the same
  four categories.
- **One constant.** `AMAZON_ASSOCIATE_TAG` in `pipeline/src/cfpa/site.py` is
  the one place the tag is written. `tests/test_site_affiliate.py` rebuilds
  the site with a different value and fails if the old one survives.
- **Disclosure.** Beside every block: "As an Amazon Associate I earn from
  qualifying purchases." (Amazon's wording, kept exactly), a plain sentence
  that these are affiliate links and cost the reader nothing extra, and a
  link to the privacy page. Every link carries `rel="sponsored nofollow
  noopener"`. No redirect, shortener or cloaking: the address in the page is
  the address the browser opens.
- **Agency non-endorsement.** This site shows California Department of
  Fish and Wildlife data, and a commercial link beside it must not suggest
  the agency stands behind it. The gear block and the privacy section both
  say: "The links are Trout Truck's, not CDFW's, and CDFW does not endorse
  them or Amazon." The site name and the agency's short name come from
  `SITE_NAME` and `CDFW_SHORT_NAME` through `gear_endorsement()`, and a test
  fails if a page with a tagged link lacks the sentence for its agency.
- **Not the same design as PR #64.** An older open PR (#64, branch
  `feat/gear-links`) proposes a separate Bass Pro link that ships switched
  off, and numbers its own entry 0028 there. This decision does not depend
  on it. 0028 on main is the launch switch, and 0029 was free on
  origin/main when this was written.
- **No added tracking.** No script, pixel or event for these links. The
  existing GA4 tag (0011) is unchanged and still obeys Global Privacy
  Control, Do Not Track and the opt-out; Google's own outbound-click
  measurement may count a click on any off-site link, which the privacy page
  already said and now says again for these. The `app_store_click` handler
  matches App Store links alone.
- **Guards.** `tests/test_site_affiliate.py` fails when a tagged link lacks
  the rel values or the disclosure, appears on any page except a California
  water page, appears in JSON-LD, a feed, the sitemap or the snapshot, or
  appears in the `ios` or `android` sources; each guard has a negative
  control that checks its sabotage applied. Existing site checks needed no
  change: they forbid off-origin requests the browser makes by itself
  (script, image, stylesheet, frame), and an `<a href>` is not one.

## 0030 — A "What to bring" guide at /gear/ (2026-10-20)

Extends 0029 with one more website page, for the same Amazon Associates
account (`trouttruck-20`) and the same reason: it needs 3 qualifying sales by
about 2027-04-17, and the links come out in one edit if there are none.

- **What.** `/gear/` is a plain checklist for a day at a California water on
  the schedule: a license reminder with a link to CDFW's license page (no
  legal advice), trout and catfish basics, rod, line and small tackle, bait
  and lures, cold-weather and sun items, and a cooler and cleaning list. It is
  general fishing knowledge. It states no statistic, price, rating or product
  claim, and names no brand.
- **Links.** Each section ends with Amazon search links for a category, built
  by `amazon_search_url()` from `GEAR_GUIDE_LINKS` in `site.py`, so the tag is
  still written in one place. Same rel values, same disclosure, same plain
  affiliate sentence and the same CDFW non-endorsement sentence as 0029, shown
  before the first link and again after the last.
- **Where it is linked.** From each water page's gear block ("More gear ideas")
  and from the footer of every page, as an ordinary internal link.
- **Still the website alone.** No Amazon link in the iOS or Android sources,
  the feeds, the data, the sitemap or structured data. The page has a
  canonical URL, a sitemap entry and a breadcrumb.
- **Click labels.** Each Amazon link carries `data-ga-event="gear_click"`,
  `data-ga-placement="gear_guide"` and `data-ga-type="amazon_search"`, the
  labels the click handler in the pending click-event work reads. Without that
  handler they do nothing.
- **Guards.** `tests/test_site_gear_guide.py` (with negative controls) and
  the widened page list in `tests/test_site_affiliate.py`.

## 0031 — Plain explainer pages under /guide/ (2026-10-21)

Three short pages and an index explain the schedule the site already shows:
how to read it, scheduled vs. confirmed, and what a trout plant is. They are built by
`pipeline/src/cfpa/guides.py` from `guide_*.html.jinja` templates and are in
the sitemap, the footer of every page and the home page.

- **A claim has a source or is cut.** Each statement is either computed from
  the snapshot (counts, the earliest recorded week) or taken from a CDFW page
  fetched with curl and read on `guides.CDFW_READ_ON`. Every guide names that
  day and links the page. A license guide was drafted from CDFW's license page and dropped
  by the owner before merge.
- **No recommendations.** No product, no affiliate link, no outbound link to
  anything but CDFW. A test fails on any other host.
- **The demand evidence is weak.** Search Console has 5 days of data, and none
  of its visible queries asks a how-to question. The pages answer
  confusion the schedule itself invites; they are not a bet on a measured
  query. If they earn no impressions in 8 weeks after indexing, drop them in
  one edit (delete `guides.py`, the templates and the three links).
- **No ranking claim.** Only the thin weeks above are noindex.

## 0032 — Oregon is built and tested behind a flag that is off (2026-10-21)

(0030 is the /gear/ guide on main, so this is the next free number.)

ODFW's weekly trout stocking schedule has an adapter
(`pipeline/src/cfpa/states/oregon.py`), but Oregon is not registered, not
fetched, not published and not in the sitemap. It stays that way until the
owner decides, because ODFW's page and the State of Oregon's website terms are
silent on reuse, and 0004 says unknown is not used.

- **The flag.** `CFPA_ENABLE_OREGON=1` in the environment registers Oregon
  (`cfpa.states.registered_sources`) and adds it to the states the daily run
  fetches. Unset, empty and `0` are off; any other value refuses the run.
  `pipeline/src/cfpa/states/__init__.py` reads it once, at import.
- **Off means identical.** A default build is byte-identical to main (checked
  by building both and diffing the trees, and by
  `tests/test_oregon.py::test_a_default_build_is_byte_identical_whether_or_not_oregon_is_registered`).
  `publish.yml` is not changed: it does not set the flag and does not commit
  `pipeline/data/states/or.json`. Turning Oregon on also means adding that
  path to the commit step and setting the flag there. That is the owner's edit.
- **Shape of the source.** Weeks run Monday to Friday. The view is capped at
  50 rows and the print view at 500 (it stops at 2027-05-07), so the fetch
  reads one week at a time, splits a full week into ODFW's six zones, and
  refuses a zone that is still full. It reads 8 weeks from this week's
  Monday, a fixed window (the far weeks look carried forward from the year
  before). There is no county, species or size in inches; a water is a name
  plus a zone.
- **Shared code touched, all additive.** `StateSource` gained
  `week_starts_on`, `week_days` and `week_phrase` (Sunday, 7, "the week of a
  Sunday" by default, so Tennessee is unchanged); the v2 snapshot checks a
  week against its state's start day; the hub names a zone when a water has
  no county.
- **Copy rules** are in the module docstring and `COPY_RULES`, pinned by
  tests: "scheduled", never "planted" or "stocked on"; a week, never a day;
  ODFW's size-class words with no inch sizes; a water's frequency is ODFW's
  plan for the weeks read, not a rate.

## 0035 — Ask for App Store ratings only at the end of a task (2026-10-12; recorded 2026-10-21)

(Written as 0028 on the branch that carried it, feat/ratings-and-water-seo;
0028 on main is the website's App Store launch value, and 0030 to 0034 are
taken by the gear guide, the guides, Oregon, the email ADR and the second
wave of states, so this is the next free number.)

**Context.** Every stocking app in App Store search has 0 to 6 ratings
(`_agent-tools/remediate-2026-10-12/seamline/COMPETE.md`, move 3), so the
first honest ratings matter. The owner approved asking for them: "do 3 and
5. do 3 across my ios apps". App Review Guideline 5.6.1 allows only the
system prompt, with no reward and no step that sorts people by whether
they like the app.

**Decision.** The app calls `AppStore.requestReview` (StoreKit) and has no
prompt of its own. It asks only when someone goes back from a water's page:
after opening a planting alert (second launch on), or from the third launch
on with at least one favorite. Both are state-agnostic: an alert exists
only for a state the person unlocked, whichever state that is, and a
favorite in any state counts. Nothing is tied to California's product
(0025). It never asks on the first launch, over a sheet, the introduction
or a refresh, more than once per app version, within 120 days of the last
ask, or more than three times in 365 days. iOS has the same yearly cap,
but the app counts the asks iOS chose not to show. Debug builds never ask
unless launched with `-ReviewPrompt allow`. About has a "Rate Trout Truck"
row that opens the App Store's write-review page.

The state (`review-prompt.json`: launch count, ask dates, versions asked)
lives in Application Support, like favorites, so the app still calls no
required-reason API and its privacy manifest is unchanged. The rules are
in PlantingCore (`ReviewPromptPolicy`, `ReviewPrompter`) behind an
injectable clock. The Android app (0022) carries the same rules in
`android/core/.../ReviewPrompt.kt`.

**Consequences.** iPad users are asked less often: choosing another water
beside the list is not "going back". A rating prompt cannot be tested on
TestFlight (Apple never shows it there), so only the trigger logic is
tested. `HostAllowlistTests` allows `apps.apple.com` in one file, as a
link the system opens rather than a request the app makes.

## 0034 — States wave 2: Michigan, Massachusetts and New York, and a v2 reader that ignores what it does not know (2026-10-13; rebased 2026-10-21)

(Numbered 0028 on the `feat/states-wave2` branch of 2026-10-13; that number
went to the launch switch on main. 0031 is the guides, 0032 Oregon, 0033
is reserved for the email digest ADR and 0035 is the ratings prompt, so this
is 0034. The owner confirmed
on 2026-10-21 that iOS 1.1.0 ships all four states, Tennessee plus these
three, each as its own in-app purchase, while 1.0.0 is in Apple's review.)

**Owner answers, 2026-10-13** (multiple choice, recorded as given):

1. **Michigan:** the owner accepts the dataset's indemnity and release
   clauses. Read the DNR's own CSV,
   `https://michigandnr.com/publications/PDFS/Fishing/FishStocking/FishStockingData.csv`
   (robots.txt 404, which DECISIONS 0025 counts as "no rules"), with one
   conditional download a day instead of ArcGIS paging. Water ids come
   from county + water + site name; trout only; report semantics, with the
   DNR's lag said beside the data.
2. **Massachusetts:** the owner accepts the ArcGIS Hub download route.
   `hub.arcgis.com` serves a readable robots.txt (200, `Crawl-delay: 60`,
   `/api/` allowed). `services1.arcgis.com`, the layer's own host (robots
   403), is never touched. The run asks Hub for the CSV, waits the
   Crawl-delay on a 202, and reads the `resultUrl` only on Hub's host: two
   or three requests a day, 61 s apart.
3. **New York:** NYS DEC's spring plan from OPEN-NY, as planned-period
   reminders plus the plans' history, in DEC's own words ("April - third
   week", "Spring"), never turned into dates, with "planned for" wording.
4. Each state is its own $9.99 non-consumable:
   `com.chelseakr.cafishplanting.state.mi`, `.state.ma`, `.state.ny`.
   A state is enabled only once its fetch works on live data.

**What was built.**

- **Michigan** (`cfpa/states/mi.py`). One GET with `If-None-Match` and
  `If-Modified-Since`; a 304 records "checked, unchanged" and nothing else.
  The server answers `Accept: text/csv` with 406 (measured), so the request
  accepts `application/octet-stream`. Kept: species whose name contains
  "trout" (brown, rainbow, brook, lake), stockings into public water only
  (State, Federal, Tribal, Tribal/DNR and IN DNR/DNR coop, Public and
  Mitigation plants; private ponds under permit, research, school,
  rearing-pond and out-of-state rows are left out), and 2021 onward. The
  site name, when it differs from the water, is part of the water's name.
- **Massachusetts** (`cfpa/states/ma.py`). The real field is
  `Stocked_Date` (`2026/09/25 22:00:00+00`), not the guessed `Date`.
  Species codes are mapped with MassWildlife's own legend, the layer's
  coded-value domain `cvd_FishSpecies` read from Hub's metadata: BT Brown
  Trout (verified there), EBT Eastern Brook Trout, RT Rainbow Trout, S
  Broodstock Salmon, TT Tiger Trout. A code outside the legend refuses the
  feed rather than being guessed. "Lake Wyola - Shutesbury" is shown as
  "Lake Wyola" with its town beside it. An empty file (the season is over)
  is not an error: a report never infers a removal.
- **New York** (`cfpa/states/ny.py`). A new semantics, `plan`: it looks
  forward like a schedule, says "planned for", and never infers a removal
  (one publication a year). A new precision, `approximate`: the label is
  DEC's words and the year, verbatim ("April - third week, 2026"); start
  and end only bound it, for ordering and reminders. The 25 forms in the
  2026 file are read; any other form refuses the feed.
- **Reminders** (iOS; Android from 2026-10-24, `ReminderPlanner` in
  `android/core`). For a New York favorite in a bought state and not
  muted, the app schedules a local reminder at 9 a.m. on the first day of
  each planned period no longer than 31 days ("April - third week",
  "May", "Mid April"), saying the period in DEC's words and that it is a
  plan, not a date. "Spring" and two-month ranges are too loose and get
  none. The notification priming copy says so.
- **Crawl-delay** is honored: requests to a host that declares one wait it
  plus a second.
- The ArcGIS paging module is removed; no source uses it.

**Live check, 2026-10-13.** Each fetch ran through the production code on
live data before its state was enabled: Michigan 3,406 public trout
stockings at 604 waters from 2021 on (and a second request answered 304);
Massachusetts 150 stockings at 123 waters through Hub; New York 889
planned stockings at 582 waters. Their histories are seeded from those
fetches. `ENABLED_STATES` is now TN, MI, MA, NY.

**Live check again, 2026-10-21** (the rebase; one fetch per source through
the same adapters, the pipeline's own User-Agent, eight requests in all,
into a scratch directory, nothing committed from it): `hub.arcgis.com`
robots.txt 200 `text/plain`, the download status answered 200 Completed on
the first call and the CSV 200 `text/csv`, 150 records at 123 waters, file
dated 2026-10-13; `michigandnr.com` robots.txt 404, the CSV 200
`application/octet-stream` with an ETag and `Last-Modified: Mon, 19 Oct
2026 15:40:36 GMT`, 3,406 public trout stockings at 604 waters from 2021
on; `data.ny.gov` robots.txt 200 `text/plain`, the plan 200 JSON, 889
planned stockings at 582 waters, rows dated 2026-03-19. The same counts as
on 2026-10-13, so the seeded histories stand.

**Compatibility.** v1 is unchanged. v2 gains the `plan` semantics and the
`approximate` precision. The v2 reader on main before this change refused a
file with any `semantics` or `precision` it did not know, and the app then
kept its last good snapshot forever: had 1.1.0 shipped that reader, adding
New York to the live `v2.json` later would have stopped every install from
refreshing. So two things change together:

- **The reader ignores a vocabulary it does not know, and refuses only a
  broken contract** (`ios/PlantingCore/Sources/PlantingCore/SnapshotV2Decoding.swift`).
  A state whose `semantics` this build has no words for, or whose code this
  build has no product for (`StateAccess.isKnown`), is left out with its
  waters and its `this_week` entries; a plant whose `status` or
  `period.precision` is new is left out, and a water left with nothing to
  show goes too, as does a state left with no water. A malformed file (a
  week labeled as a day, a `reported` plant in a schedule or plan state,
  California not first, a water in a state the file does not list) still
  throws, and the caller keeps the last good snapshot. `StatesWave2Tests`
  pins each case with a sabotage that is checked to have landed.
- **The reader ships in the same app release as these states** (1.1.0),
  with New York's `plan` records in it.

**Products.** `.state.mi`, `.state.ma` and `.state.ny` follow Tennessee's
pattern in `Configuration.storekit` and App Store Connect: Non-Consumable,
USD 9.99, description "Alerts, widget, Watch: <State> waters". The
California product is unchanged.

**The daily run.** `ENABLED_STATES` is TN, MI, MA, NY, and `publish.yml`'s
commit step lists `pipeline/data/states/mi.json`, `ma.json` and `ny.json`
beside `tn.json` (the one-line edit 0032 describes for Oregon), so each run
commits the three histories and Massachusetts' rows accumulate past the end
of its season instead of aging off.

## 0038 — A page for each past week on record, at /week/YYYY-MM-DD/ (2026-10-22)

(0036 and 0037 are reserved by other branches; 0035 is the last on main.)

Each past week in which CDFW's schedule listed at least one water gets a
permanent page, `/week/<week start>/`, and `/week/` lists them most recent to
oldest. They are built by `pipeline/src/cfpa/weeks.py` from the snapshot's
plants (the record the water pages and the species pages already read) and
nothing else.

- **Which weeks.** A week with at least one `listed` plant that starts before
  the snapshot's current week. The current week is the home page and is
  linked, not copied. A later week can still change and has no page. A week
  with no listings gets no page, and with no such week at all `/week/` is not
  written and nothing links to it.
- **Thin weeks are not indexed (owner decision 2026-10-22).** A week with
  fewer than `WEEK_INDEX_MIN_WATERS` = 8 listed waters keeps its page, is
  linked from `/week/` like the others, and carries `robots` `noindex,follow`
  and no sitemap entry. A week with 8 or more is indexed and in the sitemap.
  The index says nothing about which is which.
- **Removed entries are never shown.** A removed plant is not a listing;
  a page says so in one sentence.
- **Copy.** The week, the count, "CDFW's schedule for that week, as this
  site recorded it", "subject to change", "scheduled, not confirmed". No
  ranking, no "first", "only", "best", no "stocked", no day or time. Titles
  stay under 60 characters and descriptions under 155, and a test checks every
  title and description is unique across all page kinds.
- **Past pages do not churn.** No page prints the check time or the day. A
  week page's sitemap `lastmod` is the newest date one of its plants was first
  listed or marked removed; the index's is the later of that and the day its
  newest week became a past week. Only the share card's alt text (every page
  has it) carries the check date.
- **The demand evidence is thin.** Search Console shows two or three queries
  about stocking dates and weekly schedules, none naming a week
  (`trout-truck-query-evidence-2026-10-22.md`), so this is a bet on long-tail
  date queries, not a measured one. If the week pages earn no impressions by
  the next review, delete `weeks.py`, the two templates and the links to /week/.
- **No ranking claim.** Only the thin weeks above are noindex.

## 0039 — Gear links on the pages people land on (2026-10-23)

Extends 0029 and 0030. Same Amazon Associates account (`trouttruck-20`), same
search links, same deadline: 3 qualifying sales by about 2027-04-17, or the
links come out in one edit.

- **Why.** GA4, 28 days to 2026-10-23: 48 engaged sessions. By landing page,
  14 began on a Tennessee water page, 11 on a California water page, 8 on a
  California county page and 8 on the home page. 0029 put the gear block on
  California water pages alone, so more than half of the engaged landings
  that reached a water or county page never saw a gear link. GA4 recorded
  no `gear_click` in that window, and the click label has only been live
  since 2026-10-21, so this is a bet on reach, not a measured conversion.
- **Where it is added.** Each California county page, after "Recently on the
  schedule", and each other state's water page, after its stocking table.
  California water pages and `/gear/` are unchanged byte for byte (checked
  against a build of main). The home page, hubs, `/states/`,
  `/county/`, region, species, week and guide pages still carry none.
- **Which states.** `site_states.gear_allowed()` allows the block only when
  every license source of the state's data says `commercial_reuse:
  "permitted"` and the water's species word is trout, the only gear the block
  offers. Tennessee, the only other state on the live site today, passes, and
  so would Massachusetts, Michigan and New York if they are switched on. Oregon's
  terms are `unknown`, so it would get none if it is switched on. TN.gov's
  linking policy asks for no implied endorsement, so the sentence names the
  page's own agency ("The links are Trout Truck's, not TWRA's, and TWRA does
  not endorse them or Amazon."), and a test fails if a state page names CDFW.
- **One block.** `templates/_gear_block.html.jinja` holds the markup for every
  page kind; each page sets the heading, the opening question and the click
  placement (`water`, `county`, `state_water`). The other states' blocks leave
  out the link to `/gear/`, because that guide is about California waters.
- **Copy.** Unchanged in kind: categories, never products; no price, rating,
  image, brand or "best"; Amazon's disclosure sentence exactly; the plain
  "costs you nothing extra" sentence; `rel="sponsored nofollow noopener"`.
  The privacy page's "Gear links" section and the about page say where the
  links now are.
- **Guards.** `tests/test_site_affiliate.py` allows tagged links on these page
  kinds alone, checks the agency sentence per page, and has negative controls
  for a state with unknown terms (no links), CDFW named on a state page, and
  a link on a state hub.

## 0040 — Winter on the record, and gear links on the home page and /county/ (2026-10-29)

Extends 0039. Same Amazon Associates account (`trouttruck-20`), same search
links, same deadline: 3 qualifying sales by about 2027-04-17.

- **Why.** Search Console, 2026-07-30 to 2026-10-27, `sc-domain:trouttruck.com`:
  1,264 impressions and 41 clicks, almost all of them from 2026-10-15 to
  2026-10-22 (135 to 197 a day), then 3 to 9 a day from 2026-10-23. The
  queries are county and water schedule searches ("fresno trout plant",
  position 5 to 10; "lake ralphine stocking schedule", 7.3) and the old
  agency name ("dfg fish planting schedule", "dfg trout plants", positions
  10 to 55). GA4, 28 days to 2026-10-28: the home page is the most common
  landing page (71 sessions, 11 of them engaged), and it carried no
  gear link. GA4 recorded no `gear_click` in that window.
- **Winter on the record.** The record holds a whole past winter (listed
  weeks from 2025-09 on). Each county page gains "Winter plants in X County":
  the county's waters CDFW's schedule listed from November through February
  of the most recent complete winter, with the number of listed weeks each,
  and the home page gains the statewide count and the counties with the most
  listed waters. "Winter" is the calendar months, not a CDFW term. The block
  appears only when the record begins on or before that November 1, so a
  county with no listed water is a fact about the record, never a gap read
  as absence; it says it is a record of what was scheduled, not a forecast.
  A county page's lastmod counts the rollover at which a new winter becomes
  the latest complete one (`latest_complete_winter()["shown_from"]`).
- **Gear links.** The home page and `/county/` carry the same block as the
  county pages (`_gear_block.html.jinja`, placements `home` and `counties`).
  From November through February, by the start of CDFW's current week, the
  home page's block adds one cold-weather search ("Insulated fishing
  gloves"); the home page's lastmod already moves at every rollover, so no
  page changes while its lastmod says it did not. Water and county pages keep
  the fixed four. Region, species, week, guide, `/states/` and state hub
  pages still carry none.
- **Copy.** Unchanged in kind (0029, 0039): categories, never products; no
  price, rating, image, brand or "best"; Amazon's disclosure sentence; the
  CDFW non-endorsement sentence; `rel="sponsored nofollow noopener"`. The
  county index description and lede say CDFW was called the Department of
  Fish and Game (DFG) before 2013, as the home page description already did.
  County page h1s say "stocking and planting schedule", the wording of the
  water page titles. Ads stay off.

## 0041 — Thin water pages: noindex, out of the sitemap, no gear links (2026-10-30)

Owner decision after Google re-ranked the whole site down on 2026-10-23
(Search Console: about 160 impressions a day before, 3 to 9 after; every
page group fell, and every sampled page is still indexed).

- **Rule.** A water page, in any state, with fewer than two dated stocking
  rows (`cfpa.thin`, `WATER_INDEX_MIN_DATED_ROWS = 2`) carries
  `<meta name="robots" content="noindex,follow">`, is left out of
  `sitemap.xml`, and has no Amazon gear block. The page, its calendar feed,
  its canonical and every link to it stay, so visitors and the apps reach it
  as before. One function decides all three, so they always agree.
- **Dated row.** A plant that is not `removed` and whose period is a day, a
  week, or an agency's own words for part of a month (New York's
  `approximate`). A bare month (Tennessee's "TBD 12/2026") is not a date,
  the same line the state hub's date span already draws.
- **Counts** (live snapshot, 2026-10-30; indexed / noindexed): California
  312 / 76, Tennessee 93 / 43 (with the exception below), Massachusetts
  27 / 96, Michigan 542 / 65, New York 161 / 421. In all, 1,135 of 1,836
  water pages stay indexed with their links and 701 are noindexed without.
- **Exception.** `/tn/water/fountain-city-lake-knox-county/` has one dated
  row but was the 10th page by Search Console impressions over the 90 days
  to 2026-10-30 (18, 1 click), so it stays indexed with its links
  (`KEEP_INDEXED_PATHS`). No other thin page had more than 7.
- **Not changed.** Week pages keep their own rule (fewer than 8 waters,
  0038). Region and species pages are other templates and are untouched.
  County pages and the home page keep their gear block (0039, 0040).

## 0042 — No new page families until 2026-11-27 (2026-10-30)

No new page types (like the region, species and week pages of 2026-10-21
and 2026-10-22) and no large template changes until 2026-11-27. Google
re-ranked the site on 2026-10-23, two days after about 35 site changes
including three new page families. A stable site lets Google re-score it,
and lets any recovery be traced to a cause. Fixes to existing pages are
fine.

## 0043 — A holiday gift section on /gear/, 11-15 to 12-26 (2026-10-30)

The Amazon plan of 2026-10-30 ranked one seasonal change inside the existing
guide above any new link surface: late November through December is when an
Amazon purchase is most likely, and any purchase within 24 hours of a click
counts.

- **What.** A "Gifts for someone who fishes for trout" section near the top
  of `/gear/`, after the first disclosure and before the license section,
  with five category searches (`HOLIDAY_GIFT_LINKS`). Same rules as the rest
  of the guide (0030): tagged search links, the sponsored rel values and
  click labels, the disclosure before and after, no brand, price, rating or
  image.
- **When.** The build's date decides: shown from 11-15 through 12-26 each
  year, both days included (`holiday_gifts_shown`). The date is the UTC day
  of the snapshot's `generated_at`, so the daily publish adds the section
  and removes it with no edit. A build given `--run-today` uses that date.
- **Where not.** No other page changes. Water, county, home and state pages
  keep the blocks 0039, 0040 and 0041 give them, and the section is not a
  new page, so it fits 0042.

## 0044 — Android launches free, with nothing for sale (2026-11-03)

Google Play shows a personal developer account's full address once it
sells: "If you monetize on Google Play, Google displays your full address"
([Required information](https://support.google.com/googleplay/android-developer/answer/13628312)),
and "merchant accounts (developer accounts with apps that monetize via paid
apps or in-app purchases) must show their full address"
([About you](https://support.google.com/googleplay/android-developer/answer/13634081)).
The address is the Google payments profile's, a PO box isn't accepted, and
the owner won't use a mailbox (2026-10-23) or publish her home address. So
the Android app launches with nothing for sale.

- **What.** On Android, alerts, New York's reminders and the Favorite waters
  widget are free in every state. Browsing, history and favorites were
  already free. No screen shows a price, a purchase, an unlock or Restore
  purchases, and nothing says a paid tier is coming.
- **How.** One Gradle property, `troutTruck.androidFreeTier` in
  `android/gradle.properties`, `true` by default. When true, the Play
  Billing library is not a dependency (so the release manifest has no
  `com.android.vending.BILLING` permission), `BuildConfig.FREE_TIER` is
  true, and `app/src/free` supplies a store that reports every state as
  owned (`FreeLaunch.entitlements`). The per-state gate in `FreeTier` is
  unchanged, so the same checks let every alert through. When false,
  `app/src/billing` brings back Play Billing and the purchase screens as
  they were (0025). CI builds and tests both sides.
- **Why not hide the paid features instead.** Hiding alerts and the widget
  would ship a smaller app with a gate nobody can open, and Play's
  reviewers and testers would meet dead features. Free and complete is the
  honest version, and the 14-day closed test needs testers who use alerts.
- **Why remove the library, not just the products.** Google's pages tie
  the address to monetizing (paid apps or in-app purchases), not to the
  library. Leaving billing code out anyway removes the question, the
  BILLING permission and a Data safety prompt, and costs nothing.
- **iOS.** iOS keeps its per-state purchases (0025); it is not on sale
  (Apple rejected 1.0.0 under 4.3(a)). The two platforms now differ on
  price. The Android listing says nothing about iOS pricing.
- **Later.** A free Play app can add in-app products later, but can never
  become a paid app
  ([Set the price](https://support.google.com/googleplay/android-developer/answer/6334373)),
  so a paid version is the flag plus new products, and the address question
  comes back then. Whether people who had alerts free keep them is decided
  then. The free build saves every state as owned on the device; the paid
  build replaces that with what Google Play reports once it connects.
- **Not the website.** 0042's freeze is about the website's page families;
  this changes only the app and its docs. The privacy page still names
  Google Play Billing among the Android app's libraries, which overstates
  what the free build carries; it can be corrected separately.

## 0045 — Keep five clicked thin pages indexed; gear that fits the water, moved up (2026-10-31)

Follows 0041 and fits 0042: no new page, no new link surface, and no new
links on any page. Two fixes to existing water pages.

- **Five thin pages stay indexed.** 0041 kept thin pages by impressions.
  By clicks, Search Console (`sc-domain:trouttruck.com`, 2026-08-01 to
  2026-10-30) shows 41 clicks on the site, 4 of them on pages 0041
  noindexed, one each at an average position of 2 to 4:
  `/tn/water/martin-city-pond-weakley-county/`,
  `/tn/water/milan-city-pond-gibson-county/`,
  `/tn/water/mossy-creek-new-jefferson-county/` and
  `/water/lake-berryessa/`. GA4 also shows an engaged organic landing on
  the Milan and Mossy Creek pages. A fifth, `/water/eagle-lake/` (Eagle
  Lake, Lassen County), earned one click at position 1 on 2026-11-03, after
  that window closed; it is 1 of the site's 3 clicks from 2026-10-23 to
  2026-11-04. All five join `KEEP_INDEXED_PATHS`. No other thin page earned
  a click.
- **Gear that fits the water.** Water pages are where people land (GA4,
  2026-10-03 to 2026-10-31: most engaged organic and AI-assistant landings
  are water pages), and no `gear_click` has been recorded. The click event
  itself works: on 2026-10-31 a headless browser clicked the first gear link
  on the live `/county/fresno/` and home pages, and the page sent a
  `gear_click` hit (the test blocked the hit and the Amazon request, so
  nothing reached GA4 or Amazon). So the block was reaching no one, or
  offering nothing they wanted. A water page now picks its four searches by
  the agency's own name for the water (`cfpa.water_kind`): a lake, pond or
  reservoir gets dough bait and bobbers in place of the lure assortment and
  waders; a river or creek gets spinners and spoons in place of the lure
  assortment. A name with neither word keeps the general four. The rod and
  the net stay in every set. County pages, the home page and `/county/`
  keep the general four.
- **Moved up.** On a California water page the block now follows the
  planting history table instead of "About this water". On a phone that is
  about two screens down instead of about four (measured on the live
  `/water/ralphine-lake/` and `/water/shadow-cliff-lake/`, 390 px wide).
  Label, disclosure, endorsement sentence, rel values and click labels are
  unchanged.
- **Risk.** The 2026-10-30 audit could not rule out that the affiliate
  block fed the 2026-10-23 re-rank. Moving it up makes it more prominent on
  about 310 California pages. Revert the move alone if that is a worry.

## 0049 — National framing; every California URL unchanged (2026-11-05)

Chelsea, 2026-11-05: "reorient trout truck as a national platform not
focused on california." She approved the nine recommendations in the
2026-11-05 national plan as written.

- **Brand line.** "Trout stocking schedules, state by state." It stays true
  at one state or fifty and carries the search words. Copy never says "all
  states", "every state", "nationwide" or "50 states".
- **Names stay.** The display name stays "Trout Truck" and the repository
  stays `ca-fish-planting-alerts`: both apps read
  `chelseakr.github.io/ca-fish-planting-alerts/snapshot/v2.json`, and GitHub
  Pages does not redirect a renamed repository's site, so a rename would cut
  every installed build's data. Bundle, product and package IDs never change
  (0010).
- **California's URLs and page titles stay.** About 79% of Search Console
  impressions from 2026-08-01 to 2026-11-03 landed on California's root
  pages, and California's head terms rank on `/county/`, not on `/`. There
  is no `/ca/` move and no redirect. Only the frame changes: shared chrome,
  then `/states/`, then the home page, each a separate PR at least a week
  apart and none before 2026-11-27 (0042).
- **Live states come from data.** Shared copy that lists states builds the
  list from `snapshot/v2.json`, so a state that is added or paused changes
  the words by itself. Hand-written drafts (the README and the store
  listings) are dated, and leave out a state whose newest check failed more
  than 7 days earlier. Tennessee is out of the store copy for now: its last
  good read was 2026-10-15.
- **Apps.** The apps' national wording merges to `main` now. Android ships
  it in the next Play release; iOS waits for the Board's answer on 1.0.0,
  whose App Store Connect copy stays frozen. A first-run state picker
  (no location; skipping shows the States list) comes later, in its own PR.
- **First change (this one).** The README, the next iOS version's listing
  (`docs/app-store/LISTING-MULTISTATE.md`) and a Play listing draft
  (`docs/PLAY-LISTING.md`) are reworded national. `docs/APP-STORE-LISTING.md`
  gets only a "frozen during the appeal" note.

## 0053 — Android asks which state on first run; no California default (2026-11-05)

Plan N6 from the 2026-11-05 national plan, decision 9, option A: ask on
first run with no location, and if the person skips, show the list of
states. Chelsea hasn't picked an option for decision 9 yet; this builds the
recommended one.

- **What.** The introduction's "Find your waters" page lists the states in
  the snapshot, none chosen, and saves a pick as it is made. Skipping, or
  any launch with no pick, opens Browse on that same list instead of any one
  state's waters. A pick the snapshot no longer carries counts as no pick,
  never as California.
- **Only from v2.** The list is the v2 snapshot's `states`, in its order.
  Nothing in the app types a list of states. A v1 file (California alone,
  from before states) offers none and says the data doesn't list its
  states yet.
- **Paused, never current.** Each row says what the agency publishes and
  "Read <date>", from `checks.last_success_at`. A state whose latest check
  failed and whose last good read is more than 7 days old says "Updates
  paused since <date>" with a warning mark, the site's rule from 0051. The
  same words show on the States sheet and in Browse's state menu. With the
  bundled data, Tennessee shows "Updates paused since Oct 15, 2026".
- **Existing installs.** `browse-state.json` written before this keeps its
  pick. An install that never picked (it saw California by default) now
  sees the list once and taps a state.
- **No location.** The picker doesn't ask for or use location, so the Play
  Data safety form and the iOS privacy label are unchanged (option C would
  have changed both).
- **iOS waits.** iOS is unchanged here. Its default (`AppEnvironment.swift`
  `state = "CA"`) and onboarding change after the App Review Board answers,
  in their own PR, with the same rules and words as `StateChoice.kt`.

## 0054 — Water pages answer the visit in the first screen (2026-11-05)

Measured 2026-11-05, read-only (GA4 property "Trout Truck", 28 days; Search
Console `sc-domain:trouttruck.com`, whose data starts 2026-10-14, to
2026-11-03): 164 sessions landed on a `/water/` page and 60 of them were
engaged, about two thirds of the site's 92 engaged landings. Most engaged
water landings viewed one page (1.0 views per session on la-mirada-lake,
santa-fe-reservoir, mather-lake). The 28 days had 4
`calendar_subscribe_click` and 1 `gear_click`, all on water pages. Water
pages got 30 of the site's 43 Search clicks and 1,020 of its 1,530
impressions. The subscribe link sat below the lede and, on a water with
nothing current, below the county lists.

- **One answer line.** The status block opens with one sentence under the
  badge: on the schedule this week (and the next listed week, if any); next
  on the schedule the week of X; or not on the schedule for this week or
  later yet, as of the last check, with the last listed week and how many
  days before that check it began. A water with no listed week says so in
  words. Nothing is a zero or a blank.
- **Subscribe in the first screen.** The calendar subscribe paragraph moves
  into the status block, right after the answer line. Its links, events and
  wording are unchanged.
- **Same-county links say where each water stands.** Each link in "Other
  X County waters on the schedule" ends with "scheduled this week", "next
  scheduled the week of X" or "last scheduled the week of X", and the list
  leads with this week's waters, then later weeks, then the rest by most
  recent week. A water with none of these keeps a bare link. The section
  still never says "nearby" (the snapshot has no locations for every water).
- **Lastmod.** Because every page now shows its siblings' weeks, a
  sibling's data change or rollover moves the page's sitemap lastmod, not
  only on a page with nothing current.
- **Unchanged.** URLs, titles, H1s and meta descriptions (the 10-30 title
  test is still being measured), the state (`/tn/water/` etc.) template, and
  the gear block.

## 0057 — Android About gets "Write to the developer"; alerts keep their one button (2026-11-06)

From the 2026-11-05 app parity audit (Trout Truck items 2 and 3; Chelsea
chose all recommended).

- **What.** About has a "Questions and corrections" section with one row,
  "Write to the developer". It opens the email app with a `mailto:` to
  chelsea@chelseakr.com (the address `/support/` shows) and a subject of
  "Trout Truck <version> for Android". The footnote shows the address, so it
  still works on a device with no email app. When the build carries no
  version, the subject leaves it out rather than showing a placeholder.
- **Nothing new is sent.** The app sends no email itself and makes no new
  network request. The Data safety answers are unchanged.
- **Notification actions: none added.** The audit said alerts had no action
  button. They already have one: "Mute this water" (`MuteReceiver`, since
  the first Android build), and tapping the alert opens the water. An extra
  "Open water" button would repeat the tap, so it isn't added.
- **iOS waits.** The same row comes to iOS after the App Review Board
  answers, in its own PR, with the same words (`FeedbackMail.swift`).

## 0060 — StoreKit tests fail fast instead of hanging (2026-11-06)

- **Problem.** `PurchaseManagerTests` hangs on `main`, not just on some
  feature branches. On the iOS 26.5 simulator (Xcode 26.6) the
  `SKTestSession` isn't connected (Apple bug 163377768, `ios/README.md`), so
  StoreKit answers from the real App Store sandbox. Only California's
  product loads, the first `purchase()` waits on a sign-in no one answers,
  and the run never ends. Measured three times on `main` at 3df4d6c: each
  run stuck on the first test and was killed at 15 minutes.
- **What.** Test code only; the app's `PurchaseManager` is unchanged. The
  tests wait for all 5 products in `Configuration.storekit` and stop in
  about 8 seconds, saying how many loaded, when any are missing. Every
  `purchase()` and `restorePurchases()` call in the tests has a 30-second
  deadline, so a call that hangs once the products do load still fails the
  test. Checked by loosening the product check by hand: the stuck purchase
  failed at 51 seconds instead of hanging.
- **Result on this simulator.** The class finishes red in about 105
  seconds (13 failures, 3 passes, three runs). That is the known Apple bug,
  not a regression. The tests still can't pass until a simulator runtime
  or device with Apple's fix is used.
- **Not done.** Turning on test timeouts in the shared scheme
  (`testTimeoutsEnabled`) had no effect from `xcodebuild` in a trial run,
  so it isn't included. The README's command-line flags are the backstop.


## 0061 — Tennessee: load TWRA's published download by hand while the automated read is refused (2026-11-07)

tn.gov has answered the pipeline's requests with HTTP 403 since 2026-10-15
(issue #97), so Tennessee's pages froze at that read. TWRA's communications
manager pointed Chelsea to the page's own download formats, and Chelsea told
TWRA that Trout Truck won't get around tn.gov's security settings.

- **No workaround of tn.gov's filter.** The automated fetch, its honest
  User-Agent and the strict robots.txt rule (0025) are unchanged. Nothing
  fetches tn.gov from a laptop, and nothing needs a laptop on daily.
- **Manual import of TWRA's published CSV.** Now and then Chelsea downloads
  the CSV from TWRA's page in a browser and runs `make import-tn-csv`
  (`cfpa.import_tn_csv`). Its eight columns and values are the ones the JSON
  reader reads, so the rows go through the reader's own `tn.parse_rows`: TBD
  months, week-of Sundays, verbatim month letters, skipped non-Sunday weeks
  and TWRA's spellings ("Caroll"). Any header drift is refused, as is an
  older or repeated file.
- **Provenance.** `tn.json` records the file (`checks.manual_file`: source
  "TWRA's downloadable CSV", page URL, file name, SHA-256, row count,
  download and import times); `last_success_at` is the download time. The
  snapshot's `source.read_method` is `manual`. Pages say "This data is from
  TWRA's published schedule file, downloaded <date>", and a water with no
  later date says nothing later was in that file, never "right now".
- **The daily read keeps failing honestly.** `checks.last_attempt_*` stay
  the automated read's own. A failed run changes only those and never
  relabels or replaces the imported data; the run log still warns. The first
  good automated read clears `manual_file`, and the pages go back to the
  automated wording.
- **Data lands by pull request.** The publish job is the only direct writer
  of `pipeline/data/`, so an imported `tn.json` goes to `main` in a PR.


## 0062 — The calendar box moves up to the status badge and adds Google Calendar (2026-11-07)

From the 2026-11-07 visitor-to-alert review
(`_agent-tools/growth/tt-visitor-to-alert-2026-11-07.md`, outside this repo).

- **Why.** In GA4's 28 days to 2026-11-07, every key event (4
  `calendar_subscribe_click`, 1 `gear_click`) came from an iOS visitor on a
  California water page. Android had 13 engaged sessions and no key event.
  On a phone-width render of the live site the subscribe link sat 1.2 to 1.6
  screens down, as one inline sentence after the lede, and its only
  subscribe link was `webcal://`, which Android does not open unless an
  extra app has claimed it (Google Calendar for Android does not).
- **What.** A California water page shows a calendar box right after the
  status badge, inside the status block and before its facts. It has two
  full-width buttons, each named for its calendar: "Apple Calendar (iPhone,
  iPad, Mac): subscribe" (`webcal://`, as before) and "Google Calendar (any
  phone or computer): add it"
  (`https://calendar.google.com/calendar/r?cid=<the webcal address>`, which
  adds the same feed as a subscription). Below them: the feed's https
  address for any other calendar app, the one-time `.ics` download, and the
  app line as before.
- **Plain about what it is.** The box says the calendar checks for changes
  on its own and that Google can take up to a day to show one. It does not
  call a calendar event an alert or a notification; the app line keeps that
  word for the app, which still reads "on its way" while APP_STORE_LIVE is
  off.
- **Measurement.** All three links keep `calendar_subscribe_click`, with
  `link_type` `webcal`, `google` or `ics`. The Google link's host is
  `calendar.google.com`; the privacy page names that host and says the feed
  address goes to Google when the visitor presses it. A click is a tap, not a
  confirmed subscription.
- **No "Android" in the copy.** The site names Android only on the privacy
  page until the app is on Google Play (`test_copy_never_mentions_android`),
  so the Google button says "any phone or computer". The support page's
  calendar answer is unchanged; it is also the FAQ structured data.
- **Not in this change.** Tennessee, Massachusetts, Michigan and New York
  water pages have no calendar feed at all, and county and home pages have
  no subscribe action. Those need their own feeds and their own decision.

## 0063 — A Massachusetts file that Hub marks stale is a failed check (2026-11-07)

From the 2026-11-07 freshness audit of every live state.

- **What we found.** ArcGIS Hub answers MassWildlife's download with
  `"cacheStatus": "stale"`. Its file was built 2026-10-13 02:35 UTC and has
  150 rows, the last dated 2026-10-09. Hub's metadata for the same layer
  says 155 records, last edited 2026-10-13 17:06 UTC. Every run since then
  read the old file and called the check good, so the Massachusetts pages
  said "That is what the agency's own data says, not a failed read."
- **The rule.** When Hub says Completed with `cacheStatus` "stale", the
  reader stops before the file and reports a failed check. The last good
  data is kept, and the state and water pages say the check failed, as they
  already do for any failed check. "ready" or no `cacheStatus` reads as
  before.
- **Not changed.** The route stays Hub only (0034). The layer's own host,
  services1.arcgis.com, still answers its robots.txt with 403 and is never
  read. Nothing asks Hub to rebuild the file.
- **Known gap.** The run of 2026-11-07 13:22 UTC already recorded a good
  check, so "last read" shows that time, not 2026-10-13. The pages also show
  "last changed the file Tue, 13 Oct 2026", which is the true age.


## 0064 — Calendar feeds on Tennessee water pages, honest about TWRA's three date shapes (2026-11-07)

From the 2026-11-07 visitor-to-alert review
(`_agent-tools/growth/tt-visitor-to-alert-2026-11-07.md`, outside this
repo): the other live states' water pages had 22 engaged sessions in 28 days
and nothing to press. Tennessee now has real future dates (0061, #159, #160:
689 rows in TWRA's 2027 file), so it goes first.

- **The same box.** A Tennessee water page shows the calendar box of 0062,
  the same partial after its lede: the Apple Calendar button (`webcal://`),
  the Google Calendar button (`calendar.google.com/calendar/r?cid=`), the
  feed's https address and the one-time `.ics`, each with
  `calendar_subscribe_click` and `link_type` `webcal`, `google` or `ics`.
  The partial takes the agency's name and its date words as variables that
  default to California's, so a California page renders byte for byte as
  before (checked by a build of both). `placement` is `state_water`, as the
  gear block on these pages already reports, so a report can tell the two
  page families apart. The privacy page's sentence about the Google link
  already covers it.
- **The feed, at `/tn/water/<slug>/feed.ics`.** Built by `cfpa.ics` from the
  v2 snapshot, with California's header: the same PRODID, `REFRESH-INTERVAL`
  and `X-PUBLISHED-TTL` of PT12H, and the same escaping. Only `listed`
  records become events; a date TWRA took off its schedule does not.
  - A **day** is one all-day event on that day, "<water> stocking scheduled
    (TWRA)".
  - A **week** ("week of" a Sunday) is one all-day event spanning TWRA's
    seven days, "Week of <Sunday>: <water> stocking scheduled (TWRA)". No
    day inside it is singled out; the description repeats TWRA's rule that
    the stocking falls within five days after that Sunday.
  - A **"TBD <month>"** is **no event**. TWRA set no day or week, and a
    month-long block or a guessed day would render that absence as a date.
    It is words instead: "TBD in December 2027 per TWRA: no day or week set
    yet" in the calendar's description and in the nearest dated event's.
  - **Month letters** ("M, A, M, J, J, A, S") are never events; the
    calendar's description says TWRA lists the water that way and that the
    letters are not dates. A water with letters only has a feed with no
    event and still shows the box, so a subscriber hears when TWRA sets a
    day.
  - Two species on one date are one event that names both. UIDs are
    `<water id>-<start>-<day|week>@ca-fish-planting-alerts.invalid`, pinned
    by test like California's.
- **Every event says what it is.** The description credits the Tennessee
  Wildlife Resources Agency, says the date is scheduled and not confirmed
  (TWRA's own caveat), says where the data came from at the pages' precision
  (0061: "from TWRA's published schedule file, downloaded <date>" after a
  hand load, else "read <date>"), says Trout Truck is independent, and ends
  with the water page's address, which is also the event's `URL`. No line a
  person reads calls an event an alert or a notification, or says "stocked"
  or "planted".
- **The rule is the state's semantics, not its code.** A `schedule` state
  other than California gets the box and the feed. Today that is Tennessee
  alone; Oregon, built behind an off flag (0032), would get one on the day
  it is turned on, with its Monday-to-Friday weeks as five-day events, since
  the event takes the agency's own period.
- **Massachusetts, Michigan and New York wait**, each for its own reason:
  - Massachusetts and Michigan publish **reports of stockings that
    happened**. Every date is in the past, so there is nothing to put on a
    calendar ahead of time; a feed of past days would read as a schedule and
    is not one. They would need a forward signal that does not exist in the
    data: at most a feed that adds a day after the agency reports it, which
    is a notice, not a calendar, and is better served by the app's alerts.
    That needs its own decision about what a past-only calendar means.
  - New York publishes a **once-a-year plan in its own words** ("April -
    third week", "Spring"), which the pipeline keeps as `approximate` with a
    bounding start and end. An event needs a start and an end a calendar can
    draw; drawing the bounds would show a precision NYS DEC did not give
    (0034's rule). It would need a rule for how an approximate period is
    drawn, if at all, and words that say the span is the site's reading of
    the plan, not the plan.
- **Not shared yet.** `cfpa.ics` carries its own copies of the escaping,
  folding and refresh interval that `site.build_water_ics` has, held equal
  by test, so the open California water-page pull requests (#146, #148)
  merge clean; `site.py` switches to the shared helpers after they land.
  The shared fold also keeps a continuation line within 75 octets (its
  leading space counted) and never splits a multi-byte character, which
  `site._ics_fold` does not; California's lines are short, so no feed of
  hers has hit either.
- **Overlaps.** #150 (0056) rewrites `_render_water` in `site_states.py`
  and the top of the state water template; this change adds a kwarg and a
  feed write in the same function, and the box after the lede, which lands
  below 0056's answer line. #160 changes only `pipeline/data/states/tn.json`;
  the feeds are built from whatever that file holds, so no code here depends
  on it.
- **Measurement.** 28 days after deploy: `calendar_subscribe_click` with
  `placement` `state_water` against engaged Tennessee water landings (22 in
  the 28 days before, with nothing to press), and the share of Google taps,
  once `link_type` and `placement` are GA4 custom dimensions (owner step in
  the review).

## 0065 — A stuck state is a red job on main, not a warning and not an issue (2026-11-07)

From the 2026-11-07 freshness audit
(`_agent-tools/growth/freshness-audit-2026-11-07.md`, outside this repo).

- **Problem.** tn.gov began refusing the runner's robots.txt request on
  2026-10-15. For 23 days every publish run kept Tennessee's last good
  data, printed one `::warning` and finished green, by design (0025: a
  failing state stops nothing). The daily health check
  (`publish-health.yml`, since 10-21) did see it: it opened #104 on 10-22
  and commented on it every day since, sixteen times, and its own run was
  green every day too, because an unhealthy reading becomes an issue
  comment, not a failed job. Nobody read the issue. Massachusetts was a
  second silent case of another kind: Hub served a file it had itself
  marked stale and the reader counted it a good read; that is fixed at the
  reader (0063), and this check cannot see it.
- **Decision.** The publish workflow gets a third job, `freshness`, after
  the build job. It reads the history files the build just committed
  (`pipeline/src/cfpa/freshness.py`, `make freshness`) and fails when any
  live state's last SUCCESSFUL read is older than its allowance. The job's
  red is the publish run's red on main, which is the signal that gets seen.
  It opens no issue, and agents must not open one for it.
- **Its own job, not a step in the build.** A failing step in `build` would
  stop the data commit and the deploy, so one stuck agency would freeze
  California and every other state. The `freshness` job `needs: build`,
  runs whenever the build was not cancelled, and nothing waits on it:
  `deploy` needs `build` alone, and `alert-on-failure` watches `build` and
  `deploy` alone. It checks out `main` as it is at that moment, so it reads
  the files the build pushed, not the tip from before the run. About one
  billed minute per run on a public repository, so none.
- **What it measures.** The age of `checks.last_success_at`, never the
  newest record: Michigan's DNR files a stocking days after it happens, and
  New York's plan is one spring publication; neither says anything about
  whether the read still works. Default allowance 7 days, which is fourteen
  refused reads at two runs a day; a state module may declare its own
  (`StateSource.max_read_age_days`), and none does today. A manual import
  (0061, `checks.manual_file`) is a good read as of its `downloaded_at`,
  read from the file's own JSON so it holds whether or not the import's
  code has landed; the later of the automated and the manual read counts.
  A state behind an off flag (Oregon, 0032) is not live and is not checked;
  naming one on the command line while its flag is off is an error, not a
  pass. Older than the allowance is stuck; equal is not.
- **Absence is a failure.** A missing history file, a file for the wrong
  state, no `checks`, no good read on record, a time that will not parse, a
  time with no zone, or a time more than an hour later than the job's clock
  each fail with a line that says which. Zero states to check is a usage
  error, because it would pass by checking nothing.
- **Output.** One line per state, the same words in the run log, in the job
  summary's table (state, last good read and how, age in days, allowance,
  result) and in the `::error` annotation on a stuck state. Today's:
  `TN (Tennessee): STUCK: last good read 2026-10-15 13:31Z (automated),
  23.4 days ago, allowed 7 days; older than allowed`; Michigan,
  Massachusetts and New York fresh at 0.4 days.
- **Not part of `make verify`.** The watchdog measures the agencies' feeds,
  not this code; in `verify` a stuck feed would block every merge, a gate
  that measures the world. `publish-health.yml` stays as it is: it reads
  the live site and also covers a run that never happened or never
  deployed, which this job cannot see. Its issue is not the signal.
- **What to expect.** Tennessee stays red here until 0061's import lands
  (its download time becomes the last good read) or tn.gov answers the
  runner again. Massachusetts has failed its Hub check since the 2026-11-08
  01:18 run (0063); its last good read is still the false one from
  2026-11-07 13:22, so it goes red here about 2026-11-14 unless Hub
  rebuilds its file first. That false read is the known gap: this check
  cannot see a read that was wrong when it was made.


## 0069 — A free web push test: one water per browser, on California and Tennessee water pages, for 60 days (2026-11-08)

From the 2026-11-08 idea lane
(`_agent-tools/growth/idea3-web-push-alerts-2026-11-08.md`, outside this
repo), its Top 1. Chelsea's explicit yes on 2026-11-08 overrides, for this
test only, the roadmap's "no server, no push" line (roadmap §10, and 0001's
"not server push"): the website gets a push subscription store and a sender.
The apps are unchanged: still local notifications, no APNs, no device token,
"Data Not Collected". No paid tier is in this change; the paid step is a
later decision, gated on the read below.

- **What.** The calendar box of a California or Tennessee water page (0062,
  0064: the pages with a calendar feed) has a third option under its two
  calendar buttons: "Or get a notification in this browser when CDFW adds,
  moves or drops a date for Shadow Cliff Lake. One water per browser; free;
  no account or email address." and a button, **"Alert me about this
  water"**. Allowing it subscribes the browser to web push for that one
  water. Massachusetts, Michigan and New York pages get nothing, for the
  reasons 0064 gives: nothing forward to say.
- **Where, and why there.** Inside the existing calendar box, after the
  Apple and Google buttons and before the fine print, not as a box of its
  own. 0062 moved the calendar box to the status badge so the way to hear
  about the next week is on a phone's first screen; a second box there would
  split that screen and compete with the calendar, which is the path that
  works on every device without a permission prompt. Third in the box, it
  is seen by the people who read the box and never above the calendar. The
  button reuses the calendar buttons' style; it is a real `<button>`, since
  it changes a setting in this browser and goes nowhere.
- **When a message goes.** After each publish, `cfpa.push` compares the
  snapshot that was live (fetched before the deploy replaces it) with the
  one just built, water by water, on exactly the records the water's
  calendar feed carries: `listed` plants with a `day` or `week` period,
  this week or later. A new one, a dropped one or a moved one is one message
  per water; a TBD month, a month letter, a withdrawn record, a past week's
  correction, a water new to or gone from the snapshot (0017), and a cold
  start with no previous snapshot are never a message. Push services hold a
  message three days for an offline browser (TTL), then drop it: a week-old
  "scheduled" would read wrong.
- **What a message says.** The pages' own words, never more. New: "Shadow
  Cliff Lake: scheduled, week of Nov 15" / "CDFW lists Shadow Cliff Lake for
  planting the week of Sunday, November 15, 2026. Scheduled, not confirmed:
  CDFW's plans can change." Dropped: "Shadow Cliff Lake: schedule changed" /
  "CDFW took the week of ... off its planting schedule. CDFW's plans can
  change." Moved: "CDFW moved Shadow Cliff Lake from the week of ... to the
  week of ...". Tennessee names TWRA's species and carries TWRA's two
  sentences from the feed (the five-day rule for a week-of date; "any
  stocking could be postponed or cancelled"). Never "stocked", never
  "planted on", never a superlative, and the message never calls itself an
  alert or a guarantee (`test_push_events.py`). It links the water page
  with `utm_source=web-push&utm_medium=push`.
- **The service.** The site stays static. One Lambda behind a function URL,
  one DynamoDB table and four SSM parameters, in Trout Truck's own AWS
  member account (trouttruck, 266294231534), written as Terraform under
  `infra/web-push` with the `allowed_account_ids` guard Lot Code Log's
  waitlist uses. Not applied by an agent: the owner steps are in
  `infra/web-push/README.md`. A row per browser, keyed by the SHA-256 of
  the endpoint, holds the water, the endpoint, its two keys, created_at,
  last_sent_at (absent until a first send) and expires_at; one row holds
  the totals. The publish workflow's send step calls the service with a
  bearer token; the service fans each message out to that water's
  subscribers with the `web-push` library Family Greenhouse uses, deletes
  an endpoint that answers 404 or 410, and refreshes expires_at on a
  success, so DynamoDB's TTL drops a browser nothing could reach for about
  13 months. The endpoint host must be a browser push service's (ported
  from Family Greenhouse's `pushEndpoint.ts`); a message's link must be a
  page of this site, checked by the service and again by the worker.
- **One water per browser** is the table's key: a second water from the
  same browser replaces the first (the page says so before the tap and
  counts it as a switch). A browser that rotates its subscription renews
  under the old endpoint's water (`pushsubscriptionchange`).
- **iPhone and iPad.** In a Safari tab there is no Push API; a site must be
  added to the Home Screen first (iOS 16.4 and later), and before iOS 26 it
  opens as a web app only with a manifest that says `display: standalone`.
  So: the build gets a `manifest.webmanifest` (name, display, scope; no
  start_url, so the page a person adds is the page that opens; nothing
  more, no icon yet) linked from every head; the page script shows the
  two-step instruction instead of a button on an iPhone or iPad that is
  not a web app, and the button inside the web app. 71% of engaged sessions
  are iOS (the lane's measurement), so how many finish that step is the
  number this test exists to learn.
- **Honesty and privacy.** The privacy page gains "Web push notifications":
  the service's address, what is stored (the endpoint, the two keys, the
  water, the two timestamps), where (the site's own AWS account, in the
  United States), that the request carries an IP address the service does
  not keep (its logs hold a route, a status and counts), what a message
  is, how to stop (the "Stop these notifications" control on the page, or
  the browser's own setting; a dead endpoint is deleted on its next
  failure), the 13-month expiry, and that the button press is a GA4
  `calendar_subscribe_click` of `link_type` `push`. The page never says
  "no tracking". With no push config, the privacy page is as before.
- **Named for the secret scan.** The public key sits in every water page and
  the worker, and the publish job runs `gitleaks dir site` before it deploys.
  An attribute or variable with "key" or "api" in its name ("vapid" counts),
  next to that value, is a finding and fails the run, so they are
  `data-push-public` and `SERVER_PUBLIC` (`test_site_push.py` scans a build,
  with a control that the old name fails).
- **Off by default, byte for byte.** `PUSH_API_URL` and
  `PUSH_VAPID_PUBLIC_KEY`, both public, both repository variables, turn it
  on together; one without the other refuses the run like a malformed GA4
  id. Unset, the build writes no script, no worker, no manifest and no
  control. Turning the test off is deleting the two variables.
- **Measurement.** GA4: `calendar_subscribe_click` with `link_type` `push`
  (a tap, not a subscription; the button has no host, so `link_host` is left
  out rather than sent empty). The service's totals: subscribes, switches,
  renewals, unsubscribes, send runs, sends, failures, dead endpoints
  removed, and the live subscription count; `tools/web-push/counts.sh`
  prints them. Visits from a message land with `utm_medium=push`.
- **The 60-day read**, on the day the control has been live 60 days: (1)
  live subscriptions (the count, not the sign-ups); (2) subscribes per 100
  engaged sessions = subscribes / GA4 engaged sessions on California and
  Tennessee water pages over the same 60 days x 100; (3) whether any iOS
  completion happened at all (`live_apple`, the subscriptions on
  `web.push.apple.com`; a Mac's Safari counts there too, so it is a ceiling). **Kill rule:** under 25 live
  subscriptions, or under 1 subscribe per 100 engaged sessions, at day 60
  means the control, the worker, the manifest and the privacy section go
  (delete the two variables, then remove the code and `terraform destroy`).
  **Pass** is 25 or more live and 1% or more; only then is a paid step
  (the lane's 7.1: one $9.99/yr plan on a Payment Link, first water free)
  put to Chelsea as its own decision. If a paid step ever follows, under 10
  paid in its first 90 days stops selling and keeps the free water.
- **Known limits.** A message is sent once: if the send step fails, that
  run's changes are not retried, and the step's error is the only sign (the
  deploy never waits on it). The function URL has no rate limit, so a script
  could inflate the subscribe count with made-up endpoint paths; a live count
  that looks wrong should be checked against GA4's taps before it passes the
  kill rule. A failed send to one browser is counted, not retried.
- **The app's story.** 0009's reason for the paid unlock was that a website
  cannot push to a phone. With this control on, it can, for one water, after
  a Home Screen install. The lane rates that neutral for 4.3(a) and a small
  negative for 4.2 while the appeal is open. Nothing here turns it on: when
  to set the two variables is Chelsea's call.
- **Not in this change.** No paid tier. No push for Massachusetts, Michigan
  or New York. No notification icon or Home Screen icon (the design
  identity work, #151, owns the mark). No support-page FAQ entry. No change
  to the apps or to the App Store copy, which is frozen during the appeal.
  No server-side knowledge of which waters exist: a subscription to an id
  that never changes simply never fires. No second water per browser.
- **Overlaps with the open date-gated pull requests.** `base.html.jinja`
  (#144 edits the header, #151 adds a favicon line; this adds a manifest
  line near the top of head), `privacy.html.jinja` (#144 and #146 edit
  other paragraphs; this adds one self-contained section and two guarded
  clauses), `_ga4.html.jinja` (#146 restructures the same click handler
  into a `params` object as this does, and adds a third event; the merge
  will need a hand), `style.css` (#148, #151; this appends to the calendar
  section), `site.py` (#144, #146, #148; this adds a parameter, a context
  key and one function), `site_states.py` (#150 rewrites `_render_water`;
  this adds one kwarg to it), `water.html.jinja` and
  `_water_status.html.jinja` are untouched here. The new files
  (`cfpa/push.py`, `_push_subscribe.html.jinja`, `push.js`,
  `push-worker.js.jinja`, `manifest.webmanifest.jinja`, `infra/web-push`,
  `tools/web-push`) overlap nothing.
