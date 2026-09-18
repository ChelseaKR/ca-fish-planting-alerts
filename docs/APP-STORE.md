# App Store listing (draft) and TestFlight path

Status: draft, unsubmitted. This session (like the one that wrote the
original draft below) has `xcodebuild` and simulator access only — no
App Store Connect access, no Apple Developer portal access, and no
interactive Apple ID sign-in — and submits and registers nothing (per
the task boundary). Everything below is prepared for Chelsea to execute.

**2026-09-14 follow-up pass.** Re-verified against `origin/main` after
PR #1 (pipeline/site) and PR #2 (iOS app) merged: the app icon gap this
doc originally flagged is closed (`0be59fd`, before this pass started —
see "App icon" under Known gaps), `xcodebuild ... -destination
'generic/platform=iOS Simulator' build` still succeeds clean (zero
warnings) from a fresh worktree, and `swift test` in `ios/PlantingCore`
still passes 38/38, and a universal-links/`.well-known` section and a
screenshots plan are added below since the task that produced this doc
didn't cover either. Nothing else in the listing draft, review-clause
analysis, or owner steps needed correction.

## Listing draft

| Field | Value | Notes |
|---|---|---|
| Name | **Trout Truck** — `docs/DECISIONS.md` 0010 (settles 0006) | `CFBundleDisplayName` in `ios/CAFishPlanting/Resources/Info.plist` is "Trout Truck". The bundle ID, product ID, scheme and target names keep `CAFishPlanting`. No trademark search has been run yet. |
| Subtitle | See `docs/APP-STORE-LISTING.md` | The earlier draft, "Trout stocking alerts for California", is **36** characters, over the 30-character limit (it was miscounted as 29). The paste-ready replacement, with measured counts, is in `APP-STORE-LISTING.md`. |
| Description | See draft below. | States the weekly cadence and local-only alerts in the first two sentences, per the task's plain-statement requirement. |
| Keywords | See `docs/APP-STORE-LISTING.md` | The earlier list repeated subtitle words, which Apple already indexes. The replacement is 96/100 characters. No brand terms beyond CDFW's own program name (a factual reference, not a trademark claim). |
| Category (primary) | **Sports** | See justification below. |
| Category (secondary) | Reference (was: Weather) | The app has no weather content, and guideline 2.3.5 asks for the most appropriate category. A schedule-and-history lookup is Reference. See `APP-STORE-LISTING.md`. |
| Age rating | **4+** | No objectionable content categories apply (no UGC, no gambling, no mature themes, no web browser). Apple's questionnaire should be answered "None" throughout. |
| Price | **Free to download; $9.99 one-time in-app purchase, no subscription** | `docs/DECISIONS.md` 0003/0007: the app itself is free (App Store Connect price tier "Free"); the $9.99 is the one-time non-consumable in-app purchase implemented in `ios/` (`PurchaseManager.swift`). See "In-App Purchase to create in App Store Connect" below for the exact product to configure. |
| Privacy label | **Data Not Collected** | Matches `ios/CAFishPlanting/Resources/PrivacyInfo.xcprivacy` (`NSPrivacyCollectedDataTypes` is empty) and `docs/DECISIONS.md` 0002 ("posture: none"). Fill in the App Store Connect privacy questionnaire identically: every category "Data Not Collected." |

### Description draft

> **New this week's stocking schedule, without checking CDFW by hand.**
> This app checks California's official trout stocking schedule roughly
> once a day and tells you — with a notification on your phone, nothing
> else — when a water you've favourited appears in that week's list. The
> schedule itself only updates about once a week, so an alert can arrive
> within days of a new listing, not the minute it's posted; iOS also
> decides exactly when background checks run, so timing is never
> instant. There is no account, no server, and no push notification
> service behind this — every alert is scheduled on your own phone from
> a file the app downloads itself.
>
> Every water also has a history: every week California's Department of
> Fish and Wildlife (CDFW) has listed it, going back as far as this app
> has been tracking, with species and the most recent listed week shown
> up front. CDFW publishes only the week a plant is scheduled, not the
> day, and plans can change — this app always says "scheduled for the
> week of…", never "stocked on."
>
> No account. No ads. No analytics. No tracking. One data source,
> credited on every screen that uses it: the California Department of
> Fish and Wildlife's Fish Planting Schedule.

