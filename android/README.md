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

## States and purchases

Browse has a state picker and a States screen once the snapshot has more
than one state. Each state is its own Google Play one-time product
(`StateProducts` in `core`):

| State | Google Play  | App Store                                 |
|-------|--------------|-------------------------------------------|
| CA    | `fullaccess` | `com.chelseakr.cafishplanting.fullaccess` |
| TN    | `state_tn`   | `com.chelseakr.cafishplanting.state.tn`   |
| MA    | `state_ma`   | `com.chelseakr.cafishplanting.state.ma`   |
| MI    | `state_mi`   | `com.chelseakr.cafishplanting.state.mi`   |

A Play product ID already belongs to this one app, so the Play IDs drop the
package-name prefix. A state's product unlocks alerts for that state's
favorites and lists them in the widget. Massachusetts and Michigan are off
(DECISIONS 0025), so their products are placeholders and need nothing in
Play Console.

## Debug switches

Debug builds only (`app/src/debug/.../DebugHooks.kt`; release builds use
`app/src/release/`, which has none of this). Each switch is a file under the
app's own `files/debug/`, written with `adb shell run-as
com.chelseakr.cafishplanting`:

- `network-snapshot.json` is served as the snapshot URL's response instead
  of the network, so an alert can be produced on demand.
- `fake-billing` replaces Google Play with a local store that sells every
  product, since Play has no product until the owner creates one.
- `allow-review` lets the app request Play's review card. Debug builds
  never ask otherwise.

## Owner steps (Chelsea)

The app can't reach testers until these are done in Play Console.

1. Create the app: name Trout Truck, package `com.chelseakr.cafishplanting`,
   free with in-app products.
2. App signing: enroll in Play App Signing, so Google holds the app key.
   Create an upload key outside the repo, then sign release builds with
   it. No key or keystore password goes in this repository.
3. In-app products: create two one-time products. `fullaccess` is
   California, at the iOS price. `state_tn` is Tennessee, at USD 9.99. Each
   unlocks alerts and the home screen widget for its own state. The IDs are
   in `StateProducts` in `core`; if Play needs a different one, change it
   there.
4. Data safety: no data collected or shared. The app has no account,
   analytics or crash reporting. Its only requests are plain GETs of the
   public snapshot (v2, or v1 when v2 isn't there). Favorites, mutes and
   the alert baseline stay on the device and are excluded from cloud backup
   (`app/src/main/res/xml/backup_rules.xml` and
   `data_extraction_rules.xml`).
5. Store listing, content rating and target audience, using the iOS
   listing's copy with "home screen" in place of "Home Screen and Lock
   Screen". The iOS listing still says California; DECISIONS 0025 says it
   changes when a state goes on sale.
6. Upload a signed release bundle to the internal testing track and add
   testers.
