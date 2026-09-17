# Decisions

## 0001 — Free static site + paid native app with local notifications (2026-09-13)

The site is the discovery surface (per-water pages rank for "<water> trout
stocking"); the app is the product. Alerts are **local notifications** from a
snapshot the app refreshes itself (BGAppRefreshTask), not server push: no APNs,
no device tokens, no accounts, no email. iOS decides when background refresh
runs, which is honest only because the source updates **weekly** — say so in
the app and the listing. Same architecture as the queer-tv-guide app; reuse it.

## 0002 — Data posture: none (2026-09-13)

Per DATA-GOVERNANCE-STANDARD §4a: "none". No analytics, no cookies, no
third-party script on the site; nothing collected by the app. Per-product
choice; revisit only with data.

## 0003 — Paid up front, one price (2026-09-13, provisional)

One-time purchase, no StoreKit, no subscription. The price is $9.99, one-time. [moved to private strategy notes]

## 0004 — Licence before bytes (2026-09-13)

CDFW's terms are quoted verbatim in `docs/LICENSES-AND-ATTRIBUTION.md` before
any fetch, with the attribution the app and site must show. Unknown = not used.

## 0005 — The history is the asset (2026-09-13)

CDFW publishes the current week only. Keeping every week, forever, per water,
is what no one else offers and what makes "when was X last planted" answerable.
The pipeline never overwrites history; a stale or failed fetch never becomes a
"no plants this week" fact.

## 0006 — Name and domain: undecided

## 0007 — Zero parsed rows is a valid empty week, not a parse error (2026-09-14)

`parse_schedule_table` originally raised on any zero-row table body,
because the 54 weeks of real production data on hand (2025-09-14 to
2026-09-20) never once contained a genuinely empty statewide week -- so the
distinction from a broken/malformed fetch had never been exercised and
looked unsafe to assume. Confirmed live against production on 2026-09-14
by issuing a query (a specific `Params.StockingWaterID` with
`Params.PlantTimeFrame=2`, "Current-Future Plants") guaranteed to match
nothing: CDFW's own server still renders the full `#fishPlantsExternal`
table, with the exact expected `<thead>` and a present, empty `<tbody>` --
not a missing table, not an error page (captured response committed at
`pipeline/tests/fixtures/schedule-empty-week-2026-09-14.html`). Every
structural gate the parser already checks (table found, headers match
exactly, tbody found) still does the job of catching a broken fetch; only
the very last "zero `<tr>`" case was being over-conservative. That case now
returns `[]` instead of raising -- see `parse_schedule_table`'s docstring
for the reasoning kept next to the code.

This does not weaken decision 0005: a stale page is still caught
independently and earlier, in `fetch.py`'s own freshness check, before
`parse_schedule_table` ever sees the HTML.
