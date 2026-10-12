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

from cfpa.states import ENABLED_STATES, SOURCES, ma, mi, tn
from cfpa.states import run as srun
from cfpa.states.base import (
    USER_AGENT_TEMPLATE,
    FetchedBody,
    Period,
    RobotsDisallowedError,
    RobotsUnreadableError,
    StateFormatError,
    check_robots_strict,
    no_sleep,
)
from cfpa.states.store import (
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


def test_tn_negative_control_a_week_date_that_is_not_a_sunday_is_refused():
    doc = _tn_doc()
    row = next(r for r in doc["data"] if r["STOCKING WEEK"].strip())
    row["STOCKING WEEK"] = "10/13/2026"  # a Tuesday
    text = json.dumps(doc)
    assert '"STOCKING WEEK": "10/13/2026"' in text  # the sabotage landed
    with pytest.raises(StateFormatError, match="Sunday"):
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


def test_ma_fixture_is_labeled_synthetic():
    doc = json.loads((STATE_FIXTURES / "ma.json").read_text())
    assert doc["_fixture_note"].startswith("SYNTHETIC FIXTURE")


def test_ma_parses_reports_by_day_with_towns_not_counties():
    feed = ma.parse([_body((STATE_FIXTURES / "ma.json").read_text())])
    assert feed.skipped == 1  # the row with no date
    swift = feed.waters["ma-swift-belch"]
    assert swift.towns == ("Belchertown",)
    assert swift.counties == ()
    assert swift.source_id == "SWIFT-BELCH"
    days = sorted(
        r.period.start for r in feed.records if r.water_id == "ma-swift-belch"
    )
    assert days == [dt.date(2026, 10, 6), dt.date(2026, 10, 9)]
    assert {r.period.precision for r in feed.records} == {"day"}


def test_ma_negative_control_a_renamed_field_is_refused():
    text = (STATE_FIXTURES / "ma.json").read_text().replace('"Waterbody"', '"Water"')
    assert '"Waterbody"' not in text
    with pytest.raises(StateFormatError, match="missing fields"):
        ma.parse([_body(text)])


def test_mi_reads_every_page_and_sums_two_lots_on_one_day():
    bodies = [_body((STATE_FIXTURES / f"mi-{i}.json").read_text()) for i in (0, 1)]
    feed = mi.parse(bodies)
    au_sable = sorted(
        (r.period.start, r.species, r.count)
        for r in feed.records
        if r.water_id == "mi-1234"
    )
    assert au_sable == [
        (dt.date(2026, 4, 21), "Brown Trout", 5000),
        (dt.date(2026, 7, 29), "Rainbow Trout", 4000),
    ]
    assert feed.waters["mi-1234"].counties == ("Crawford",)


def test_mi_negative_control_a_negative_count_is_refused():
    text = (
        (STATE_FIXTURES / "mi-0.json")
        .read_text()
        .replace('"number_fish": 5000', '"number_fish": -5')
    )
    assert '"number_fish": -5' in text
    with pytest.raises(StateFormatError, match="whole count"):
        mi.parse([_body(text)])


def test_mi_rereads_a_lookback_window_and_never_before_its_publish_date():
    assert mi.since_date(None) == mi.PUBLISH_SINCE
    assert mi.since_date(dt.date(2026, 9, 18)) == dt.date(2026, 5, 21)
    assert mi.since_date(dt.date(2021, 2, 1)) == mi.PUBLISH_SINCE


def test_only_tennessee_is_fetched_by_the_daily_run():
    assert ENABLED_STATES == ("TN",)
    assert set(SOURCES) == {"TN", "MA", "MI"}


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
        (404, {"content-type": "text/html"}, "<html>"),
        (500, {}, ""),
        (200, {"content-type": "text/html"}, "<html>home</html>"),
    ],
)
@respx.mock
def test_an_unreadable_robots_txt_puts_the_host_off_limits(status, headers, body):
    robots = respx.get("https://services1.arcgis.com/robots.txt").respond(
        status, text=body, headers=headers
    )
    data = respx.get(url__startswith=ma.LAYER_URL)
    with httpx.Client() as client, pytest.raises(RobotsUnreadableError):
        ma.fetch(client, UA, no_sleep)
    assert robots.called
    assert not data.called  # nothing else on the host is asked for


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


@respx.mock
def test_arcgis_pages_are_requested_politely_one_after_another():
    respx.get("https://utility.arcgis.com/robots.txt").respond(
        200, text="User-agent: *\nAllow: /", headers={"content-type": "text/plain"}
    )
    pages = [(STATE_FIXTURES / f"mi-{i}.json").read_text() for i in (0, 1)]
    route = respx.get(url__startswith=mi.LAYER_URL).mock(
        side_effect=[httpx.Response(200, text=p) for p in pages]
    )
    slept: list[float] = []
    with httpx.Client() as client:
        bodies = mi.fetch(client, UA, slept.append, dt.date(2026, 9, 18))
    assert len(bodies) == 2
    assert slept == [5.0]
    first = route.calls[0].request.url.params
    assert first["where"] == "stocking_date >= DATE '2026-05-21'"
    assert route.calls[1].request.url.params["resultOffset"] == "1000"


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
    feed = ma.parse([_body((STATE_FIXTURES / "ma.json").read_text())])
    history = merge(
        StateHistory.empty("MA"), feed, ma.SOURCE, as_of=dt.date(2026, 10, 12)
    )
    assert {r.status for r in history.records} == {"reported"}
    one_row = dataclasses.replace(feed, records=feed.records[:1])
    merged = merge(history, one_row, ma.SOURCE, as_of=dt.date(2026, 10, 30))
    assert {r.status for r in merged.records} == {"reported"}
    assert len(merged.records) == len(history.records)


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
    (fixtures / "ma.json").write_text("{not json", encoding="utf-8")
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
