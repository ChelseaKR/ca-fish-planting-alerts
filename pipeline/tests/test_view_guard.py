"""A page showing a partial Time Period view must never reach the merge.

The pipeline infers "CDFW dropped this plant" from a plant's absence inside
the window the page states. That holds only when the table is the whole
window. The repository's own capture of a real response from 2026-09-14 has
"Current-Future Plants" checked and a table with zero rows; run against an
existing history it used to flip every listed plant in the window to
``removed`` and publish. These tests pin the refusal, and the end-to-end ones
are written so they FAIL on the code that shipped before the guard (they go
through ``cli.main`` and the files it writes, not through the new names).
"""

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, fetch, history, parse

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
STALE = FIXTURES / "schedule-stale-2025-cache.html"
CURRENT_FUTURE_EMPTY = FIXTURES / "schedule-empty-week-2026-09-14.html"

ALL_RADIO = (
    '<input data-val="true" data-val-number="The field Time Period must be a number." '
    'id="list1" name="Params.PlantTimeFrame" text="All Plants (9/13/2025 - 9/27/2026)" '
    'type="radio" value="1" />'
)
CURRENT_FUTURE_RADIO = (
    '<input id="list2" name="Params.PlantTimeFrame" '
    'text="Current-Future Plants (9/13/2026 - 9/27/2026)" type="radio" value="2" />'
)
PAST_RADIO = (
    '<input id="list3" name="Params.PlantTimeFrame" '
    'text="Past Plants (9/13/2025 - 9/13/2026)" type="radio" value="3" />'
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _with_radio(html: str, old: str, new: str) -> str:
    """Swap one radio tag, asserting the swap really landed (a control that
    silently changes nothing would read as a pass)."""
    assert old in html, "the fixture no longer contains the radio being swapped"
    out = html.replace(old, new, 1)
    assert out != html
    return out


def _check(radio: str, attribute: str = 'checked="checked" ') -> str:
    return radio.replace("<input ", f"<input {attribute}", 1)


# ---- extract_time_period_view --------------------------------------------


@pytest.mark.parametrize("fixture", [FRESH, MIDWEEK, STALE])
def test_a_plain_full_year_response_has_no_option_checked(fixture: Path):
    """Real plain-GET responses (2026-09-13, 2026-09-17) carry the whole year
    with no Time Period option checked. That is the daily run's shape, so it
    must stay accepted."""
    view, labels = fetch.extract_time_period_view(_read(fixture))
    assert view is fetch.TimePeriodView.NONE_CHECKED
    assert labels == ()
    assert view.covers_full_window


def test_the_real_2026_09_14_capture_is_the_current_future_view():
    view, labels = fetch.extract_time_period_view(_read(CURRENT_FUTURE_EMPTY))
    assert view is fetch.TimePeriodView.CURRENT_FUTURE
    assert labels == ("Current-Future Plants (9/13/2026 - 9/27/2026)",)
    assert not view.covers_full_window
    assert parse.parse_schedule_table(_read(CURRENT_FUTURE_EMPTY)) == []


def test_all_plants_checked_is_the_full_window():
    html = _with_radio(_read(FRESH), ALL_RADIO, _check(ALL_RADIO))
    view, labels = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.ALL
    assert labels == ("All Plants (9/13/2025 - 9/27/2026)",)
    assert view.covers_full_window


def test_past_plants_checked_is_the_past_view():
    html = _with_radio(_read(FRESH), PAST_RADIO, _check(PAST_RADIO))
    view, labels = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.PAST
    assert labels == ("Past Plants (9/13/2025 - 9/13/2026)",)
    assert not view.covers_full_window


@pytest.mark.parametrize(
    "attribute",
    [
        'checked="checked" ',  # what ASP.NET renders
        "checked ",  # a bare boolean attribute
        "CHECKED='CHECKED' ",  # other case and single quotes
        'checked="" ',
    ],
)
def test_every_spelling_of_the_checked_attribute_is_seen(attribute: str):
    html = _with_radio(
        _read(FRESH), CURRENT_FUTURE_RADIO, _check(CURRENT_FUTURE_RADIO, attribute)
    )
    view, _ = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.CURRENT_FUTURE


def test_the_word_checked_inside_a_label_is_not_the_attribute():
    """Only an attribute counts, never the word inside another attribute's value."""
    tricky = ALL_RADIO.replace(
        'text="All Plants', 'title="not checked here" text="All Plants'
    )
    html = _with_radio(_read(FRESH), ALL_RADIO, tricky)
    view, _ = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.NONE_CHECKED


def test_two_options_checked_is_ambiguous_not_trusted():
    html = _with_radio(_read(FRESH), ALL_RADIO, _check(ALL_RADIO))
    html = _with_radio(html, PAST_RADIO, _check(PAST_RADIO))
    view, labels = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.AMBIGUOUS
    assert len(labels) == 2
    assert not view.covers_full_window


def test_a_checked_option_with_an_unknown_label_is_not_trusted():
    renamed = ALL_RADIO.replace("All Plants", "Every Plant")
    html = _with_radio(_read(FRESH), ALL_RADIO, _check(renamed))
    view, labels = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.UNRECOGNIZED
    assert labels and labels[0].startswith("Every Plant")
    assert not view.covers_full_window


def test_a_page_with_no_time_period_options_is_format_drift():
    html = re.sub(r'<input[^>]*name="Params.PlantTimeFrame"[^>]*/>', "", _read(FRESH))
    assert 'name="Params.PlantTimeFrame"' not in html
    with pytest.raises(fetch.PageFormatError, match="Time Period options"):
        fetch.extract_time_period_view(html)


def test_a_checked_input_elsewhere_on_the_page_is_ignored():
    stray = '<input type="checkbox" name="Params.Other" checked="checked" />'
    html = _read(FRESH).replace("</form>", stray + "</form>", 1)
    assert stray in html
    view, _ = fetch.extract_time_period_view(html)
    assert view is fetch.TimePeriodView.NONE_CHECKED


# ---- load_fixture / assert_full_window_view -------------------------------


def test_a_loaded_page_carries_its_view():
    page = fetch.load_fixture(str(CURRENT_FUTURE_EMPTY))
    assert page.view is fetch.TimePeriodView.CURRENT_FUTURE
    assert page.view_labels == ("Current-Future Plants (9/13/2026 - 9/27/2026)",)
    assert fetch.load_fixture(str(FRESH)).view is fetch.TimePeriodView.NONE_CHECKED


def test_the_guard_passes_a_full_window_page_and_refuses_the_rest(tmp_path: Path):
    fetch.assert_full_window_view(fetch.load_fixture(str(FRESH)))  # must not raise
    with pytest.raises(fetch.WrongViewError) as excinfo:
        fetch.assert_full_window_view(fetch.load_fixture(str(CURRENT_FUTURE_EMPTY)))
    message = str(excinfo.value)
    assert "Current-Future Plants (9/13/2026 - 9/27/2026)" in message
    assert "not the full 'All Plants' window" in message
    assert "History and the last published snapshot are unchanged" in message
    assert excinfo.value.view is fetch.TimePeriodView.CURRENT_FUTURE


@pytest.mark.parametrize(
    ("view", "needle"),
    [
        (fetch.TimePeriodView.PAST, "not the full 'All Plants' window"),
        (fetch.TimePeriodView.AMBIGUOUS, "more than one Time Period option"),
        (fetch.TimePeriodView.UNRECOGNIZED, "does not recognize"),
    ],
)
def test_each_refusal_names_its_own_cause(view: fetch.TimePeriodView, needle: str):
    assert needle in str(fetch.WrongViewError(view, ("some label",)))


def test_the_live_fetch_path_refuses_a_partial_view_too():
    """``fetch_schedule`` is a second, independent line of defense."""
    import httpx

    html = _read(CURRENT_FUTURE_EMPTY)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text=html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(fetch.WrongViewError):
        fetch.fetch_schedule(
            version="test", run_today=dt.date(2026, 9, 14), client=client
        )

    ok = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                text="User-agent: *\nAllow: /\n"
                if r.url.path == "/robots.txt"
                else _read(FRESH),
            )
        )
    )
    page = fetch.fetch_schedule(
        version="test", run_today=dt.date(2026, 9, 13), client=ok
    )
    assert page.view is fetch.TimePeriodView.NONE_CHECKED


