# App Store Connect: paste-ready listing copy (draft)

Drafted 2026-09-17. This file holds only the text that gets pasted into App
Store Connect. The review-clause analysis, the in-app purchase setup, the
screenshot plan and the TestFlight steps are in `docs/APP-STORE.md`.

Nothing here has been submitted. Everything in `[brackets]` is the owner's to
fill in. Character counts were measured with `len()` on the exact strings
below, and the limits are Apple's.

**What this copy assumes about the product.** It follows the free/paid split
in PR #12 (DECISIONS 0009 there): browsing, history and favourites are free,
and a one-time $9.99 in-app purchase unlocks local notifications. If #12 does
not merge, rewrite the "Free / one-time purchase" paragraph and the IAP
description.

**Rules this copy keeps:**
- Plants are "scheduled for the week of…". Never write "stocked on" or a
  single day (CDFW publishes weeks on purpose, and plants are subject to
  change).
- No "only", "first" or "nobody else" claims. Other apps
  already cover California stocking.
- No competitor names anywhere in the metadata.
- Counts come from the snapshot at submission time, never from this file.

## Fields

| Field | Limit | Value | Chars |
|---|---|---|---|
| Name | 30 | `[Name]`. DECISIONS 0006 leaves the name undecided. If the brand is 11 characters or fewer, `[Name]: CA Trout Stocking` puts the highest-intent phrase in the field Apple weights most. | — |
| Subtitle | 30 | `CA trout stocking alerts` | 24 |
| Subtitle, if the name already says "Trout Stocking" | 30 | `Stocking alerts for California` | 30 |
| Keywords | 100 | `California,fish planting,stocked,catfish,lake,reservoir,creek,river,hatchery,angler,fishing,CDFW` | 96 |
| Promotional text | 170 | `Know when your lake is on California's trout planting schedule. Week-by-week history, local alerts, no account, nothing tracked.` | 128 |
| Description | 4000 | See [Description](#description) below. | 1,638 |
| Primary category | — | Sports. | — |
| Secondary category | — | **Reference**, not the Weather that `APP-STORE.md` suggests. The app is a schedule-and-history lookup with no weather content, and guideline 2.3.5 asks for the most appropriate category. | — |
| Age rating | — | Answer "None" to every content question in the questionnaire, which should come out at the lowest tier. There is no user-generated content, no web browsing, no gambling and no messaging. | — |
| Price | — | Free app, plus one non-consumable in-app purchase at $9.99. See `APP-STORE.md` for the product ID. | — |
| Support URL | — | `[SITE]/support/` | — |
| Marketing URL (optional) | — | `[SITE]/` | — |
| Privacy Policy URL | — | `[SITE]/privacy/` | — |
| Copyright | — | `2026 [legal name of the account holder]` | — |

`[SITE]` means `https://chelseakr.github.io/ca-fish-planting-alerts` until a
custom domain is set. Once one is set, it means that domain (repository
variable `SITE_BASE_URL`). The `/support/` and `/privacy/` pages come from
PR #14 and go live on the first successful `publish` run, which needs
PR #13. The Support URL also needs the owner to set `SUPPORT_EMAIL`,
because without it the page has no contact line.

## In-app purchase localization

| Field | Limit | Value | Chars |
|---|---|---|---|
| Display name | 30 | `Full Access` | 11 |
| Description | 45 | `Alerts when a favourite water is listed` | 39 |

PR #12 proposes this IAP description: "Unlocks a notification on this device
whenever one of your favourite waters appears in CDFW's new weekly schedule.
Favouriting and browsing are always free." That is **156** characters,
against App Store Connect's 45-character limit for an IAP description. Use
the line above in the form, or check the form's limit before pasting.

## Description

Paste everything between the two rules. `[N]` is
`coverage.waters_with_history` from the live snapshot on the day you
submit. It was 385 on 2026-09-17.

---

Get a notification when a California lake, reservoir or creek you fish appears on the Department of Fish and Wildlife's trout planting schedule.

CDFW updates its schedule weekly and lists each plant by the week, never the day. This app checks the schedule in the background, and when a water you've favourited is newly listed, it schedules an alert on your phone. The source changes weekly and iOS decides when background checks run, so an alert arrives within days of a new listing, not the minute it's posted.

EVERY WATER, WEEK BY WEEK
• Browse [N] waters CDFW has scheduled, or search by water or county, or filter by CDFW region.
• See each water's history: every week it has been on the schedule since September 2025, with the species, kept as CDFW's own one-year window moves on.
• Plants CDFW later drops from its schedule stay in the history, marked as removed.

FREE, WITH ONE OPTIONAL PURCHASE
Browsing, history and favourites are free, with no limit. A one-time purchase unlocks local notifications for your favourites. No subscription. No account.

PRIVATE BY DESIGN
No account, no ads, no analytics, no tracking. The app makes one kind of network request: it downloads the public schedule file. Your favourites never leave your phone. Privacy label: Data Not Collected.

HONEST ABOUT THE DATA
CDFW notes that all plants are subject to change depending on road, water, weather and operational conditions. So this app always says "scheduled for the week of", never "stocked on".

Data: California Department of Fish and Wildlife, Fish Planting Schedule. This app is independent and is not affiliated with or endorsed by CDFW.

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
- **Tracking (App Tracking Transparency):** none, so no ATT prompt is needed.

## App Review notes

Paste this into App Review Information → Notes. No demo account is needed.

---

This app has no accounts and no sign-in (5.1.1).

What it is: a schedule-and-history app for California's public trout planting schedule, published weekly by the Department of Fish and Wildlife (CDFW). Each water keeps its week-by-week history beyond CDFW's own one-year window, which is the main content. Open any water from Browse to see it.

Network: the app's only request is a GET of one public JSON file, https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json, rebuilt daily from CDFW's schedule. A copy ships in the app, so it works offline on first launch.

Background modes (2.5.4): "fetch" and "processing" are declared only to run one BGAppRefreshTask. It downloads that file and, for purchasers, schedules a local notification when a favourited water is newly listed. There is no push service, no APNs, no location and no audio.

In-app purchase: About → "Unlock full access" (one-time, non-consumable). It unlocks local notifications. Browsing, history and favourites are free. "Restore purchases" is on the same screen.

Alerts depend on CDFW listing a new week, so one may not fire during review. The history view is visible immediately.

The app is independent and not affiliated with CDFW. Data attribution is shown in the app's About screen and on the website.

---

## Before pasting: open items

| Item | Blocks | Owner step |
|---|---|---|
| Name | Name field, and the brand in the copy | Decide (DECISIONS 0006) |
| Live `/support/` and `/privacy/` | Support and Privacy Policy URLs | Merge #13 and #14, let `publish` run, and set `SUPPORT_EMAIL` |
| Free/paid split | Description and IAP text | Merge or reject #12 |
| "Not affiliated with CDFW" line inside the app | Parity with this description and the review notes | The app shows attribution in About but has no non-affiliation line. That is an `ios/` change, which is outside this PR's scope. |
| Screenshots | Submission | See the plan in `APP-STORE.md` |
| Bundled snapshot | First-launch content and the screenshots | `ios/CAFishPlanting/Resources/snapshot.json` is the 2026-09-14 seed. Refresh it from the live `snapshot/v1.json` before archiving, once `publish` has run. This is an `ios/` change. |
