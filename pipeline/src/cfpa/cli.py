"""Orchestrate one pipeline run: fetch -> parse -> match -> history -> snapshot
-> validate -> site -> coverage report.

A failed run (fetch failure, stale page, a page showing a partial Time Period
view, parse drift, a live fetch with too few rows, history-integrity violation,
schema validation failure) writes nothing new and exits non-zero.
There is no code path that publishes a partial or assumed result.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import jsonschema

from . import VERSION
from . import aliases as aliases_mod
from . import fetch as fetch_mod
from . import history as history_mod
from . import legacy as legacy_mod
from . import locations as locations_mod
from . import parse as parse_mod
from . import site as site_mod
from . import snapshot as snapshot_mod
from . import snapshot_v2 as snapshot_v2_mod
from . import source_log as source_log_mod
from . import species_aliases as species_aliases_mod
from . import states as states_mod
from .states import base as states_base
from .states import run as states_run
from .states import store as states_store

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE_DIR.parent
DEFAULT_HISTORY_PATH = PIPELINE_DIR / "data" / "history.json"
DEFAULT_ALIASES_PATH = PIPELINE_DIR / "data" / "aliases.json"
DEFAULT_SPECIES_ALIASES_PATH = PIPELINE_DIR / "data" / "species_aliases.json"
DEFAULT_SOURCE_LOG_PATH = PIPELINE_DIR / "data" / "source_log.json"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
DEFAULT_V2_SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v2.json"
DEFAULT_STATES_DIR = PIPELINE_DIR / "data" / "states"
DEFAULT_LOCATIONS_PATH = PIPELINE_DIR / "data" / "water_locations.json"
DEFAULT_SITE_OUT = REPO_ROOT / "site"
DEFAULT_BASE_URL = site_mod.LEGACY_BASE_URL


class PipelineError(RuntimeError):
    pass


def print_unlisted_report(unlisted: Sequence[snapshot_mod.UnlistedWater]) -> None:
    """Say loudly, on stderr, which waters with history were left out of this
    run's snapshot because neither CDFW's table nor its picker names them.

    Silent on an empty list. Under GitHub Actions it also emits a ``::warning``
    workflow command, so the run's summary page shows it without opening the
    log. It does not change the exit status: the data is right, and a failed
    step would stop the commit and deploy steps for every other water.
    """
    if not unlisted:
        return
    n = len(unlisted)
    print(
        f"cfpa: WARNING {n} {'water' if n == 1 else 'waters'} with history "
        f"{'is' if n == 1 else 'are'} in neither CDFW's schedule table nor its water "
        "picker on this fetch. Left out of this run's snapshot and site; "
        "their history is kept, not deleted:",
        file=sys.stderr,
    )
    for u in unlisted:
        print(
            f"  cdfw-{u.cdfw_stock_id} {u.name}: {u.records} record(s) on file, "
            f"{u.listed_records} still listed, newest week of {u.newest_week_start}",
            file=sys.stderr,
        )
    print(
        "  They come back on their own if CDFW lists them again. Until then the "
        "app tells a user who favorited one that the schedule no longer lists it.",
        file=sys.stderr,
    )
    if os.environ.get("GITHUB_ACTIONS") == "true":
        ids = ", ".join(f"cdfw-{u.cdfw_stock_id}" for u in unlisted)
        print(
            "::warning title=Waters CDFW no longer lists::"
            f"{n} {'water' if n == 1 else 'waters'} with history left out of "
            f"this run's snapshot (history kept): {ids}"
        )


def _report_source_staleness(path: Path, page: fetch_mod.FetchedPage) -> None:
    """Record this run's content hash and warn when it has not changed for
    ``source_log.STALE_SOURCE_DAYS``. Advisory: a log that cannot be read or
    written is reported and skipped, and never fails the run."""
    try:
        log = source_log_mod.SourceLog.load(path)
        cold_start = not log.runs
        log.record(page.fetched_at.date(), page.content_sha256)
        log.save(path)
    except (OSError, source_log_mod.SourceLogError) as exc:
        print(
            f"cfpa: WARNING the source log could not be updated, so unchanged-page "
            f"detection is off for this run: {exc}",
            file=sys.stderr,
        )
        return
    source_log_mod.print_report(log.unchanged_days(), cold_start=cold_start)


def _load_locations(path: Path | None) -> dict[int, dict[str, Any]] | None:
    """The committed coordinates, or None. A file that fails its own checks
    refuses the run like any other bad input, before anything is written."""
    if path is None:
        return None
    try:
        return locations_mod.load_locations(path)
    except (OSError, ValueError, KeyError) as exc:
        raise snapshot_v2_mod.SnapshotV2Error(
            f"water locations at {path} could not be read: {exc}"
        ) from exc


def run(
    *,
    fixture_path: str | None,
    history_path: Path,
    aliases_path: Path,
    species_aliases_path: Path = DEFAULT_SPECIES_ALIASES_PATH,
    schema_path: Path,
    site_out: Path,
    base_url: str,
    write_site: bool = True,
    legacy_site_out: Path | None = None,
    app_store_url: str | None = None,
    app_store_live: bool = False,
    support_email: str | None = None,
    ga4_measurement_id: str | None = None,
    google_site_verification: str | None = None,
    fixture_fetched_at: dt.datetime | None = None,
    run_today: dt.date | None = None,
    states_dir: Path | None = None,
    states_fetch: Sequence[str] = (),
    states_fixtures: Path | None = None,
    v2_schema_path: Path = DEFAULT_V2_SCHEMA_PATH,
    locations_path: Path | None = DEFAULT_LOCATIONS_PATH,
    source_log_path: Path | None = None,
) -> dict[str, Any]:
    """Execute one full run. Returns the built snapshot dict. Raises on any
    of: fetch failure, stale page, wrong Time Period view, parse error,
    history-integrity violation, schema violation -- and writes nothing to
    history/aliases/site/snapshot on any of those.

    The freshness check runs here, uniformly, for *both* the live and
    ``--fixture`` paths (the live path also self-checks inside
    ``fetch_schedule`` as a second, independent line of defense -- but this
    call is what a ``--fixture`` dry run relies on; without it a stale saved
    page would build a snapshot just like a fresh one).

    ``legacy_site_out``, given only with a custom-domain ``base_url``, also
    writes the github.io site that keeps the snapshot and the calendar feeds
    and redirects every page to the domain (``cfpa.legacy``, DECISIONS 0019).

    ``states_dir`` turns on the other states (DECISIONS 0025): their histories
    are read from it, the states in ``states_fetch`` are fetched (from
    ``states_fixtures`` when given, else live), and ``snapshot/v2.json`` and
    the state pages are built. A state that fails keeps its last good data
    and never stops California. None (the default) builds v2 with
    California alone and touches no state file.

    ``source_log_path`` turns on the unchanged-source warning
    (``cfpa.source_log``; in CI the file travels as a workflow artifact, and it
    is never committed): this run's content hash is added to the log and the
    days it has gone unchanged are reported. It only warns, never refuses, and
    None (the default) leaves the log alone.
    """
    cname = site_mod.custom_domain(base_url)
    if legacy_site_out is not None and (cname is None or not write_site):
        raise legacy_mod.LegacySiteError(
            "--legacy-site-out needs a site build (no --no-site) for a custom "
            f"domain (https://<host>, no path, not github.io); got {base_url!r}"
        )
    if fixture_path:
        page = fetch_mod.load_fixture(fixture_path, fetched_at=fixture_fetched_at)
    else:
        page = fetch_mod.fetch_schedule(version=VERSION)
    fetch_mod.assert_fresh(
        page.stated_today, run_today or dt.datetime.now(dt.UTC).date()
    )
    # A page showing "Current-Future Plants" or "Past Plants" is a partial
    # table, and the merge below reads a plant missing from the table as
    # dropped by CDFW. Refuse it before anything is parsed, merged or written
    # (DECISIONS 0016). Like the freshness check, this runs for --fixture too.
    fetch_mod.assert_full_window_view(page)

    rows = parse_mod.parse_schedule_table(page.html)
    # A live fetch that parses far fewer rows than any real one has is a
    # truncated or emptied table, and the merge below would read every plant
    # missing from it as removed. Fixtures are small by design and skip this.
    if not fixture_path:
        parse_mod.assert_live_row_floor(len(rows))
    water_options = parse_mod.parse_select_options(page.html, "Params_StockingWaterID")
    county_options = parse_mod.parse_select_options(page.html, "Params_Counties")
    region_county_options = parse_mod.parse_select_options(
        page.html, "RegionCountyMappings"
    )

    alias_table = aliases_mod.AliasTable.load(aliases_path)
    observed_names = [(r.cdfw_stock_id, r.water_name) for r in rows]
    match_report = aliases_mod.apply_all(alias_table, observed_names)
    match_report.print_report()

    species_alias_table = species_aliases_mod.SpeciesAliasTable.load(
        species_aliases_path
    )

    existing_history = history_mod.HistoryStore.load(history_path)

    # Species text is normalized *before* it becomes part of a history
    # record's identity (see species_aliases.py's module docstring): a
    # future inconsistent CDFW spelling must not fork one species into two
    # separate (and separately removed/relisted) history keys.
    parsed_rows_by_key: dict[
        history_mod.RecordKey, tuple[int, dt.date, dt.date, str]
    ] = {}
    observed_keys: set[history_mod.RecordKey] = set()
    for r in rows:
        species = species_alias_table.normalize(r.species)
        key = (r.cdfw_stock_id, r.week_start.isoformat(), species)
        parsed_rows_by_key[key] = (r.cdfw_stock_id, r.week_start, r.week_end, species)
        observed_keys.add(key)

    merged_records = history_mod.merge_observations(
        existing_history.records,
        observed_keys,
        parsed_rows_by_key,
        page_window_start=page.stated_period_start,
        page_window_end=page.stated_period_end,
        fetched_at=page.fetched_at,
    )
    new_history = history_mod.HistoryStore(records=merged_records)
    # Refuse an overwrite before anything else is built from it.
    history_mod.assert_append_only(existing_history.records, new_history.records)

    # A water with history that neither the table nor the picker names has no
    # county to give its snapshot entry. It is left out of THIS run's snapshot,
    # never guessed and never dropped from history, so one such water does not
    # stop the run for every other water (DECISIONS 0017). Too many at once
    # looks like a truncated page and refuses the run.
    unlisted = snapshot_mod.find_unlisted_waters(
        new_history, alias_table, rows, water_options
    )
    snapshot_mod.assert_unlisted_within_limit(unlisted)

    # Build and validate the snapshot from the in-memory history BEFORE any
    # file is written: a snapshot that cannot be built (e.g. a county with no
    # region) or that fails the schema must leave data/history.json and
    # data/aliases.json exactly as they were.
    generated_at = dt.datetime.now(dt.UTC)
    snap = snapshot_mod.build_snapshot(
        page=page,
        rows=rows,
        history=new_history,
        aliases=alias_table,
        generated_at=generated_at,
        names_matched=match_report.names_matched,
        names_seen=match_report.names_seen,
        counties_options=county_options,
        region_county_options=region_county_options,
        waters_known=len(water_options),
        water_options=water_options,
        leave_out={u.cdfw_stock_id for u in unlisted},
    )
    snapshot_mod.validate_snapshot(snap, schema_path)

    # The other states, then v2, built and validated before anything is
    # written, like v1. v1 above is final: nothing below changes it.
    state_runs: list[states_run.StateRun] = []
    if states_dir is not None:
        state_runs = states_run.run_states(
            states_dir=states_dir,
            fetch_codes=states_fetch,
            user_agent=states_base.USER_AGENT_TEMPLATE.format(version=VERSION),
            now=fixture_fetched_at
            if states_fixtures is not None and fixture_fetched_at is not None
            else dt.datetime.now(dt.UTC),
            fixtures_dir=states_fixtures,
        )
    # California's coordinates go into v2 only (DECISIONS 0024); v1 above
    # keeps location null byte for byte.
    snap_v2 = snapshot_v2_mod.build_snapshot_v2(
        snap,
        [(r.source, r.history) for r in state_runs],
        generated_at=generated_at,
        locations=_load_locations(locations_path),
    )
    snapshot_v2_mod.validate_snapshot_v2(snap_v2, v2_schema_path)

    new_history.save(
        history_path
    )  # raises HistoryIntegrityError; nothing written on failure
    alias_table.save(aliases_path)
    states_run.write(state_runs)

    if write_site:
        site_out.mkdir(parents=True, exist_ok=True)
        snap_dir = site_out / "snapshot"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "v1.json").write_text(
            json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (snap_dir / "v2.json").write_text(
            json.dumps(snap_v2, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        site_mod.build_site(
            snap,
            site_out,
            base_url=base_url,
            app_store_url=app_store_url,
            app_store_live=app_store_live,
            support_email=support_email,
            ga4_measurement_id=ga4_measurement_id,
            google_site_verification=google_site_verification,
            cname=cname,
            snapshot_v2=snap_v2,
        )
        if legacy_site_out is not None:
            legacy_mod.build_legacy_site(
                site_out,
                legacy_site_out,
                new_base_url=base_url,
                google_site_verification=google_site_verification,
            )

    coverage = snapshot_mod.Coverage(**snap["coverage"])
    coverage.print_report()
    if source_log_path is not None:
        _report_source_staleness(source_log_path, page)
    print_unlisted_report(unlisted)
    states_run.print_report(state_runs)
    return snap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cfpa", description=__doc__)
    parser.add_argument(
        "--fixture",
        help="path to a saved schedule HTML page, instead of a live fetch (offline/dry-run/CI)",
    )
    parser.add_argument(
        "--fixture-fetched-at",
        type=lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")),
        default=None,
        help="the real UTC timestamp --fixture was originally fetched at (ISO 8601), "
        "for accurate provenance when seeding history from an already-fetched page; "
        "defaults to now",
    )
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES_PATH)
    parser.add_argument(
        "--species-aliases", type=Path, default=DEFAULT_SPECIES_ALIASES_PATH
    )
    parser.add_argument(
        "--source-log",
        type=Path,
        default=DEFAULT_SOURCE_LOG_PATH,
        help="the committed log of each run's page hash, for the unchanged-page "
        "warning (cfpa.source_log)",
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--v2-schema", type=Path, default=DEFAULT_V2_SCHEMA_PATH)
    parser.add_argument(
        "--states-dir",
        type=Path,
        default=DEFAULT_STATES_DIR,
        help="where each other state's history file lives (DECISIONS 0025)",
    )
    parser.add_argument(
        "--states",
        default=None,
        help="comma-separated state codes to fetch this run (default: "
        f"{','.join(states_mod.ENABLED_STATES)} on a live run, none with "
        "--fixture unless --states-fixtures is given; empty = none)",
    )
    parser.add_argument(
        "--states-fixtures",
        type=Path,
        default=None,
        help="read each fetched state's response from <dir>/<code>.json instead "
        "of the network (offline runs and tests)",
    )
    parser.add_argument(
        "--no-states",
        action="store_true",
        help="leave the other states out entirely: v2 carries California alone",
    )
    parser.add_argument("--site-out", type=Path, default=DEFAULT_SITE_OUT)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="the site's root URL (the SITE_BASE_URL repository variable; empty = "
        f"{DEFAULT_BASE_URL}). An https:// URL at the root of a host that is not "
        "github.io is a custom domain: the build also writes CNAME",
    )
    parser.add_argument(
        "--legacy-site-out",
        type=lambda s: Path(s) if s else None,
        default=None,
        help="with a custom-domain --base-url, also write the github.io site here: "
        "the snapshot and calendar feeds byte for byte, and a redirect page for "
        "every page (DECISIONS 0019; empty = unset)",
    )
    parser.add_argument(
        "--app-store-url",
        default=None,
        help="the app's App Store URL; until one is given the site says the app "
        "is not in the App Store yet rather than linking to it (empty = unset)",
    )
    parser.add_argument(
        "--app-store-live",
        default=None,
        help="'true' once Apple has approved the app: adds the Smart App Banner "
        "tag to every page and the App Store badge to the home and support pages, "
        "linking to the app's App Store URL; 'false' or empty = off "
        "(the APP_STORE_LIVE repository variable in publish.yml)",
    )
    parser.add_argument(
        "--support-email",
        default=None,
        help="contact address shown on the support and privacy pages (empty = unset)",
    )
    parser.add_argument(
        "--no-site",
        action="store_true",
        help="skip site generation (schema/history only)",
    )
    parser.add_argument(
        "--run-today",
        type=dt.date.fromisoformat,
        default=None,
        help="override 'today' for the freshness check (ISO date) -- for --fixture "
        "reprocessing/backfill and deterministic tests only; a live fetch should "
        "not normally need this",
    )
    args = parser.parse_args(argv)

    # The committed GA4 measurement ID (site.GA4_MEASUREMENT_ID, DECISIONS
    # 0011), read and checked here, before anything is written: a malformed
    # one refuses the run like any other failure instead of shipping a tag
    # that records nothing. Empty = no analytics on any page.
    try:
        ga4_measurement_id = site_mod.ga4_measurement_id_or_none(
            site_mod.GA4_MEASUREMENT_ID
        )
        # The committed Search Console token (site.GOOGLE_SITE_VERIFICATION,
        # docs/adr/0013), checked the same way. Empty = no tag.
        google_site_verification = site_mod.google_site_verification_or_none(
            site_mod.GOOGLE_SITE_VERIFICATION
        )
        # The APP_STORE_LIVE switch, checked the same way: a value that is
        # neither true nor false refuses the run instead of being guessed.
        app_store_live = site_mod.app_store_live_or_false(args.app_store_live)
    except ValueError as exc:
        print(f"cfpa: run refused -- nothing published: {exc}", file=sys.stderr)
        return 1

    if args.states is not None:
        states_fetch: tuple[str, ...] = tuple(
            c.strip().upper() for c in args.states.split(",") if c.strip()
        )
    elif args.fixture and args.states_fixtures is None:
        # An offline run never reaches the network for a state either.
        states_fetch = ()
    else:
        states_fetch = states_mod.ENABLED_STATES

    try:
        run(
            fixture_path=args.fixture,
            history_path=args.history,
            aliases_path=args.aliases,
            species_aliases_path=args.species_aliases,
            schema_path=args.schema,
            site_out=args.site_out,
            base_url=args.base_url or DEFAULT_BASE_URL,
            write_site=not args.no_site,
            legacy_site_out=args.legacy_site_out,
            app_store_url=args.app_store_url or None,
            app_store_live=app_store_live,
            support_email=args.support_email or None,
            ga4_measurement_id=ga4_measurement_id,
            google_site_verification=google_site_verification,
            run_today=args.run_today,
            fixture_fetched_at=args.fixture_fetched_at,
            states_dir=None if args.no_states else args.states_dir,
            states_fetch=states_fetch,
            states_fixtures=args.states_fixtures,
            v2_schema_path=args.v2_schema,
            source_log_path=args.source_log,
        )
    except (
        fetch_mod.FetchError,
        fetch_mod.StalePageError,
        fetch_mod.WrongViewError,
        fetch_mod.PageFormatError,
        fetch_mod.RobotsDisallowedError,
        parse_mod.ParseError,
        history_mod.HistoryIntegrityError,
        snapshot_mod.SnapshotBuildError,
        snapshot_v2_mod.SnapshotV2Error,
        states_base.StateFetchError,
        states_store.StateHistoryError,
        legacy_mod.LegacySiteError,
    ) as exc:
        print(f"cfpa: run refused -- nothing published: {exc}", file=sys.stderr)
        return 1
    except jsonschema.ValidationError as exc:
        # str(exc) can carry the whole failing snapshot; keep the refusal to
        # the rule that broke and where.
        where = "/".join(str(part) for part in exc.absolute_path) or "the snapshot"
        print(
            "cfpa: run refused -- nothing published: the snapshot failed schema "
            f"validation at {where}: {exc.message[:300]}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
