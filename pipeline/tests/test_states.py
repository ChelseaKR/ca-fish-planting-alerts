"""The non-California state sources (DECISIONS 0025): parsing, the strict
robots rule, the append-only state history, and isolation of a failing
state. Each state has a negative control that changes the fixture and
asserts both that the change landed and that the feed is refused."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
import respx

from cfpa import snapshot_v2
from cfpa.states import ENABLED_STATES, SOURCES, ma, mi, ny, tn
from cfpa.states import run as srun
from cfpa.states.base import (
    USER_AGENT_TEMPLATE,
    FetchedBody,
    Period,
    RobotsDisallowedError,
    RobotsUnreadableError,
    StateFetchError,
    StateFormatError,
    check_robots_strict,
    no_sleep,
)
from cfpa.states.store import (
    MAX_NEWLY_WITHDRAWN,
    StateHistory,
    StateHistoryError,
    merge,
    record_failure,
)

STATE_FIXTURES = Path(__file__).parent / "fixtures" / "states"
UA = USER_AGENT_TEMPLATE.format(version="0.1.0")
NOW = dt.datetime(2026, 10, 12, 19, 18, 13, tzinfo=dt.UTC)


def _body(text: str, when: dt.datetime = NOW) -> FetchedBody:
    return FetchedBody(url="file://x", text=text, fetched_at=when, last_modified=None)


def _tn_text() -> str:
    return (STATE_FIXTURES / "tn.json").read_text(encoding="utf-8")


def _tn_doc() -> dict:
    return json.loads(_tn_text())


# ---- Tennessee, from the real 2026-10-12 file


def test_tn_real_file_parses_to_every_water_at_the_precision_twra_gives():
    feed = tn.parse([_body(_tn_text())])
    assert len(feed.waters) == 136
    assert len(feed.records) == 599
    precisions = {r.period.precision for r in feed.records}
    assert precisions == {"day", "week", "month"}
    for r in feed.records:
        if r.period.precision == "week":
            assert r.period.start.weekday() == 6
            assert r.period.end - r.period.start == dt.timedelta(days=6)
        if r.period.precision == "day":
            assert r.period.start == r.period.end


def test_tn_tbd_month_is_a_month_never_a_day():
    feed = tn.parse([_body(_tn_text())])
    mckenzie = [r for r in feed.records if r.water_id == "tn-caroll-mckenzie-city-park"]
    months = [r.period for r in mckenzie if r.period.precision == "month"]
    assert months == [Period.month(2026, 12)]
    assert months[0].label == "December 2026"
    assert months[0].end == dt.date(2026, 12, 31)


def test_tn_months_column_is_kept_verbatim_never_turned_into_dates():
    feed = tn.parse([_body(_tn_text())])
    notes = {w.months_note for w in feed.waters.values() if w.months_note}
    assert "M, A, M, J, J, A, S" in notes
    # A water listed only by month letters has no dated record.
    month_only = [
        wid
        for wid, w in feed.waters.items()
        if w.months_note and not any(r.water_id == wid for r in feed.records)
    ]
    assert month_only


def test_tn_ids_and_slugs_keep_counties_apart():
    feed = tn.parse([_body(_tn_text())])
    hurricane = sorted(w for w in feed.waters if w.endswith("hurricane-creek"))
    assert hurricane == ["tn-houston-hurricane-creek", "tn-humphreys-hurricane-creek"]
    slugs = [w.slug for w in feed.waters.values()]
    assert len(slugs) == len(set(slugs))


def _tn_2027_text() -> str:
    # Constructed from the real 2026 file plus the five rows the 2026-11-05
    # read of TWRA's 2027 file found (see the fixture's "_fixture_note").
    return (STATE_FIXTURES / "tn-2027-constructed.json").read_text(encoding="utf-8")


def test_tn_2027_file_parses_and_skips_exactly_the_four_non_sunday_weeks():
    feed = tn.parse([_body(_tn_2027_text())])
    assert len(feed.skipped_notes) == 4
    assert feed.skipped >= 4
    joined = " | ".join(feed.skipped_notes)
    for date, day in (
        ("3/21/2026", "Saturday"),
        ("7/12/2027", "Monday"),
        ("7/19/2027", "Monday"),
        ("7/26/2027", "Monday"),
    ):
        assert f"week of {date} is a {day}, not a Sunday" in joined
    # Each note names the water, so the run log says which rows were dropped.
    assert all("County)" in n for n in feed.skipped_notes)
    # No skipped row was moved to a guessed Sunday: the weeks read are exactly
    # the Sunday cells in the file, nothing more.
    sundays = set()
    for row in json.loads(_tn_2027_text())["data"]:
        m, d, y = [*row["STOCKING WEEK"].split("/"), "", "", ""][:3]
        if y.isdigit() and m.isdigit():
            when = dt.date(int(y), int(m), int(d))
            if when.weekday() == 6:
                wid = tn.water_id(row["COUNTY"].strip(), row["LOCATION"].strip())
                sundays.add((wid, row["SPECIES"].strip(), when))
    weeks = {
        (r.water_id, r.species, r.period.start)
        for r in feed.records
        if r.period.precision == "week"
    }
    assert weeks == sundays
    assert max(r.period.end for r in feed.records) >= dt.date(2027, 12, 1)


def test_tn_tbd_in_the_week_column_is_a_month_never_a_week():
    feed = tn.parse([_body(_tn_2027_text())])
    hurricane = [r for r in feed.records if r.water_id == "tn-houston-hurricane-creek"]
    months = [r.period for r in hurricane if r.period.precision == "month"]
    assert months == [Period.month(2027, 12)]
    assert months[0].label == "December 2027"
    assert not any(
        r.period.precision == "week"
        and r.period.start.month == 12
        and r.period.start.year == 2027
        for r in hurricane
    )


def test_tn_skipped_rows_are_named_in_the_run_report(tmp_path: Path):
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    (fixtures / "tn.json").write_text(_tn_2027_text(), encoding="utf-8")
    runs = srun.run_states(
        states_dir=tmp_path,
        fetch_codes=["TN"],
        user_agent=UA,
        now=NOW,
        fixtures_dir=fixtures,
    )
    tn_run = next(r for r in runs if r.source.code == "TN")
    assert tn_run.outcome == "updated"
    assert "week of 7/12/2027 is a Monday" in tn_run.message
    assert "skipped" in tn_run.message


def test_tn_negative_control_non_sunday_weeks_over_the_cap_refuse_the_file():
    doc = _tn_doc()
    rows = [r for r in doc["data"] if r["STOCKING WEEK"].strip()]
    cap = min(tn.MAX_BAD_ROWS, int(len(doc["data"]) * tn.MAX_BAD_SHARE))
    # At the cap: still read.
    for r in rows[:cap]:
        r["STOCKING WEEK"] = "10/13/2026"  # a Tuesday
    text = json.dumps(doc)
    assert text.count('"STOCKING WEEK": "10/13/2026"') == cap  # the sabotage landed
    assert len(tn.parse([_body(text)]).skipped_notes) == cap
    # One over the cap: refused, so a reshaped feed is never read as fewer weeks.
    rows[cap]["STOCKING WEEK"] = "10/13/2026"
    text = json.dumps(doc)
    assert text.count('"STOCKING WEEK": "10/13/2026"') == cap + 1
    with pytest.raises(StateFormatError, match="Sunday"):
        tn.parse([_body(text)])


def test_tn_negative_control_an_unknown_week_form_is_still_refused():
    doc = _tn_doc()
    row = next(r for r in doc["data"] if r["STOCKING WEEK"].strip())
    row["STOCKING WEEK"] = "TBD"
    text = json.dumps(doc)
    assert '"STOCKING WEEK": "TBD"' in text
    with pytest.raises(StateFormatError, match="STOCKING WEEK"):
        tn.parse([_body(text)])


def test_tn_negative_control_an_unknown_day_form_is_refused():
    doc = _tn_doc()
    row = next(r for r in doc["data"] if r["STOCKING DAY"].strip())
    row["STOCKING DAY"] = "mid-October"
    text = json.dumps(doc)
    assert "mid-October" in text
    with pytest.raises(StateFormatError, match="STOCKING DAY"):
        tn.parse([_body(text)])


def test_tn_negative_control_a_renamed_column_is_refused():
    doc = _tn_doc()
    for r in doc["data"]:
        r["STOCKING DATE"] = r.pop("STOCKING DAY")
    text = json.dumps(doc)
    assert '"STOCKING DAY"' not in text
    with pytest.raises(StateFormatError, match="missing columns"):
        tn.parse([_body(text)])


def test_tn_negative_control_a_truncated_file_is_refused_and_keeps_last_good_data(
    tmp_path: Path,
):
    good = srun.run_states(
        states_dir=tmp_path,
        fetch_codes=["TN"],
        user_agent=UA,
        now=NOW,
        fixtures_dir=STATE_FIXTURES,
    )
    srun.write(good)
    before = (tmp_path / "tn.json").read_text(encoding="utf-8")

    doc = _tn_doc()
    doc["data"] = doc["data"][:20]
    cut = tmp_path / "cut"
    cut.mkdir()
    (cut / "tn.json").write_text(json.dumps(doc), encoding="utf-8")
    assert len(json.loads((cut / "tn.json").read_text())["data"]) == 20

    later = NOW + dt.timedelta(days=1)
    runs = srun.run_states(
        states_dir=tmp_path,
        fetch_codes=["TN"],
        user_agent=UA,
        now=later,
        fixtures_dir=cut,
    )
    tn_run = next(r for r in runs if r.source.code == "TN")
    assert tn_run.outcome == "failed"
    assert "fewer than 100" in tn_run.message
    srun.write(runs)
    after = json.loads((tmp_path / "tn.json").read_text(encoding="utf-8"))
    assert after["records"] == json.loads(before)["records"]
    assert after["checks"]["last_attempt_ok"] is False
    assert after["checks"]["last_success_at"] == "2026-10-12T19:18:13Z"


# ---- Massachusetts and Michigan, from labeled synthetic fixtures


def _text(name: str) -> str:
    return (STATE_FIXTURES / name).read_text(encoding="utf-8")


# ---- Massachusetts, from the real 2026-10-12 Hub download


def test_ma_parses_reports_by_day_with_towns_and_the_legends_species():
    feed = ma.parse([_body(_text("ma.csv"))])
    assert len(feed.records) == 150
    assert len(feed.waters) == 123
    assert {r.species for r in feed.records} == {"Rainbow Trout", "Brown Trout"}
    wyola = feed.waters["ma-34103-272"]
    assert wyola.name == "Lake Wyola"  # " - Shutesbury" is the town, kept apart
    assert wyola.towns == ("Shutesbury",)
    assert wyola.counties == ()
    assert {r.period.precision for r in feed.records} == {"day"}
    assert min(r.period.start for r in feed.records) == dt.date(2026, 9, 24)
    assert max(r.period.start for r in feed.records) == dt.date(2026, 10, 9)


def test_ma_negative_control_an_unknown_species_code_is_refused_not_guessed():
    text = _text("ma.csv").replace(",RT,34103-272,", ",XX,34103-272,", 1)
    assert ",XX,34103-272," in text
    with pytest.raises(StateFormatError, match="legend"):
        ma.parse([_body(text)])


def test_ma_negative_control_the_old_guessed_date_field_is_refused():
    text = _text("ma.csv").replace("Stocked_Date", "Date", 1)
    assert "Stocked_Date" not in text.splitlines()[0]
    with pytest.raises(StateFormatError, match="missing columns"):
        ma.parse([_body(text)])


# ---- Michigan, from the real DNR CSV (a subset of its rows, verbatim)


def test_mi_keeps_public_trout_stockings_from_2021_only():
    feed = mi.parse([_body(_text("mi.csv"))])
    assert len(feed.records) >= mi.SOURCE.min_rows
    species = {r.species for r in feed.records}
    assert species == {"Brown trout", "Rainbow trout", "Brook trout", "Lake trout"}
    assert min(r.period.start for r in feed.records) >= mi.PUBLISH_SINCE
    names = {w.name for w in feed.waters.values()}
    assert not any(n.startswith("Private Pond") for n in names)


def test_mi_ids_come_from_county_water_and_site():
    feed = mi.parse([_body(_text("mi.csv"))])
    wid = next(iter(feed.waters))
    assert wid.startswith("mi-")
    assert all(w.counties for w in feed.waters.values())
    slugs = [w.slug for w in feed.waters.values()]
    assert len(slugs) == len(set(slugs))


def test_mi_negative_control_a_negative_count_is_refused():
    lines = _text("mi.csv").splitlines()
    i = next(
        n
        for n, line in enumerate(lines)
        if "Brown trout" in line and "State Plant" in line
    )
    cells = lines[i].split(",")
    cells[10] = "-5"
    lines[i] = ",".join(cells)
    text = "\n".join(lines)
    assert ",-5," in text
    with pytest.raises(StateFormatError, match="negative"):
        mi.parse([_body(text)])


def test_mi_negative_control_a_renamed_column_is_refused():
    text = _text("mi.csv").replace("Stocking_Date", "Date_Stocked", 1)
    assert "Stocking_Date" not in text.splitlines()[0]
    with pytest.raises(StateFormatError, match="missing columns"):
        mi.parse([_body(text)])


# ---- New York, from OPEN-NY's real 2026 plan


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("April - third week", dt.date(2026, 4, 15), dt.date(2026, 4, 21)),
        ("March - fourth week", dt.date(2026, 3, 22), dt.date(2026, 3, 31)),
        ("May", dt.date(2026, 5, 1), dt.date(2026, 5, 31)),
        ("Mid April", dt.date(2026, 4, 11), dt.date(2026, 4, 20)),
        ("Early May", dt.date(2026, 5, 1), dt.date(2026, 5, 10)),
        ("March - April", dt.date(2026, 3, 1), dt.date(2026, 4, 30)),
        ("Spring", dt.date(2026, 3, 1), dt.date(2026, 6, 30)),
    ],
)
def test_ny_words_are_kept_verbatim_and_only_bounded(text, start, end):
    p = ny.period(text, 2026)
    assert p.precision == "approximate"
    assert p.label == f"{text}, 2026"  # DEC's words, never a date
    assert (p.start, p.end) == (start, end)


def test_ny_real_plan_parses_every_row_it_can_read():
    feed = ny.parse([_body(_text("ny.json"))])
    assert len(feed.waters) == 582
    assert len(feed.records) >= ny.SOURCE.min_rows
    assert {r.period.precision for r in feed.records} == {"approximate"}
    assert all(r.period.label.endswith(", 2026") for r in feed.records)


def test_ny_negative_control_an_unknown_date_form_is_refused():
    text = _text("ny.json").replace(
        '"date":"April - third week"', '"date":"Around Easter"', 1
    )
    if text == _text("ny.json"):
        text = _text("ny.json").replace(
            '"date": "April - third week"', '"date": "Around Easter"', 1
        )
    assert "Around Easter" in text
    with pytest.raises(StateFormatError, match="does not know"):
        ny.parse([_body(text)])


def test_a_plan_never_infers_a_removal():
    feed = ny.parse([_body(_text("ny.json"))])
    history = merge(
        StateHistory.empty("NY"), feed, ny.SOURCE, as_of=dt.date(2026, 3, 1)
    )
    fewer = dataclasses.replace(feed, records=feed.records[:10])
    merged = merge(history, fewer, ny.SOURCE, as_of=dt.date(2026, 3, 2))
    assert {r.status for r in merged.records} == {"listed"}
    assert not ny.SOURCE.removal_inference


def test_every_state_is_fetched_by_the_daily_run_now_that_each_works_live():
    assert ENABLED_STATES == ("TN", "MI", "MA", "NY")
    assert set(SOURCES) == {"TN", "MA", "MI", "NY"}


# ---- the strict robots rule


@respx.mock
def test_robots_readable_and_allowing_lets_the_fetch_go_ahead():
    respx.get("https://www.tn.gov/robots.txt").respond(
        200, text="User-agent: *\n\nAllow: /", headers={"content-type": "text/plain"}
    )
    with httpx.Client() as client:
        check_robots_strict(client, tn.DATA_URL, UA)


@pytest.mark.parametrize(
    ("status", "headers", "body"),
    [
        (403, {"content-type": "text/plain"}, "Invalid URL"),  # services1.arcgis.com
        (301, {"location": "https://www.arcgis.com"}, ""),  # utility.arcgis.com
        (500, {}, ""),
        (200, {"content-type": "text/html"}, "<html>home</html>"),
    ],
)
@respx.mock
def test_an_unreadable_robots_txt_puts_the_host_off_limits(status, headers, body):
    robots = respx.get("https://services1.arcgis.com/robots.txt").respond(
        status, text=body, headers=headers
    )
    layer = "https://services1.arcgis.com/x/arcgis/rest/services/y/FeatureServer/0"
    data = respx.get(url__startswith=layer)
    with httpx.Client() as client, pytest.raises(RobotsUnreadableError):
        check_robots_strict(client, layer, UA)
    assert robots.called
    assert not data.called  # nothing else on the host is asked for


@respx.mock
def test_a_missing_robots_txt_404_means_no_rules():
    """The owner's ruling (DECISIONS 0025): no file is "no rules"."""
    robots = respx.get("https://www.tn.gov/robots.txt").respond(404, text="<html>")
    with httpx.Client() as client:
        check_robots_strict(client, tn.DATA_URL, UA)
    assert robots.called


