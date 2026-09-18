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
said plainly, and the last good snapshot stays on screen, labelled with its
week. Once that week has ended the app says so, and the tag on a listed
water shows the week instead of "This week". A failed fetch never becomes
"nothing listed": `SnapshotStore` keeps the last good snapshot, and
`FailedFetchNeverRendersAbsenceTests` checks each kind of failure.

App-hosted unit tests run inside the app, so the launch refresh is skipped
when `XCTestConfigurationFilePath` is set. `AppEnvironmentTests` calls
`refreshIfDue` itself against a mocked session. UI tests launch the app
normally, so they fetch the live snapshot.

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

All of the above ran clean in this environment: `swift test` — 38/38;
`xcodebuild build` — BUILD SUCCEEDED, zero warnings besides the expected
"no AppIntents.framework dependency" note; `CAFishPlantingTests` — 5/5;
`CAFishPlantingUITests` — the browse → favourite → explainer-sheet →
Favourites-tab smoke path (see `docs/APP-STORE.md` for the exact run
Chelsea can repeat).

## Two things worth knowing before re-running these

1. **Pick (or create) a simulator device explicitly** rather than relying
   on Xcode's default. A device that is mid-boot or shared with another
   concurrently-running `xcodebuild` (this session hit exactly that: a
   sibling session's `queer-tv-guide` test run was using the same "iPhone
   17 Pro" simulator, which stalled both) will look "hung" for minutes.
   `xcrun simctl list devices` shows what's booted/booting; prefer `-destination
   'platform=iOS Simulator,id=<UDID>'` with a device nothing else is using.
2. **First-launch content.** If `xcodebuild`/the simulator fails with
   something like "failed to load IDESimulatorFoundation" or a device
   permanently stuck "Booting", the fix is an interactive owner step:
   `sudo xcodebuild -runFirstLaunch`. Not needed in this session — noted
   here because the task brief anticipated it.
3. **StoreKit tests can't pass on the iOS 26.5 simulator.** See the next
   section.

## StoreKit tests can't pass on the iOS 26.5 simulator

`PurchaseManagerTests` has never passed on this machine. PR #7 merged it
unverified, and origin/main and PR #12 fail the same way (measured
2026-09-17 on fresh simulators). This is an Apple bug in the simulator
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

`ios/` started against a hand-built fixture (schema-valid, real water
names, invented plants) while the pipeline lane was still in flight. That
lane finished within the session — `schema/snapshot.v1.json` +
`schema/README.md` landed as commit `1b1d0eb` on
`origin/feat/pipeline-schema-site`, and a real generated snapshot later
appeared at `site/snapshot/v1.json` (385 waters, `source_week` "week of
2026-09-13", 7 waters listed that week) — so
`CAFishPlanting/Resources/snapshot.json` is now **that real output**,
copied in and verified: valid against `schema/snapshot.v1.json` (checked
with the `jsonschema` Python package) and decodes cleanly through
`SnapshotDecoder`, including the `this_week`-agrees-with-`waters[].plants`
self-consistency check. The synthetic version this replaced is gone; if
the pipeline lane's committed output ever diverges from this copy,
re-sync `CAFishPlanting/Resources/snapshot.json` from whatever it
publishes at the URL below (same filename, same location — nothing in
`ios/` treats "real vs. fixture" specially, any schema-valid file drops
in cleanly). `PlantingCore/Sources/PlantingCore/SnapshotEndpoint.swift`
has the live URL from `schema/README.md`
(`https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json`,
following redirects once a custom domain is set).

Refreshed 2026-09-18 to the live snapshot built at 03:50:44 UTC (week of
2026-09-13, 26 waters listed that week). `scripts/sync-bundled-snapshot.sh`
downloads the live file, checks it against `schema/snapshot.v1.json`,
refuses one older than the bundled copy, and copies it in. Run it just
before archiving. `scripts/app-store-screenshots.sh` regenerates the App
Store screenshots from whatever is bundled (see `docs/APP-STORE.md`,
"Screenshots").

One assumption flagged for the pipeline/site lane: `schema/snapshot.v1.json`
has no per-water site-page URL field, so `SnapshotEndpoint.siteWaterURL(slug:)`
derives it from the snapshot's own host + `/water/<slug>/` (matching the path
convention `schema/README.md` documents). If the real site ends up on a
different host than the snapshot, that derivation breaks — the clean fix is
an explicit `site_url` per water in a future schema revision, which is a
`schema/` change outside this task's boundary.
