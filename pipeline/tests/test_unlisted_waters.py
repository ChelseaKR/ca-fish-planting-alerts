"""A water CDFW no longer lists must not stop the daily run for every water.

The snapshot needs a county for every water with history. History stores none,
so it comes from this run's table rows and then from CDFW's water picker. A
water in neither used to raise a bare ``ValueError``: nothing was written, but
every later run hit the same error, so the site and snapshot for all ~385
waters stopped updating, and the refusal printed a raw traceback.

Now such a water is left out of that run's snapshot (its history is kept, not
deleted, and not shown as an empty schedule), the run says so loudly, and every
other water is published. The end-to-end tests go through ``cli.main`` and the
files it writes, and are written so they FAIL on the code that shipped before
this change (they do not reference any name it added).
"""

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from cfpa import cli, history, parse, snapshot

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"

# The water the issue's reproduction retires: a real one in the 2026-09-13 capture.
RETIRED_ID = 501477
RETIRED_NAME = "Tule River South Fork, Middle Fork #3"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _retire(html: str, *stock_ids: int, keep_picker: bool = False) -> str:
    """The page with these waters gone from the table and, unless
    ``keep_picker``, from the water picker too. Asserts each removal really
    landed (a control that changes nothing would read as a pass)."""
    out = html
    for sid in stock_ids:
        picker = re.compile(rf'<option[^>]*value="{sid}"[^>]*>[^<]*</option>')
        assert picker.search(out), f"cdfw-{sid} is not in the picker"
        if not keep_picker:
            out = picker.sub("", out)
        rows = 0

        def drop(m: re.Match[str], sid: int = sid) -> str:
            nonlocal rows
            if f"stockid={sid}" in m.group(0):
                rows += 1
                return ""
            return m.group(0)

        out = re.sub(r"(?s)<tr[^>]*>.*?</tr>", drop, out)
        assert rows >= 1, f"cdfw-{sid} has no table row to remove"
        assert f"stockid={sid}" not in out
        assert bool(picker.search(out)) == keep_picker
    return out


def _argv(
    tmp_path: Path, fixture: Path, fetched_at: str, run_today: str, site: str = "site"
) -> list[str]:
    """``site`` names the site output directory. Each run gets its own where a
    test looks at pages: the build does not clear pages an earlier run wrote,
    and the daily workflow always starts from a fresh checkout."""
    out = tmp_path / "out"
    return [
        "--fixture",
        str(fixture),
        "--fixture-fetched-at",
        fetched_at,
        "--run-today",
        run_today,
        "--history",
        str(out / "history.json"),
        "--aliases",
        str(out / "aliases.json"),
        "--species-aliases",
        str(out / "species_aliases.json"),
        "--site-out",
        str(out / site),
    ]


def _seed(tmp_path: Path) -> None:
    assert cli.main(_argv(tmp_path, FRESH, "2026-09-13T12:00:00Z", "2026-09-13")) == 0


def _write(tmp_path: Path, name: str, html: str) -> Path:
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return path


def _history(tmp_path: Path) -> list[dict]:
    return json.loads((tmp_path / "out" / "history.json").read_text())["plants"]


def _snapshot(tmp_path: Path, site: str = "site") -> dict:
    path = tmp_path / "out" / site / "snapshot" / "v1.json"
    return json.loads(path.read_text())


def _tree_bytes(tmp_path: Path) -> dict[str, bytes]:
    root = tmp_path / "out"
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---- the run continues for every other water --------------------------------