@respx.mock
def test_a_robots_disallow_is_honored():
    respx.get("https://www.tn.gov/robots.txt").respond(
        200,
        text="User-agent: *\nDisallow: /twra/",
        headers={"content-type": "text/plain"},
    )
    data = respx.get(tn.DATA_URL)
    with httpx.Client() as client, pytest.raises(RobotsDisallowedError):
        tn.fetch(client, UA, no_sleep)
    assert not data.called


@respx.mock
def test_tn_live_fetch_sends_an_honest_user_agent_and_never_a_browser_one():
    respx.get("https://www.tn.gov/robots.txt").respond(
        200, text="User-agent: *\n\nAllow: /", headers={"content-type": "text/plain"}
    )
    data = respx.get(tn.DATA_URL).respond(
        200, text=_tn_text(), headers={"last-modified": "Fri, 09 Oct 2026 21:29:40 GMT"}
    )
    with httpx.Client() as client:
        bodies = tn.fetch(client, UA, no_sleep)
    sent = data.calls.last.request.headers["user-agent"]
    assert sent == UA
    assert "Mozilla" not in sent
    assert bodies[0].last_modified == "Fri, 09 Oct 2026 21:29:40 GMT"


HUB_ROBOTS = "User-agent: *\nCrawl-delay: 60\nDisallow: /sites/\n"


