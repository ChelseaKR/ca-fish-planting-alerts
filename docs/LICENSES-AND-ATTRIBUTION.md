# Sources, terms, attribution

Read before any fetch of the schedule page for pipeline use, 2026-09-13.
Unknown = not used. Nobody is contacted.

| Source | What we take | Terms (verbatim, link, date read) | Commercial reuse OK? | Attribution required | Update cadence / rate |
|---|---|---|---|---|---|
| CDFW fish planting schedule (weekly table) | water name, CDFW stock id, county, species, week planted | Governed by CDFW's site-wide Conditions of Use (below); the schedule page itself carries no separate license notice, only a generic page-info note and a "Copyright © 2026 State of California" footer. | Permitted (see Ownership clause below; no commercial-use, no-automation, or no-deep-link clause exists on this page or its Conditions of Use, unlike parks.ca.gov's) | Yes, as a matter of stated policy (see Attribution decision below) | weekly (CDFW's own cadence); we fetch it once a day |
| CDFW / state of California Conditions of Use (governs the above) | — | `https://wildlife.ca.gov/Conditions-of-Use`, read 2026-09-13, page dated "December 7, 2000": **"Ownership — In general, information presented on this web site, unless otherwise indicated, is considered in the public domain. It may be distributed or copied as permitted by law. However, the State does make use of copyrighted data (e.g., photographs) which may require additional permissions prior to your use. Furthermore, the unique branding of the site and various official seals and marks may not be used without permission of the State. In order to use any information on this web site not owned or created by the State you must seek permission directly from the owning (or holding) sources."** The state-wide equivalent, `https://www.ca.gov/legal/conditions-of-use/` (redirected from `https://www.ca.gov/use/`), read 2026-09-13, carries the identical clause verbatim. Neither page contains any restriction on commercial use, automation, scraping, or deep-linking — a contrast confirmed against the 2026-09-13 research notes §2a, which quotes parks.ca.gov's Conditions of Use doing exactly that ("Commercial Use is Restricted... You may not use any 'deep-link', 'spider' or other automatic device..."). CDFW's page has no such clause. | Permitted — public domain by default, no commercial carve-out | Not textually mandated by this clause alone; attribution required is a policy decision, see below | n/a (site-wide policy) |
| CDFW Fishing Guide dataset on data.ca.gov (a related CDFW product — the ArcGIS-based map, not the live schedule table; its description names "Fish Planting locations" as one of its layers) | corroborating evidence of CDFW's licensing posture for fish-planting data | `https://data.ca.gov/dataset/cdfw-fishing-guide2`, read 2026-09-13: page shows **License: "Creative Commons Attribution"** (linking `http://www.opendefinition.org/licenses/cc-by`) and **Rights: "No restrictions on public use."** | Permitted (CC-BY) | Yes — CC-BY is explicit | Frequency: "Irregular" (per the dataset's own metadata) |
| data.ca.gov open-data policy (cited by the research as governing the above) | — | `https://data.ca.gov/about`, read 2026-09-13: data.ca.gov is described as a state-run open data portal ("a statewide open data portal created to improve collaboration, expand transparency..."); individual datasets each carry their own license field (see row above — CC-BY for the CDFW Fishing Guide). No blanket portal-wide license text beyond the per-dataset field was found. | Governed per-dataset (see above) | Governed per-dataset | n/a |
| USGS Geographic Names Information System (GNIS), Domestic Names, California (text file, published 2026-09-29) | feature names, feature class, county, primary point, used offline by `cfpa-geocode` to find the one federal feature a CDFW water names | `https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits`, read 2026-10-12: **"USGS-authored or produced data and information are considered to be in the U.S. Public Domain."** The file's own metadata (`DomesticNames_CA_Text.xml`), read 2026-10-12: access constraints **"None"**; use constraints **"None. Acknowledgment of the U.S. Geological Survey would be appreciated for products derived from these data."**; liability **"No liability for content or accuracy is presumed by the USBGN or USGS for data."** | Permitted (public domain) | Not required; given anyway (see Water locations below) | Downloaded once by hand, 2026-10-12, from `https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/DomesticNames_CA_Text.zip`; never fetched by the daily run |
| USGS National Hydrography Dataset (NHD), California, GeoPackage (published 2023-12-27) | lake and reservoir polygons and stream flowlines, each tagged with its GNIS id | Same USGS policy page, read 2026-10-12 (quoted above). The file's metadata, read 2026-10-12: access and use constraints **"None"**. `https://www.usgs.gov/information-policies-and-instructions/acknowledging-or-crediting-usgs`, read 2026-10-12: **"Most U.S. Geological Survey (USGS) information resides in the Public Domain and may be used without restriction. When using information from USGS information products, publications, or websites, we ask that proper credit be given."** Suggested form: "Source of (product or data name): U.S. Geological Survey". | Permitted (public domain) | Requested, not required; given | Downloaded once by hand, 2026-10-12, from `https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHD/State/GPKG/NHD_H_California_State_GPKG.zip`; never fetched by the daily run |
| U.S. Census Bureau TIGER/Line Shapefiles 2024, Counties | county polygons, only to test that a point lies in the county CDFW lists | The file's metadata (`tl_2024_us_county.shp.iso.xml`), read 2026-10-12: **"The TIGER/Line Shapefile products are not copyrighted however TIGER/Line and Census TIGER are registered trademarks of the U.S. Census Bureau. These products are free to use in a product or publication, however acknowledgement must be given to the U.S. Census Bureau as the source."** | Permitted | **Yes** (acknowledgement must be given) | Downloaded once by hand, 2026-10-12, from `https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip`; never fetched by the daily run |
| CDFW fishing map (`apps.wildlife.ca.gov/fishing`) | — | Not fetched. It has coordinates, but its terms and robots.txt are unknown, so under "unknown = not used" it is not a source. | n/a — unused | n/a — unused | n/a |

