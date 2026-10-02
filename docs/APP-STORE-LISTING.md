# App Store Connect: paste-ready listing copy (draft)

Drafted 2026-09-17, and updated the same day for the name **Trout Truck**
(DECISIONS 0010). This file holds only the text that gets pasted into App
Store Connect. The review-clause analysis, the in-app purchase setup, the
screenshot plan and the TestFlight steps are in `docs/APP-STORE.md`.

Nothing here has been submitted. Everything in `[brackets]` is the owner's to
fill in. Character counts were measured with Python's `len()` on the exact
strings below (for the description, the text between the two rules with
line breaks counted), re-measured after the rename, and the limits are
Apple's.

**What this copy assumes about the product.** It follows the free/paid split
in PR 12 (DECISIONS 0009 there): browsing, history and favorites are free,
and a one-time $9.99 in-app purchase unlocks local notifications. If PR 12 does
not merge, rewrite the "Free / one-time purchase" paragraph and the IAP
description.

**Rules this copy keeps:**
- Plants are "scheduled for the week of…". Never write "stocked on" or a
  single day (CDFW publishes weeks on purpose, and plants are subject to
  change).
- No "only", "first", "nobody else" or "the app for" claims. Other apps
  already cover California stocking.
- No competitor names anywhere in the metadata.
- Counts come from the snapshot at submission time, never from this file.

## Fields