@respx.mock
def test_ma_reads_hub_politely_and_never_the_403_host():
    respx.get("https://hub.arcgis.com/robots.txt").respond(
        200, text=HUB_ROBOTS, headers={"content-type": "text/plain"}
    )
    blocked = respx.get(url__startswith="https://services1.arcgis.com/")
    result = (
        "https://hub.arcgis.com/api/v3/datasets/e27aa5ec1ef74659aac1ef12b39510f1_0"
        "/downloads/data?format=csv&spatialRefId=2249&where=1%3D1"
    )
    status = respx.get(url__startswith=ma.DOWNLOAD_URL).mock(
        side_effect=[
            httpx.Response(202, json={"status": "Pending"}),
            httpx.Response(200, json={"status": "Completed", "resultUrl": result}),
        ]
    )
    csv_route = respx.get(url__startswith=result.split("?")[0]).respond(
        200, text=_text("ma.csv")
    )
    slept: list[float] = []
    with httpx.Client() as client:
        bodies = ma.fetch(client, UA, slept.append)
    assert status.call_count == 2 and csv_route.called
    assert slept == [61.0, 61.0]  # the Crawl-delay, plus a second, between requests
    assert not blocked.called
    assert len(ma.parse(bodies).records) == 150


@respx.mock
def test_ma_refuses_a_result_url_on_another_host():
    respx.get("https://hub.arcgis.com/robots.txt").respond(
        200, text=HUB_ROBOTS, headers={"content-type": "text/plain"}
    )
    respx.get(url__startswith=ma.DOWNLOAD_URL).respond(
        200,
        json={"status": "Completed", "resultUrl": "https://services1.arcgis.com/x.csv"},
    )
    blocked = respx.get(url__startswith="https://services1.arcgis.com/")
    with httpx.Client() as client, pytest.raises(StateFetchError, match="not followed"):
        ma.fetch(client, UA, no_sleep)
    assert not blocked.called


