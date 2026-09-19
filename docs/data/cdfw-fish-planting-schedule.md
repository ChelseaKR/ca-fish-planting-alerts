# Data card: CDFW Fish Planting Schedule

The only source the pipeline ingests. Everything the site, the snapshot and
the app show comes from this page. `DATA-GOVERNANCE-STANDARD.md` §1 asks for
one card per ingest source, and `pipeline/tests/test_data_cards.py` fails if
a source the pipeline fetches has no card, or if a card is missing a field.

## Source

- **URL:** https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch (the weekly
  planting table). It is `cfpa.fetch.SCHEDULE_URL`.
- **Publisher:** California Department of Fish and Wildlife (CDFW), a
  California state agency.
- **What is taken:** CDFW's numeric stock id for each water, the water name
  as published, county, species, and the week of each plant. It also takes
  the water picker on the same page, used for counties when a water's rows
  have aged off the table, and the page's own statement of its current week.
- **How:** one HTTP GET per scheduled run, after `robots.txt` has been read
  and allows the path. The request is identified by its `User-Agent`. The
  crawl budget and the rules behind it are in
  `docs/LICENSES-AND-ATTRIBUTION.md`.

## License

Public domain under CDFW's and California's Conditions of Use ("information
presented on this web site, unless otherwise indicated, is considered in the
public domain"), with no commercial-use restriction. No SPDX identifier fits
a state's public-domain policy, so this is the plain-language statement.
The related CDFW Fishing Guide dataset on data.ca.gov gives its license as
"Creative Commons Attribution", without a version. The stricter of the two
readings is taken, so every page and the snapshot attribute CDFW
unconditionally. Verbatim terms, links and the date they
were read (2026-09-13) are in `docs/LICENSES-AND-ATTRIBUTION.md`.

## Fetch/refresh cadence

- CDFW updates the schedule **weekly** and lists plants by week, never by
  day. The pipeline fetches **once a day** (`publish.yml`, 13:17 UTC).
- **Staleness SLA:** a page whose stated current week is not the run date's
  week (±1 day at the Sunday boundary) is refused. No snapshot is built and
  nothing is committed or deployed (`cfpa.fetch.assert_fresh`). A stale page
  is never published as "no plants this week". A refused or failed run
  opens an issue (`publish.yml` `alert-on-failure`), so the operator is told
  within a day.
- What readers see: every site page says when the schedule was last checked.
  The app shows the snapshot's build time on its About screen only. Showing
  staleness on the app's main screens is part of #8.

## Fetch timestamp

Machine-readable, UTC, on every layer:

- `snapshot.source.fetched_at`: when the page was fetched, and
  `snapshot.generated_at`: when the snapshot was built
  (`schema/snapshot.v1.json`).
- `history.json` plants: `first_observed_at` and `last_observed_at` on
  every record.
- `snapshot.source.content_sha256`: the hash of the fetched page, so a
  snapshot can be tied to the exact bytes it was built from.

## Tier

**L1: public, non-sensitive** (`DATA-GOVERNANCE-STANDARD.md` §0). Hatchery
stocking schedules for public waters. The source holds no personal data,
and the pipeline takes none from it.

## Known limitations

- **Week-of granularity only.** A plant is "the week of <date>", never a
  day. CDFW does not publish days.
- **Subject to change.** CDFW's schedule can move or cancel a plant. Every
  surface says "scheduled, not confirmed".
- **About a year of history on CDFW's page.** Rows age off one day at a
  time. `history.json` keeps every week ever seen (DECISIONS 0005), and a
  row that ages off is not recorded as a cancellation.
- **Names drift.** CDFW's stock id is the stable identity. Spellings are
  mapped through `pipeline/data/aliases.json`, and every unmatched spelling
  is printed on every run.
- **The page has served a stale cache before** (the 2025 cache on the first
  fetch, 2026-09-13). That is why the freshness check exists.
- No location coordinates. No geocoding source is used.

## Retention

Indefinite: this history is the product (`DATA-GOVERNANCE-STANDARD.md` §2,
DG-06). If CDFW revokes or relicenses the data, it is removed within 30 days
of notice. That removal is manual and would be tracked as an issue.
`pipeline/data/history.json` is append-only in code
(`HistoryStore.save` raises rather than drop or rewrite a recorded plant), and
git keeps every prior version.

## Dataset version

The snapshot carries `schema_version: 1` and its timestamps, but no dataset
version of its own. Whether it should have one (DG-17/18) is open in #8.

---

Last verified: 2026-09-17 · Recheck cadence: when CDFW changes the page or
its Conditions of Use, and at least quarterly.
