# ios/

SwiftUI, iOS 17+, no third-party dependencies. Two pieces:

- `PlantingCore/` — a Swift package (models, the strict snapshot decoder, the
  pure alert-diff logic, on-disk stores, the network refresher). Builds and
  tests with plain `swift build` / `swift test` — **no Xcode project, no
  simulator needed** for this half.
- `CAFishPlanting.xcodeproj` — the app target (SwiftUI views, `BGAppRefreshTask`,
  `UNUserNotificationCenter`, StoreKit 2), plus `CAFishPlantingTests` (hosted
  unit tests) and `CAFishPlantingUITests`. Depends on `PlantingCore` as a
  local Swift package (`type: .dynamic` — see the comment in
  `PlantingCore/Package.swift` for why static fails to link here).

## The Home Screen and Lock Screen widget

`CAFishPlantingWidgets/` is a WidgetKit extension
(`com.chelseakr.cafishplanting.widgets`) with one widget, "Favorite
waters", in small, medium and large Home Screen sizes and the Lock
Screen's rectangular and inline sizes.

- **Data.** The app writes a small digest of the snapshot it already has
  (`WidgetDigest` in PlantingCore) to the App Group
  `group.com.chelseakr.cafishplanting`, after every refresh (the
  background task's too), every favorite change, and when the app goes to
  the background (`App/WidgetBridge.swift`). It reloads the widget only
  when the digest changed. The widget reads that file and nothing else:
  **it makes no network request**, so the snapshot GET stays the app's
  only one. The digest is ~1 KB; the widget never decodes the 1 MB
  snapshot.
- **Honest when stale or missing.** Every line names its week. At
  midnight after the week's Saturday (Los Angeles time) the timeline
  switches from "This week" to "Schedule for the week of …", without the
  app running. A failed last check says so. No digest yet reads "Open
  Trout Truck to load the schedule here", and favorites the snapshot no
  longer has are counted, never shown as "nothing scheduled".
- **Taps.** Each row in the medium and large sizes, and the small and
  Lock Screen widgets as a whole, open a water through
  `trouttruck://water/<id>`.
- **Part of full access** (`docs/DECISIONS.md` 0015).
  `FreeTier.widgetsRequireFullAccess` is `true`. Before the purchase the
  digest is `locked`: it carries the schedule's week and how many waters
  it lists, and no favorites. The widget says it is part of full access,
  and a tap opens the purchase screen through `trouttruck://unlock`
  (`UnlockLink`). `PurchaseManager.onEntitlementChange` rewrites the
  digest the moment the entitlement changes, so a purchase, a restore or
  a refund redraws the widget without waiting for a refresh.
- **Signing.** Both targets use team `6X5YH93QNM` with automatic signing,
  as before. On a device (not the simulator) the App Group has to be
  registered for the team; see `docs/APP-STORE.md` step 7.

## The one-time purchase

`CAFishPlanting/App/PurchaseManager.swift` is StoreKit 2 only (no
`SKPaymentQueue`/transaction-observer code) for the app's single
non-consumable product. `CAFishPlanting/Configuration.storekit` is a local
StoreKit testing configuration carrying that same product — no App Store
Connect access is needed to build, run, or test the purchase flow; the
scheme points both Run and Test at it. The scheme's
`StoreKitConfigurationFileReference` path is resolved from
`CAFishPlanting.xcodeproj/project.xcworkspace`, not from `ios/`, so it has
to be `../../CAFishPlanting/Configuration.storekit`. Before 2026-09-17 it
was `CAFishPlanting/Configuration.storekit`, which points at a file that
doesn't exist. Before relying on local StoreKit testing, see "StoreKit tests
can't pass on the iOS 26.5 simulator" below. See `docs/APP-STORE.md`
("In-App Purchase to create in App Store Connect") for the exact product
Chelsea has to create there before a real purchase can happen outside this
local configuration, and `docs/DECISIONS.md` 0007 for why this replaced
0003's original "no StoreKit, App-Store-price-tier" plan.

## When the app fetches the snapshot

The app makes one kind of network request: a GET of the snapshot
(`PlantingCore/Sources/PlantingCore/SnapshotRefresher.swift`). It runs:

- from the `BGAppRefreshTask`, when iOS chooses (`App/BackgroundRefresh.swift`);
- on launch and on each return to the foreground
  (`AppEnvironment.refreshIfDue`), at most once every 6 hours, or 30 minutes
  after a failed check (`RefreshThrottle.foreground`). Background checks
  count toward that, because both read the same `SnapshotMeta`. When launch
  asks twice, both share one fetch.

Browse shows which week the schedule is for, how many waters that week
lists, and how the last check went (`SnapshotFreshness`). A failed check is
said plainly, and the last good snapshot stays on screen, labeled with its
week. Once that week has ended the app says so, and the tag on a listed
water shows the week instead of "This week". A failed fetch never becomes
"nothing listed": `SnapshotStore` keeps the last good snapshot, and
`FailedFetchNeverRendersAbsenceTests` checks each kind of failure.

App-hosted unit tests run inside the app, so the launch refresh is skipped
when `XCTestConfigurationFilePath` is set. `AppEnvironmentTests` calls
`refreshIfDue` itself against a mocked session. UI tests launch the app
normally, so they fetch the live snapshot.

## Opening a water from an alert or a link

A local notification carries only its water's ID (`WaterLink` in
PlantingCore, key `water_id`). `App/NotificationResponder.swift` is the
`UNUserNotificationCenter` delegate, installed in `App.init()` so the tap
that launches the app is delivered too. It hands the ID to
`App/AppRouter.swift`, which opens the water under Favorites (every alert is
for a favorite) or, for any other water, under Browse. A water the snapshot
doesn't have is never pushed as a blank screen.