@respx.mock
def test_mi_asks_conditionally_and_a_304_changes_nothing(tmp_path: Path):
    respx.get("https://michigandnr.com/robots.txt").respond(404, text="<html>")
    route = respx.get(mi.CSV_URL).respond(304)
    history = StateHistory.empty("MI")
    history = dataclasses.replace(
        history,
        checks=dataclasses.replace(
            history.checks, etag='"abc"', last_modified="Fri, 09 Oct 2026 18:27:05 GMT"
        ),
    )
    history.save(tmp_path / "mi.json")
    with httpx.Client() as client:
        runs = srun.run_states(
            states_dir=tmp_path,
            fetch_codes=["MI"],
            user_agent=UA,
            now=NOW,
            client=client,
            sleep=no_sleep,
        )
    sent = route.calls.last.request.headers
    assert sent["if-none-match"] == '"abc"'
    assert sent["if-modified-since"] == "Fri, 09 Oct 2026 18:27:05 GMT"
    assert "text/csv" in sent["accept"] and "octet-stream" in sent["accept"]
    run = next(r for r in runs if r.source.code == "MI")
    assert run.outcome == "unchanged"
    assert run.history.records == []
    assert run.history.checks.last_success_at == NOW


# ---- the state history


def _tn_history() -> StateHistory:
    feed = tn.parse([_body(_tn_text())])
    return merge(StateHistory.empty("TN"), feed, tn.SOURCE, as_of=dt.date(2026, 10, 12))


