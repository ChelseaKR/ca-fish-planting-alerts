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
in PR #12 (DECISIONS 0009 there): browsing, history and favourites are free,
and a one-time $9.99 in-app purchase unlocks local notifications. If #12 does
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
| Subtitle | 30 | `CA trout stocking alerts` | 24 |
| Keywords | 100 | `California,fish planting,stocked,catfish,lake,reservoir,creek,river,hatchery,angler,fishing,CDFW` | 96 |
| Promotional text | 170 | `Know when your lake is on California's trout planting schedule. Week-by-week history, local alerts, no account, nothing tracked.` | 128 |
| Description | 4000 | See [Description](#description) below. | 1,647 |
| Primary category | — | Sports. | — |
| Secondary category | — | **Reference**, not the Weather that `APP-STORE.md` suggests. The app is a schedule-and-history lookup with no weather content, and guideline 2.3.5 asks for the most appropriate category. | — |
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
because without it the page has no contact line. See step 2 of the owner
checklist in `APP-STORE.md`.

## In-app purchase localization

| Field | Limit | Value | Chars |
|---|---|---|---|
| Display name | 30 | `Full Access` | 11 |
| Description | 45 | `Alerts when a favourite water is listed` | 39 |

PR #12 first proposed a 156-character IAP description, well over App Store
Connect's 45-character limit. #12 now uses the line above in both
`APP-STORE.md` and `ios/CAFishPlanting/Configuration.storekit`.

## Description

Paste everything between the two rules. `[N]` is
`coverage.waters_with_history` from the live snapshot on the day you
submit. It was 385 on 2026-09-17.

---

Get a notification when a California lake, reservoir or creek you fish appears on the Department of Fish and Wildlife's trout planting schedule.

CDFW updates its schedule weekly and lists each plant by the week, never the day. Trout Truck checks the schedule in the background, and when a water you've favourited is newly listed, it schedules an alert on your phone. The source changes weekly and iOS decides when background checks run, so an alert arrives within days of a new listing, not the minute it's posted.

EVERY WATER, WEEK BY WEEK
• Browse [N] waters CDFW has scheduled, or search by water or county, or filter by CDFW region.
• See each water's history: every week it has been on the schedule since September 2025, with the species, kept as CDFW's own one-year window moves on.
• Plants CDFW later drops from its schedule stay in the history, marked as removed.

FREE, WITH ONE OPTIONAL PURCHASE
Browsing, history and favourites are free, with no limit. A one-time purchase unlocks local notifications for your favourites. No subscription. No account.

PRIVATE BY DESIGN
No account, no ads, no analytics, no tracking. The app makes one kind of network request: it downloads the public schedule file. Your favourites never leave your phone. Privacy label: Data Not Collected.

HONEST ABOUT THE DATA
CDFW notes that all plants are subject to change depending on road, water, weather and operational conditions. So Trout Truck always says "scheduled for the week of", never "stocked on".

Data: California Department of Fish and Wildlife, Fish Planting Schedule. Trout Truck is independent and is not affiliated with or endorsed by CDFW.

---

## App Privacy questionnaire

- **Do you or your third-party partners collect data from this app?** No.
  The label then reads **Data Not Collected**.
- **Why this is accurate:**
  - Favourites and the alert baseline are stored only in the app's
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
One non-consumable product, Full Access (com.chelseakr.cafishplanting.fullaccess). To test: About tab, "Unlock full access", then the purchase button, which shows the price. Nothing else in the app opens this sheet. After a sandbox purchase, the About tab's "Full access" section reads "Unlocked". "Restore purchases" is on the same sheet. Browsing, history and favourites are free and unlimited; the purchase unlocks notifications only.

NOTIFICATIONS ARE LOCAL
There is no push service, no APNs and no device token. Favouriting a water (the star on its page) first shows a short explanation, and the system permission prompt appears only if you choose "Allow notifications". The "fetch" and "processing" background modes (2.5.4) exist only for one BGAppRefreshTask: when iOS runs it, the app downloads the JSON file above and, for purchasers only, schedules a local notification if a favourited water is newly listed. CDFW updates weekly and iOS decides when background refresh runs, so a notification may not fire during review; the entitlement state is visible in About.

PRIVACY
No accounts, analytics, ads or third-party SDKs. The only network request the app makes is the GET of the JSON file above. Favourites stay on the device. Privacy label: Data Not Collected.

---

## Before pasting: open items

Updated 2026-09-18. The ordered steps are the owner checklist in
`APP-STORE.md`.

| Item | Blocks | Status |
|---|---|---|
| Trademark search | Name field | **Open (owner).** The name is decided (Trout Truck, DECISIONS 0010), but no trademark search has been run. Checklist step 1. |
| Support contact | Support URL (guideline 1.5) | **Open (owner).** `/support/` and `/privacy/` are live, but no support address is recorded anywhere in this repo, so `SUPPORT_EMAIL` is unset and the pages have no contact line. Checklist step 2. |
| Live site predates #16 and #20 | Privacy Policy URL | **Done.** The 03:50 UTC build predated the rename and the GA4 copy; the 06:10 UTC `publish` run on 2026-09-18 brought `/privacy/` up to date (checked). Checklist step 3. |
| Free/paid split | Description and IAP text | **Done.** #12 merged. |
| "Not affiliated with CDFW" line inside the app | Parity with this description and the review notes | **Done.** #19 merged. It shows in About (screenshot `05-about.png`). |
| Screenshots | Submission | **Done.** Five 1320x2868 PNGs in `docs/app-store/screenshots/`. See `APP-STORE.md`. |
| Bundled snapshot | First-launch content and the screenshots | **Done, then repeat before archiving.** Refreshed on 2026-09-18 to the live snapshot built at 03:50:44 UTC (week of 2026-09-13, 26 waters this week). Run `ios/scripts/sync-bundled-snapshot.sh` again just before archiving. |