## Category justification (2.3.1 / metadata accuracy)

**Primary: Sports.** The app exists for anglers deciding where and when
to fish; that is the entire feature set (favourite waters, stocking
history, alerts tied to a fishing activity). Apple's own examples of
Sports-category apps include league/team/activity trackers for a specific
sport — trout stocking is the same shape, one level more specific.
**Not News**: the app carries no editorial content, only a structured
schedule. **Not Weather**: nothing here is a forecast; it is a
government schedule of a human activity. Weather is offered only as
a secondary category because the alert *mechanism* (a periodic,
best-effort, locally-scheduled check) most resembles what a weather app
does with a forecast API, which may help discovery without misdescribing
the app.

## Review clauses that apply

- **5.1.1 (Data Collection and Storage) — no login required.** The app
  has no account system anywhere (`docs/DECISIONS.md` 0001/0002); nothing
  in `ios/` calls any authentication API. Nothing to configure for this
  clause; call it out in the App Review notes so a reviewer isn't left
  looking for a sign-in screen that doesn't exist.
- **4.2 (Minimum Functionality) — the history is the substance.** A
  guideline-4.2 rejection risk for a "thin wrapper around a public
  webpage" is real for this shape of app. The rebuttal, to state in App
  Review notes: this app is not a live view of CDFW's page — it is a
  **kept history** CDFW itself does not publish (CDFW shows only the
  current window; `docs/DECISIONS.md` 0005: "The pipeline never
  overwrites history... this is the asset"). The per-water history table,
  the offline-first snapshot, favourites, and device-local alerting are
  all functionality beyond "a webview of a government page." Screenshot
  the water detail history table prominently in the review notes and the
  listing itself.
- **2.5.4 (Background Modes) — justified by the feature.** `UIBackgroundModes`
  declares `fetch` and `processing` (`ios/CAFishPlanting/Resources/Info.plist`)
  solely to run one `BGAppRefreshTask` (`ios/CAFishPlanting/App/BackgroundRefresh.swift`)
  that performs the app's single network operation (one GET of the
  snapshot, `ios/PlantingCore/Sources/PlantingCore/SnapshotRefresher.swift`)
  and, if a favourite has a new listing, schedules a local notification.
  No audio, VoIP, location, or Bluetooth background mode is declared —
  only the two needed for `BGTaskScheduler`. State this directly in the
  review notes, since "why does a fish-schedule app run in the
  background" is a fair reviewer question and the honest answer (weekly
  source, local alerts, no server push) is also the selling point.
