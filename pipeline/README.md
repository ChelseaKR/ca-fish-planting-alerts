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
  "today" in a Time Period widget, and a page whose stated date is more than
  a day off the run date is refused rather than treated as "no plants this
  week".
- `src/cfpa/parse.py` — turns the table into rows. Fails loudly (`ParseError`)
  on any structural surprise (missing table, changed headers, wrong cell
  count, missing `stockid=` map link) rather than emitting a partial table.
- `src/cfpa/aliases.py` — `data/aliases.json`: CDFW's own numeric `stockid`
  is the stable identity; this keeps every spelling ever seen per id, a
  curated canonical name, and a slug that never changes once assigned.
  Prints every newly-seen (id, spelling) pair as `UNMATCHED` on every run.
- `src/cfpa/history.py` — `data/history.json`: append-only. `HistoryStore.save`
  loads whatever is on disk first and raises `HistoryIntegrityError` (writing
  nothing) if the new write would drop or mutate an already-recorded
  observation. Only `status` (listed/removed) and `last_observed_at` may
  change after a record is first written.
- `src/cfpa/snapshot.py` — builds the schema-validated snapshot dict from
  history + aliases + the fetched page, plus the coverage report.
- `src/cfpa/site.py` + `templates/` — the static site (Jinja2, no JS
  anywhere in the output).
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

## Tests

`uv run pytest` runs entirely offline against two committed fixtures in
`tests/fixtures/`: a trimmed-but-real CDFW page (`schedule-fresh-2026-09-13.html`,
41 of the 2,039 rows CDFW served on 2026-09-13, plus its full ~895-water
picker) and a synthetic stale-cache reproduction of the exact bug class
the 2026-09-13 research notes hit on first fetch
(`schedule-stale-2025-cache.html` -- same page, only its stated "today"
rewritten back a year).