| Field | Limit | Value | Chars |
|---|---|---|---|
| Name | 30 | `Trout Truck` | 11 |
| Subtitle | 30 | `CA stocking schedule & alerts` | 29 |
| Keywords | 100 | `california,fish,fishing,planting,plant,cdfw,stocked,lake,river,creek,reservoir,pond,wildlife,angler` | 99 |
| Promotional text | 170 | `This week's California trout planting schedule and each water's week-by-week history, free to browse. One-time purchase adds alerts and a widget. No account, no tracking.` | 170 |
| Description | 4000 | See [Description](#description) below. | 1,900 |
| Primary category | — | Sports. | — |
| Secondary category | — | **Reference**, not the Weather an earlier draft suggested. The app is a schedule-and-history lookup with no weather content, and guideline 2.3.5 asks for the most appropriate category. | — |
| Age rating | — | Answer "None" to every content question in the questionnaire, which should come out at the lowest tier. There is no user-generated content, no web browsing, no gambling and no messaging. | — |
| Price | — | Free app, plus one non-consumable in-app purchase at $9.99. See `APP-STORE.md` for the product ID. | — |
| Support URL | — | `[SITE]/support/` | — |
| Marketing URL (optional) | — | `[SITE]/` | — |
| Privacy Policy URL | — | `[SITE]/privacy/` | — |
| Copyright | — | `2026 [legal name of the account holder]` | — |

`[SITE]` means `https://chelseakr.github.io/ca-fish-planting-alerts`.
DECISIONS 0010 keeps the site on `github.io` for now. If a custom domain is
set later, it means that domain (repository variable `SITE_BASE_URL`). The
`/support/` and `/privacy/` pages are live (both returned 200 on
2026-09-18). The Support URL still needs the owner to set `SUPPORT_EMAIL`,
because without it the page has no contact line. See step 5 of
`docs/app-store/OWNER-STEPS.md`.

## In-app purchase localization

| Field | Limit | Value | Chars |
|---|---|---|---|
| Display name | 30 | `Full Access` | 11 |
| Description | 45 | `Alerts and a widget for your favorite waters` | 44 |

The description names both things full access unlocks, alerts and the
widget (DECISIONS 0015), within App Store Connect's 45-character limit.
`APP-STORE.md` and `ios/CAFishPlanting/Configuration.storekit` use the same
line.

## Description

Paste everything between the two rules. `[N]` is
`coverage.waters_with_history` from the live snapshot on the day you
submit. It was 385 on 2026-09-17.

---

See which California lakes, reservoirs, rivers and creeks are on the Department of Fish and Wildlife's trout planting schedule, and each water's week-by-week history. Browsing, search and favorites are free. A one-time purchase adds an alert on your phone when a water you've favorited is newly listed, and a Home Screen widget with your favorite waters.

CDFW updates its schedule weekly and lists each plant by the week, never the day. Trout Truck checks the schedule in the background, and when a water you've favorited is newly listed, it schedules an alert on your phone. The source changes weekly and iOS decides when background checks run, so an alert arrives within days of a new listing, not the minute it's posted.

EVERY WATER, WEEK BY WEEK
• Browse [N] waters CDFW has scheduled, or search by water or county, or filter by CDFW region.
• See each water's history: every week it has been on the schedule since September 2025, with the species, kept as CDFW's own one-year window moves on.
• Plants CDFW later drops from its schedule stay in the history, marked as removed.

FREE, WITH ONE OPTIONAL PURCHASE
Browsing, history and favorites are free, with no limit. A one-time purchase unlocks local notifications and the Home Screen and Lock Screen widget for your favorites. No subscription. No account.

PRIVATE BY DESIGN
No account, no ads, no analytics, no tracking. The app makes one kind of network request: it downloads the public schedule file. Your favorites never leave your phone. Privacy label: Data Not Collected.

HONEST ABOUT THE DATA
CDFW notes that all plants are subject to change depending on road, water, weather and operational conditions. So Trout Truck always says "scheduled for the week of", never "stocked on".

Data: California Department of Fish and Wildlife, Fish Planting Schedule. Trout Truck is independent and is not affiliated with or endorsed by CDFW.

---

## App Privacy questionnaire

- **Do you or your third-party partners collect data from this app?** No.
  The label then reads **Data Not Collected**.
- **Why this is accurate:**
  - Favorites and the alert baseline are stored only in the app's
    Application Support directory (`ios/PlantingCore/.../Stores.swift`).
  - The single network call is a GET of the public snapshot over an
    ephemeral `URLSession` (`SnapshotRefresher.swift`), and it carries no
    identifier.
  - There are no third-party SDKs, and `PrivacyInfo.xcprivacy` declares no
    collected data types.
  - GitHub Pages, the static host, sees the request's IP address in the
    ordinary course of serving it. The developer never receives it.
  - The full check, with file references, is in `APP-STORE.md` under
    "Privacy answers, verified in code" (2026-09-18).
- **Tracking (App Tracking Transparency):** none, so no ATT prompt is needed.

### Apple's data categories, one by one

Added 2026-10-01. App Store Connect asks only the first question when the
answer is "No", so this table is for checking the answer, not for pasting.
"Collect" in Apple's sense means data that leaves the device and is
available to the developer or a partner for longer than it takes to
service the request.

| Apple category | Collected? | Why not |
|---|---|---|
| Contact Info (name, email, phone, address) | No | No account, sign-up, form or email anywhere in the app. |
| Health and Fitness | No | No HealthKit, no fitness data. |
| Financial Info | No | The purchase is StoreKit: Apple processes payment; the app sees only its own entitlement, stored on the device. |
| Location (precise or coarse) | No | No Core Location. The county and region filters are pickers over the snapshot. |
| Sensitive Info | No | None is asked for or inferred. |
| Contacts | No | No Contacts framework. |
| User Content | No | Favorites are a JSON file in Application Support and never leave the phone. No photos, messages or uploads. |
| Browsing History | No | No web view; links open Safari, outside the app. |
| Search History | No | Search filters the bundled or downloaded snapshot on the device; no query is sent anywhere. |
| Identifiers (user ID, device ID) | No | No `identifierForVendor`, no advertising identifier, no account ID. The one request carries a fixed `User-Agent: CAFishPlanting` and no identifier. |
| Purchases | No | Purchase history stays with Apple; the app keeps one "unlocked" flag on the device and sends it nowhere. |
| Usage Data (product interaction, advertising data) | No | No analytics SDK and no ads. The website's Google Analytics never runs in the app (no web view; DECISIONS 0011). |
| Diagnostics (crash, performance) | No | No crash-reporting SDK. Crash reports a user chooses to share with Apple are Apple's, not the developer's collection. |
| Other Data | No | The only network request downloads the public schedule file. GitHub Pages sees the request's IP address to serve it, gives the developer no access log, and keeps nothing for the developer. |

`make appstore` fails if a privacy manifest ever gains a collected data type
or tracking, or if a Swift file that ships imports a non-Apple module.

## Age rating answers

Added 2026-10-01 for App Store Connect's current age-rating questionnaire
(App Information → Age Rating). Answer every item as below; the result
should be **4+**. If the questionnaire has an item not listed here, the
answer is still None or No for this app.

| Questionnaire item | Answer | Why |
|---|---|---|
| Parental controls / in-app controls | No | The app has no settings that restrict content. |
| Age assurance | No | No age check; nothing is age-gated. |
| Unrestricted web access | No | No web view or browser. Links open Safari. |
| User-generated content | No | Nothing is posted or shared between users. |
| Messaging and chat | No | None. |
| Advertising | No | No ads. |
| Profanity or crude humor | None | Schedule data only. |
| Horror or fear themes | None | |
| Alcohol, tobacco or drug use or references | None | |
| Mature or suggestive themes | None | |
| Sexual content or nudity | None | |
| Cartoon, fantasy or realistic violence | None | Fishing is the subject; nothing depicts violence. |
| Guns or other weapons | None | |
| Medical or treatment information; health or wellness topics | None | |
| Simulated gambling; contests; gambling | None / No | |
| Loot boxes | No | The one purchase is a fixed, disclosed unlock. |

## App Review notes

Paste this into App Review Information → Notes. The limit is 4,000
characters, and this block is 2,407, measured with Python's `len()`. No
demo account is needed. Revised 2026-09-18 to add the week-of granularity,
the sandbox steps and the notification detail.

---

No account or sign-in exists in this app (5.1.1), so no demo account is needed.

WHAT IT DOES
Trout Truck shows California's public trout planting schedule and keeps each water's week-by-week history, which CDFW's own page does not keep past its one-year window. That history is the main content (4.2). To see it: Browse, search "Kings River", open "Kings River, Below Pine Flat Dam", then tap a year under Stocking history.

WHERE THE DATA COMES FROM
The California Department of Fish and Wildlife (CDFW) Fish Planting Schedule, nrm.dfg.ca.gov/FishPlants/PublicPlantSearch. CDFW lists each plant by week, never by day, and says all plants are subject to change, so the app always shows "week of <date>" and never a stocking day. Our pipeline reads the schedule once a day and publishes one public JSON file: https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json. A copy ships inside the app, so it works offline on first launch; About, "This snapshot", shows which copy is on screen. The app is independent and not affiliated with or endorsed by CDFW; the attribution is on the About screen.

IN-APP PURCHASE (SANDBOX)
One non-consumable product, Full Access (com.chelseakr.cafishplanting.fullaccess). To test: About tab, "Unlock full access", then the purchase button, which shows the price. A tap on the locked Home Screen widget opens it too. After a sandbox purchase, the About tab's "Full access" section reads "Unlocked". "Restore purchases" is on the same sheet. Browsing, history and favorites are free and unlimited; the purchase unlocks notifications and the Home Screen widget.

NOTIFICATIONS ARE LOCAL
There is no push service, no APNs and no device token. Favoriting a water (the star on its page) first shows a short explanation, and the system permission prompt appears only if you choose "Allow notifications". The "fetch" and "processing" background modes (2.5.4) exist only for one BGAppRefreshTask: when iOS runs it, the app downloads the JSON file above and, for purchasers only, schedules a local notification if a favorited water is newly listed. CDFW updates weekly and iOS decides when background refresh runs, so a notification may not fire during review; the entitlement state is visible in About.

PRIVACY
No accounts, analytics, ads or third-party SDKs. The only network request the app makes is the GET of the JSON file above. Favorites stay on the device. Privacy label: Data Not Collected.

---

## Before pasting: open items

Updated 2026-10-01. The ordered steps are in
`docs/app-store/OWNER-STEPS.md`.

| Item | Blocks | Status |
|---|---|---|
| Trademark search | Name field | **Open (owner).** The name is decided (Trout Truck, DECISIONS 0010), but no trademark search has been run (still open 2026-10-01). OWNER-STEPS step 1.3. |
| Support contact | Support URL (guideline 1.5) | **Open (owner).** `/support/` and `/privacy/` are live, but no support address is recorded anywhere in this repo, so `SUPPORT_EMAIL` is unset and the pages have no contact line (still unset 2026-10-01: no repository variable, no `mailto:` on `/support/`). OWNER-STEPS step 5. |
| Live site predates PR 16 and PR 20 | Privacy Policy URL | **Done.** The 03:50 UTC build predated the rename and the GA4 copy; the 06:10 UTC `publish` run on 2026-09-18 brought `/privacy/` up to date (checked, and re-checked 2026-10-01). |
| Free/paid split | Description and IAP text | **Done.** PR 12 merged. |
| "Not affiliated with CDFW" line inside the app | Parity with this description and the review notes | **Done.** PR 19 merged. It shows in About (screenshot `05-about.png`). |
| Screenshots | Submission | **Regenerate before upload.** Five 1320x2868 PNGs are in `docs/app-store/screenshots/`, but they show the week of 2026-09-13 and predate the browse filters in PRs #40 and #41. OWNER-STEPS step 9. |
| Bundled snapshot | First-launch content and the screenshots | **Done, then repeat before archiving.** Refreshed on 2026-09-18 to the live snapshot built at 03:50:44 UTC (week of 2026-09-13, 26 waters this week). Run `ios/scripts/sync-bundled-snapshot.sh` again just before archiving. |