def test_schedule_removal_only_for_a_period_that_has_not_ended():
    history = _tn_history()
    feed = tn.parse([_body(_tn_text(), NOW + dt.timedelta(days=1))])
    future = next(r for r in feed.records if r.period.start > dt.date(2026, 10, 20))
    past = next(r for r in feed.records if r.period.end < dt.date(2026, 10, 1))
    shrunk = dataclasses.replace(
        feed, records=[r for r in feed.records if r not in (future, past)]
    )
    merged = merge(history, shrunk, tn.SOURCE, as_of=dt.date(2026, 10, 13))
    by_key = {r.key(): r for r in merged.records}
    assert by_key[future.key()].status == "removed"
    assert by_key[past.key()].status == "listed"  # aged off, not removed
    # Relisted: listed again.
    again = merge(merged, feed, tn.SOURCE, as_of=dt.date(2026, 10, 14))
    assert {r.key(): r for r in again.records}[future.key()].status == "listed"


def test_a_report_never_infers_a_removal():
    feed = ma.parse([_body(_text("ma.csv"))])
    history = merge(
        StateHistory.empty("MA"), feed, ma.SOURCE, as_of=dt.date(2026, 10, 12)
    )
    assert {r.status for r in history.records} == {"reported"}
    one_row = dataclasses.replace(feed, records=feed.records[:1])
    merged = merge(history, one_row, ma.SOURCE, as_of=dt.date(2026, 10, 30))
    assert {r.status for r in merged.records} == {"reported"}
    assert len(merged.records) == len(history.records)