`trouttruck://water/<water id>` (registered in `Info.plist`) goes through the
same router. The Home Screen widget uses it. Opening one makes no network
request and can only show a water already on the device.

## Commands

```sh
# PlantingCore alone — fast, no Xcode/simulator dependency. This is where
# almost all the logic lives (decoder, AlertPlanner, stores).
cd ios/PlantingCore
swift build
swift test

# The whole app: build for a simulator.
cd ios
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -destination 'platform=iOS Simulator,name=iPhone 17' build

# App-hosted unit tests (HostAllowlistTests, AppEnvironmentTests — these need
# the real app bundle, e.g. Bundle.main resolving to it, so they run hosted
# rather than as a plain SwiftPM test).
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:CAFishPlantingTests test

# UI smoke test.
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:CAFishPlantingUITests test

# Everything the shared scheme covers in one pass.
xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
  -destination 'platform=iOS Simulator,name=iPhone 17' clean build test
```

What each command covers:

- `swift test` runs the `PlantingCore` unit tests: the strict snapshot
  decoder (which also decodes the bundled snapshot), `AlertPlanner`, the
  stores, the refresher and the freshness rules. CI runs this one on every
  pull request (the `ios` job in `.github/workflows/ci.yml`).
- `xcodebuild ... build` builds the app and its widget extension for a
  simulator.
- `-only-testing:CAFishPlantingTests` runs the app-hosted unit tests.
  `PurchaseManagerTests` in that target cannot pass on an iOS 26.5
  simulator; see "StoreKit tests can't pass on the iOS 26.5 simulator"
  below.
- `-only-testing:CAFishPlantingUITests` runs the UI tests: the
  browse, favorite, explainer-sheet and Favorites-tab smoke path
  (`SmokeUITests`, and see `docs/APP-STORE.md` for a run to repeat by hand)
  and the automated accessibility audit (`AccessibilityAuditUITests`).

CI does not run the Xcode builds or tests (the comment on the `ios` job in
`ci.yml` says why), so run them by hand before a release. Pass and fail
counts are not recorded here, because they go stale as tests are added. The
commands print them.

## Three things worth knowing before re-running these

1. **Pick (or create) a simulator device explicitly** rather than relying
   on Xcode's default. A device that is mid-boot, or shared with another
   `xcodebuild` run at the same time, will look "hung" for minutes. Two test
   runs from different checkouts on the same "iPhone 17 Pro" simulator have
   stalled each other this way. `xcrun simctl list devices` shows what's
   booted or booting; prefer `-destination 'platform=iOS Simulator,id=<UDID>'`
   with a device nothing else is using.
2. **First-launch content.** If `xcodebuild` or the simulator fails with
   something like "failed to load IDESimulatorFoundation", or a device stays
   in "Booting", the fix is an interactive owner step:
   `sudo xcodebuild -runFirstLaunch`.
3. **StoreKit tests can't pass on the iOS 26.5 simulator.** See the next
   section.

## StoreKit tests can't pass on the iOS 26.5 simulator

`PurchaseManagerTests` has not passed on an iOS 26.5 simulator in any run
made so far. The tests were merged without a passing simulator run, and the
copy on `main` at the time failed the same way (measured 2026-09-17 on
fresh simulators; not re-run since). This is an Apple bug in the simulator
runtime. It is not a problem with this repo's code, the product ID, or the
`.storekit` file.

