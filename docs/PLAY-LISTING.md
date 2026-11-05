# Google Play listing (draft)

The text for Play Console, Grow users, Store presence, Main store listing,
for the free Android build (DECISIONS 0044). Written 2026-11-05 from the
2026-11-03 closed-test kit's listing, reworded to lead with the brand line
"Trout stocking schedules, state by state" (DECISIONS 0049). Nothing here is
a price, a purchase or a paid tier, because the build sells nothing.

Counts are Python `len()` of the exact string between the backticks, or of
the text between the two rules (line breaks counted, no trailing newline).

**Rules this copy keeps.** It names only the states that are live and
healthy on the day it is pasted. It never says "all states", "every state",
"nationwide", "50 states", "only", "first", "official", or a competitor's
name. "No tracking" is not used; the privacy paragraph says what the app
does not have.

**Tennessee is left out for now.** TWRA's source has not been read
successfully since 2026-10-15 (`last_attempt_ok: false` in
`snapshot/v2.json`). The app still carries Tennessee and shows that date.
Add it back when its `last_attempt_ok` has been true for at least 7 days:
"Tennessee" in the first paragraph's state list, the bullet "Tennessee:
TWRA's trout stocking schedule, by the day, the week or the month, as TWRA
gives it.", "(California, Tennessee)" in the alerts paragraph, "In California
and Tennessee, plants the agency later drops" in the history paragraph, and
"Tennessee Wildlife Resources Agency" in the data line. Re-measure the count.

## Fields

| Field | Limit | Value | Chars |
|---|---|---|---|
| App name | 30 | `Trout Truck` | 11 |
| Short description | 80 | `Trout stocking schedules, state by state, with each water's history.` | 68 |
| Full description | 4000 | See [Full description](#full-description). | 2,588 |
| Category | — | Sports | — |

The short description names no state, so it never needs editing when a
state is added or paused.

## Full description

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

EVERY WATER'S HISTORY
Browse a state's waters, or search by name or county. Open a water to see every time it has been on its state's schedule or report since Trout Truck began keeping it, with the species. In California, plants CDFW later drops from its schedule stay in the history, marked as removed.

ALERTS
Trout Truck checks each state's source in the background and tells you on this phone when a favorite is newly scheduled (California) or newly reported as stocked (Massachusetts, Michigan). For New York, you get a reminder when a favorite's planned period begins. Android decides when background checks run, so an alert can arrive a day or more after the agency posts. Mute any one water from the alert itself; it stays a favorite.

HOME SCREEN WIDGET
Add the Favorite waters widget to see your favorites' latest listing without opening the app. It lists your favorites from each state you follow.

PRIVATE BY DESIGN
No account, no ads, no analytics, no crash reporting. The app downloads one public schedule file. Your favorites stay on your phone and are kept out of cloud backup.

HONEST ABOUT THE DATA
Agencies change plans with road, water, weather and hatchery conditions. Trout Truck says "scheduled", "stocked" or "planned" as the agency does, and when a state's source can't be read, the app says so instead of showing old data as new. Check your state's fishing rules and closures before you go.

Data: California Department of Fish and Wildlife; MassWildlife; Michigan Department of Natural Resources; New York State Department of Environmental Conservation.

---
