# App Store listing for the multistate version (draft)

Written 2026-10-24 for the version after 1.0.0: California plus Tennessee,
Massachusetts, Michigan and New York, each state its own one-time purchase
(DECISIONS 0025, 0034), with iPad, Apple Watch and the rating prompt that are
already on `main`. Nothing here has been pasted into App Store Connect. The
1.0.0 copy that is in review stays in `docs/APP-STORE-LISTING.md`; this file
replaces it only when the multistate version is created, after 1.0.0 leaves
review. `LISTING-MULTISTATE` tests (`StateProductListingTests`) hold the
limits, the stated counts and the purchase table to the StoreKit file.

Counts are Python `len()` of the exact string between the backticks, or of the
text between the two rules for long fields (line breaks counted, no trailing
newline).

## Why this copy reads the way it does (4.3)

1.0.0 was rejected once for 4.3(a) (similar binary, metadata or concept), and
several one-person "app factory" stocking apps launched in October 2026. Apple
asks for one app with in-app purchases instead of an app per place, which is
what this version is. The copy keeps the listing from reading like a
template:

- It leads with what is particular to this app: each water's history kept
  after the agency's own page moves on, and each state's data shown exactly
  as the agency publishes it (a week, a day, a month, a report after the
  fact, or a plan in the agency's own words). It does not lead with "alerts
  for every state".
- It names the five agencies and says what each one publishes. It never
  says "all states", "every state", "only", "first", or a competitor's name.
- The screenshots (owner step) show a different state on each frame, with
  the state's own wording visible: "scheduled", "stocked", "planned".
- Queer Frame and Lake Notice share the code pattern, so this listing
  shares no sentence with theirs. Check by eye before pasting.

## Fields

| Field | Limit | Value | Chars |
|---|---|---|---|
| Name | 30 | `Trout Truck` | 11 |
| Subtitle | 30 | `Stocking schedules & history` | 28 |
| Keywords | 100 | `california,tennessee,michigan,massachusetts,new york,cdfw,twra,dnr,dec,planting,stocked,lake,river` | 98 |
| Promotional text | 170 | `Trout stocking in California, Tennessee, Massachusetts, Michigan and New York. Browse free; a one-time purchase per state unlocks alerts and the widget. No subscription.` | 169 |
| Description | 4000 | See [Description](#description). | 2,943 |
| What's New | 4000 | See [What's New](#whats-new). | 801 |
| Support URL | — | `https://trouttruck.com/support/` | — |
| Marketing URL | — | `https://trouttruck.com/` | — |
| Privacy Policy URL | — | `https://trouttruck.com/privacy/` | — |
| Categories | — | Sports, then Reference (unchanged) | — |
| Price, storefronts | — | Free app; United States only (unchanged, DECISIONS 0018) | — |

The subtitle names no state, so it never needs editing when a state is added
or paused; the state names are in the keywords, where Apple combines them
with the name and subtitle words ("tennessee trout stocking" still matches).
No keyword repeats a word from the name or subtitle.

No customer-facing field states a price. The App Store shows each in-app
purchase's price on the product page and on the purchase sheet, a written
price goes stale the day the price changes, and Guideline 2.3.7 warns
against pricing information in metadata. `StateProductListingTests` checks
the promotional text, description and What's New for a price.

## Description

`[N]` is each state's `waters_count` in the live `snapshot/v2.json` on the
day you submit. Paste everything between the two rules.

---

Trout Truck keeps the trout stocking schedule for California, Tennessee, Massachusetts, Michigan and New York in one place, and keeps each water's history after the agency's own page moves on. Browsing, search, history and favorites are free in every one of these states. A one-time purchase for a state adds alerts for your favorites there, plus the Home Screen widget and Apple Watch.

EACH STATE, IN ITS AGENCY'S OWN TERMS
Agencies publish different things, and Trout Truck shows each one as it is, never more precise:
• California: CDFW's weekly planting schedule, by the week.
• Tennessee: TWRA's trout stocking schedule, by the day, the week or the month, as TWRA gives it.
• Massachusetts: stockings MassWildlife reports as done.
• Michigan: stockings the Michigan DNR reports, often weeks after the fact. The app says so next to the data.
• New York: NYS DEC's spring stocking plan, in DEC's own words such as "April - third week", never turned into a date.

EVERY WATER'S HISTORY
Open a water to see every time it has been on its state's schedule or report since Trout Truck began keeping it, with the species. In California and Tennessee, plants the agency later drops from its schedule stay in the history, marked as removed.

ALERTS, PER STATE
With a state's purchase, Trout Truck checks that state's source in the background and tells you on this device when a favorite is newly scheduled (California, Tennessee), newly reported as stocked (Massachusetts, Michigan), or when its planned period begins (New York). iOS decides when background checks run, so an alert can arrive a day or more after the agency posts. Mute any one water from the alert itself; it stays a favorite.

ON IPHONE, IPAD AND APPLE WATCH
• iPad shows the list beside the water.
• Apple Watch shows your favorites and a Next favorite complication, from the iPhone app's purchase.
• Home Screen and Lock Screen widgets, a Shortcuts action, VoiceOver, Dynamic Type and dark mode.

ONE PAYMENT PER STATE, NO SUBSCRIPTION
Each state is a one-time purchase, and the App Store shows its price. If you bought Full Access, it still covers California exactly as before. Restore purchases brings back each state you bought on a new device.

PRIVATE BY DESIGN
No account, no ads, no analytics, no tracking. The app downloads one public schedule file; your favorites never leave your device. Privacy label: Data Not Collected.

HONEST ABOUT THE DATA
Agencies change plans with road, water, weather and hatchery conditions. Trout Truck says "scheduled", "stocked" or "planned" as the agency does, and when a state's source can't be read, the app says so instead of showing old data as new.

Data: California Department of Fish and Wildlife; Tennessee Wildlife Resources Agency; MassWildlife; Michigan Department of Natural Resources; New York State Department of Environmental Conservation. Trout Truck is independent and is not affiliated with or endorsed by any of them.

---

## What's New

Paste everything between the two rules.

---

Four more states, iPad and Apple Watch.
• Tennessee, Massachusetts, Michigan and New York, free to browse, each with its own one-time purchase for alerts, the widget and Apple Watch. Full Access still covers California exactly as before.
• New York favorites get a reminder when their planned stocking period begins, in DEC's own words.
• The purchase screen now says when each state's data was last read, and says plainly if the newest check failed.
• iPad shows the list beside the water.
• Apple Watch: your favorites and a Next favorite complication, plus a round Lock Screen widget on iPhone.
• "Mute this water" on an alert turns off that water's alerts without opening the app.
• A short introduction for new installs, a light tap when a refresh finishes, and a "Rate Trout Truck" row in About.

---

## In-app purchases

California's Full Access is unchanged: same Product ID, price and display
name. Its live description is `Alerts and a widget for your favorite waters`
(checked read-only 2026-10-24); change it to the StoreKit file's
`Alerts, widget, Watch: your favorite waters` with this version, not before
(it names Apple Watch, which 1.0.0 does not have).

The four new products. Every value matches
`ios/CAFishPlanting/Configuration.storekit`, `StateAccess.productIDsByState`
and `docs/APP-STORE.md`.

| State | Product ID | Reference Name | Display Name | Description | Desc. chars |
|---|---|---|---|---|---|
| TN | `com.chelseakr.cafishplanting.state.tn` | `Tennessee access` | `Tennessee` | `Alerts, widget, Watch: Tennessee waters` | 39 |
| MA | `com.chelseakr.cafishplanting.state.ma` | `Massachusetts access` | `Massachusetts` | `Alerts, widget, Watch: Massachusetts waters` | 43 |
| MI | `com.chelseakr.cafishplanting.state.mi` | `Michigan access` | `Michigan` | `Alerts, widget, Watch: Michigan waters` | 38 |
| NY | `com.chelseakr.cafishplanting.state.ny` | `New York access` | `New York` | `Reminders, widget, Watch: New York waters` | 41 |

All four: Non-Consumable, USD 9.99, United States only, Family Sharing off
(as California's is in App Store Connect). New York's says "Reminders"
because its purchase adds a reminder when a planned period begins, not an
alert about a new listing.

## App Review notes

Add this block after the 1.0.0 notes' 4.3(a) explanation, and change the
snapshot URL in those notes to `snapshot/v2.json`. Keep the total under
4,000 characters.

---

MORE STATES, ONE APP (4.3(a))
This version adds Tennessee, Massachusetts, Michigan and New York inside the same app, each as its own non-consumable in-app purchase, rather than a separate app per state. California's Full Access product is unchanged and still covers California.

TO SEE A STATE'S PURCHASE
Browse, then the map icon at the top left ("States and full access"), then a state, then "Unlock alerts and widget". Restore purchases is on the same screen. Browsing and every water's history stay free in each of the five states. The purchase sheet shows when that state's data was last read.

WHAT EACH STATE'S DATA IS
Tennessee's is a schedule; Massachusetts' and Michigan's are reports of stockings already done (Michigan's often weeks later, which the app says); New York's is a spring plan in the agency's own words, never turned into dates. New York's purchase adds reminders when a favorite's planned period begins.

---
