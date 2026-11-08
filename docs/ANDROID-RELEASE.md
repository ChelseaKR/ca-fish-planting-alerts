# Android release: from a signed bundle to Google Play

This is the owner's checklist for getting Trout Truck for Android (package
`com.chelseakr.cafishplanting`) from this repository to a Google Play closed
test, then to production. Steps marked **Owner** need Chelsea's Google
account, ID, device or legal attestation; no agent can do them. The app
itself is described in `android/README.md` and `docs/DECISIONS.md` 0022.

The store listing text, the Data safety answers and the content rating
answers are in `docs/PLAY-LISTING.md`, derived from the code. The tester
plan and the owner's dated click-path checklist live outside the repository
(`_agent-tools/growth/tt-android-release-checklist-2026-11-08.md` in the
portfolio). Nothing here posts, submits or changes a Play account.

## What the repository does for you

- `android/app/build.gradle.kts` signs the release build with an upload key
  when four environment variables are set, and does nothing when they are
  not. CI's unsigned `assembleRelease` is unchanged.
- `.github/workflows/android-release.yml` is a manual workflow
  (`workflow_dispatch` is its sole trigger). It builds a signed `.aab` from main and
  uploads it as a workflow artifact. It never talks to Google Play.

The four secrets, by name (values never appear in the repository or the log):

| Secret | What it holds |
|---|---|
| `ANDROID_UPLOAD_KEYSTORE_BASE64` | the upload keystore file, base64 on one line |
| `ANDROID_UPLOAD_KEYSTORE_PASSWORD` | the keystore password |
| `ANDROID_UPLOAD_KEY_ALIAS` | the key alias, `upload` below |
| `ANDROID_UPLOAD_KEY_PASSWORD` | the key password (the same as the keystore password for a PKCS12 keystore) |

If any is unset, the workflow stops before building and names the missing
ones.

## Steps, in order

### 1. Owner: Play Console account

