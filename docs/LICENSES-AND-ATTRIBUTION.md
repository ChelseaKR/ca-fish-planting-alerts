# Sources, terms, attribution

To be completed before any fetch. Unknown = not used. Nobody is contacted.

| Source | What we take | Terms (verbatim, link, date read) | Commercial reuse OK? | Attribution required | Update cadence / rate |
|---|---|---|---|---|---|
| CDFW fish planting schedule (weekly table) | water name, county, species, week planted | | | | weekly |
| CDFW / data.ca.gov open-data policy | (governs the above) | | | | |
| Any geocoding source for water locations (if used) | lat/long per water | | | | |

## Crawl budget (declared 2026-09-13, before the first fetch)

- Source: one page, `https://nrm.dfg.ca.gov/FishPlants/` (the weekly table). No
  other CDFW page is crawled; the terms pages below are read once, by hand.
- Budget: **at most 5 fetches of the schedule page on 2026-09-13** (licence
  read, then freshness + parse checks), **≥ 5 s apart**; thereafter **one fetch
  per scheduled run, once a day**, with `If-None-Match` / `If-Modified-Since`
  when the server offers validators.
- Identification: `User-Agent: ca-fish-planting-alerts/<version>
  (+https://github.com/ChelseaKR/ca-fish-planting-alerts)`.
- `robots.txt` for `nrm.dfg.ca.gov` is read first and honoured; the schedule
  path is not fetched if it is disallowed.
- Cache headers are honoured (no query-string busting). A stale page is
  detected from its own content (the newest "week of" date it lists compared
  with today) and refused; it is never treated as "no plants this week".
