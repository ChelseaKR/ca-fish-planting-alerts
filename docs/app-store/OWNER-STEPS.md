# Owner steps: from here to "Submitted for Review"

Written 2026-10-01. This is the one ordered list of what is left before
Trout Truck can be submitted, and every step on it needs the owner: an
Apple ID, App Store Connect, a signing key, a legal or payment form, or a
decision. Everything an agent can do in the repository is done, and is
listed in [What is already done](#what-is-already-done) so you can check it
rather than redo it.

Values in `code` are exact; paste them as they are. The paste-ready listing
text, the App Privacy answers and the App Review notes are in
[`docs/APP-STORE-LISTING.md`](../APP-STORE-LISTING.md). The reasoning behind
them (review clauses, the privacy check in code, the in-app purchase) is in
[`docs/APP-STORE.md`](../APP-STORE.md).

## Values used below

| Field | Value | Where it comes from |
|---|---|---|
| App name | `Trout Truck` | DECISIONS 0010; `CFBundleDisplayName` |
| Bundle ID (app) | `com.chelseakr.cafishplanting` | `PRODUCT_BUNDLE_IDENTIFIER` in `ios/CAFishPlanting.xcodeproj/project.pbxproj` |
| Bundle ID (widget) | `com.chelseakr.cafishplanting.widgets` | same file |
| App Group | `group.com.chelseakr.cafishplanting` | both `.entitlements` files |
| Team ID | `6X5YH93QNM` | `DEVELOPMENT_TEAM`. Never `ACKGM9XK9V`, which is the enrollment ID; `make appstore` fails if it appears in the project. |
| SKU | `cafishplanting-ios` (suggested) | Any unique string; it can't be changed later. |
| In-app purchase | Non-Consumable, `com.chelseakr.cafishplanting.fullaccess`, USD 9.99 | `PurchaseManager.productID`; DECISIONS 0007 and 0009 |
| Version, build | `0.1.0`, build `1` today | `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION` (see step 1) |
| Support URL | `https://chelseakr.github.io/ca-fish-planting-alerts/support/` | 200 on 2026-10-01, but no contact line yet (step 5) |
| Privacy Policy URL | `https://chelseakr.github.io/ca-fish-planting-alerts/privacy/` | 200 on 2026-10-01; says the app collects no data |
| Marketing URL | `https://chelseakr.github.io/ca-fish-planting-alerts/` | optional field |

## 1. Decide four things first

These change what later steps type in, so settle them before App Store
Connect.

1. **Price model.** The code ships the app **free to download** with one
   **$9.99 one-time in-app purchase** (Full Access) that unlocks
   notifications and the widget; browsing, history and favorites are free
   (DECISIONS 0007 and 0009). Charging $9.99 at download instead is a
   different product: it needs a code change to remove the purchase gate,
   not just a different price in App Store Connect. Confirm which one, and
   confirm $9.99.
2. **Version number.** The project says `0.1.0`. App Store Connect accepts
   it, but a first public release usually ships as `1.0.0`. If you want
   `1.0.0`, step 9 sets it.
3. **Trademark screen for "Trout Truck"** (DECISIONS 0010 records that none
   was run). USPTO Trademark Search (`https://tmsearch.uspto.gov/`) for
   `TROUT TRUCK`, `TROUTTRUCK` and sound-alikes, live and dead, in classes 9,
   41 and 42; the California Secretary of State's trademark search; and the
   App Store, Google Play and the web for "trout truck". Record the result
   and date in DECISIONS 0010. A conflict means renaming before submitting.
   This is a screen, not legal advice.
4. **Storefronts.** The data is California's and the listing is English, so
   the United States alone is the simplest choice. Any EU storefront needs a
   Digital Services Act trader declaration, and a trader's address, phone
   and email are then shown on the EU product page.

## 2. Merge what the build depends on

`main` does not build the app today: a merge-conflict marker sits in
`FavoritesView.swift`. In order:

1. The CI fix branch `agent/tt-ci-fix` (PR #43), which makes `main`'s `ci`
   check green again.
2. The conflict-marker fix branch `agent/tt-ios-conflict-markers`, which
   removes the marker and adds a hygiene check so it can't recur.
3. This branch, `agent/tt-appstore` (readiness check, release workflow,
   these docs).
4. Optional for the first version: the iOS feature PRs #40, #41 and #42
   (species filter, "this week" toggle, notification history). If they go
   in, regenerate the screenshots afterwards (step 9), because they change
   the Browse screen.

## 3. Xcode on your Mac

- First-launch content: **already installed** (checked 2026-10-01:
  `xcodebuild -checkFirstLaunchStatus` exits 0 with Xcode 26.6). If that
  command ever exits non-zero, run this in **Terminal.app** (it asks for your
  password, which can't pass through an agent session):
  `sudo xcodebuild -runFirstLaunch`
- Sign in: Xcode → Settings → Accounts → **+** → Apple ID, and check that
  team `6X5YH93QNM` is listed. Interactive; only you can do it.
- Xcode 26.6 builds with the iOS 26 SDK, which App Store Connect requires
  for new uploads in 2026.

## 4. Agreements, tax and banking (start early)

App Store Connect → **Business**: the **Paid Applications Agreement** must
be **Active**, with tax forms and a bank account done. The app is free to
download, but the in-app purchase can't be sold, or even tested in
TestFlight, without it. Banking and tax review can take days.

## 5. Support contact

Guideline 1.5 asks for a Support URL that gives an easy way to reach you,
and `/support/` has no contact line until a support address is set. Create
the alias on chelseakr.com, then, in your own terminal:

    gh variable set SUPPORT_EMAIL --repo ChelseaKR/ca-fish-planting-alerts --body '<the alias>'
    gh workflow run publish.yml --repo ChelseaKR/ca-fish-planting-alerts

Check that `/support/` and `/privacy/` now show a `mailto:` line.

## 6. Register the identifiers

developer.apple.com → Certificates, Identifiers & Profiles:

1. Identifiers → **+** → App Groups: `group.com.chelseakr.cafishplanting`.
2. Identifiers → **+** → App IDs → App: Description `Trout Truck`, Bundle ID
   **Explicit** `com.chelseakr.cafishplanting`, capability **App Groups**
   with the group above. Leave Push Notifications off: every alert is local.
3. The same for the widget: Description `Trout Truck Widget`, Bundle ID
   **Explicit** `com.chelseakr.cafishplanting.widgets`, **App Groups** with
   the same group.

Xcode's automatic signing can create these on the first archive, but the
app's ID has to exist before step 7 can select it.

## 7. Create the app record

App Store Connect → Apps → **+** → New App: Platform **iOS**; Name
`Trout Truck`; Primary Language **English (U.S.)**; Bundle ID
`com.chelseakr.cafishplanting`; SKU `cafishplanting-ios`; User Access
**Full Access**.

## 8. Fill in the record

Paste from [`docs/APP-STORE-LISTING.md`](../APP-STORE-LISTING.md); its
character counts are measured.

1. **App Information:** Subtitle; Category Primary **Sports**, Secondary
   **Reference**; Content Rights **Yes** (CDFW's schedule is public domain
   under its Conditions of Use, `docs/LICENSES-AND-ATTRIBUTION.md`; the app
   uses no CDFW seal or logo); **Age Rating**: the answers in the listing
   file (every item None or No, which should give 4+).
2. **Pricing and Availability:** price **Free** (USD 0.00), unless step 1.1
   changed the model; the storefronts from step 1.4.
3. **App Privacy:** Privacy Policy URL from the table above; "Do you or your
   third-party partners collect data from this app?" **No**. The label
   becomes **Data Not Collected**. The per-category reasoning is in the
   listing file. Publish the answers.
4. **In-App Purchase:** Monetization → In-App Purchases → **+**: Type
   **Non-Consumable**; Reference Name `Full Access`; Product ID
   `com.chelseakr.cafishplanting.fullaccess` (byte for byte; a mismatch
   makes the button say "Not available right now" for everyone). Price:
   the **USD 9.99** price point, other storefronts at Apple's equivalents.
   English (U.S.) Display Name `Full Access`, Description
   `Alerts and a widget for your favorite waters`. Family Sharing: your call
   (it can't be turned off once on). Review screenshot: the purchase sheet,
   taken in step 12. Review notes: `Unlocks local notifications and the Home Screen widget for favorited waters. About → Unlock full access.`
   Status must reach **Ready to Submit**.

## 9. Prepare the release commit (a normal pull request)

On a branch from `main`:

1. Refresh the bundled snapshot so a fresh install opens on the current
   week: `ios/scripts/sync-bundled-snapshot.sh` (downloads the live
   snapshot and validates it against `schema/snapshot.v1.json`).
2. Regenerate the screenshots from that snapshot, with no other simulator
   work running: `ios/scripts/app-store-screenshots.sh`. Do this right
   after step 9.1: the app refreshes on launch and shows the live week, so
   the script picks its region and waters from the bundled snapshot and
   refuses one more than 7 days old. Optional 6.5" set:
   `SCREENSHOT_CLASS=6.5 ios/scripts/app-store-screenshots.sh`. Look at the
   five images before committing them.
3. If you chose `1.0.0`, set `MARKETING_VERSION = 1.0.0;` in every build
   configuration of `ios/CAFishPlanting.xcodeproj/project.pbxproj` (all
   targets must match, or the upload is refused). Raise
   `CURRENT_PROJECT_VERSION` for every later upload, including a re-upload
   of the same version.
4. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [1.0.0] - <date>` (or
   your version) and start a new empty `## [Unreleased]` above it.
5. `make verify` passes (it runs `make appstore`, the readiness check), then
   open the PR and merge it once `ci` is green.

## 10. Tag and run the release workflow

From a clone whose `origin` is `ChelseaKR/ca-fish-planting-alerts`, on the
merged `main`. The tag is signed with your release-signing key, whose public
half is committed in `.github/allowed_signers`:

    git config gpg.format ssh
    git config user.signingkey ~/.ssh/github-release-signing.pub
    git tag -s v1.0.0 -m "release: v1.0.0"
    git push origin v1.0.0
    gh workflow run ios-release.yml --repo ChelseaKR/ca-fish-planting-alerts -f tag=v1.0.0

`ios-release` verifies the tag's signature, checks that the tag matches
`MARKETING_VERSION`, that the build number is higher than every earlier
release's and that the CHANGELOG has the section, runs the PlantingCore
tests, archives the app **unsigned** for a generic iOS device (the same Archive action as Xcode, without signing), reads the
version back out of the built app and widget, and creates a **draft**
GitHub Release with the notes and a `release-stamp.json`. It never signs or
uploads anything. If it fails, fix the cause on `main` and cut the next
patch version; release tags aren't moved.

## 11. Archive and upload from Xcode

1. `git checkout v1.0.0` (the commit the workflow verified).
2. Open `ios/CAFishPlanting.xcodeproj`, scheme **CAFishPlanting**,
   destination **Any iOS Device (arm64)**, Product → **Archive**.
3. Organizer → the archive → **Validate App**, then **Distribute App** →
   **App Store Connect** → Upload, with automatic signing and symbols on.
   Export compliance isn't asked: `Info.plist` sets
   `ITSAppUsesNonExemptEncryption` to false (the only encryption is iOS's
   own HTTPS).
4. Optional: Organizer → the archive → **Generate Privacy Report**. It
   should list no collected data and no required-reason API, matching
   `PrivacyInfo.xcprivacy`.

## 12. TestFlight, internal testing

Once the build finishes processing: TestFlight → Internal Testing → add
yourself → install on your iPhone, then check:

- About → "Unlock full access" shows **$9.99**. Buy (sandbox, not charged);
  About reads "Unlocked". Delete the app, reinstall, "Restore purchases"
  unlocks it again.
- Take the purchase-sheet screenshot for step 8.4 here (the simulator can't
  load the sandbox price).
- Favorite a water, choose "Allow notifications", and check Settings →
  Trout Truck: Notifications on, Background App Refresh available.
- On first launch the Browse header should show the current week and
  "Last checked …" (the app refreshes on launch); pull down to refresh
  again.
- Add the Home Screen widget; it lists your favorites once unlocked.

## 13. Version page and submit

On the iOS App version page:

1. **Screenshots → iPhone 6.9" Display:** the five PNGs in
   `docs/app-store/screenshots/`, in numbered order. The app is iPhone-only,
   so no iPad set. Upload the 6.5" set only if you made one.
2. **Promotional Text, Description, Keywords, Support URL, Marketing URL,
   Copyright:** from the listing file. Replace `[N]` in the description with
   `coverage.waters_with_history` from the snapshot you bundled.
3. **Build:** **+** → the uploaded build.
4. **In-App Purchases and Subscriptions:** select `Full Access` (a first
   in-app purchase can only be submitted with an app version).
5. **App Review Information:** Sign-in required **off** (no accounts); your
   name, phone and email; **Notes:** paste the "App Review notes" block from
   the listing file (2,407 of 4,000 characters).
6. **Version Release:** **Manually release this version**.
7. **Add for Review → Submit to App Review.**

After approval, press **Release**, then publish the draft GitHub Release
for the same tag.

## What is already done

Checked 2026-10-01 against the code on this branch; `make appstore` re-checks
the first six on every `make verify`.

- One version and one integer build number across the app, widget and test
  targets; both Info.plists take them from the build settings.
- iPhone-only (`TARGETED_DEVICE_FAMILY = 1` everywhere), team `6X5YH93QNM`
  everywhere, iOS 17.0 minimum.
- Export compliance declared (`ITSAppUsesNonExemptEncryption` false); a
  launch screen (`UILaunchScreen`); background modes limited to `fetch` and
  `processing` for the one refresh task.
- Privacy manifests for the app and the widget: no tracking, no tracking
  domains, no collected data, and no required-reason API, which the check
  confirms against every Swift file that ships (no `UserDefaults`, no file
  timestamps, no boot time, no disk space).
- No third-party code: every import is an Apple framework or the local
  `PlantingCore` package, and the project has no remote package.
- App icon: every iPhone size plus the 1024x1024 marketing image, all
  opaque.
- No notification-permission string is needed in `Info.plist`: iOS shows its
  own wording for local notifications, and the app explains first, in its
  "Stay in the loop" sheet.
- Privacy policy and support pages are live on the site; the policy says the
  app collects nothing.
- A release workflow (`.github/workflows/ios-release.yml`) and the signer
  file it verifies against (`.github/allowed_signers`).