def test_a_water_missing_from_table_and_picker_does_not_stop_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Acceptance. Seed history from the 2026-09-13 capture, then run a fetch
    where one water is in neither the rows nor the picker. The run succeeds
    and publishes every other water; that water keeps all of its history and
    is left out of the snapshot, so it is never published as an empty schedule.

    NEGATIVE CONTROL: before this change the second run raised ``ValueError:
    cdfw-501477 ... has history but no county data from this run`` out of
    ``cli.main`` and wrote nothing.
    """
    _seed(tmp_path)
    seeded_snapshot = _snapshot(tmp_path)
    seeded_history = _history(tmp_path)
    mine = [p for p in seeded_history if p["cdfw_stock_id"] == RETIRED_ID]
    assert mine, "the water must have history for the control to mean anything"
    retired = _write(tmp_path, "retired.html", _retire(_read(FRESH), RETIRED_ID))
    capsys.readouterr()

    code = cli.main(
        _argv(tmp_path, retired, "2026-09-14T12:00:00Z", "2026-09-14", site="site2")
    )

    assert code == 0
    snap = _snapshot(tmp_path, "site2")
    ids = {w["cdfw_stock_id"] for w in snap["waters"]}
    assert RETIRED_ID not in ids
    assert ids == {w["cdfw_stock_id"] for w in seeded_snapshot["waters"]} - {RETIRED_ID}
    # Not published as "nothing scheduled" in any form.
    assert all(e["water_id"] != f"cdfw-{RETIRED_ID}" for e in snap["this_week"])
    site = tmp_path / "out" / "site2"
    assert not (site / "water" / "tule-river-south-fork-middle-fork-3").exists()
    assert (site / "water" / "baker-creek").exists()  # the others still publish
    # History is preserved: every record still there, none deleted.
    after = _history(tmp_path)
    assert len(after) >= len(seeded_history)
    assert {(p["cdfw_stock_id"], p["week_start"], p["species"]) for p in mine} <= {
        (p["cdfw_stock_id"], p["week_start"], p["species"]) for p in after
    }
    assert not any(
        p["status"] == "removed" for p in after if p["cdfw_stock_id"] != RETIRED_ID
    )


def test_the_run_says_loudly_which_water_was_left_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _seed(tmp_path)
    retired = _write(tmp_path, "retired.html", _retire(_read(FRESH), RETIRED_ID))
    capsys.readouterr()

    assert cli.main(_argv(tmp_path, retired, "2026-09-14T12:00:00Z", "2026-09-14")) == 0

    captured = capsys.readouterr()
    assert "cfpa: WARNING 1 water with history is in neither" in captured.err
    assert f"cdfw-{RETIRED_ID} {RETIRED_NAME}" in captured.err
    assert "history is kept, not deleted" in captured.err
    assert "still listed, newest week of" in captured.err
    assert "::warning" not in captured.out  # only under GitHub Actions
    assert "Traceback" not in captured.err


def test_under_github_actions_it_is_also_a_workflow_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _seed(tmp_path)
    retired = _write(tmp_path, "retired.html", _retire(_read(FRESH), RETIRED_ID))
    capsys.readouterr()

    assert cli.main(_argv(tmp_path, retired, "2026-09-14T12:00:00Z", "2026-09-14")) == 0

    out = capsys.readouterr().out
    warnings = [line for line in out.splitlines() if line.startswith("::warning")]
    assert warnings == [
        "::warning title=Waters CDFW no longer lists::1 water with history left out "
        f"of this run's snapshot (history kept): cdfw-{RETIRED_ID}"
    ]


def test_a_water_that_comes_back_is_published_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    _seed(tmp_path)
    retired = _write(tmp_path, "retired.html", _retire(_read(FRESH), RETIRED_ID))
    assert cli.main(_argv(tmp_path, retired, "2026-09-14T12:00:00Z", "2026-09-14")) == 0
    assert RETIRED_ID not in {w["cdfw_stock_id"] for w in _snapshot(tmp_path)["waters"]}
    capsys.readouterr()

    assert cli.main(_argv(tmp_path, FRESH, "2026-09-15T12:00:00Z", "2026-09-15")) == 0

    assert RETIRED_ID in {w["cdfw_stock_id"] for w in _snapshot(tmp_path)["waters"]}
    assert "WARNING" not in capsys.readouterr().err


def test_a_water_still_in_the_picker_is_placed_not_left_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """The existing fallback is unchanged: a water whose rows have aged off the
    table but that the picker still names keeps its page and snapshot entry, and
    nothing is reported. (Real case, 2026-09-17: two waters planted only the
    week of 2025-09-14.)"""
    _seed(tmp_path)
    aged_off = _write(
        tmp_path, "aged-off.html", _retire(_read(FRESH), RETIRED_ID, keep_picker=True)
    )
    capsys.readouterr()

    code = cli.main(
        _argv(tmp_path, aged_off, "2026-09-14T12:00:00Z", "2026-09-14", site="site2")
    )

    assert code == 0
    assert "WARNING" not in capsys.readouterr().err
    snap = _snapshot(tmp_path, "site2")
    water = next(w for w in snap["waters"] if w["cdfw_stock_id"] == RETIRED_ID)
    assert water["counties"] == ["Tulare"]


# ---- too many at once looks like a broken page ------------------------------


def _first_water_ids(n: int) -> list[int]:
    rows = parse.parse_schedule_table(_read(FRESH))
    return sorted({r.cdfw_stock_id for r in rows})[:n]


def test_as_many_as_the_limit_are_left_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    _seed(tmp_path)
    gone = _first_water_ids(snapshot.MAX_UNLISTED_WATERS)
    page = _write(tmp_path, "some.html", _retire(_read(FRESH), *gone))
    capsys.readouterr()

    assert cli.main(_argv(tmp_path, page, "2026-09-14T12:00:00Z", "2026-09-14")) == 0

    err = capsys.readouterr().err
    assert f"WARNING {len(gone)} waters with history are in neither" in err
    assert {w["cdfw_stock_id"] for w in _snapshot(tmp_path)["waters"]}.isdisjoint(gone)


def test_more_than_the_limit_refuses_the_run_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """A picker or table that lost this many waters at once is a truncated or
    reshaped page, not retirements. Refuse, keep the last good snapshot."""
    _seed(tmp_path)
    before = _tree_bytes(tmp_path)
    gone = _first_water_ids(snapshot.MAX_UNLISTED_WATERS + 1)
    page = _write(tmp_path, "many.html", _retire(_read(FRESH), *gone))
    capsys.readouterr()

    code = cli.main(_argv(tmp_path, page, "2026-09-14T12:00:00Z", "2026-09-14"))

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith(
        "cfpa: run refused -- nothing published: 6 waters with history"
    )
    assert "truncated or reshaped page" in err
    assert len(err.strip().splitlines()) == 1
    assert _tree_bytes(tmp_path) == before


# ---- refusals are one line, not a traceback ---------------------------------


def test_a_water_with_history_and_no_alias_is_a_one_line_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """History without an alias entry is corrupt data, not a retired water: it
    still refuses, now as the same one line every other refusal prints.

    NEGATIVE CONTROL: before this change ``cli.main`` let the ``ValueError``
    escape as a traceback."""
    _seed(tmp_path)
    aliases_path = tmp_path / "out" / "aliases.json"
    data = json.loads(aliases_path.read_text())
    data["waters"] = [w for w in data["waters"] if w["cdfw_stock_id"] != RETIRED_ID]
    aliases_path.write_text(json.dumps(data, indent=2) + "\n")
    retired = _write(tmp_path, "retired.html", _retire(_read(FRESH), RETIRED_ID))
    before = _tree_bytes(tmp_path)
    capsys.readouterr()

    code = cli.main(_argv(tmp_path, retired, "2026-09-14T12:00:00Z", "2026-09-14"))

    err = capsys.readouterr().err
    assert code == 1
    assert (
        err.strip()
        == f"cfpa: run refused -- nothing published: cdfw-{RETIRED_ID} has history "
        "but no alias table entry"
    )
    assert _tree_bytes(tmp_path) == before


def test_a_snapshot_that_fails_the_schema_is_a_one_line_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """``jsonschema.ValidationError`` used to escape ``main`` as a traceback that
    also printed the whole failing snapshot."""
    strict = json.loads(SCHEMA_PATH.read_text())
    strict["required"] = [*strict["required"], "a_field_no_snapshot_has"]
    schema = tmp_path / "strict.schema.json"
    schema.write_text(json.dumps(strict), encoding="utf-8")
    argv = _argv(tmp_path, FRESH, "2026-09-13T12:00:00Z", "2026-09-13")

    code = cli.main([*argv, "--schema", str(schema)])

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith(
        "cfpa: run refused -- nothing published: the snapshot failed schema"
    )
    assert "'a_field_no_snapshot_has' is a required property" in err
    assert len(err.strip().splitlines()) == 1
    assert not (tmp_path / "out" / "history.json").exists()


def test_a_water_with_no_county_still_fails_when_the_caller_did_not_opt_in():
    """``build_waters`` keeps its strict default: only a water the caller names
    in ``leave_out`` is skipped; any other water without a county raises."""
    from cfpa import aliases

    rec = history.PlantRecord(
        cdfw_stock_id=1,
        week_start=dt.date(2026, 9, 13),
        week_end=dt.date(2026, 9, 19),
        species="Trout",
        status="listed",
        first_observed_at=dt.datetime(2026, 9, 13, tzinfo=dt.UTC),
        last_observed_at=dt.datetime(2026, 9, 13, tzinfo=dt.UTC),
    )
    store = history.HistoryStore(records=[rec])
    table = aliases.AliasTable(
        by_id={
            1: aliases.WaterAlias(
                cdfw_stock_id=1,
                canonical_name="Lost Lake",
                slug="lost-lake",
                aliases=["Lost Lake"],
            )
        }
    )
    args = (store, table, [], dt.date(2026, 9, 13), {"Plumas": "R2"})
    with pytest.raises(snapshot.SnapshotBuildError, match="has history but no county"):
        snapshot.build_waters(*args)
    with pytest.raises(ValueError):  # still a ValueError for older callers
        snapshot.build_waters(*args)
    assert snapshot.build_waters(*args, leave_out={1}) == []
    listed = snapshot.find_unlisted_waters(store, table, [], [])
    assert listed == [
        snapshot.UnlistedWater(
            cdfw_stock_id=1,
            name="Lost Lake",
            records=1,
            listed_records=1,
            newest_week_start="2026-09-13",
        )
    ]
