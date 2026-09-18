# Decisions

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
- **Global Privacy Control and Do Not Track are honoured.** When
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

The paid-app-price-tier route is dropped in favour of **StoreKit 2**: a
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
gates a clearly-labelled placeholder — a cap on how many waters a
non-purchaser may favourite — so the StoreKit mechanism itself is complete
and real without inventing product scope that is Chelsea's call. Owner
follow-up: decide the real free/paid split and repoint `FreeTier` (or
delete it in favour of whatever the real gate turns out to be).

## 0004 — Licence before bytes (2026-09-13)

CDFW's terms are quoted verbatim in `docs/LICENSES-AND-ATTRIBUTION.md` before
any fetch, with the attribution the app and site must show. Unknown = not used.

## 0005 — The history is the asset (2026-09-13)

CDFW publishes the current week only. Keeping every week, forever, per water,
is what no one else offers and what makes "when was X last planted" answerable.
The pipeline never overwrites history; a stale or failed fetch never becomes a
"no plants this week" fact.

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

## 0007 — Zero parsed rows is a valid empty week, not a parse error (2026-09-14)

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
