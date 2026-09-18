import datetime as dt
from pathlib import Path

import pytest

from cfpa import parse

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
EMPTY_WEEK = FIXTURES / "schedule-empty-week-2026-09-14.html"


def test_parses_every_row_and_shapes_are_sane():
    html = FRESH.read_text(encoding="utf-8")
    rows = parse.parse_schedule_table(html)
    assert len(rows) == 41  # the trimmed fixture's exact row count
    for r in rows:
        assert r.week_end == r.week_start + dt.timedelta(days=6)
        assert r.week_start.weekday() == 6  # Sunday
        assert r.cdfw_stock_id > 0
        assert r.water_name
        assert r.counties
        assert r.species


def test_a_week_is_never_a_single_day():
    html = FRESH.read_text(encoding="utf-8")
    rows = parse.parse_schedule_table(html)
    # every parsed row spans exactly 7 days -- there is no code path that
    # can produce a single-day "plant".
    assert all((r.week_end - r.week_start).days == 6 for r in rows)


def test_stock_id_survives_name_collisions():
    """Silver Lake is published under 3 different stock ids in this fixture
    -- the parser must keep them distinct, not collapse them by name."""
    html = FRESH.read_text(encoding="utf-8")
    rows = parse.parse_schedule_table(html)
    silver = {r.cdfw_stock_id for r in rows if r.water_name == "Silver Lake"}
    assert len(silver) >= 2, (
        "fixture should carry >1 distinct stock id spelled 'Silver Lake'"
    )


def test_multi_county_row_splits_on_comma():
    html = FRESH.read_text(encoding="utf-8")
    rows = parse.parse_schedule_table(html)
    multi = [r for r in rows if len(r.counties) > 1]
    assert multi, "fixture should include at least one multi-county row"
    assert all(isinstance(c, str) and c == c.strip() for r in multi for c in r.counties)


def test_missing_table_raises_parse_error():
    with pytest.raises(parse.ParseError, match="no <table"):
        parse.parse_schedule_table("<html><body>nothing here</body></html>")


def test_header_drift_raises_parse_error():
    import re as _re

    html = FRESH.read_text(encoding="utf-8")
    drifted, n = _re.subn(
        r"(<th[^>]*>\s*)Species(\s*</th>)", r"\1Species (kind)\2", html, count=1
    )
    assert n == 1, "test setup: expected to find exactly one Species <th>"
    with pytest.raises(parse.ParseError, match="table headers changed"):
        parse.parse_schedule_table(drifted)


def test_missing_stockid_link_raises_parse_error():
    """If CDFW ever drops the map link, our only stable id disappears --
    this must fail loudly, not silently fall back to name-only identity."""
    html = FRESH.read_text(encoding="utf-8")
    assert html.count("stockid=1116") == 1, (
        "test setup: expected exactly one occurrence"
    )
    drifted = html.replace("stockid=1116", "waterid=1116", 1)
    assert "stockid=1116" not in drifted
    with pytest.raises(parse.ParseError, match="no stockid="):
        parse.parse_schedule_table(drifted)


def test_zero_rows_in_a_well_formed_table_is_a_valid_empty_week():
    """A table+headers+tbody that are all structurally intact, just with zero
    <tr> rows, is CDFW's own real "nothing matched" shape (confirmed live
    against production on 2026-09-14 -- see
    test_real_empty_query_response_parses_to_zero_rows below), not a parse
    failure. It must return [], not raise."""
    html = FRESH.read_text(encoding="utf-8")
    import re

    emptied = re.sub(r"(?s)(<tbody>).*?(</tbody>)", r"\1\2", html)
    assert parse.parse_schedule_table(emptied) == []


def test_real_empty_query_response_parses_to_zero_rows():
    """fixtures/schedule-empty-week-2026-09-14.html is a real, unmodified
    response captured live from CDFW's production search on 2026-09-14, for
    a Params.StockingWaterID + Params.PlantTimeFrame combination known to
    match nothing in the current-future window. It is direct evidence (not
    a synthetic guess) that a genuine zero-result query still renders the
    full #fishPlantsExternal table with exact headers and a present, empty
    tbody -- not a missing table, not an error page. This is the real shape
    a genuinely empty statewide week would be expected to take."""
    html = EMPTY_WEEK.read_text(encoding="utf-8")
    assert parse.parse_schedule_table(html) == []


def test_missing_tbody_tag_entirely_still_raises_parse_error():
    """Distinguish 'tbody present but empty' (valid empty week, see above)
    from 'tbody missing entirely' (a structurally different, broken
    response) -- the latter must still raise, never fall through to []."""
    html = FRESH.read_text(encoding="utf-8")
    import re

    no_tbody = re.sub(r"(?s)<tbody>.*?</tbody>", "", html, count=1)
    with pytest.raises(parse.ParseError, match="no <tbody>"):
        parse.parse_schedule_table(no_tbody)


def test_parse_select_options_reads_waters_regions_counties():
    html = FRESH.read_text(encoding="utf-8")
    waters = parse.parse_select_options(html, "Params_StockingWaterID")
    regions = parse.parse_select_options(html, "Params_Regions")
    counties = parse.parse_select_options(html, "Params_Counties")
    assert len(waters) > 800  # real CDFW picker had 895 non-blank options on 2026-09-13
    assert {r.value for r in regions} == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert len(counties) == 58


def test_parse_select_options_missing_id_raises():
    html = FRESH.read_text(encoding="utf-8")
    with pytest.raises(parse.ParseError):
        parse.parse_select_options(html, "Params_DoesNotExist")


def test_parse_select_options_zero_options_raises_not_silently_empty():
    """A <select> that survives but loses all its <option>s (e.g. a markup
    drift that breaks the attribute regex) must fail loudly -- these are
    static reference catalogs (waters, counties), never legitimately empty.
    Silently returning [] would publish a wrong-but-plausible number like
    "waters_known": 0 instead of refusing the run."""
    html = FRESH.read_text(encoding="utf-8")
    import re as _re

    drifted, n = _re.subn(
        r'(?s)(<select[^>]*id="Params_StockingWaterID"[^>]*>).*?(</select>)',
        r"\1\2",
        html,
        count=1,
    )
    assert n == 1, "test setup: expected to find exactly one matching <select>"
    with pytest.raises(parse.ParseError, match="zero non-blank"):
        parse.parse_select_options(drifted, "Params_StockingWaterID")