Google's account page
(https://support.google.com/googleplay/android-developer/answer/6112435)
says "There is a US$25 one-time registration fee." and that a personal
account may be asked for "a valid government ID and a credit card, both
under your legal name." A new personal account must also verify access to an
Android device through the Play Console mobile app.

The account's type (personal or organization) and creation date are not
recorded anywhere in this repository or in the portfolio's notes. Read them
in Play Console under Developer account, About you ("Account type (read
only)"). What depends on the answer:

- **Personal, created after November 13, 2023:** the closed-test rule in
  step 9 applies. Google displays "your legal name, your country (as per
  your legal address), and developer email address on Google Play", and "If
  you decide to monetize on Google Play then Google will display your full
  address"
  ([Required information](https://support.google.com/googleplay/android-developer/answer/13628312),
  read 2026-11-07).
- **Organization:** needs a D-U-N-S number, and Google displays "your legal
  name, legal address, developer email address, and developer phone number
  on Google Play" (same page) whether or not the app sells anything. That
  would change the reasoning in 0044, which rests on the address staying
  private while nothing is sold. Google's closed-test page names only
  personal accounts.

Google's [account types page](https://support.google.com/googleplay/android-developer/answer/10840893)
says "Personal and organization accounts have access to the same
functionality" and "You will be able to change your account type if your
circumstances change."

### 2. Nothing to sell: no payments profile step

The Android build sells nothing (`docs/DECISIONS.md` 0044): alerts and the
widget are free in every state, and the build carries no Play Billing
library and no BILLING permission. Google shows a personal account's full
address only when it sells: "If you monetize on Google Play, Google displays
your full address"
([Required information](https://support.google.com/googleplay/android-developer/answer/13628312)).
So skip any payments-profile setup under Settings, Monetization, and create
no in-app products. A personal account's legal name, country and developer
email are still shown.

### 3. Owner: create the app and turn on Play App Signing

In Play Console choose Create app: name `Trout Truck`, default language
English (United States), type App, price Free. A free app can never become
a paid app
([Set the price of your app](https://support.google.com/googleplay/android-developer/answer/6334373)),
which is fine: a later paid version would add in-app products (0044), not a
price. Answer No to in-app purchases. The package name is fixed by the initial bundle
you upload: `com.chelseakr.cafishplanting`. Accept the declarations.

Use Play App Signing (the default for new apps). Google then holds the key
that signs what users install; you hold an upload key, and nothing more, that proves a
bundle came from you. If the upload key is ever lost or leaked, Google can
reset it. Without Play App Signing you would hold the sole copy of the app
key, and losing it would end updates.

### 4. Owner: make the upload key and set the four secrets

Needs a JDK (`keytool`). Do this in a directory outside any git checkout.

Create the keystore (it asks for a password and your name details):

```
keytool -genkeypair -v -storetype PKCS12 -keystore upload-keystore.jks \
  -alias upload -keyalg RSA -keysize 2048 -validity 9125
```

Store it safely before anything else:

- Keep `upload-keystore.jks` and its password in your password manager
  (as a file attachment and a note). Make one more copy on an encrypted
  drive. Never put either in a git repository, an email, a chat or a
  screenshot.
- Losing it is recoverable (Play Console, App integrity, App signing, Request
  upload key reset), but it takes days. Losing Play App Signing's key is not
  recoverable, which is why you do not hold it.

Put the values into GitHub, from a terminal where `gh` is signed in as
ChelseaKR. The base64 goes through the clipboard so it never lands in shell
history:

```
base64 -i upload-keystore.jks | tr -d '\n' | pbcopy
pbpaste | gh secret set ANDROID_UPLOAD_KEYSTORE_BASE64 --repo ChelseaKR/ca-fish-planting-alerts
gh secret set ANDROID_UPLOAD_KEYSTORE_PASSWORD --repo ChelseaKR/ca-fish-planting-alerts
gh secret set ANDROID_UPLOAD_KEY_ALIAS --repo ChelseaKR/ca-fish-planting-alerts
gh secret set ANDROID_UPLOAD_KEY_PASSWORD --repo ChelseaKR/ca-fish-planting-alerts
```

Each of the last three prompts for the value; type `upload` for the alias
and the password you chose for the other two. Then clear the clipboard
(copy any short text) and confirm with
`gh secret list --repo ChelseaKR/ca-fish-planting-alerts`, which lists the
secret names without values.

### 5. Run the workflow

The workflow refuses to run from any branch but main. Version code must be above every earlier
upload's: use 1 for the initial upload, then 2, 3 and so on. The version
name follows `CHANGELOG.md`'s SemVer; the code and name in
`android/app/build.gradle.kts` are the defaults (1 and 1.0.0).

```
gh workflow run android-release.yml --repo ChelseaKR/ca-fish-planting-alerts \
  -f version_code=1 -f version_name=1.0.0
gh run watch --repo ChelseaKR/ca-fish-planting-alerts
gh run download --repo ChelseaKR/ca-fish-planting-alerts -n trout-truck-1.0.0-1-aab
```

Before a release, re-run `android/scripts/sync-bundled-snapshot.sh` in a
reviewed change, so the bundled snapshot is current. The workflow checks the
bundle is signed and carries the committed `assets/snapshot.json`. The run
prints the bundle's SHA-256; the downloaded file should match it
(`shasum -a 256 app-release.aab`).

### 6. No in-app products in this build

The free build (`troutTruck.androidFreeTier=true`, the default) has no
products and nothing to create here. The per-state product IDs stay in
`StateProducts` in `android/core` for a later paid build (0044): if that
build is ever chosen, the products are one-time, one per state, created
then, and creating them makes the account a merchant account that shows the
payments-profile address. Don't create one now: a product ID can't be reused
after it is created.

### 7. Owner: upload to Internal testing

Testing, Internal testing, Create new release, upload `app-release.aab`.
Add a tester list (your own Google account to start) and open the opt-in
link on a real Android phone. Smoke test: the app opens on the bundled
schedule, a water can be favorited in two states, no screen offers a
purchase, a price or a Restore purchases button, an alert can be received
(and a New York reminder, for a New York favorite), and the widget can be
added and lists favorites from more than one state.

Internal testing is separate from the closed test. Google's Data safety page
says apps active only on internal testing tracks "do not need to complete
the Data safety form"; closed, open and production tracks do. Complete the
app setup tasks in the Play Console dashboard now, all from
`docs/PLAY-LISTING.md`: the store listing (sections 1 and 2), store
settings (3), graphics (4), the App content declarations and content rating
(5), and Data safety (6).

### 8. Owner: promote to Closed testing

Testing, Closed testing, create a track. Add testers by email list or by a
Google Group (the listing pack has a plan). Create a release with the same
bundle (or a newer one), and send it for review. Share the track's opt-in
link with testers.

How a tester opts in: they open the opt-in link while signed in to a Google
account that is on your list or in your group, press Become a tester, then
install Trout Truck from the Play Store link on that page. They must stay
opted in, and should keep the app installed.

### 9. The closed-test rule

From Google's page
(https://support.google.com/googleplay/android-developer/answer/14151465):

- "Developers with personal accounts created after November 13, 2023, must run
  a closed test for their app."
- "At least 12 testers must be opted in to your closed test when you apply for
  production access" and they must have "been opted in continuously for at
  least 14 days."

An opt-out and re-entry restarts that tester's count. Aim for 15 to 20 real
opted-in testers so a few dropouts do not reset the plan. Google then
reviews the application: "Review usually takes seven days or less, but can
occasionally take longer."

Google's page said 12 testers and 14 days on 2026-10-20, 2026-11-03 and
2026-11-07; older guidance said 20. Its FAQ adds that "the 14 days must be
consecutive to count toward the minimum requirement of 12 continuous
opted-in testers", and that "Testers who opt in, test for fewer than 14
days, and then opt out do not count toward the requirement." Read the page
again on the day you apply.

### 10. Owner: apply for production access

After 14 days with at least 12 testers opted in continuously, open the
Dashboard in Play Console and choose Apply for production. Answer the
questions plainly: how you recruited testers, the feedback you received and
what you changed, and why the app is ready. Keep a short list of tester
feedback while the test runs. If Google rejects the application, keep the
test running, fix what it names, and apply again.

When approved, create a Production release (staged or 100 percent), complete
the remaining declarations, and send it for review.

## Later releases

Bump `ANDROID_VERSION_CODE` (the workflow input), keep the version name in
step with `CHANGELOG.md`, refresh the bundled snapshot, run the workflow and
upload the new bundle to the track. `targetSdk` is 36 today (checked in the
merged manifest of a debug build on 2026-11-07). Google's target API page
(https://developer.android.com/google/play/requirements/target-sdk, read
2026-11-07) says "Starting August 31 2026: New apps and app updates must
target Android 16 (API level 36) or higher to be submitted to Google Play",
and the extension it offered ran "to November 1, 2026", which has passed.
So the first upload meets the rule with no change. Google raises the level
once a year with an August 31 deadline; read the page before each release
and plan the bump to the next level in the spring.

## Local build

From `android/` with JDK 21 and the Android SDK (`ANDROID_HOME`):

- `./gradlew :app:bundleRelease` builds an unsigned `app-release.aab`.
- To test signing, make a throwaway keystore in a temp directory (not in this
  repository), then set `ANDROID_UPLOAD_KEYSTORE_FILE` (a path),
  `ANDROID_UPLOAD_KEYSTORE_PASSWORD`, `ANDROID_UPLOAD_KEY_ALIAS` and
  `ANDROID_UPLOAD_KEY_PASSWORD` in the shell. Do not use the real upload key
  on a shared machine.

## Known gaps to close before production

- The privacy page (`https://trouttruck.com/privacy/`) covers the Android
  app (checked live 2026-11-07, "Last updated 2026-11-04": "Covers this
  website and the Trout Truck apps for iPhone and Android"; it says the
  Android app is free with no purchases and names Google Play In-App Review
  as its one Google library). Re-check it just before the Data safety form
  is submitted.
- The app fetches its snapshot from `chelseakr.github.io`
  (`SnapshotEndpoint.URL`). The site has moved to `trouttruck.com`, and the
  old address still serves the file; keep it serving until a later Android
  release changes the URL.
- The 512 px icon and the 1024 x 500 feature graphic (made 2026-10-29) and
  eight 1080 x 1920 phone screenshots (captured 2026-11-04 from the free
  debug build on an emulator) exist outside the repository; paths and
  caveats are in `docs/PLAY-LISTING.md` section 4. The repository has no
  script that generates Android screenshots (only iOS has one), so a
  refresh is a manual emulator session.
- The bundled snapshot (`android/app/src/main/assets/snapshot.json`) was
  generated 2026-10-29T13:24Z. Re-run `android/scripts/sync-bundled-snapshot.sh`
  in a reviewed change before the release build.
- The four `ANDROID_UPLOAD_*` repository secrets were not set as of
  2026-11-07 (`gh secret list` showed only `DOMAIN_SITE_DEPLOY_KEY`), so the
  release workflow would stop at its first step.
- Permissions in the merged manifest (debug build, 2026-11-07): `INTERNET`,
  `POST_NOTIFICATIONS`, and from WorkManager `ACCESS_NETWORK_STATE`,
  `FOREGROUND_SERVICE`, `RECEIVE_BOOT_COMPLETED` and `WAKE_LOCK`, plus
  AndroidX's own `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. No `AD_ID` and
  no location permission. If Play Console asks about any of them, that is
  the list.