- **3.1.1 / payment model.** DECISIONS 0007 (superseding 0003's "no
  StoreKit" line) implements the one-time purchase as a StoreKit 2
  non-consumable in-app purchase — this *is* a real digital unlock inside
  the app, so it correctly goes through Apple's in-app purchase system
  rather than any external payment link (which 3.1.1 would reject). No
  entitlements/capability toggle is needed in Xcode for non-consumable
  IAP — unlike Push or HealthKit, it is available to every app by default.

## In-App Purchase to create in App Store Connect

The app ships free; `ios/CAFishPlanting/App/PurchaseManager.swift` looks up
exactly one product. Nothing will load until this exists in App Store
Connect with this exact identifier:

| Field | Value |
|---|---|
| Type | **Non-Consumable** |
| Product ID | `com.chelseakr.cafishplanting.fullaccess` — must match `PurchaseManager.productID` exactly, byte-for-byte |
| Reference Name (internal, App Store Connect only) | `Full Access` |
| Price tier | $9.99 (USD Tier matching $9.99; DECISIONS 0003/0007) |
| Display Name (customer-facing) | `Full Access` |
| Description (customer-facing, 45 max) | `Alerts when a favourite water is listed` (39 characters) |
| Cleared for sale | Yes, once the app record itself is created |
| Review screenshot | A screenshot of the in-app purchase sheet (`PurchaseView` — reachable from About > "Unlock full access" only; there is no other trigger) is required by App Store Connect for the IAP's own review |

App-side, what it unlocks is decided (DECISIONS 0009, resolving 0007's
"owner follow-up"): favouriting and browsing are free and unconstrained for
everyone, matching the free website. Purchasing unlocks **local
notifications** — a notification on this device whenever a favourited
water's planting schedule changes. Without the purchase, favouriting still
works in full; no local notification is ever scheduled for any favourited
water. See `PlantingCore/Sources/PlantingCore/FreeTier.swift`
(`notificationsAllowed(isEntitled:)`) and
`ios/CAFishPlanting/App/AppEnvironment.swift`'s `performBackgroundRefresh()`,
which is the one call site that checks it before
`NotificationScheduler.schedule(_:)`.

### Local testing without an App Store Connect product

`ios/CAFishPlanting/Configuration.storekit` is a local StoreKit testing
configuration already carrying this exact product (same ID, $9.99, same
description) — no App Store Connect access is needed to exercise the full
purchase/restore/entitlement flow:

- **Automated tests** (`ios/CAFishPlantingTests/PurchaseManagerTests.swift`)
  drive it directly via `StoreKitTest.SKTestSession(contentsOf:)` — this is
  what `xcodebuild test` already runs; see "Owner steps" step 2.
- **Manual testing in Simulator**: the scheme (`CAFishPlanting.xcscheme`)
  already references `Configuration.storekit` for both Run and Test, so
  building and running the app in Xcode/Simulator gets a working local
  App Store — purchase, cancel, and Manage StoreKit Transactions
  (Xcode's Debug menu, while the app is running) are all live immediately,
  no signing-in required.
- This file is intentionally **not** part of the app's Resources/Copy
  Bundle build phase — it must never ship inside the real app bundle;
  Xcode reads it straight from the project during local development only.

## Universal links / `.well-known` — not needed, and none is present

Checked (2026-09-14): there is no `ios/CAFishPlanting.xcodeproj` entitlements
file at all (`git ls-tree -r origin/main -- ios/ | grep -i entitlement` is
empty), no `Associated Domains` capability, and no `.well-known/`
directory anywhere in this repo (`site/` included). That's correct, not
missing:

- The app has exactly one outbound web link pattern — `Link` views to
  `water.cdfwMapURL` (CDFW's own page) and, when the snapshot supplies
  one, `SnapshotEndpoint.siteWaterURL(slug:)` (this repo's own static
  site) — both opened in the system browser via a plain `URL`, not a
  custom scheme or a universal link. Tapping either never needs to route
  back *into* the app.
- Nothing in `site/` links to `cafishplanting://` or any
  `applinks:`-style URL that would need an `apple-app-site-association`
  file to resolve into the app. The site and the app are two independent
  surfaces (DECISIONS 0001: "the site is the discovery surface... the
  app is the product") that share a data snapshot, not a navigation path.
- Every alert is a local notification (`NotificationScheduler.swift`)
  scheduled by `BGAppRefreshTask`; tapping one opens the app directly
  through the standard `UNUserNotificationCenter` delegate, which needs
  no associated domain either.

Conclusion: this is a fully standalone, notification-only app. Add
`Associated Domains` and an `apple-app-site-association` file only if a
future decision makes the site deep-link into specific app screens
(e.g. "Add to Favourites" from a site water page) — there's no such
feature today, so building the infrastructure now would be unused
surface area with its own review and hosting requirements.

## Screenshots plan

Not yet captured. App Store Connect requires at least one 6.9" (or
6.5"/6.7") iPhone screenshot set before a listing can be submitted, even
for TestFlight-only builds heading toward review. Capture from a real
simulator run against the bundled snapshot — `ios/README.md` confirms
`CAFishPlanting/Resources/snapshot.json` is real CDFW pipeline output
(385 waters, real "week of 2026-09-13" data), not a hand-built fixture —
so no seeding or synthetic data is needed first; just favourite a couple
of real waters that actually appear in the current snapshot before
shooting.

Suggested order (matches the description draft's own emphasis and the
4.2 rebuttal above, which leans on the history view being the
substance):

1. **Waters / Browse** (`BrowseView`) — the region picker and the "this
   week" freshness row visible, ideally with the search bar showing a
   real county or water name. Establishes the full catalogue and the
   weekly-cadence framing from screenshot one.
2. **Water detail — stocking history** (`WaterDetailView`) — a water
   with a real, non-trivial history (more than one or two rows), the
   "Species seen" line populated, and the CDFW/site links visible. This
   is the single most important screenshot for the 4.2 argument: it's
   the thing CDFW's own page doesn't show.
3. **Favourites** (`FavoritesView`) — at least two favourited waters, one
   of which ideally appears in `thisWeek` so the "new this week" state is
   visible, not an empty-favourites placeholder.
4. **About / privacy** (`AboutView`) — the "Privacy" and "How alerts
   work" sections, both fully visible in one frame. Doubles as evidence
   for the "Data Not Collected" privacy label and the 2.5.4 background-
   modes explanation — a reviewer or a sceptical user can see the claim
   and the UI agree.

Avoid: any screen captured mid-load (`SnapshotUnavailableView`'s "No
stocking schedule is available yet." state), the search field showing a
query with zero results, or a freshly-installed/no-favourites state for
anything other than screenshot one if a "getting started" shot is
wanted separately. None of those represent what a real user sees after
using the app for a week, and a reviewer comparing the screenshots to a
fresh install will notice if the "history" screenshot shows one row.

## Owner steps to a TestFlight build

Commands, run from `ios/`, in order. Each `xcodebuild archive`/`gh` step
that touches App Store Connect needs Chelsea's own Apple ID session in
Xcode and is outside this session's access.

```sh
# 1. Confirm the app's own identity is final (name, bundle id, version)
#    before archiving — MARKETING_VERSION / CURRENT_PROJECT_VERSION live in
#    ios/CAFishPlanting.xcodeproj/project.pbxproj build settings.
#    CFBundleDisplayName lives in ios/CAFishPlanting/Resources/Info.plist.

# 2. Run the full local check one more time. This exercises the StoreKit
#    purchase/restore/entitlement flow for real, against the local
#    Configuration.storekit file — see "In-App Purchase to create in App
#    Store Connect" below. No App Store Connect access needed for this step.
cd ios
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -destination 'platform=iOS Simulator,name=iPhone 17' clean build test

# 3. Sign in to Xcode with the Apple ID for Team 6X5YH93QNM
#    (Xcode > Settings > Accounts) — interactive, cannot be scripted here.
#    project.pbxproj already sets DEVELOPMENT_TEAM = 6X5YH93QNM and
#    PRODUCT_BUNDLE_IDENTIFIER = com.chelseakr.cafishplanting with
#    CODE_SIGN_STYLE = Automatic, so once this Apple ID is signed in,
#    Xcode should register/reuse the App ID itself on the next archive —
#    but that registration cannot be confirmed from this session (no
#    Apple Developer portal access); verify it actually succeeded
#    (Xcode > Settings > Accounts > [team] > "Manage Certificates", or
#    the Signing & Capabilities tab showing no red error) before step 5.

# 4. Archive for release.
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath build/CAFishPlanting.xcarchive archive

# 5. Export an App Store-signed .ipa. Requires an ExportOptions.plist
#    (teamID 6X5YH93QNM, method app-store-connect) — not included in this
#    repo; create it alongside build/ (it contains no secret, but keep it
#    out of git since it's a local export artifact, not app source).
xcodebuild -exportArchive \
  -archivePath build/CAFishPlanting.xcarchive \
  -exportOptionsPlist build/ExportOptions.plist \
  -exportPath build/export

# 6. Upload to App Store Connect (needs an app-specific password or API key
#    Chelsea generates in App Store Connect — interactive/credentialed,
#    not available to this session).
xcrun altool --upload-app -f build/export/CAFishPlanting.ipa \
  -t ios -u "<APPLE_ID_EMAIL>" -p "<APP_SPECIFIC_PASSWORD>"

# 7. In App Store Connect: create the app record (bundle id
#    com.chelseakr.cafishplanting, price tier Free), create the
#    in-app purchase from the table in "In-App Purchase to create in App
#    Store Connect" above, fill in the listing fields from the table at
#    the top of this doc, complete the privacy questionnaire as "Data Not
#    Collected" for every category, attach the build from step 6 to a
#    TestFlight group, upload the screenshots plan's captures, and submit
#    for TestFlight review (a lighter review than full App Store review,
#    but still Apple's, not this session's).
#    Note: TestFlight does not require the in-app purchase to be
#    "Ready to Submit" first, but full App Store review does — create and
#    fill in the IAP well before submitting for real review.
```

## Known gaps to close before any of the above

1. ~~No app icon~~ **Closed 2026-09-14** (was open when this doc was
   first drafted). `0be59fd` wired a full `AppIcon.appiconset` (all
   required iPhone sizes plus the 1024×1024 marketing image) and set
   `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon` in `project.pbxproj`.
   It's a real, presentable vector-style icon (a golden trout over
   rippling water on a green gradient) — but per the task boundary that
   produced it, it's a **placeholder graphic**, not commissioned final
   art; confirm it's the icon Chelsea wants to ship before archiving, or
   swap `icon-*.png`/`icon-1024.png` in the same asset set for a final
   version (no build-setting changes needed either way).
2. **The in-app purchase does not exist in App Store Connect yet** —
   `ios/` now has a complete, tested StoreKit 2 purchase mechanism
   (DECISIONS 0007), but `Product.products(for:)` will return nothing
   until Chelsea creates the exact product in "In-App Purchase to create
   in App Store Connect" above. Until then the purchase button in the app
   will show "Not available right now" against the real App Store (it
   already works today against the local `Configuration.storekit`).
3. ~~Name and domain undecided~~ **Closed 2026-09-17** (DECISIONS 0010).
   The name is Trout Truck (`CFBundleDisplayName` and the share-sheet
   text), and the site stays on `github.io`. Still open: a trademark
   search before submitting.
4. **App ID registration status unverified.** `project.pbxproj` already
   declares `DEVELOPMENT_TEAM = 6X5YH93QNM` (the same Apple Developer
   Program team as family-greenhouse) and
   `PRODUCT_BUNDLE_IDENTIFIER = com.chelseakr.cafishplanting` with
   `CODE_SIGN_STYLE = Automatic` — so the *project* already knows which
   team and bundle ID to use. Whether that specific App ID
   (`com.chelseakr.cafishplanting`) is actually registered under that
   team in the Apple Developer portal cannot be checked from this
   session (no portal access, no interactive Apple ID sign-in — see the
   task boundary at the top of this doc). With Automatic signing, Xcode
   normally registers a new App ID itself the first time it archives or
   builds for a real device once Chelsea is signed in, so this is likely
   a non-issue — but it's unverified, not confirmed, and is the one
   step in "Owner steps" (step 3) worth watching for a signing error
   rather than assuming success.
5. **No screenshots captured yet** — see "Screenshots plan" above; none
   of the required App Store Connect image sizes exist in this repo or
   elsewhere in this session's outputs.
6. ~~The free/paid feature split is a placeholder~~ **Closed 2026-09-17**
   (DECISIONS 0009). Favouriting and browsing are free and unconstrained
   for everyone; the purchase unlocks local notifications on a favourited
   water's schedule change. See
   `PlantingCore/Sources/PlantingCore/FreeTier.swift`.
