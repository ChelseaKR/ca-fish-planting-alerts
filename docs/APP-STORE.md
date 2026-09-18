# App Store listing (draft) and TestFlight path

**2026-09-18 submission pass.** Everything an agent can do before
submission is done: the screenshots are captured from real snapshot data
(see [Screenshots](#screenshots)), the privacy answers are checked against
the code (see [Privacy answers, verified in code](#privacy-answers-verified-in-code)),
the App Review notes are in `docs/APP-STORE-LISTING.md`, and the rest is
the owner's, in order, in
[Owner checklist: from here to submitted](#owner-checklist-from-here-to-submitted).
The sections after the checklist are the earlier drafts, kept for their
reasoning.

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

## Owner checklist: from here to submitted

Every step below needs the owner's Apple ID, App Store Connect, a
payment or legal form, or a decision. Nothing here has been done. Values
in `code` are exact; paste them as they are.

**Values this checklist uses**

| Field | Value | Source |
|---|---|---|
| App name | `Trout Truck` | DECISIONS 0010; `CFBundleDisplayName` |
| Bundle ID | `com.chelseakr.cafishplanting` | `PRODUCT_BUNDLE_IDENTIFIER` in `ios/CAFishPlanting.xcodeproj/project.pbxproj` |
| Team ID | `6X5YH93QNM` | `DEVELOPMENT_TEAM` in the same file. Not `ACKGM9XK9V`, which is the enrollment ID. |
| SKU | `cafishplanting-ios` (suggested) | Any unique string. Customers never see it, and it can't be changed after the record is created. |
| Primary category | Sports | See [Category justification](#category-justification-231--metadata-accuracy) |
| Secondary category | Reference | `APP-STORE-LISTING.md` |
| App price | Free | DECISIONS 0007 |
| In-app purchase | Non-consumable, `com.chelseakr.cafishplanting.fullaccess`, **$9.99** | DECISIONS 0003/0007/0009. 0009 keeps "still $9.99". |
| Version | `0.1.0`, build `1` | `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION`. The App Store Connect version must match `MARKETING_VERSION`. To ship as `1.0`, change `MARKETING_VERSION` before archiving. |
| Support URL | `https://chelseakr.github.io/ca-fish-planting-alerts/support/` | Returns 200 (checked 2026-09-18). It has no contact line yet; see step 2. |
| Privacy Policy URL | `https://chelseakr.github.io/ca-fish-planting-alerts/privacy/` | Returns 200 (checked 2026-09-18) |
| Marketing URL (optional) | `https://chelseakr.github.io/ca-fish-planting-alerts/` | |
| Support email | **TODO(owner):** no address is recorded in this repo | The owner said she would create a support alias on chelseakr.com. |

### Before App Store Connect

1. **Trademark search for "Trout Truck".** DECISIONS 0010 records that
   none has been run. Before submitting:
   - USPTO Trademark Search (`https://tmsearch.uspto.gov/`): `TROUT TRUCK`,
     `TROUTTRUCK`, `TROUT TRUCKS`, and sound-alikes, live and dead marks, in
     International Classes 9 (downloadable software and apps), 42 (online
     software and services) and 41 (information about recreation and
     fishing).
   - California state marks: the Secretary of State's trademark search.
   - Common-law use: the App Store, Google Play and a web search for
     "trout truck" app or fishing.
   - Record the result and the date in DECISIONS 0010, replacing
     "Trademarks were not searched". A conflict means a new name before
     submitting, not after. This is a screen, not legal advice.
2. **Support contact (TODO(owner)).** Create the support alias on
   chelseakr.com. Then set it for the site and republish:
   ```sh
   gh variable set SUPPORT_EMAIL --repo ChelseaKR/ca-fish-planting-alerts --body '<the alias>'
   gh workflow run publish.yml --repo ChelseaKR/ca-fish-planting-alerts
   ```
   Check that `/support/` and `/privacy/` now show a `mailto:` line.
   Guideline 1.5 asks for a Support URL that gives an easy way to contact
   you, and the page has no contact line until this is set.
3. **Live privacy page: done 2026-09-18.** The 03:50 UTC build predated
   #16 (the name) and #20 (GA4), but the `publish` run at 06:10 UTC
   redeployed the site. Checked after it: `/privacy/` names Trout Truck,
   describes the website's Google Analytics 4, says the app collects
   nothing and that the host sees the requesting IP, and its app section
   states "App Store privacy label: Data Not Collected". Re-read it
   once before submitting, and whenever the privacy copy changes.
4. **Paid Applications Agreement.** App Store Connect → Business: the
   Paid Apps agreement must be **Active**, with banking and tax forms
   done. Without it, the in-app purchase can't be tested in the sandbox
   or TestFlight, and it can't be sold. Banking and tax review can take
   days, so start this first.
5. **Refresh the bundled snapshot** just before archiving, so a fresh
   install opens on the current week:
   ```sh
   ios/scripts/sync-bundled-snapshot.sh   # downloads, validates against schema/snapshot.v1.json
   git add ios/CAFishPlanting/Resources/snapshot.json   # then commit and merge through a PR
   ```
   To match the screenshots to the new week too, run
   `ios/scripts/app-store-screenshots.sh` (see [Screenshots](#screenshots)).
   This is optional: the committed screenshots are real data from the
   week of 2026-09-13.

### Register the app

6. **Sign in to Xcode** with the Apple ID for team `6X5YH93QNM` (Xcode →
   Settings → Accounts). This is interactive.
7. **Register the bundle ID** at developer.apple.com → Certificates,
   Identifiers & Profiles → Identifiers → **+** → App IDs → App:
   Description `Trout Truck`, Bundle ID **Explicit**
   `com.chelseakr.cafishplanting`. Don't add capabilities. In-App Purchase
   is on for every App ID by default. Push Notifications is **not**
   needed, because every alert is local. Xcode's automatic signing can also
   register it on the first archive (step 16), but it has to exist before
   it appears in step 8's Bundle ID menu.
8. **Create the app record.** App Store Connect → Apps → **+** → New App:
   Platforms **iOS**; Name `Trout Truck`; Primary Language **English
   (U.S.)**; Bundle ID `com.chelseakr.cafishplanting`; SKU
   `cafishplanting-ios` (or your own); User Access **Full Access**.

### Fill in the record

9. **App Information:** Subtitle `CA trout stocking alerts`; Category
   Primary **Sports**, Secondary **Reference**. Content Rights: **Yes**,
   the app shows third-party content (CDFW's schedule), and you have the
   rights to use it. CDFW's Conditions of Use put it in the public domain
   (`docs/LICENSES-AND-ATTRIBUTION.md`). The app uses no CDFW seals or
   logos, which those terms reserve. Age Rating: answer **None** / **No**
   to every question (no user-generated content, no web browsing, no
   messaging, no ads, no gambling). The result should be the lowest tier,
   4+.
10. **Pricing and Availability:** Price **Free** (USD 0.00). Availability:
    your call. The data is California's, and the listing is English. If
    you include EU storefronts, App Store Connect requires a Digital
    Services Act trader declaration, and a trader's address, phone and
    email are shown on the EU product page.
11. **App Privacy:** Privacy Policy URL (from the table). Data collection:
    **"No, we do not collect data from this app"**, so the label is
    **Data Not Collected**. Why that's true, with file references:
    [Privacy answers, verified in code](#privacy-answers-verified-in-code).
    Publish the answers.
12. **In-app purchase:** Monetization → In-App Purchases → **+**: Type
    **Non-Consumable**; Reference Name `Full Access`; Product ID
    `com.chelseakr.cafishplanting.fullaccess`. Check this byte for byte
    against `PurchaseManager.productID`. A mismatch means the button says
    "Not available right now" for everyone. Then:
    - Price: **$9.99** (USD), all storefronts at Apple's equivalents, or
      the availability chosen in step 10.
    - Localization, English (U.S.): Display Name `Full Access`;
      Description `Alerts when a favourite water is listed` (39 of 45
      characters).
    - Family Sharing: your call. Once turned on for a product, it
      can't be turned off.
    - Review Information: a screenshot of the purchase sheet (About →
      "Unlock full access"). App Review sees it, and it isn't shown on the
      App Store, so it may show the price. Take it from the TestFlight
      build in step 18, where the sandbox price loads. The simulator can't
      load it on iOS 26.5 (`ios/README.md`). Review notes: "Unlocks local
      notifications for favourited waters. About → Unlock full access."
    - Status must reach **Ready to Submit**. Apple reviews the first
      in-app purchase with an app version (step 20).
13. **Version page (iOS App 0.1.0):**
    - Screenshots → iPhone **6.9" Display**: upload the five PNGs in
      [Screenshots](#screenshots) in their numbered order. The app is
      iPhone-only (`TARGETED_DEVICE_FAMILY = 1`), so no iPad set is
      needed, and App Store Connect scales the 6.9" set down for smaller
      iPhones.
    - Promotional Text, Description, Keywords, Support URL, Marketing URL
      and Copyright: paste from `APP-STORE-LISTING.md`. Replace `[N]` in
      the description with `coverage.waters_with_history` from the live
      snapshot on the day (385 on 2026-09-18).
14. **App Review Information** (same page): Sign-in required **off**, since
    there are no accounts. Contact: your name, phone and email. Notes:
    paste the "App Review notes" block from `APP-STORE-LISTING.md`.
    Attachment: none needed.
15. **Version Release:** choose **Manually release this version**, so you
    pick the day it goes live after approval.

### Archive and upload

16. **Archive.** In Xcode: open `ios/CAFishPlanting.xcodeproj`, scheme
    `CAFishPlanting`, destination **Any iOS Device (arm64)**, then Product
    → Archive. Or from `ios/`:
    ```sh
    xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
      -configuration Release -destination 'generic/platform=iOS' \
      -archivePath build/CAFishPlanting.xcarchive archive
    ```
    Every upload needs a new build number. Raise `CURRENT_PROJECT_VERSION`
    (currently `1`) before re-archiving after any rejected or replaced
    upload.
17. **Upload.** Xcode Organizer → the archive → Distribute App → **App
    Store Connect** → Upload. Keep automatic signing and "Upload your
    app's symbols". Or from `ios/`, with a `build/ExportOptions.plist`
    that you keep out of git:
    ```xml
    <dict>
      <key>method</key><string>app-store-connect</string>
      <key>destination</key><string>upload</string>
      <key>teamID</key><string>6X5YH93QNM</string>
      <key>signingStyle</key><string>automatic</string>
    </dict>
    ```
    ```sh
    xcodebuild -exportArchive -archivePath build/CAFishPlanting.xcarchive \
      -exportOptionsPlist build/ExportOptions.plist -exportPath build/export \
      -allowProvisioningUpdates
    ```
    Export compliance won't be asked: `Info.plist` sets
    `ITSAppUsesNonExemptEncryption` to `false`, because the only
    encryption is the HTTPS that iOS itself provides.
18. **TestFlight on your own iPhone** before you submit. Once the build
    finishes processing, install it through TestFlight and check:
    - About → "Unlock full access" shows **$9.99**. TestFlight purchases
      use the sandbox and aren't charged. Buy, and About shows
      "Unlocked". Delete the app, reinstall, then Restore purchases
      unlocks it again.
    - Take the in-app purchase review screenshot (step 12) here.
    - Favourite a water, choose Allow notifications, and check that
      Settings → Trout Truck shows Notifications on and Background App
      Refresh available.
    - To test outside TestFlight, for example from an Xcode run on a
      device, create a sandbox tester in App Store Connect → Users and
      Access → Sandbox. App Review uses its own sandbox accounts, so the
      review notes need no credentials.

### Submit

19. **Attach the build** on the version page (Build → **+** → the
    uploaded build).
20. **Attach the in-app purchase:** on the same page, under "In-App
    Purchases and Subscriptions", select `Full Access`. A first in-app
    purchase can only be submitted together with an app version.
21. **Add for Review → Submit to App Review.** Check once more that the
    trademark result (step 1) and the support contact (step 2) are done.
    With manual release, approval doesn't publish anything until you press
    Release.

## Screenshots

Five iPhone 6.9" screenshots, 1320×2868 portrait, captured 2026-09-18 on
an iPhone 17 Pro Max simulator (iOS 26.5). Upload them in this order to
the 6.9" Display slot:

| File | Screen | What it shows |
|---|---|---|
| `docs/app-store/screenshots/01-this-week.png` | Browse | Filtered to Inland Deserts Region (R6), the region with the most waters on this week's schedule (15 of 26). "This week" badges on the scheduled waters, and the header "Current schedule: week of 2026-09-13". |
| `docs/app-store/screenshots/02-water-history.png` | Water detail | Carrville Pond (Trinity County): "Last planted week of 2026-09-13", then the 2026 history expanded, newest week first. The top row, week of 2026-09-20, is next week's scheduled plant. Every row is a week, never a day. |
| `docs/app-store/screenshots/03-favourites.png` | Favourites | Five favourited waters. Four are on this week's schedule and one, Owens River, Section 2, is not, so the badge means something. |
| `docs/app-store/screenshots/04-notifications.png` | The first-favourite sheet ("Stay in the loop") | What notifications will and won't do, "once you unlock full access". No price appears. The system permission prompt is not shown. |
| `docs/app-store/screenshots/05-about.png` | About, scrolled to Privacy | The privacy statement, the CDFW attribution, and "This app is independent. It is not affiliated with or endorsed by the California Department of Fish and Wildlife." |

**The data is real.** Every screen shows
`ios/CAFishPlanting/Resources/snapshot.json`, which this branch refreshed
to the live `snapshot/v1.json` the pipeline built at 2026-09-18T03:50:44Z
(week of 2026-09-13; 385 waters, 26 scheduled this week). It was checked
against `schema/snapshot.v1.json` before it was copied in. No fixture was
used, and nothing was seeded: the favourites were added by tapping the
star, as a user would.

**Honest details a reviewer may notice.** The Browse header says "Not
refreshed on this device yet — showing the schedule bundled with the
app", because the shots come from a fresh install and the app only
refreshes in the background (Known gaps 7). The status bar is set to 9:41
with full signal and battery (`simctl status_bar`), which is Apple's
convention. The purchase sheet isn't among the shots, because it shows the
price. Its App Review screenshot is checklist step 12.

**To regenerate** (for example after checklist step 5 brings in a new
week), run this from the repository root with no other simulator work
running:

```sh
ios/scripts/app-store-screenshots.sh
```

It creates or reuses a simulator named "Trout Truck screenshots" (iPhone
17 Pro Max), deletes the app so the run starts from a fresh install, and
picks the region and waters from the bundled snapshot. It then runs
`CAFishPlantingUITests/AppStoreScreenshotsUITests`, which is skipped in
ordinary test runs, and fails unless all five PNGs come back at
1320×2868. The waters change with the data, so re-check this table
against the new images.

## Privacy answers, verified in code

Checked 2026-09-18 against `origin/main` at `0c53741` plus this branch.
The App Store answers are **Data Not Collected** and **no tracking**, and
the code supports both.

**One network request, to one host.**
- The app has one `URLSession`, made by `SnapshotRefresher.makeSession()`
  (`ios/PlantingCore/Sources/PlantingCore/SnapshotRefresher.swift`). It is
  ephemeral, with no cookie store, no URL cache and no credential store.
- It has one request builder, `makeRequest(etag:)`: a `GET` of
  `SnapshotEndpoint.url`
  (`https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json`)
  with `Accept: application/json`, a fixed `User-Agent: CAFishPlanting`
  with no version or device, and `If-None-Match` when an ETag is stored.
  `refresh(into:)` stops with a `precondition` if the host is anything
  else.
- The only caller is `AppEnvironment.performBackgroundRefresh()`, which
  the `BGAppRefreshTask` runs. `refreshNow()` exists but nothing calls it,
  so the app never fetches in the foreground (Known gaps 7).
- `HostAllowlistTests` fails if any host other than the snapshot host
  appears in `PlantingCore/Sources`, `CAFishPlanting/App` or
  `CAFishPlanting/Views`. A `grep` for `https?://` in those directories on
  this branch finds only that URL.
- Links aren't requests the app makes. The CDFW page, the water's site
  page, the attribution URL and the licence URLs are SwiftUI `Link`s, which
  open Safari only when tapped. There is no `WKWebView` or
  `SFSafariViewController`, so the website's Google Analytics never runs
  inside the app (DECISIONS 0011). The share button opens the system share
  sheet with text only when tapped.
- StoreKit (`Product.products`, `purchase()`, `Transaction.currentEntitlements`,
  `Transaction.updates`, `AppStore.sync()`) talks to Apple. No receipt or
  transaction is sent anywhere else, and no developer server exists.
- **Measured on the wire (2026-09-18).** A scratch harness sent the app's
  own request (`SnapshotRefresher.makeSession()` and `makeRequest(etag:)`
  from `PlantingCore`, with only the endpoint pointed at a local listener)
  on macOS 26.4 CFNetwork. The complete header set was `Host`,
  `Accept: application/json`, `User-Agent: CAFishPlanting`,
  `Accept-Language: en-US,en;q=0.9`, `Accept-Encoding: gzip, deflate`,
  `Cache-Control: no-cache` and `Connection: keep-alive`, plus
  `If-None-Match` on the second request. There was no cookie, no
  authorization and no device or app identifier. CFNetwork, not the app,
  adds `Accept-Language`, which carries the device's language preference
  and is not an identifier. The ETag the app echoes is GitHub's ETag for the file, which
  is the same for every client.

**No analytics or third-party SDK.**
- Every `import` in `CAFishPlanting/` and `PlantingCore/Sources` is an
  Apple framework (`Foundation`, `SwiftUI`, `Observation`,
  `UserNotifications`, `BackgroundTasks`, `StoreKit`) or the local
  `PlantingCore` package.
- `PlantingCore/Package.swift` declares no dependencies. The Xcode
  project has one package reference, the local `PlantingCore`
  (`XCLocalSwiftPackageReference`), and no remote package. There is no
  CocoaPods or Carthage.
- **Built app (2026-09-18, simulator build from this branch).** `otool -L`
  on the app's code (`CAFishPlanting.debug.dylib`) lists only system
  frameworks: Foundation, SwiftUI, UIKit, StoreKit, UserNotifications,
  BackgroundTasks, DeveloperToolsSupport (Xcode previews, Debug only) and
  the Swift runtime. Beyond those it links only `PlantingCore.framework`,
  which links only Foundation and the Swift runtime. `strings` over the
  app and `PlantingCore` finds two URLs: the snapshot URL and Apple's
  plist DTD, which is never fetched.

**No identifiers.**
- None of these appear in the app or `PlantingCore` source: `AdSupport`,
  `ASIdentifierManager`, `AppTrackingTransparency`, `identifierForVendor`,
  `UIDevice`, `DeviceCheck`/App Attest, `UserDefaults`, `@AppStorage`,
  Keychain (`SecItem`), CloudKit or iCloud key-value storage.
- Favourites, the alert baseline and the cached entitlement are JSON
  files in the app's Application Support directory
  (`PlantingCore/Sources/PlantingCore/Stores.swift`). They never leave
  the device.
- Notifications are local `UNUserNotificationCenter` requests. There is
  no `registerForRemoteNotifications`, no `aps-environment` entitlement
  (the project has no entitlements file) and so no device token.

**The privacy manifest agrees.** `PrivacyInfo.xcprivacy` sets
`NSPrivacyTracking` false with no tracking domains, no collected data
types and no required-reason APIs. That last one holds because the code
calls no `UserDefaults`, no file-timestamp APIs, no `systemUptime` and no
disk-space APIs. Re-check it (Xcode Organizer → the archive → Generate
Privacy Report) if any of those are added.

**What the host sees.** GitHub Pages serves the snapshot. Like any web
host, GitHub receives each request's IP address and headers in order to
serve it, under GitHub's privacy statement. GitHub doesn't give the
repository owner access logs for Pages, so the developer never receives
them. The snapshot is JSON, not an HTML page, so the site's GA4 tag never
runs for an app request. The live `/privacy/` page says the same ("as with
any web request, the host sees the IP address it came from"). If the
snapshot ever moves to a host that gives the owner request logs (a
custom domain behind a logging CDN, for example), the "Data Not
Collected" answer needs revisiting.

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
government schedule of a human activity. The secondary category is
Reference (a schedule-and-history lookup), not Weather, which an earlier
draft suggested; see `APP-STORE-LISTING.md`.

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

Superseded 2026-09-18: the screenshots are captured. See
[Screenshots](#screenshots).

## Owner steps to a TestFlight build

Superseded 2026-09-18 by
[Owner checklist: from here to submitted](#owner-checklist-from-here-to-submitted),
which covers the same archive and upload steps in submission order. It
drops `xcrun altool` in favour of Xcode's own upload.

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
5. ~~No screenshots captured yet~~ **Closed 2026-09-18.** Five 6.9"
   screenshots are in `docs/app-store/screenshots/`. See
   [Screenshots](#screenshots).
6. ~~The free/paid feature split is a placeholder~~ **Closed 2026-09-17**
   (DECISIONS 0009). Favouriting and browsing are free and unconstrained
   for everyone; the purchase unlocks local notifications on a favourited
   water's schedule change. See
   `PlantingCore/Sources/PlantingCore/FreeTier.swift`.
7. **The app never refreshes in the foreground** (found 2026-09-18, not
   fixed here). `AppEnvironment.refreshNow()` exists, but no view calls
   it: there is no pull-to-refresh and no refresh on launch. The only
   fetch is the `BGAppRefreshTask`, which the app requests when it goes to
   the background and iOS runs when it chooses. So a fresh install, or App
   Review, sees the bundled snapshot until iOS runs that task, and the
   Browse header says "Not refreshed on this device yet". Checklist step 5
   (refresh the bundled snapshot just before archiving) limits the
   damage. Adding a refresh on launch or pull-to-refresh is a product
   change. It would still be the same single request to the same host, so
   the privacy answers wouldn't change.
8. **Export compliance** is declared in `Info.plist`
   (`ITSAppUsesNonExemptEncryption` = `false`, added 2026-09-18). The
   only encryption is iOS's own HTTPS, so App Store Connect won't ask on
   each upload.
9. **"Last planted" breaks the copy rule** (found 2026-09-18, not fixed
   here). `WaterDetailView` titles the latest week "Last planted week
   of …". `APP-STORE-LISTING.md` rules out "stocked on" and asks for
   "scheduled for the week of…", because CDFW's weeks are plans that can
   change. Screenshot `02-water-history.png` shows the line as it is. If
   the wording changes (for example to "Last scheduled"), regenerate that
   screenshot.
