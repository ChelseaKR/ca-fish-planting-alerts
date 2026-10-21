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

The app reads `snapshot/v1.json`, California only, which stays
byte-compatible beside v2 (docs/DECISIONS.md 0025). It ships a committed v1
snapshot, `app/src/main/assets/snapshot.json`, so a fresh install opens on
a real week with no network. The iOS app bundles v2, so the two files are
separate.

Refresh it before a release build with `scripts/sync-bundled-snapshot.sh`.
The script downloads the live v1 snapshot, checks it against
`schema/snapshot.v1.json`, refuses one older than the bundled copy, and
replaces the file. It needs `curl` and `uv`, like the iOS script.
`SnapshotDecoderTest` decodes the committed file, so a file the app can't
read fails the build.

The app opens it with `SnapshotLoader` on `Dispatchers.Default`, never on
the main thread, and shows "Loading the stocking schedule…" until it has.
Refreshes, background work and a new favorite's alert baseline wait for
that load.

## The alert planner is held to the Swift one

The fixtures in `ios/PlantingCore/Tests/PlantingCoreTests/Fixtures/` are
synthetic scenarios and two real-data excerpts, with the alerts recorded
from the Swift planner. `AlertPlannerParityTests.swift` and
`AlertPlannerParityTest.kt` both run every scenario. A change to either
planner that changes an alert, an id, the words or a baseline fails one of
them.

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
   free with an in-app product.
2. App signing: enroll in Play App Signing, so Google holds the app key.
   Create an upload key outside the repo, then sign release builds with
   it. No key or keystore password goes in this repository.
   `docs/ANDROID-RELEASE.md` has the exact commands, and the manual
   `android-release` workflow builds the signed bundle.
3. In-app product: create a one-time product with the ID `fullaccess`
   (`ProductCatalog.CALIFORNIA_FULL_ACCESS` in `core`), at the iOS price.
   It unlocks alerts and the home screen widget. If Play requires a
   different ID, change that one constant.
4. Data safety: no data collected or shared. The app has no account,
   analytics or crash reporting. Its one request is a plain GET of the
   public snapshot. Favorites, mutes and the alert baseline stay on the
   device and are excluded from cloud backup
   (`app/src/main/res/xml/backup_rules.xml` and
   `data_extraction_rules.xml`).
5. Store listing, content rating and target audience, using the iOS
   listing's copy with "home screen" in place of "Home Screen and Lock
   Screen".
6. Upload a signed release bundle to the internal testing track and add
   testers.
