# Google Play listing (paste-ready)

Everything Play Console asks for under Grow users, Store presence, and
Policy, App content, for the free Android build (DECISIONS 0044), in the
order the console asks. The copy leads with the brand line "Trout stocking
schedules, state by state" (DECISIONS 0049). Nothing here is a price, a
purchase or a paid tier, because the build sells nothing. Every claim below
was checked against the code on `main` on 2026-11-07 (the merged manifest
of a debug build, `android/core/.../FreeLaunch.kt`, `StateChoice.kt`,
`Work.kt`, `SnapshotRefresher.kt`, `Review.kt`, the backup rules) and
against the live snapshot of 2026-11-08T01:18Z.

Counts are Python `len()` of the exact string between the backticks, or of
the text between the two rules (line breaks counted, no trailing newline).

**Rules this copy keeps.** It names only the states that are live and
healthy on the day it is pasted. It never says "all states", "every state",
"nationwide", "50 states", "only", "first", "official", or a competitor's
name. "No tracking" is not used; the privacy paragraph says what the app
does not have. It says nothing about iOS, the App Store or any price.

**Tennessee is left out for now.** tn.gov has refused the automated read
since 2026-10-15 (HTTP 403, issue #97); the live snapshot of 2026-11-08
still shows Tennessee with `last_attempt_ok: false` and `last_success_at`
2026-10-15, and the app shows it as "Updates paused since Oct 15, 2026".
DECISIONS 0061 lets the owner load TWRA's downloadable CSV by hand, which
sets `last_success_at` to the download time and `source.read_method` to
`manual`; the app then shows "Read <date>" for seven days and "Updates
paused since <date>" after that, until the next import. Add Tennessee to
this copy only when, on the day you paste, the live snapshot's Tennessee is
either read automatically (`last_attempt_ok: true`) or was imported within
the last seven days and you intend to keep importing at least weekly
(needs Chelsea: that cadence). The text to add back: "Tennessee" in the
first paragraph's state list, the bullet "• Tennessee: TWRA's trout
stocking schedule, by the day, the week or the month, as TWRA gives it.",
"(California, Tennessee)" in the alerts paragraph, "In California and
Tennessee, plants the agency later drops" in the history paragraph, and
"Tennessee Wildlife Resources Agency" in the data line. Re-measure the
count.

## 1. Main store listing

Grow users, Store presence, Main store listing.

| Field | Limit | Value | Chars |
|---|---|---|---|
| App name | 30 | `Trout Truck` | 11 |
| Short description | 80 | `Trout stocking schedules, state by state, with each water's history.` | 68 |
| Full description | 4000 | See [2. Full description](#2-full-description). | 3,059 |

The short description names no state, so it never needs editing when a
state is added or paused.

## 2. Full description

Paste everything between the two rules.

---

Trout stocking schedules, state by state. Trout Truck shows what each state's wildlife agency publishes about trout stocking, exactly as the agency publishes it, and keeps each water's history after the agency's own page moves on. Today that means California, Massachusetts, Michigan and New York. Browsing, search, history, favorites, alerts and the home screen widget are free in each of these states.

Trout Truck is independent. It is not affiliated with or endorsed by any of the agencies below.

EACH STATE, IN ITS AGENCY'S OWN TERMS
Agencies publish different things, and Trout Truck shows each one as it is, never more precise:
• California: CDFW's weekly fish planting schedule, by the week, never a single day.
• Massachusetts: stockings MassWildlife reports as done.
• Michigan: stockings the Michigan DNR reports, often weeks after the fact. The app says so next to the data.
• New York: NYS DEC's spring stocking plan, in DEC's own words such as "April - third week", never turned into a date.

PICK YOUR STATE
Trout Truck opens by asking which state you fish. It never asks for your location: you pick from the list, and you can switch states any time from the States list.

EVERY WATER'S HISTORY
Browse a state's waters by region and county, or search by a water's name, a name the agency used before, or its county. Open a water to see every time it has been on its state's schedule or report since Trout Truck began keeping it, with the species. In California, plants CDFW later drops from its schedule stay in the history, marked as removed.

ALERTS
Trout Truck checks each state's source and publishes one schedule file. The app downloads that file about once a day in the background and tells you on this phone when a favorite is newly scheduled (California) or newly reported as stocked (Massachusetts, Michigan). For New York, you get a reminder when a favorite's planned period begins. Android decides when background checks run, so an alert can arrive a day or more after the agency posts. Mute any one water from the alert itself; it stays a favorite.

HOME SCREEN WIDGET
Add the Favorite waters widget to see your favorites' latest listing without opening the app. It lists your favorites from each state where you have some.

PRIVATE BY DESIGN
No account, no ads, no analytics, no crash reporting, no location. The app downloads one public schedule file. Your favorites stay on your phone and are kept out of cloud backup.

HONEST ABOUT THE DATA
Agencies change plans with road, water, weather and hatchery conditions. Trout Truck says "scheduled", "stocked" or "planned" as the agency does. When a state's source hasn't been readable for more than a week, the app keeps the last data it has and marks that state "Updates paused since" with the date of the last good read, so old data is never shown as new. Check your state's fishing rules and closures before you go.

Data: California Department of Fish and Wildlife; MassWildlife; Michigan Department of Natural Resources; New York State Department of Environmental Conservation.

---

Why each claim is true, in the code: the first-run state picker with no
location is `StateChoice` (DECISIONS 0053, "No location needed"); the
24-hour background refresh is `PeriodicWorkRequestBuilder<RefreshWorker>(24,
TimeUnit.HOURS)` in `Work.kt`; "Updates paused since" after seven days is
`StateChoice.pausedSince` (`PAUSED_AFTER_DAYS = 7`); the alert kinds per
state are the alert planner's (schedule states alert on "newly scheduled",
report states on "newly reported", New York's plan state gets
`ReminderPlanner`); cloud backup is excluded in
`res/xml/backup_rules.xml` and `data_extraction_rules.xml`; the free build
owns every state (`FreeLaunch.entitlements`), so the widget lists favorites
from every state that has them.

## 3. Store settings

Grow users, Store presence, Store settings.

| Field | Value |
|---|---|
| App category | Sports (the owner's 2026-10-29 choice; Travel & Local and Tools are the alternatives, needs Chelsea only if she wants to change it) |
| Tags | None chosen |
| Store listing contact email | `chelsea@chelseakr.com` (shown publicly on the listing) |
| Store listing contact phone | None |
| Store listing website | `https://trouttruck.com/` |
| External marketing | Owner's choice; nothing in the app depends on it |

## 4. Graphics and phone screenshots

The repository does not generate Android screenshots (only iOS has
`ios/scripts/app-store-screenshots.sh`). The files below were made outside
the repository and live in the portfolio's `_agent-tools/growth/` folder:

| Asset | Play rule | File |
|---|---|---|
| App icon, 512 x 512 PNG | required | `_agent-tools/growth/tt-play-graphics/play-icon-512.png` (made 2026-10-29) |
| Feature graphic, 1024 x 500 PNG | required | `_agent-tools/growth/tt-play-graphics/play-feature-graphic-1024x500.png` (made 2026-10-29) |
| Phone screenshots, 1080 x 1920, 24-bit PNG, no alpha | 2 to 8 | `_agent-tools/growth/tt-play-screenshots-2026-11-04/01` to `08` |

The eight frames, in upload order (captured 2026-11-04 from the free
debug build at `1cca6ca` on a Pixel 2 profile emulator, Android 16, with
the committed bundled snapshot and the device clock set to 2026-10-29):

1. `01-browse-california-this-week.png`: Waters tab, California, the week of 2026-10-25.
2. `02-california-water-history.png`: Kings River, Below Pine Flat Dam, with its weekly history.
3. `03-states-all-free.png`: the States sheet; every card has a Browse button and nothing else.
4. `04-michigan-water-stocked.png`: Lake Huron (Adams Point), last stocked, with the DNR's delay note.
5. `05-new-york-planned-for.png`: Saranac River, DEC's plan by period.
6. `06-favorites.png`: four favorites, one tagged This week (one is Tellico River, Tennessee; it shows no price).
7. `07-california-water-alerts-on.png`: a favorited water with "Alerts for this water" on.
8. `08-favorite-waters-widget.png`: the Favorite waters widget on the emulator's stock home screen (drop it if you don't want other apps' icons in the listing; 01 to 07 still meet the minimum).

Each frame was checked on 2026-11-04 for no price, "unlock", "purchase",
"buy", "restore purchases", debug banner or test-store text. Two caveats
for the day you upload:

- The frames show the week of 2026-10-25 and the States sheet's wording of
  that build ("free in every state"); #143 later changed that line to "free
  in each state", and the bundled snapshot will be newer by release. The
  words and dates in the frames are true of the build they came from, not
  of the one you upload. Recapture after `android/scripts/sync-bundled-snapshot.sh`
  runs for the release, if you want them to match exactly.
- The design-identity change (#151, raceway teal and the gold trout) is held
  until 12-21 or later. If it merges before the Play release, the icon,
  feature graphic and frames need remaking in the new look.

## 5. App content answers

Policy, App content. Each answer is what the code does; the console's exact
question wording may differ, so read each question against the facts here.

| Declaration | Answer | Why |
|---|---|---|
| Privacy policy | `https://trouttruck.com/privacy/` | Live page, "Last updated 2026-11-04", says it covers the Android app, that the app is free with no purchases, and names Google Play In-App Review as its one Google library (checked 2026-11-07). Re-fetch it on the day you submit. |
| Ads | No, the app has no ads | No ad SDK; no `AD_ID` permission in the merged manifest. |
| App access | All functionality is available without special access | No account, no login, no region lock inside the app. |
| Content rating | See below | |
| Target audience | 18 and over; "Could your store listing unintentionally appeal to children?" No | The app is text and dates for people who fish; it is not designed for children. Choosing a group under 13 would put it under the Families policy for no reason. (Needs Chelsea only if she wants 13 to 17 included.) |
| News app | No | It republishes agency data; it is not a news app. |
| Data safety | No data collected, no data shared | Section 6. |
| Government app | No | Trout Truck is independent of every agency it credits. |
| Financial features | None | No payments, loans, or money transfers in the app. |
| Health | No | |
| Advertising ID | No, the app does not use advertising ID | `grep -c AD_ID` on the merged debug manifest returns 0 (2026-11-07). |
| Any declaration added after this was written | Read it against sections 5 and 6 | The console adds declarations over time; none of the facts here changes unless the code does. |

### Content rating questionnaire

Policy, App content, Content rating. Start it with `chelsea@chelseakr.com`.
Pick the non-game category the questionnaire offers for a utility or
reference app (the console's label was read as "All other app types" on
2026-11-03; it is not Game, Entertainment or Social). Then:

| Topic the questionnaire asks about | Answer | Why |
|---|---|---|
| Violence (realistic or fantasy, toward people or animals) | No | The app shows agency text and dates; no images or depictions of fishing or fish. |
| Sexual content or nudity | No | |
| Profanity or crude humor | No | |
| Controlled substances (drugs, alcohol, tobacco) | No | |
| Gambling, simulated or real | No | |
| Users interact or exchange content with other users | No | No accounts, chat, comments or user content. "Share" hands a water's name and link to an app the person picks, through Android's share sheet. |
| Shares the user's location with other users | No | No location permission; the first-run picker says "No location needed". |
| Users can purchase digital goods | No | The free build has no billing library, no products and no purchase screen (DECISIONS 0044). |
| Contains ads | No | |
| Unrestricted web access inside the app | No | Links open in the system browser by Intent; there is no in-app web view. |
| Promotes or sells tobacco, alcohol, weapons | No | |

Accept the rating the questionnaire computes; don't guess it in advance.

## 6. Data safety, from what the app does

Policy, App content, Data safety. Google's definition
([Data safety](https://support.google.com/googleplay/android-developer/answer/10787469),
read 2026-11-07): collect means "transmitting data from your app off a
user's device"; data "only processed locally on the user's device and not
sent off device" is not declared; developers must also reflect "data
collected and handled through any third-party libraries or SDKs used in
their apps"; and apps that collect nothing "must complete this form and
provide a link to their privacy policy". Apps active only on the internal
testing track "do not need to complete the Data safety form"; the closed
test does.

| What the app does | Leaves the device? | In the form |
|---|---|---|
| One GET of `snapshot/v2.json` (or `v1.json` when v2 is 404 or 410) from `chelseakr.github.io`, with `HttpURLConnection`, caching off, no cookie handler, a fixed `User-Agent` and `If-None-Match` (`SnapshotRefresher.kt`, `Links.kt`). About every 24 hours (`Work.kt`), on open, and on swipe down. | An HTTP request: the device's IP address is visible to the host (GitHub Pages), with the fixed UA string and the server's own ETag. Nothing about the person, the device or favorites. The developer receives no request logs. | Not declared. Google says IP addresses are declared "based on how you use them"; the app doesn't read, store or use them. |
| Google Play In-App Review card (`review-ktx` 2.0.2, `Review.kt`), asked at most after the second launch at the end of a task, never twice per version, 120 days apart, 3 times a year (`ReviewPrompt.kt`); Play applies its own quota on top. | The card is the Play Store's own UI. Google's page says the data collected is "User-entered data (rating and free-text review)", used "to leave a review on the Play Store", and "if the app is in a closed test track, the data collected is shared privately with the app developer" ([In-app reviews, Data Safety](https://developer.android.com/guide/playcore/in-app-review), read 2026-11-07). The app never receives it. | Recommended: not declared. The app's code transmits nothing the person enters; the Play Store handles the review under Google's terms, and Google says "you are solely responsible for deciding how to respond" to the form. Conservative alternative (needs Chelsea): declare "App activity, Other user-generated content", collected, optional, not shared. If you choose that, the listing's "no analytics, no crash reporting" stays true, but the privacy page should say a review card's text goes to Google. |
| Local notifications (`Notifications.kt`), `POST_NOTIFICATIONS` asked after the app's own explanation sheet | No. No push service, no device token. | Nothing. |
| Favorites, mutes, the alert baseline, the review-prompt record, the onboarding flag and a copy of the schedule, in app-private files | No. Excluded from cloud backup (`backup_rules.xml`, `data_extraction_rules.xml`); a device-to-device transfer carries them. | Not declared (processed locally). |
| "Write to the developer" in About (DECISIONS 0057) | Opens the person's email app with a `mailto:` to `chelsea@chelseakr.com` and the app version in the subject. The person decides whether to send. | Not declared. The app transmits nothing; a sent email is the person's own message to you. |
| Share a water | Android's share sheet with the water's name and its page link; the person picks the app. | Not declared. |
| Links to agency pages, trouttruck.com and the app's Play Store page | Open in the browser or the Play Store app by Intent. | Not declared. |
| Account, analytics, crash reporting, ads, advertising ID, location, contacts, camera, photos, storage | None of these exist in the app. Merged manifest permissions (debug build, 2026-11-07): `INTERNET`, `POST_NOTIFICATIONS`, and WorkManager's `ACCESS_NETWORK_STATE`, `FOREGROUND_SERVICE`, `RECEIVE_BOOT_COMPLETED`, `WAKE_LOCK`, plus AndroidX's `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. | Nothing. |

**The answers.** "Does your app collect or share any of the required user
data types?" No. Privacy policy: `https://trouttruck.com/privacy/`. The
preview should read "No data collected" and "No data shared". The
security-practices questions (encryption in transit, a way to request
deletion) are only asked when something is collected.

## 7. Release notes

For the closed test release (under 500 characters):

`Test build. Please open the app, pick your state and favorite a water or two.`

For the first production release:

`Trout stocking schedules and each water's history for California, Massachusetts, Michigan and New York. Alerts and a home screen widget for your favorite waters.`

## 8. What this copy does not say, and why

- No price, purchase, unlock, Restore purchases, or "coming soon": the free
  build has none (DECISIONS 0044), and a test holds every free-build line to
  that (`FreeLaunchTest.theFreeWordsSellNothing`).
- No iOS or App Store mention: the two platforms differ on price, and the
  App Store copy is frozen during Apple's review.
- No "no tracking": the portfolio rule for this app. The privacy paragraph
  lists what the app does not have instead.
- No "only", "first", "official" or competitor names: Play's and Apple's
  guidance, and the 4.3(a) history.
- No "every state" or "all states" as coverage: only the live states are
  named, and the paused-state sentence covers the one the app carries but
  can't currently refresh.
