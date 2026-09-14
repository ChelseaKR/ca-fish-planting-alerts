# App Store listing (draft) and TestFlight path

Status: draft, unsubmitted. This session has `xcodebuild` and simulator
access only — no App Store Connect access — and submits nothing (per the
task boundary). Everything below is prepared for Chelsea to execute.

## Listing draft

| Field | Value | Notes |
|---|---|---|
| Name | **TBD** — `docs/DECISIONS.md` 0006 ("Name and domain: undecided") | Working placeholder in code/Info.plist: "CA Fish Planting" (`CFBundleDisplayName`, `ios/CAFishPlanting/Resources/Info.plist`) — the one place that string appears. |
| Subtitle | "Trout stocking alerts for California" | 29/30 chars — fits the 30-char subtitle limit. |
| Description | See draft below. | States the weekly cadence and local-only alerts in the first two sentences, per the task's plain-statement requirement. |
| Keywords | `trout,fishing,stocking,fish planting,CDFW,angler,California,lake,creek,hatchery` | No brand terms beyond CDFW's own program name (factual reference, not a trademark claim). |
| Category (primary) | **Sports** | See justification below. |
| Category (secondary) | Weather | The alert mechanism (scheduled, local, "check back") reads closer to a weather-alert app than a game/score app; Sports is still primary since the audience and the underlying activity (angling) are sport, not meteorology. |
| Age rating | **4+** | No objectionable content categories apply (no UGC, no gambling, no mature themes, no web browser). Apple's questionnaire should be answered "None" throughout. |
| Price | **$9.99, one-time purchase, no subscription** | `docs/DECISIONS.md` 0003: [moved to private strategy notes] No StoreKit is implemented in `ios/` yet (0003: "no StoreKit") — the owner steps below include adding an in-app purchase or paid-app-price flow before submission; this app currently has no purchase gate of any kind. |
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
- **3.1.1 / payment model.** DECISIONS 0003 chose a one-time paid-up-front
  app with no StoreKit (i.e., the *app itself* is the paywall — Apple's
  standard paid-app pricing, not an in-app purchase). This requires
  **no StoreKit code** — App Store Connect's own price tier gates the
  download. Confirm this reading against Apple's current guidelines before
  submission; if it changes, that is an owner decision under 0003, not an
  `ios/` code change.

## Owner steps to a TestFlight build

Commands, run from `ios/`, in order. Each `xcodebuild archive`/`gh` step
that touches App Store Connect needs Chelsea's own Apple ID session in
Xcode and is outside this session's access.

```sh
# 1. Confirm the app's own identity is final (name, bundle id, version)
#    before archiving — MARKETING_VERSION / CURRENT_PROJECT_VERSION live in
#    ios/CAFishPlanting.xcodeproj/project.pbxproj build settings.
#    CFBundleDisplayName lives in ios/CAFishPlanting/Resources/Info.plist.

# 2. Run the full local check one more time.
cd ios
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -destination 'platform=iOS Simulator,name=iPhone 17' clean build test

# 3. Add a real app icon (this repo ships none — see "Known gaps" below).
#    Xcode: CAFishPlanting/Resources — add an Assets.xcassets with an
#    AppIcon set, then set ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon
#    in the CAFishPlanting target's build settings (currently empty string
#    in project.pbxproj, deliberately, so a build never silently ships a
#    placeholder icon it doesn't have).

# 4. Sign in to Xcode with the Apple ID for Team 6X5YH93QNM
#    (Xcode > Settings > Accounts) — interactive, cannot be scripted here.

# 5. Archive for release.
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath build/CAFishPlanting.xcarchive archive

# 6. Export an App Store-signed .ipa. Requires an ExportOptions.plist
#    (teamID 6X5YH93QNM, method app-store-connect) — not included in this
#    repo; create it alongside build/ (it contains no secret, but keep it
#    out of git since it's a local export artifact, not app source).
xcodebuild -exportArchive \
  -archivePath build/CAFishPlanting.xcarchive \
  -exportOptionsPlist build/ExportOptions.plist \
  -exportPath build/export

# 7. Upload to App Store Connect (needs an app-specific password or API key
#    Chelsea generates in App Store Connect — interactive/credentialed,
#    not available to this session).
xcrun altool --upload-app -f build/export/CAFishPlanting.ipa \
  -t ios -u "<APPLE_ID_EMAIL>" -p "<APP_SPECIFIC_PASSWORD>"

# 8. In App Store Connect: create the app record (bundle id
#    com.chelseakr.cafishplanting), fill in the listing fields from the
#    table above, complete the privacy questionnaire as "Data Not
#    Collected" for every category, attach the build from step 7 to a
#    TestFlight group, and submit for TestFlight review (a lighter review
#    than full App Store review, but still Apple's, not this session's).
```

## Known gaps to close before any of the above

1. **No app icon** — `ASSETCATALOG_COMPILER_APPICON_NAME` is deliberately
   empty in the project so a Debug/simulator build never ships a fake
   placeholder; a real 1024×1024 icon is an owner asset (design or
   commission it), step 3 above.
2. **No purchase mechanism** — DECISIONS 0003 says "paid up front, no
   StoreKit," meaning App Store Connect's own price tier is the gate;
   confirm that is still how Apple prices non-subscription paid apps
   before archiving, since App Store Connect's pricing UI changes
   independently of this codebase.
3. **Name and domain undecided** (DECISIONS 0006) — the listing Name
   field above is a placeholder; `CFBundleDisplayName` ("CA Fish
   Planting") is the one place a working name appears in `ios/` and is
   safe to change without touching logic.