# ---- Michigan: a row the DNR revises is not shown twice (audit 2026-11-05 #9)

# A real fixture row with a site. The "before" file is the same file with
# that row's site blank, which is how the DNR first published the two
# Manistee River rows it gave a site on 2026-10-30.
_SITED = (
    "Iosco,Au Sable River,REA ROAD,24N,08E,35,Rainbow trout           "
    ",Michigan         ,none,06/01/2026,5076,7.68,State Plant"
)


def _mi_before_and_after() -> tuple[str, str]:
    after = _text("mi.csv")
    assert after.count(_SITED) == 1
    before = after.replace(_SITED, _SITED.replace(",REA ROAD,", ",,"))
    assert before != after
    return before, after


def _mi_key(site: str) -> tuple[str, str, str, str]:
    wid = mi.water_id("Iosco", "Au Sable River", site)
    return (wid, "2026-06-01", "day", "Rainbow trout")


def test_mi_a_revised_row_is_withdrawn_and_published_once():
    before, after = _mi_before_and_after()
    later = NOW + dt.timedelta(days=6)
    first = merge(
        StateHistory.empty("MI"),
        mi.parse([_body(before)]),
        mi.SOURCE,
        as_of=NOW.date(),
    )
    revised = merge(
        first, mi.parse([_body(after, later)]), mi.SOURCE, as_of=later.date()
    )
    by_key = {r.key(): r for r in revised.records}
    ghost, real = by_key[_mi_key("")], by_key[_mi_key("REA ROAD")]
    assert ghost.status == "withdrawn"
    assert ghost.last_observed_at == NOW  # the last time the DNR had it
    assert ghost.first_observed_at == NOW
    assert real.status == "reported"
    # Nothing is deleted: the history keeps both, and still saves.
    assert len(revised.records) == len(first.records) + 1
    # Every other record is untouched.
    assert {r.status for r in revised.records if r.key() != ghost.key()} == {"reported"}

    published = snapshot_v2._published(mi.SOURCE, revised.records)
    stocked = [
        r
        for r in published
        if r.period.start == dt.date(2026, 6, 1)
        and r.species == "Rainbow trout"
        and r.count == 5076
    ]
    assert [r.water_id for r in stocked] == [real.water_id]
    # The site-less water had only that stocking, so it gets no entry (and
    # no page) at all.
    waters = snapshot_v2._state_waters(mi.SOURCE, revised, published, later.date())
    assert ghost.water_id not in {w["id"] for w in waters}
    assert real.water_id in {w["id"] for w in waters}


