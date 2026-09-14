# Sources, terms, attribution

Read before any fetch of the schedule page for pipeline use, 2026-09-13.
Unknown = not used. Nobody is contacted.

| Source | What we take | Terms (verbatim, link, date read) | Commercial reuse OK? | Attribution required | Update cadence / rate |
|---|---|---|---|---|---|
| CDFW fish planting schedule (weekly table) | water name, CDFW stock id, county, species, week planted | Governed by CDFW's site-wide Conditions of Use (below); the schedule page itself carries no separate licence notice, only a generic page-info note and a "Copyright © 2026 State of California" footer. | Permitted (see Ownership clause below; no commercial-use, no-automation, or no-deep-link clause exists on this page or its Conditions of Use, unlike parks.ca.gov's) | Yes, as a matter of stated policy (see Attribution decision below) | weekly (CDFW's own cadence); we fetch it once a day |
| CDFW / state of California Conditions of Use (governs the above) | — | `https://wildlife.ca.gov/Conditions-of-Use`, read 2026-09-13, page dated "December 7, 2000": **"Ownership — In general, information presented on this web site, unless otherwise indicated, is considered in the public domain. It may be distributed or copied as permitted by law. However, the State does make use of copyrighted data (e.g., photographs) which may require additional permissions prior to your use. Furthermore, the unique branding of the site and various official seals and marks may not be used without permission of the State. In order to use any information on this web site not owned or created by the State you must seek permission directly from the owning (or holding) sources."** The state-wide equivalent, `https://www.ca.gov/legal/conditions-of-use/` (redirected from `https://www.ca.gov/use/`), read 2026-09-13, carries the identical clause verbatim. Neither page contains any restriction on commercial use, automation, scraping, or deep-linking — a contrast confirmed against the 2026-09-13 research notes §2a, which quotes parks.ca.gov's Conditions of Use doing exactly that ("Commercial Use is Restricted... You may not use any 'deep-link', 'spider' or other automatic device..."). CDFW's page has no such clause. | Permitted — public domain by default, no commercial carve-out | Not textually mandated by this clause alone; attribution required is a policy decision, see below | n/a (site-wide policy) |
| CDFW Fishing Guide dataset on data.ca.gov (a related CDFW product — the ArcGIS-based map, not the live schedule table; its description names "Fish Planting locations" as one of its layers) | corroborating evidence of CDFW's licensing posture for fish-planting data | `https://data.ca.gov/dataset/cdfw-fishing-guide2`, read 2026-09-13: page shows **License: "Creative Commons Attribution"** (linking `http://www.opendefinition.org/licenses/cc-by`) and **Rights: "No restrictions on public use."** | Permitted (CC-BY) | Yes — CC-BY is explicit | Frequency: "Irregular" (per the dataset's own metadata) |
| data.ca.gov open-data policy (cited by the research as governing the above) | — | `https://data.ca.gov/about`, read 2026-09-13: data.ca.gov is described as a state-run open data portal ("a statewide open data portal created to improve collaboration, expand transparency..."); individual datasets each carry their own licence field (see row above — CC-BY for the CDFW Fishing Guide). No blanket portal-wide licence text beyond the per-dataset field was found. | Governed per-dataset (see above) | Governed per-dataset | n/a |
| Any geocoding source for water locations | lat/long per water | Not fetched. No geocoding source was read or used. | n/a — unused | n/a — unused | n/a |

## Attribution decision

Two readings are available: (a) the general Conditions of Use makes CDFW's
page text public domain with no attribution *requirement*, or (b) the
directly-related CDFW Fishing Guide dataset is explicitly CC-BY, which does
require attribution. Per DECISIONS 0004 ("licence before bytes... with the
attribution the app and site must show") we take the stricter reading and
attribute unconditionally: every page the site or app shows carries

> Data: California Department of Fish and Wildlife, Fish Planting Schedule
> (`https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch`). Schedule is subject
> to change; treat all plants as scheduled, not confirmed.

This is the `attribution` block written into every `schema/snapshot.v1.json`
(`attribution.text`, `attribution.url`).

## robots.txt

`https://nrm.dfg.ca.gov/robots.txt`, read 2026-09-13: `Sitemap:
http://nrm.dfg.ca.gov/sitemap.xml` only — no `Disallow` rules, no
`Crawl-delay`. The schedule path is not disallowed. Checked programmatically
before every fetch regardless (see `pipeline/src/cfpa/fetch.py`).

## Crawl budget (declared 2026-09-13, before the first fetch)

- Source: one page, `https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch`
  (the weekly table; `https://nrm.dfg.ca.gov/FishPlants/` 301-redirects to
  it). No other CDFW page is crawled; the terms pages above were read once,
  by hand, outside the pipeline.
- Budget spent so far today: **2 of at most 5** licence/freshness/parse-check
  fetches, **≥ 5 s apart** (used: one redirect probe, one full fetch — see
  `pipeline/tests/fixtures/` for the saved page and headers).
- Going forward: **one fetch per scheduled run, once a day**, with
  `If-None-Match` / `If-Modified-Since` when the server offers validators
  (this server sends `Cache-Control: private` and no `ETag`/`Last-Modified`
  on the live page, so conditional GET may be a no-op — the pipeline still
  sends the headers and logs whether the server honoured them).
- Identification: `User-Agent: ca-fish-planting-alerts/<version>
  (+https://github.com/ChelseaKR/ca-fish-planting-alerts)`.
- `robots.txt` is fetched and parsed before every run; the schedule path is
  not fetched if it becomes disallowed.
- Cache headers are honoured (no query-string busting, no cache-defeating
  headers sent). A stale page is detected from its own content (the newest
  "today" date the page itself states, compared with the run's actual date)
  and refused; it is never treated as "no plants this week" — see
  `pipeline/src/cfpa/fetch.py::assert_fresh`.
