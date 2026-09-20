"""Orchestrate one pipeline run: fetch -> parse -> match -> history -> snapshot
-> validate -> site -> coverage report.

A failed run (fetch failure, stale page, a page showing a partial Time Period
view, parse drift, history-integrity violation, schema validation failure)
writes nothing new and exits non-zero.
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
from . import parse as parse_mod
from . import site as site_mod
from . import snapshot as snapshot_mod
from . import species_aliases as species_aliases_mod

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE_DIR.parent
DEFAULT_HISTORY_PATH = PIPELINE_DIR / "data" / "history.json"
DEFAULT_ALIASES_PATH = PIPELINE_DIR / "data" / "aliases.json"
DEFAULT_SPECIES_ALIASES_PATH = PIPELINE_DIR / "data" / "species_aliases.json"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
DEFAULT_SITE_OUT = REPO_ROOT / "site"
DEFAULT_BASE_URL = "https://chelseakr.github.io/ca-fish-planting-alerts"


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
    app_store_url: str | None = None,
    support_email: str | None = None,
    ga4_measurement_id: str | None = None,
    google_site_verification: str | None = None,
    fixture_fetched_at: dt.datetime | None = None,
    run_today: dt.date | None = None,
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
    """
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

    new_history.save(
        history_path
    )  # raises HistoryIntegrityError; nothing written on failure
    alias_table.save(aliases_path)

    if write_site:
        site_out.mkdir(parents=True, exist_ok=True)
        snap_dir = site_out / "snapshot"
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "v1.json").write_text(
            json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        site_mod.build_site(
            snap,
            site_out,
            base_url=base_url,
            app_store_url=app_store_url,
            support_email=support_email,
            ga4_measurement_id=ga4_measurement_id,
            google_site_verification=google_site_verification,
        )

    coverage = snapshot_mod.Coverage(**snap["coverage"])
    coverage.print_report()
    print_unlisted_report(unlisted)
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
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--site-out", type=Path, default=DEFAULT_SITE_OUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--app-store-url",
        default=None,
        help="the app's App Store URL; until one is given the site says the app "
        "is not in the App Store yet rather than linking to it (empty = unset)",
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
    except ValueError as exc:
        print(f"cfpa: run refused -- nothing published: {exc}", file=sys.stderr)
        return 1

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
            app_store_url=args.app_store_url or None,
            support_email=args.support_email or None,
            ga4_measurement_id=ga4_measurement_id,
            google_site_verification=google_site_verification,
            run_today=args.run_today,
            fixture_fetched_at=args.fixture_fetched_at,
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
