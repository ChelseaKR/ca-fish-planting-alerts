import datetime as dt
import re
from pathlib import Path

import jsonschema
import pytest

from cfpa import cli, fetch as fetch_mod

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"


def _run(tmp_path: Path, fixture=FRESH):
    return cli.run(
        fixture_path=str(fixture),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=tmp_path / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.timezone.utc),
        run_today=dt.date(2026, 9, 13),
    )


def test_schema_file_is_valid_json_schema():
    import json

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_built_snapshot_validates_against_the_schema(tmp_path: Path):
    snap = _run(tmp_path)
    jsonschema.validate(instance=snap, schema=__import__("json").loads(SCHEMA_PATH.read_text()))


def test_a_plant_is_never_a_single_day(tmp_path: Path):
    """Every plant['week'] must be a 7-day Sunday..Saturday span with a
    'week of <date>' label -- never a bare date, never 'day'."""
    snap = _run(tmp_path)
    assert snap["waters"], "fixture must produce at least one water"
    checked = 0
    for w in snap["waters"]:
        for p in w["plants"]:
            week = p["week"]
            start = dt.date.fromisoformat(week["start"])
            end = dt.date.fromisoformat(week["end"])
            assert (end - start).days == 6
            assert week["label"] == f"week of {week['start']}"
            assert re.match(r"^week of \d{4}-\d{2}-\d{2}$", week["label"])
            checked += 1
    assert checked > 0
    # this_week entries reference weeks the same way -- no shortcut to a day
    for entry in snap["this_week"]:
        assert "week_id" not in entry  # no alternate single-value date field exists at all


def test_source_week_is_a_week_not_a_day(tmp_path: Path):
    snap = _run(tmp_path)
    sw = snap["source_week"]
    start = dt.date.fromisoformat(sw["start"])
    end = dt.date.fromisoformat(sw["end"])
    assert (end - start).days == 6
    assert start.weekday() == 6
    assert sw["label"] == f"week of {sw['start']}"


def test_this_week_matches_waters_plants_for_source_week(tmp_path: Path):
    snap = _run(tmp_path)
    by_id = {w["id"]: w for w in snap["waters"]}
    derived = {
        (w["id"], p["species"])
        for w in snap["waters"]
        for p in w["plants"]
        if p["week"]["start"] == snap["source_week"]["start"] and p["status"] == "listed"
    }
    reported = {(e["water_id"], e["species"]) for e in snap["this_week"]}
    assert derived == reported


def test_location_is_null_absent_a_licensed_source(tmp_path: Path):
    snap = _run(tmp_path)
    assert all(w["location"] is None for w in snap["waters"])


def test_coverage_numbers_are_populated_and_sane(tmp_path: Path):
    snap = _run(tmp_path)
    cov = snap["coverage"]
    assert cov["rows_parsed"] == 41
    assert cov["waters_known"] > 800
    assert 0 < cov["waters_with_history"] <= cov["waters_known"]
    assert cov["names_seen"] >= cov["waters_with_history"]
    assert cov["weeks_of_history_min"] >= 1


def test_snapshot_carries_attribution_and_licence(tmp_path: Path):
    snap = _run(tmp_path)
    assert "California Department of Fish and Wildlife" in snap["attribution"]["text"]
    assert snap["licence"]["sources"]
    assert all(s["commercial_reuse"] in ("permitted", "not-permitted", "unknown") for s in snap["licence"]["sources"])


def test_stale_fixture_refuses_to_build_a_snapshot(tmp_path: Path):
    stale = FIXTURES / "schedule-stale-2025-cache.html"
    with pytest.raises(fetch_mod.StalePageError):
        _run(tmp_path, fixture=stale)
    assert not (tmp_path / "site" / "snapshot" / "v1.json").exists()
    assert not (tmp_path / "history.json").exists()