def test_mi_a_withdrawn_row_the_dnr_puts_back_is_reported_again():
    before, after = _mi_before_and_after()
    t1, t2 = NOW + dt.timedelta(days=1), NOW + dt.timedelta(days=2)
    history = merge(
        StateHistory.empty("MI"), mi.parse([_body(before)]), mi.SOURCE, as_of=NOW.date()
    )
    history = merge(history, mi.parse([_body(after, t1)]), mi.SOURCE, as_of=t1.date())
    assert {r.key(): r for r in history.records}[_mi_key("")].status == "withdrawn"
    history = merge(history, mi.parse([_body(before, t2)]), mi.SOURCE, as_of=t2.date())
    back = {r.key(): r for r in history.records}[_mi_key("")]
    assert back.status == "reported"
    assert back.first_observed_at == NOW
    assert back.last_observed_at == t2


def test_mi_negative_control_a_file_that_drops_too_many_rows_is_refused():
    feed = mi.parse([_body(_text("mi.csv"))])
    history = merge(StateHistory.empty("MI"), feed, mi.SOURCE, as_of=NOW.date())
    cut = dataclasses.replace(feed, records=feed.records[MAX_NEWLY_WITHDRAWN + 1 :])
    assert len(feed.records) - len(cut.records) == MAX_NEWLY_WITHDRAWN + 1
    with pytest.raises(StateHistoryError, match="no longer has"):
        merge(history, cut, mi.SOURCE, as_of=NOW.date())
    # At the limit it is read as revisions.
    at_limit = dataclasses.replace(feed, records=feed.records[MAX_NEWLY_WITHDRAWN:])
    merged = merge(history, at_limit, mi.SOURCE, as_of=NOW.date())
    assert sum(r.status == "withdrawn" for r in merged.records) == MAX_NEWLY_WITHDRAWN


def test_mi_run_refuses_a_shrunken_file_and_keeps_the_last_good_data(tmp_path: Path):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    states_dir = tmp_path / "states"
    feed = mi.parse([_body(_text("mi.csv"))])
    good = merge(StateHistory.empty("MI"), feed, mi.SOURCE, as_of=NOW.date())
    good.save(srun.history_path(states_dir, "MI"))
    lines = _text("mi.csv").splitlines()
    public = [
        n
        for n, line in enumerate(lines)
        if "trout" in line.lower() and line.endswith(",State Plant")
    ]
    drop = set(public[: MAX_NEWLY_WITHDRAWN * 4])
    (fixtures / "mi.csv").write_text(
        "\n".join(line for n, line in enumerate(lines) if n not in drop) + "\n",
        encoding="utf-8",
    )
    runs = srun.run_states(
        states_dir=states_dir,
        fetch_codes=["MI"],
        user_agent=UA,
        now=NOW + dt.timedelta(days=1),
        fixtures_dir=fixtures,
    )
    run = next(r for r in runs if r.source.code == "MI")
    assert run.outcome == "failed"
    assert "no longer has" in (run.history.checks.last_error or "")
    assert run.history.records == good.records


def test_a_report_that_ages_rows_off_never_withdraws_them():
    assert mi.SOURCE.whole_file
    assert not ma.SOURCE.whole_file and not tn.SOURCE.whole_file
    assert not ny.SOURCE.whole_file
    feed = ma.parse([_body(_text("ma.csv"))])
    history = merge(
        StateHistory.empty("MA"), feed, ma.SOURCE, as_of=dt.date(2026, 10, 12)
    )
    one_row = dataclasses.replace(feed, records=feed.records[:1])
    merged = merge(history, one_row, ma.SOURCE, as_of=dt.date(2026, 10, 30))
    assert {r.status for r in merged.records} == {"reported"}


