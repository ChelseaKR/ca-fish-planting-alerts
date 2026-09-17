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
scheme already points both Run and Test at it. See `docs/APP-STORE.md`
("In-App Purchase to create in App Store Connect") for the exact product
Chelsea has to create there before a real purchase can happen outside this
local configuration, and `docs/DECISIONS.md` 0007 for why this replaced
0003's original "no StoreKit, App-Store-price-tier" plan.

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

One assumption flagged for the pipeline/site lane: `schema/snapshot.v1.json`
has no per-water site-page URL field, so `SnapshotEndpoint.siteWaterURL(slug:)`
derives it from the snapshot's own host + `/water/<slug>/` (matching the path
convention `schema/README.md` documents). If the real site ends up on a
different host than the snapshot, that derivation breaks — the clean fix is
an explicit `site_url` per water in a future schema revision, which is a
`schema/` change outside this task's boundary.
