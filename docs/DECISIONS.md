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
- **Trademarks were not searched.** No USPTO or state trademark search has
  been done. Run one before the App Store submission and before buying a
  domain.
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