def test_history_refuses_to_drop_a_record_or_change_a_slug(tmp_path: Path):
    path = tmp_path / "tn.json"
    history = _tn_history()
    history.save(path)
    dropped = dataclasses.replace(history, records=history.records[1:])
    with pytest.raises(StateHistoryError, match="missing"):
        dropped.save(path)
    wid = next(iter(history.waters))
    moved = dict(history.waters)
    moved[wid] = dataclasses.replace(moved[wid], slug="somewhere-else")
    with pytest.raises(StateHistoryError, match="slug"):
        dataclasses.replace(history, waters=moved).save(path)


def test_a_water_keeps_its_first_slug_and_remembers_old_names():
    history = _tn_history()
    feed = tn.parse([_body(_tn_text())])
    wid = "tn-monroe-tellico-river"
    renamed = dict(feed.waters)
    renamed[wid] = dataclasses.replace(
        renamed[wid], name="Tellico River (upper)", slug="x"
    )
    merged = merge(
        history,
        dataclasses.replace(feed, waters=renamed),
        tn.SOURCE,
        as_of=dt.date(2026, 10, 12),
    )
    assert merged.waters[wid].slug == history.waters[wid].slug
    assert merged.waters[wid].name == "Tellico River (upper)"
    assert merged.aliases[wid] == ["Tellico River", "Tellico River (upper)"]


def test_a_failure_changes_only_the_checks():
    history = _tn_history()
    failed = record_failure(history, attempted_at=NOW, error="boom")
    assert failed.records == history.records
    assert failed.checks.last_attempt_ok is False
    assert failed.checks.last_success_at == history.checks.last_success_at


def test_one_failing_state_does_not_stop_another(tmp_path: Path):
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    (fixtures / "tn.json").write_text(_tn_text(), encoding="utf-8")
    (fixtures / "ma.csv").write_text("not,the,columns\n", encoding="utf-8")
    runs = {
        r.source.code: r
        for r in srun.run_states(
            states_dir=tmp_path,
            fetch_codes=["TN", "MA"],
            user_agent=UA,
            now=NOW,
            fixtures_dir=fixtures,
        )
    }
    assert runs["TN"].outcome == "updated"
    assert runs["MA"].outcome == "failed"
    assert runs["MI"].outcome == "skipped"
    assert not runs["MI"].needs_write


def test_an_unknown_state_code_is_refused(tmp_path: Path):
    with pytest.raises(Exception, match="unknown state"):
        srun.run_states(states_dir=tmp_path, fetch_codes=["ZZ"], user_agent=UA, now=NOW)


def test_the_committed_tn_history_is_the_real_fetch_of_2026_10_12():
    data_path = Path(__file__).resolve().parents[1] / "data" / "states" / "tn.json"
    history = StateHistory.load(data_path, "TN")
    assert history.checks.last_success_at is not None
    assert history.checks.last_success_at >= NOW
    assert len(history.waters) >= 136


@respx.mock
def test_mi_a_304_withdraws_ghosts_already_in_history(tmp_path: Path):
    """History written before the rule: the ghost was last seen by an older
    full fetch than every other record. A 304 run withdraws it, as the
    Manistee River pair (last seen 2026-10-26) will be on the first run."""
    respx.get("https://michigandnr.com/robots.txt").respond(404, text="<html>")
    respx.get(mi.CSV_URL).respond(304)
    before, after = _mi_before_and_after()
    t1 = NOW + dt.timedelta(days=4)
    plain = dataclasses.replace(mi.SOURCE, whole_file=False)
    old = merge(
        StateHistory.empty("MI"), mi.parse([_body(before)]), plain, as_of=NOW.date()
    )
    old = merge(old, mi.parse([_body(after, t1)]), plain, as_of=t1.date())
    ghost = {r.key(): r for r in old.records}[_mi_key("")]
    assert ghost.status == "reported"  # the bug, as it is on disk today
    old.save(srun.history_path(tmp_path, "MI"))
    with httpx.Client() as client:
        runs = srun.run_states(
            states_dir=tmp_path,
            fetch_codes=["MI"],
            user_agent=UA,
            now=t1 + dt.timedelta(hours=12),
            client=client,
            sleep=no_sleep,
        )
    run = next(r for r in runs if r.source.code == "MI")
    assert run.outcome == "unchanged"
    assert "1 no longer in the agency's file" in run.message
    by_key = {r.key(): r for r in run.history.records}
    assert by_key[_mi_key("")].status == "withdrawn"
    assert sum(r.status == "withdrawn" for r in run.history.records) == 1
    run.history.save(srun.history_path(tmp_path, "MI"))  # still append-only