## Attribution decision

Two readings are available: (a) the general Conditions of Use makes CDFW's
page text public domain with no attribution *requirement*, or (b) the
directly-related CDFW Fishing Guide dataset is explicitly CC-BY, which does
require attribution. Per DECISIONS 0004 ("license before bytes... with the
attribution the app and site must show") we take the stricter reading and
attribute unconditionally: every page the site or app shows carries

> Data: California Department of Fish and Wildlife, Fish Planting Schedule
> (`https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch`). Schedule is subject
> to change; treat all plants as scheduled, not confirmed.

This is the `attribution` block written into every `schema/snapshot.v1.json`
(`attribution.text`, `attribution.url`).

## Water locations

`pipeline/data/water_locations.json` is written by `cfpa-geocode` (run by
hand, offline; `pipeline/src/cfpa/geocode.py` has the rules) from the three
federal files above, and only read by the daily run. The attribution shown
with any map or location, on the site's about page and in the app:

> Source of water locations: U.S. Geological Survey, National Hydrography
> Dataset and Geographic Names Information System. County boundaries: U.S.
> Census Bureau, TIGER/Line Shapefiles.

robots.txt for the download hosts, read 2026-10-12 with an honest
User-Agent (`trout-truck-geocode/0.1
(+https://github.com/ChelseaKR/ca-fish-planting-alerts)`) before any
download:

- `www.usgs.gov` (the terms pages): HTTP 200; `User-agent: *` disallows only
  site machinery (`/core/`, `/admin/`, `/search/`, `/user/...` and similar).
  The two policy pages read are not disallowed.
- `prd-tnm.s3.amazonaws.com` (USGS's own published download bucket, linked
  from The National Map's download pages): HTTP 404 with S3's `NoSuchKey`,
  that is, no robots.txt file exists. Read as "no rules" (RFC 9309 section
  2.3.1.3), not as an error; the owner's off-limits ruling was about hosts
  whose robots.txt request fails (for example 403 or a timeout). Two files
  were downloaded, once each.
- `www2.census.gov`: HTTP 200; `User-agent: *` has no `Disallow`. One file
  was downloaded, once.
- `hydro.nationalmap.gov` answered 403 to robots.txt, so its NHD web
  services were not used (off-limits under the owner's ruling).

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
- Budget spent so far today: **2 of at most 5** license/freshness/parse-check
  fetches, **≥ 5 s apart** (used: one redirect probe, one full fetch — see
  `pipeline/tests/fixtures/` for the saved page and headers).
- Going forward: **one fetch per scheduled run, once a day**, with
  `If-None-Match` / `If-Modified-Since` when the server offers validators
  (this server sends `Cache-Control: private` and no `ETag`/`Last-Modified`
  on the live page, so conditional GET may be a no-op — the pipeline still
  sends the headers and logs whether the server honored them).
- Identification: `User-Agent: ca-fish-planting-alerts/<version>
  (+https://github.com/ChelseaKR/ca-fish-planting-alerts)`.
- `robots.txt` is fetched and parsed before every run; the schedule path is
  not fetched if it becomes disallowed.
- Cache headers are honored (no query-string busting, no cache-defeating
  headers sent). A stale page is detected from its own content (the current
  week the page itself states — the Sunday that starts it — compared with
  the run date's week) and refused; it is never treated as "no plants this
  week" — see `pipeline/src/cfpa/fetch.py::assert_fresh`.
- 2026-09-17: **one** extra diagnostic fetch of the schedule page (plus
  `robots.txt`, unchanged), by hand, ≥ 5 s apart, to find out why every
  scheduled run since 2026-09-15 had been refused as stale. It showed the
  page states its week, not its day (see `fetch.py`), and is the source of
  `pipeline/tests/fixtures/schedule-midweek-2026-09-17.html`.

## Other states (DECISIONS 0025)

Read before any fetch, 2026-10-11 (research) and re-read 2026-10-12. The
verbatim clauses live in code next to each source (`pipeline/src/cfpa/states/tn.py`,
`ma.py`, `mi.py`) and are published in each state's `license.sources[].terms_quote`
in `snapshot/v2.json`.

| State | Source we read | Terms | Attribution shown | robots.txt (2026-10-12) | Fetched |
|---|---|---|---|---|---|
| TN | TWRA schedule JSON behind `https://www.tn.gov/twra/fishing/trout-information-stockings.html` | TN.gov Linking Policy, `https://www.tn.gov/web-policies/linking-policy.html`: "The information posted on a TN.gov Web site may be copied so long as it is presented in a non-misleading way and does not imply that either the site owner or the information, as it is presented on the site owner's Web site, is endorsed by the State. Use of the information must identify the state agency that is the source of the information, and the agency's Web address." | "Data: Tennessee Wildlife Resources Agency (TWRA), trout stocking schedule (https://www.tn.gov/twra/fishing/trout-information-stockings.html)." plus "not endorsed by TWRA or the State of Tennessee" | 200, `User-agent: *` / `Allow: /` | Daily, one request each for robots.txt and the file |
| MA | ArcGIS `StockedFish_View/FeatureServer/0` (never the mass.gov page, which is fair use only) | Item license (research, 2026-10-11): "All maps and other material provided herein are protected by copyright. Permission is granted to copy and use the materials herein." | "Data: Massachusetts Division of Fisheries and Wildlife (MassWildlife), trout stocking report (https://www.mass.gov/info-details/trout-stocking-report)." | `services1.arcgis.com`: **403**. Off-limits. | No |
| MI | ArcGIS `DNR/FishStockingReportGISAGO/MapServer/0` | Dataset license, read 2026-10-12 from `www.arcgis.com` item metadata: "there are no restrictions on the use, reproduction, or distribution of this dataset", with an indemnity clause (owner question). | "Data: Michigan Department of Natural Resources, Fish Stocking Database (https://midnr.maps.arcgis.com/apps/dashboards/77581b13c6984b919ab8ed927496a31f)." | `utility.arcgis.com`: **301 to the arcgis.com home page**. Off-limits. | No |

The state fetchers identify themselves with the same User-Agent as the
California fetch, never a browser's, and are stricter about robots.txt (the
owner's rulings, 2026-10-12, DECISIONS 0025): an HTTP 200 `text/plain` file
on that host applies; a 404 (no file) means no rules; anything else (a 403,
a redirect to a page that is not a robots file, a 5xx, a timeout) puts the
host off-limits and it is not contacted further.