# ---- end to end: the run against an existing history -----------------------


def _argv(tmp_path: Path, fixture: Path, fetched_at: str, run_today: str) -> list[str]:
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
        str(out / "site"),
    ]


def _seed(tmp_path: Path) -> None:
    """A first, normal run from the 2026-09-13 capture."""
    code = cli.main(_argv(tmp_path, FRESH, "2026-09-13T12:00:00Z", "2026-09-13"))
    assert code == 0


def _tree_bytes(tmp_path: Path) -> dict[str, bytes]:
    """Every file the pipeline wrote: history, aliases, snapshot and site."""
    root = tmp_path / "out"
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _statuses(tmp_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for plant in json.loads((tmp_path / "out" / "history.json").read_text())["plants"]:
        counts[plant["status"]] = counts.get(plant["status"], 0) + 1
    return counts


def test_the_current_future_capture_is_refused_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Acceptance: seed history from the 2026-09-13 capture, then run the real
    2026-09-14 capture. Nothing becomes ``removed``, nothing is rewritten, and
    the run says why in one line.

    NEGATIVE CONTROL: on the code before this guard the same two runs flip 38
    of the 41 records to ``removed``, exit 0 and write a snapshot whose
    ``coverage.waters_this_week`` is 0, so every assertion below fails there.
    """
    _seed(tmp_path)
    seeded = _statuses(tmp_path)
    assert seeded.get("listed", 0) >= 38, (
        "the seed must give the control something to flip"
    )
    assert "removed" not in seeded
    before = _tree_bytes(tmp_path)
    capsys.readouterr()

    code = cli.main(
        _argv(tmp_path, CURRENT_FUTURE_EMPTY, "2026-09-14T12:00:00Z", "2026-09-14")
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "cfpa: run refused -- nothing published:" in captured.err
    assert "Current-Future Plants (9/13/2026 - 9/27/2026)" in captured.err
    assert "Traceback" not in captured.err + captured.out
    assert len(captured.err.strip().splitlines()) == 1  # one line, no traceback
    assert _statuses(tmp_path) == seeded
    assert _tree_bytes(tmp_path) == before  # history, aliases, snapshot, site


def test_run_raises_a_named_error_and_leaves_the_files_alone(tmp_path: Path):
    _seed(tmp_path)
    before = _tree_bytes(tmp_path)
    kwargs: dict[str, Any] = dict(
        fixture_path=str(CURRENT_FUTURE_EMPTY),
        history_path=tmp_path / "out" / "history.json",
        aliases_path=tmp_path / "out" / "aliases.json",
        species_aliases_path=tmp_path / "out" / "species_aliases.json",
        schema_path=cli.DEFAULT_SCHEMA_PATH,
        site_out=tmp_path / "out" / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 14),
    )
    with pytest.raises(fetch.WrongViewError):
        cli.run(**kwargs)
    assert _tree_bytes(tmp_path) == before


def test_the_same_page_in_the_full_window_view_would_have_removed_everything(
    tmp_path: Path,
):
    """Why the guard exists: fold the empty table into the seeded history the
    way the merge would if it were let through, and the whole window flips.
    (This documents the failure; it passes before and after the guard.)"""
    _seed(tmp_path)
    store = history.HistoryStore.load(tmp_path / "out" / "history.json")
    page = fetch.load_fixture(
        str(CURRENT_FUTURE_EMPTY),
        fetched_at=dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.UTC),
    )
    merged = history.merge_observations(
        store.records,
        set(),
        {},
        page_window_start=page.stated_period_start,
        page_window_end=page.stated_period_end,
        fetched_at=page.fetched_at,
    )
    flipped = [r for r in merged if r.status == "removed"]
    assert len(flipped) >= 38


def _drop_one_row_in_a_later_week(html: str) -> tuple[str, str]:
    """The fresh capture minus one plant whose week is safely inside the window
    (past the aging-off oldest week). Returns the html and that plant's water
    id, and asserts the row really was removed."""
    rows = parse.parse_schedule_table(html)
    window_start = fetch.extract_stated_period(html)[0]
    victim = next(
        r for r in rows if r.week_start >= window_start + history.AGE_OFF_MARGIN
    )
    seen = {"n": 0}

    def drop(m: re.Match[str]) -> str:
        row = m.group(0)
        if (
            f"stockid={victim.cdfw_stock_id}" in row
            and f"{victim.week_start.month}/{victim.week_start.day}/{victim.week_start.year}"
            in row
        ):
            seen["n"] += 1
            return "" if seen["n"] == 1 else row
        return row

    out = re.sub(r"(?s)<tr[^>]*>.*?</tr>", drop, html)
    assert seen["n"] >= 1 and out != html
    assert len(parse.parse_schedule_table(out)) == len(rows) - 1
    return out, str(victim.cdfw_stock_id)


def test_a_normal_full_window_response_still_marks_a_dropped_plant_removed(
    tmp_path: Path,
):
    """The guard is not a blanket refusal: with the "All Plants" option
    checked, CDFW dropping one plant inside the window still flips exactly
    that plant to ``removed``."""
    _seed(tmp_path)
    trimmed, stock_id = _drop_one_row_in_a_later_week(_read(FRESH))
    trimmed = _with_radio(trimmed, ALL_RADIO, _check(ALL_RADIO))
    fixture = tmp_path / "all-plants-one-dropped.html"
    fixture.write_text(trimmed, encoding="utf-8")

    code = cli.main(_argv(tmp_path, fixture, "2026-09-14T12:00:00Z", "2026-09-14"))

    assert code == 0
    removed = [
        p
        for p in json.loads((tmp_path / "out" / "history.json").read_text())["plants"]
        if p["status"] == "removed"
    ]
    assert [str(p["cdfw_stock_id"]) for p in removed] == [stock_id]


def test_a_plain_response_with_no_option_checked_still_runs(tmp_path: Path):
    """The daily run's own shape: nothing checked, the whole year."""
    _seed(tmp_path)
    code = cli.main(_argv(tmp_path, MIDWEEK, "2026-09-17T12:00:00Z", "2026-09-17"))
    assert code == 0
    assert "removed" not in _statuses(tmp_path)


def test_a_past_plants_page_is_refused_end_to_end(tmp_path: Path, capsys):
    _seed(tmp_path)
    before = _tree_bytes(tmp_path)
    html = _with_radio(_read(FRESH), PAST_RADIO, _check(PAST_RADIO))
    fixture = tmp_path / "past-view.html"
    fixture.write_text(html, encoding="utf-8")
    capsys.readouterr()

    code = cli.main(_argv(tmp_path, fixture, "2026-09-14T12:00:00Z", "2026-09-14"))

    err = capsys.readouterr().err
    assert code == 1
    assert "Past Plants (9/13/2025 - 9/13/2026)" in err
    assert _tree_bytes(tmp_path) == before, (
        "a refused run must leave every output as it was"
    )
