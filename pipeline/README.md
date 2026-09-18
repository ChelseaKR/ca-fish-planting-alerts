# pipeline

Fetches CDFW's Fish Planting Schedule, keeps an append-only per-water
history, and builds `schema/snapshot.v1.json` + the static `site/`. Python
3.12, [uv](https://docs.astral.sh/uv/), pytest.

Read `docs/LICENSES-AND-ATTRIBUTION.md` (crawl budget, licence terms) and
`schema/README.md` (the published snapshot contract) before touching this.

## Run it

```sh
cd pipeline
uv sync
uv run cfpa                      # live fetch -> history -> snapshot -> site/
uv run cfpa --no-site            # skip site generation
uv run cfpa --fixture tests/fixtures/schedule-fresh-2026-09-13.html \
            --run-today 2026-09-13   # offline / dry run, no network
uv run pytest                    # full test suite, no network
```

A run that fails for any reason (fetch failure, stale page, table-format
drift, a history-integrity violation, a schema violation) writes nothing new
to `data/history.json`, `data/aliases.json`, or `site/`, and exits non-zero.
See `.github/workflows/publish.yml` for how CI relies on that: the commit,
Pages-artifact-upload, and deploy steps only run after a clean exit.

## Shape

- `src/cfpa/fetch.py` — one HTTP GET of CDFW's schedule page, robots.txt
  check, and freshness detection (`assert_fresh`): the page states its own
  current week in a Time Period widget (the Sunday that starts it -- not the
  fetch day), and a page whose week is not the run date's week (+/- 1 day of
  skew at the boundary) is refused rather than treated as "no plants this
  week".
- `src/cfpa/parse.py` — turns the table into rows. Fails loudly (`ParseError`)
  on any structural surprise (missing table, changed headers, wrong cell
  count, missing `stockid=` map link) rather than emitting a partial table.
- `src/cfpa/aliases.py` — `data/aliases.json`: CDFW's own numeric `stockid`
  is the stable identity; this keeps every spelling ever seen per id, a
  curated canonical name, and a slug that never changes once assigned.
  Prints every newly-seen (id, spelling) pair as `UNMATCHED` on every run.
- `src/cfpa/history.py` — `data/history.json`: append-only. A listed plant
  missing from a later page flips to `removed` only if its week is past the
  page window's oldest week: CDFW ages rows off day by day while still
  stating the same window, so absence in that week means "aged off". `HistoryStore.save`
  loads whatever is on disk first and raises `HistoryIntegrityError` (writing
  nothing) if the new write would drop or mutate an already-recorded
  observation. Only `status` (listed/removed) and `last_observed_at` may
  change after a record is first written.
- `src/cfpa/snapshot.py` — builds the schema-validated snapshot dict from
  history + aliases + the fetched page, plus the coverage report.
- `src/cfpa/site.py` + `templates/` — the static site (Jinja2). Its only
  JavaScript is the Google Analytics 4 tag (`templates/_ga4.html.jinja`),
  and only when a measurement ID is configured; see "Site configuration".
- `src/cfpa/cli.py` — orchestrates the above; `cfpa` console script.

## Data files (committed)

- `data/history.json` — every `(cdfw_stock_id, week_start, species)` ever
  observed. This is the asset (DECISIONS 0005): CDFW's page only shows a
  rolling ~1-year window, so this file is the only place keeping all of it.
  Chosen over a Release asset because it's small (well under a megabyte for
  years of data) and a committed JSON file means every change is a
  reviewable `git diff` / `git blame`, not an opaque binary upload.
- `data/aliases.json` — the id -> canonical name / slug / known-spellings
  table. Also committed, also `git diff`-reviewable; a fresh water starts
  `"reviewed": false` and keeps CDFW's own spelling until someone curates it.

Both are written only through their module's `save()`, which is where the
append-only guarantee (history) and the ever-growing spelling list (aliases)
actually live -- there's no other write path.

## Coverage report

Every run prints one line, always as paired numbers:

```
coverage: waters this week 7/895 known  |  names matched 385/385 seen  |  rows parsed 2039  |  weeks of history per water: min 1, median 4
```

