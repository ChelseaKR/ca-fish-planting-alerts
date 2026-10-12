# 0021. More states, each a one-time purchase in the one app

Status: Accepted
Date: 2026-10-12
Deciders: Chelsea Kelly-Reif

## Context

On 2026-10-11 the owner decided to take Trout Truck beyond California:
"expand to more states, sold as per-state in-app purchases inside the one
app". Apple's App Review Guideline 4.3(a) asks for one app with in-app
purchases rather than an app per place. The first wave is Tennessee,
Massachusetts and Michigan; New York is optional and on hold. California
stays the base.

The research (`_agent-tools/remediate-2026-10-11/trout-truck-states/RESEARCH.md`)
found those three states' terms clear for reuse, and found that each
publishes something different:

| State | Agency | What it publishes | Precision | License (verbatim in `cfpa/states/*.py`) |
|---|---|---|---|---|
| TN | TWRA | A forward schedule for the year | day, week of a Sunday, or month | TN.gov Linking Policy: copy with attribution and no implied endorsement |
| MA | MassWildlife | A daily report of stockings done | day | The layer's item license: "Permission is granted to copy and use" |
| MI | Michigan DNR | A report of stockings done, weeks late | day | Public record, no restrictions; an indemnity clause |

## Decision

**One app, one product per state.** California's product stays the one
1.0 shipped, `com.chelseakr.cafishplanting.fullaccess`, unchanged in id,
price and meaning: alerts and the widget for California waters. Nobody who
bought it loses anything, and it is not repointed to "all states". Each
other state is its own non-consumable: `com.chelseakr.cafishplanting.state.tn`,
`.state.ma`, `.state.mi` (placeholders until created in App Store
Connect), $9.99 each (placeholder). Browsing, every water's history and
favorites stay free in every state, as in California (0009). A state's
purchase unlocks alerts for that state's favorites and adds them to the
widget (0015); the widget unlocks with any state and counts, never shows,
favorites in states not bought.

**Snapshot v2 beside v1.** `snapshot/v1.json` is built exactly as before
and stays byte-compatible for installed 1.0 builds (a test pins it).
`snapshot/v2.json` (`schema/snapshot.v2.json`) carries every state, with
California derived from the finished v1 so the two can't disagree and its
water ids (`cdfw-<id>`) don't change. Each state says what its records mean
(`semantics`: a `schedule` says "scheduled", a `report` says "stocked") and
at what precision (`day`, `week`, `month`). Nothing is ever shown finer
than the agency gave it: a Tennessee "week of" is never a day, and its
"TBD 12/2026" is "December 2026, day not set". Tennessee's one-letter
month lists ("M, A, M, J, J, A, S") are ambiguous, so they are shown as
TWRA wrote them and never turned into dates.

**Removal inference stays with schedules** (0016). A Tennessee date that
vanishes from TWRA's file before it has passed becomes "schedule changed";
one that has passed has aged off. A report never infers a removal.

**Each state is isolated.** A state's fetch that fails or is refused keeps
its last good data; its `checks` say when it was last read and that the
newest check failed, and California and the other states carry on. A state
with no record is left out of v2 and the site, never shown empty.

**Robots: unreadable means off-limits** (the owner's rule). The state
fetchers read `robots.txt` first and go no further unless it is an HTTP 200
`text/plain` file on the same host that allows the path. Never a browser
User-Agent. On 2026-10-12:

- `www.tn.gov/robots.txt`: 200, `Allow: /`. Tennessee is fetched daily.
- `services1.arcgis.com/robots.txt` (Massachusetts): **403**.
- `utility.arcgis.com/robots.txt` (Michigan): **301 to the arcgis.com home
  page**, not a robots file.

So Massachusetts and Michigan are built and tested against labeled
synthetic fixtures, but `ENABLED_STATES` is `("TN",)`: they are not
fetched, have no data, and do not appear in v2, the site or the app. Their
products exist in the StoreKit configuration only. Enabling either needs an
owner ruling (or a readable robots file) and a first real fetch checked
against the field names in `ma.py` / `mi.py`, which come from the research
description, not from the layers.

**Site.** Every California URL is unchanged. Each other state gets
`/<code>/` and `/<code>/water/<slug>/`, plus `/states/`, all in the sitemap
with structured data (no `Event`; a period is not an event), "stocking"
first in titles, and the state's own attribution and disclaimer on every
page. California's pages gain one header link, "Other states", only when
another state has data.

## Consequences

- California's DECISIONS 0009 and 0015 hold per state. 0018's "one in-app
  purchase" becomes one per state; the price of California's is unchanged.
- Michigan's records lag by weeks, so Michigan's alerts say "stocked on
  <day>" with the lag note, never "this week's stocking".
- Michigan's snapshot carries 2021 onward (`mi.PUBLISH_SINCE`) to keep the
  app's download small; history keeps whatever was fetched.
- The App Store listing (name, subtitle "CA trout stocking alerts",
  screenshots) still says California. It changes when a state goes on sale.
- Open owner questions are in the hand-off: MA/MI robots, Michigan's
  indemnity clause and all-species data, and the $9.99 placeholder price.
