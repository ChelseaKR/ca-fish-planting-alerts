# android/

The Android app, with the iOS app's features (docs/DECISIONS.md 0022).
Kotlin, Jetpack Compose and Material 3, minSdk 26, targetSdk 36. Two Gradle
modules:

- `core/`: plain Kotlin with no Android dependency. It holds the strict
  snapshot decoder, the alert planner, freshness, search, the widget digest,
  the on-disk stores, the product catalog and the words the app shows. Its
  JVM tests run without an emulator. Almost all the logic lives here, as it
  does in `ios/PlantingCore`.
- `app/`: the Compose screens, WorkManager's daily refresh, notifications,
  the Glance home screen widget, Play Billing and Play's in-app review.

## Commands

From `android/`, with JDK 21:

- `./gradlew :core:test` runs the core tests, including
  `AlertPlannerParityTest`.
- `./gradlew :app:testDebugUnitTest` runs the app's JVM tests:
  `SnapshotLoaderTest` opens the real bundled snapshot through the launch
  path, off the caller's thread.
- `./gradlew :app:lintDebug` runs Android lint, with warnings as errors.
- `./gradlew :app:assembleDebug :app:assembleRelease` builds a debug APK
  and an R8-minified, unsigned release APK.

CI's `android` job runs all of these on pull requests, then checks that
both APKs carry `assets/snapshot.json` and that it is the committed file,
byte for byte.

## The bundled snapshot

The app reads `snapshot/v2.json`, every state (docs/DECISIONS.md 0025).
Only when v2 isn't there (HTTP 404 or 410) does it read `snapshot/v1.json`,
California alone; the decoder reads both. It ships a committed v2 snapshot,
`app/src/main/assets/snapshot.json`, so a fresh install opens on real
weeks with no network.

Refresh it before a release build with `scripts/sync-bundled-snapshot.sh`.
The script downloads the live v2 snapshot, checks it against
`schema/snapshot.v2.json`, refuses one older than the bundled copy, and
replaces the file. It needs `curl` and `uv`, like the iOS script.
`SnapshotDecoderTest` decodes the committed file, so a file the app can't
read fails the build.

The app opens it with `SnapshotLoader` on `Dispatchers.Default`, never on
the main thread, and shows "Loading the stocking schedule…" until it has.
Refreshes, background work and a new favorite's alert baseline wait for
that load.

## The alert planner is held to the Swift one

The fixtures in `ios/PlantingCore/Tests/PlantingCoreTests/Fixtures/` carry
expectations recorded from the Swift planner:

- `alert-planner-parity.json`: California, synthetic scenarios and two
  real-data excerpts. `AlertPlannerParityTests.swift` and
  `AlertPlannerParityTest.kt` run it.
- `alert-planner-parity-states.json`: every state of `v2-all-states.json`,
  with weeks, days, months and reports, which alerts each state's purchase
  lets the app post, and the widget's rows. `MultiStateParityTests.swift`
  and `MultiStateParityTest.kt` run it.

A change to either planner that changes an alert, an id, the words, a
baseline or a widget row fails one of them. To re-record after a deliberate
change, run `PARITY_RECORD=1 swift test` in `ios/PlantingCore`, review the
diff, and run the Android tests against it.

## Free launch and the build flag

Android launches free (docs/DECISIONS.md 0044): alerts, reminders and the
widget are free in every state, and nothing is for sale. One Gradle
property decides it, `troutTruck.androidFreeTier` in `gradle.properties`:

- `true` (the default): `BuildConfig.FREE_TIER` is true, the Play Billing
  library isn't a dependency, and the release manifest has no
  `com.android.vending.BILLING` permission. `src/free` supplies the store
  (`FreeLaunchBackend`, which reports every state as owned) and the free
  build's words (`FreeLaunch` in `core`). No screen shows a price, a
  purchase or Restore purchases.
- `false` (`./gradlew -PtroutTruck.androidFreeTier=false ...`): `src/billing`
  supplies Play Billing (`PlayBillingBackend`) and the purchase screens
  below come back, unchanged.

`FreeLaunchBuildTest` runs in both builds and checks the billing library is
present only with the flag off. CI builds both.

## States and purchases (the paid build)

Browse has a state picker and a States screen once the snapshot has more
than one state. In the paid build, each state is its own Google Play
one-time product (`StateProducts` in `core`):

| State | Google Play  | App Store                                 |
|-------|--------------|-------------------------------------------|
| CA    | `fullaccess` | `com.chelseakr.cafishplanting.fullaccess` |
| TN    | `state_tn`   | `com.chelseakr.cafishplanting.state.tn`   |
| MA    | `state_ma`   | `com.chelseakr.cafishplanting.state.ma`   |
| MI    | `state_mi`   | `com.chelseakr.cafishplanting.state.mi`   |
| NY    | `state_ny`   | `com.chelseakr.cafishplanting.state.ny`   |

A Play product ID already belongs to this one app, so the Play IDs drop the
package-name prefix. A state's product unlocks that state's favorites'
notifications and lists them in the widget. In the free build none is sold;
in the paid build all five would be: they are the
five states in the published `snapshot/v2.json` (checked 2026-10-24). A
state missing from the snapshot is left out of the app, product and all.

New York is a plan state (DECISIONS 0034): NYS DEC publishes a spring plan
once a year in its own words ("April - third week, 2026"). The app shows
those words verbatim, never as a date, and its purchase adds a reminder on
the first day of each favorite's planned period of a month or less
(`ReminderPlanner` in `core`, scheduled by `ReminderWorker` at 9 a.m. local
time), as the iOS app does.

## Debug switches

Debug builds only (`app/src/debug/.../DebugHooks.kt`; release builds use
`app/src/release/`, which has none of this). Each switch is a file under the
app's own `files/debug/`, written with `adb shell run-as
com.chelseakr.cafishplanting`:

- `network-snapshot.json` is served as the snapshot URL's response instead
  of the network, so an alert can be produced on demand.
- `fake-billing` (paid build only) replaces Google Play with a local store
  that sells every product, since Play has no product until the owner
  creates one. The free build ignores it.
- `allow-review` lets the app request Play's review card. Debug builds
  never ask otherwise.

## Owner steps (Chelsea)

The app can't reach testers until these are done in Play Console.

1. Create the app: name Trout Truck, package `com.chelseakr.cafishplanting`,
   free. No payments profile and no in-app products (DECISIONS 0044).
2. App signing: enroll in Play App Signing, so Google holds the app key.
   Create an upload key outside the repo, then sign release builds with
   it. No key or keystore password goes in this repository.
   `docs/ANDROID-RELEASE.md` has the exact commands, and the manual
   `android-release` workflow builds the signed bundle.
3. In-app products: none. The free build sells nothing; the per-state IDs
   in `StateProducts` wait for a paid build, if one is ever chosen.
4. Data safety: no data collected or shared. The app has no account,
   analytics or crash reporting. Its only requests are plain GETs of the
   public snapshot (v2, or v1 when v2 isn't there). Favorites, mutes and
   the alert baseline stay on the device and are excluded from cloud backup
   (`app/src/main/res/xml/backup_rules.xml` and
   `data_extraction_rules.xml`).
5. Store listing, content rating and target audience, using the iOS
   listing's copy with "home screen" in place of "Home Screen and Lock
   Screen", and with no purchase or price: on Android alerts and the
   widget are free (0044).
6. Upload a signed release bundle to the internal testing track and add
   testers.