**Symptoms.** Every `[SKTestSession]` call logs
`Error Domain=SKInternalErrorDomain Code=3 "(null)"`: saving the
configuration file, clearing overrides, and deleting transactions. In the
simulator, `storekitd` logs `Allows client override: NO` for the test host.
`Product.products(for:)` comes back empty, so the purchase tests fail with
`failed("productUnavailable")` and "the local .storekit configuration
should have loaded com.chelseakr.cafishplanting.fullaccess". Then
`testRestorePurchasesRecoversEntitlementOnAFreshInstall` blocks in
`AppStore.sync()` and never returns. That is why earlier runs "took 80
minutes" or never finished.

**Cause.** The iOS & iPadOS 26.6 release notes list this as fixed under
StoreKit (163377768): "SKTestSessions does not properly connect to the test
environment when using Simulator, causing test actions to fail." As of
2026-09-17, no iOS 26.6 simulator runtime exists. The newest one Apple
offers is iOS 26.5 (23F77), which is what Xcode 26.6 uses. A fresh
simulator, a reboot, or killing `storekitd` doesn't help.
`xcodebuild test` doesn't push the scheme's StoreKit configuration to the
simulator either. The simulator's `storekitd` Octane container stays empty
even with the corrected scheme path.

**What to do.**
- Treat a red `PurchaseManagerTests` on an iOS 26.5 simulator as this bug
  only when the log shows the `SKInternalErrorDomain Code=3` lines above.
  Any other failure is real.
- Pass test timeouts so a stuck `AppStore.sync()` fails the test instead
  of hanging the run:
  ```sh
  xcodebuild -project CAFishPlanting.xcodeproj -scheme CAFishPlanting \
    -destination 'platform=iOS Simulator,id=<UDID>' \
    -test-timeouts-enabled YES -default-test-execution-time-allowance 180 \
    -only-testing:CAFishPlantingTests/PurchaseManagerTests test
  ```
- To get a real pass/fail signal, use a simulator runtime that has Apple's
  fix (iOS 26.6 or later) once Apple ships one. Check with
  `xcrun simctl runtime list`, and install with
  `xcodebuild -downloadPlatform iOS`.
- A workaround reported elsewhere but not tested here: in the Xcode app,
  Run the `CAFishPlanting` scheme on the simulator, stop it, then Test
  (Cmd-R, Cmd-., Cmd-U). The IDE pushes the scheme's StoreKit configuration
  to the simulator and `xcodebuild` doesn't. It depends on the corrected
  scheme path above.
- A physical device on iOS 26.6 or later also has Apple's fix. However,
  `PurchaseManagerTests.configurationURL()` builds a Mac-side `#filePath`
  path, which doesn't exist on a device. Running there first needs the
  `.storekit` file in the test bundle and
  `SKTestSession(configurationFileNamed:)`.

## The bundled snapshot: real pipeline output, not the hand-made fixture

`CAFishPlanting/Resources/snapshot.json` is real pipeline output: a copy of
the snapshot the site publishes, not a hand-made fixture. It is valid
against `schema/snapshot.v1.json` (`scripts/sync-bundled-snapshot.sh` checks
that with the `jsonschema` Python package before it copies a file in) and it
decodes cleanly through `SnapshotDecoder`, including the check that
`this_week` agrees with `waters[].plants` (the `PlantingCore` tests decode
it). Nothing in `ios/` treats "real
versus fixture" specially, so any schema-valid file drops in at the same
filename and location. If the pipeline's published output diverges from this
copy, re-sync it from the live URL.
`PlantingCore/Sources/PlantingCore/SnapshotEndpoint.swift` has that URL, from
`schema/README.md`
(`https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json`,
following redirects once a custom domain is set).

Refreshed 2026-09-18 to the live snapshot built at 03:50:44 UTC (week of
2026-09-13, 26 waters listed that week). `scripts/sync-bundled-snapshot.sh`
downloads the live file, checks it against `schema/snapshot.v1.json`,
refuses one older than the bundled copy, and copies it in. Run it just
before archiving. `scripts/app-store-screenshots.sh` regenerates the App
Store screenshots from whatever is bundled (see `docs/APP-STORE.md`,
"Screenshots").

One assumption to know about: `schema/snapshot.v1.json` has no per-water
site-page URL field, so `SnapshotEndpoint.siteWaterURL(slug:)` derives it from
the snapshot's own host + `/water/<slug>/` (matching the path convention
`schema/README.md` documents). If the site ever moves to a different host
than the snapshot, that derivation breaks. The clean fix is an explicit
`site_url` per water in a future schema revision.