`waters this week` / `waters known` (from CDFW's own water picker on the
page), `names matched` / `names seen` (this run's distinct spellings against
the alias table), `rows parsed` (this run's table rows), and
`weeks of history per water: min, median` (across every water this pipeline
has ever recorded).

## Site configuration

`publish.yml` passes three optional repository variables (Settings ->
Secrets and variables -> Actions -> Variables) to `cfpa`:

- `SITE_BASE_URL` -- canonical URLs, `sitemap.xml`, `robots.txt`. Unset keeps
  `https://chelseakr.github.io/ca-fish-planting-alerts`. Set it when a custom
  domain is attached to Pages.
- `APP_STORE_URL` -- until set, the site says the app is not in the App Store
  yet instead of linking to it.
- `SUPPORT_EMAIL` -- the contact line on `/support/` and `/privacy/`. Unset
  renders no contact line (App Store Connect's Support URL needs one).

The Google Analytics 4 measurement ID is not one of these variables. It is
public, so it is committed: `GA4_MEASUREMENT_ID` in `src/cfpa/site.py`
(currently `G-ZYL3RMXCZF`, property 554849409; DECISIONS 0011). `cfpa` reads
it on every run and refuses the run, writing nothing, if it is not of the
form `G-XXXXXXXXXX`. With an ID, every page gets the tag and a footer
"Opt out of analytics" button. The tag loads nothing when the browser sends
Global Privacy Control or Do Not Track, or when this browser has opted out
(the localStorage key `trout-truck:analytics-opt-out`, read before the tag
loads). With `""`, no page gets any script, and the about, privacy and
support pages say nothing is collected. `build_site()` and `cli.run()` default to no analytics;
only `cfpa`'s `main()` passes the committed ID.

Two more values are committed in `src/cfpa/site.py`, both empty today
(`docs/adr/0013-search-pages-and-truthful-structured-data.md`):

- `GOOGLE_SITE_VERIFICATION` -- the `content` value of Search Console's HTML
  tag. When set, the home page (only) gets
  `<meta name="google-site-verification">`. `cfpa` refuses the run if it is
  not a bare token. The owner's steps are in `docs/SEARCH-CONSOLE.md`.
- `DATASET_LICENSE_URL` -- the licence for the compiled history, stated in the
  Dataset structured data on `/about/`. Empty means no licence is claimed.

Pages built besides the per-water ones: `/` (this week), `/county/` and a
page per county at `/county/<county>/`, `/about/`, `/privacy/` and
`/support/` (the Privacy Policy and Support URLs App Store Connect asks for),
and `/404.html`. Every water page's title and `<h1>` carry its county,
because five CDFW names belong to two or three different waters each. Each
water page links its county pages and every other water in those counties.
Pages carry one schema.org JSON-LD block (ADR 0013): data for search engines,
never executed. `sitemap.xml`'s `<lastmod>` is when a page's data last
changed, not the build date (`site.py::_water_lastmod`, ADR 0013).
`robots.txt` is written, but crawlers only read it at a host's root, so on
the `github.io` URL the sitemap is submitted in Search Console instead.

## Tests

`uv run pytest` runs entirely offline against two committed fixtures in
`tests/fixtures/`: a trimmed-but-real CDFW page (`schedule-fresh-2026-09-13.html`,
41 of the 2,039 rows CDFW served on 2026-09-13, plus its full ~895-water
picker) and a synthetic stale-cache reproduction of the exact bug class
the 2026-09-13 research notes hit on first fetch
(`schedule-stale-2025-cache.html` -- same page, only its stated week
rewritten back a year), plus a real Monday response
(`schedule-empty-week-2026-09-14.html`) and a real Thursday response
(`schedule-midweek-2026-09-17.html`, trimmed to the 2026-09-13 fixture's
waters plus the 29 plants CDFW added in between). Run in sequence, the
2026-09-13 and 2026-09-17 fixtures pin the mid-week freshness check, the
no-false-removal rule for the ageing-off oldest week, and the county
fallback for a water whose rows have all aged off.
