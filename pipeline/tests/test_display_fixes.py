"""Two display defects found in the 2026-10-20 audits.

1. County pages put past and upcoming scheduled weeks in one "latest week"
   column. A water with a plant this week and another next week showed only
   next week (the current plant vanished), and a county with waters scheduled
   for later weeks said nothing about them under "Scheduled this week".
2. The Tennessee pages anchored "this week" and the 60-day window on the date
   of the last good fetch, so after a failed check the page named a week that
   had already ended, and the failure line gave no time for the failed check
   and no range for the dates in the data.

Each check is a function returning the problems it finds; each test runs it on
the real build and then, as a negative control, on a copy of the built file
that has been sabotaged (asserting first that the sabotage changed the file).
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from cfpa import cli, site, snapshot_v2
from cfpa.states import SOURCES
from cfpa.states.store import StateHistory

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO = Path(__file__).resolve().parents[2]
V1_SCHEMA = REPO / "schema" / "snapshot.v1.json"
COMMITTED_TN = REPO / "pipeline" / "data" / "states" / "tn.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"

BANNED_WORDS = re.compile(r"\b(only|first|stocked on|planted on)\b", re.I)


def _v1(tmp_path: Path) -> dict[str, Any]:
    """The snapshot after the two real runs the SEO tests use (the first
    teaches the aliases; the second matches them)."""
    for fixture, fetched, today in (
        (FRESH, dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC), dt.date(2026, 9, 13)),
        (
            FIXTURES / "schedule-midweek-2026-09-17.html",
            dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
            dt.date(2026, 9, 18),
        ),
    ):
        cli.run(
            fixture_path=str(fixture),
            history_path=tmp_path / "history.json",
            aliases_path=tmp_path / "aliases.json",
            schema_path=V1_SCHEMA,
            site_out=tmp_path / "plain-site",
            base_url=BASE,
            fixture_fetched_at=fetched,
            run_today=today,
        )
    return json.loads((tmp_path / "plain-site/snapshot/v1.json").read_text("utf-8"))


class _Visible(HTMLParser):
    """Collects the text outside script elements."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._in_script = self._in_script or tag == "script"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if not self._in_script:
            self.parts.append(data)


def _text(html: str) -> str:
    parser = _Visible()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _plant(week: str, species: str = "Trout") -> dict[str, Any]:
    start = dt.date.fromisoformat(week)
    return {
        "week": {
            "start": week,
            "end": (start + dt.timedelta(days=6)).isoformat(),
            "label": f"week of {week}",
        },
        "species": species,
        "status": "listed",
        "first_observed_at": "2026-09-13T12:00:00Z",
        "last_observed_at": "2026-09-13T12:00:00Z",
    }


def _with_a_water_scheduled_now_and_next_week(
    snap: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """A copy of the snapshot in which one water that is on this week's
    schedule is also scheduled for the week after. Returns (snapshot, water,
    the later week). This is the Fresno shape: a current plant that the old
    page hid behind a later one."""
    snap = copy.deepcopy(snap)
    week = snap["source_week"]["start"]
    later = (dt.date.fromisoformat(week) + dt.timedelta(days=14)).isoformat()
    entry = snap["this_week"][0]
    water = next(w for w in snap["waters"] if w["id"] == entry["water_id"])
    assert not any(p["week"]["start"] == later for p in water["plants"])
    water["plants"].append(_plant(later))
    return snap, water, later


def _county_page(out: Path, county: str) -> str:
    return (out / "county" / site.county_slug(county) / "index.html").read_text("utf-8")


def _section(html: str, start: str) -> str:
    i = html.index(start)
    j = html.find("<h2>", i + len(start))
    return html[i : j if j != -1 else len(html)]


def _row_cells(section: str) -> list[list[str]]:
    rows = re.findall(r"<tr>(.*?)</tr>", section, re.S)
    return [
        [_text(c) for c in re.findall(r"<td>(.*?)</td>", r, re.S)]
        for r in rows
        if "<td>" in r
    ]


def county_problems(
    html: str, members: list[dict[str, Any]], source_week: str, county: str
) -> list[str]:
    """What the county page gets wrong about past versus upcoming weeks."""
    problems: list[str] = []
    by_name = {w["name"]: w for w in members}
    expected_later = sorted(
        (p["week"]["start"], w["name"])
        for w in members
        for p in w["plants"]
        if p["status"] == "listed" and p["week"]["start"] > source_week
    )
    if "<h2>Scheduled for later weeks</h2>" not in html:
        return ["no later-weeks section"]
    later = _section(html, "<h2>Scheduled for later weeks</h2>")
    later_rows = _row_cells(later)
    got_later = sorted(
        (cells[0].removeprefix("week of "), cells[1]) for cells in later_rows
    )
    if got_later != expected_later:
        problems.append(f"later weeks: expected {expected_later}, saw {got_later}")
    if not expected_later and "No later week is scheduled" not in _text(later):
        problems.append("empty later-weeks section does not say so")
    history = _section(html, "<h2>Every ")
    if "(upcoming)" in history:
        problems.append("the history table still mixes upcoming into past weeks")
    for cells in _row_cells(history):
        w = by_name[cells[0]]
        through_now = [
            p["week"]["start"]
            for p in w["plants"]
            if p["status"] == "listed" and p["week"]["start"] <= source_week
        ]
        want = (
            f"week of {max(through_now)}" if through_now else "none through this week"
        )
        if cells[1] != want:
            problems.append(f"{cells[0]}: latest week {cells[1]!r}, expected {want!r}")
    if BANNED_WORDS.search(_text(html)):
        problems.append(f"banned word in {county} page")
    return problems


def test_county_pages_separate_past_from_upcoming_scheduled_weeks(tmp_path: Path):
    snap, water, later = _with_a_water_scheduled_now_and_next_week(_v1(tmp_path))
    out = tmp_path / "site"
    site.build_site(snap, out, base_url=BASE)
    source_week = snap["source_week"]["start"]
    by_county: dict[str, list[dict[str, Any]]] = {}
    for w in snap["waters"]:
        for c in w["counties"]:
            by_county.setdefault(c, []).append(w)
    # The build must exercise all three shapes, or the check proves little.
    shapes = set()
    for county, members in by_county.items():
        assert (
            county_problems(_county_page(out, county), members, source_week, county)
            == []
        ), county
        for w in members:
            starts = {p["week"]["start"] for p in w["plants"]}
            if any(s > source_week for s in starts) and any(
                s <= source_week for s in starts
            ):
                shapes.add("past and upcoming")
            elif any(s > source_week for s in starts):
                shapes.add("upcoming only")
        if not any(
            p["week"]["start"] > source_week for w in members for p in w["plants"]
        ):
            shapes.add("no upcoming in county")
    assert shapes == {"past and upcoming", "upcoming only", "no upcoming in county"}
    # The water that has a current plant and a later one shows both.
    html = _county_page(out, water["counties"][0])
    cells = next(
        c for c in _row_cells(_section(html, "<h2>Every ")) if c[0] == water["name"]
    )
    assert cells[1] == f"week of {source_week}"
    assert f"week of {later}" in _section(html, "<h2>Scheduled for later weeks</h2>")


def test_negative_control_county_check_rejects_a_page_that_merges_past_and_upcoming(
    tmp_path: Path,
):
    snap, water, later = _with_a_water_scheduled_now_and_next_week(_v1(tmp_path))
    out = tmp_path / "site"
    site.build_site(snap, out, base_url=BASE)
    county = water["counties"][0]
    members = [w for w in snap["waters"] if county in w["counties"]]
    path = out / "county" / site.county_slug(county) / "index.html"
    good = path.read_text("utf-8")
    source_week = snap["source_week"]["start"]
    assert county_problems(good, members, source_week, county) == []
    # Sabotage 1: the old display, a merged cell that hides the current week.
    cell = f"week of {source_week}"
    bad = good.replace(f"<td>{cell}</td>", f"<td>week of {later} (upcoming)</td>", 1)
    assert bad != good
    assert county_problems(bad, members, source_week, county)
    # Sabotage 2: the later-weeks section is removed.
    bad2 = good.replace("<h2>Scheduled for later weeks</h2>", "<h2>Gone</h2>", 1)
    assert bad2 != good
    try:
        problems = county_problems(bad2, members, source_week, county)
    except ValueError:
        problems = ["section missing"]
    assert problems


# ---- Tennessee


def _tn_site(tmp_path: Path, generated: dt.datetime) -> tuple[Path, dict[str, Any]]:
    history = StateHistory.load(COMMITTED_TN, "TN")
    assert history.checks.last_attempt_ok is False  # the real failed check
    v1 = _v1(tmp_path)
    v2 = snapshot_v2.build_snapshot_v2(
        v1, [(SOURCES["TN"], history)], generated_at=generated
    )
    out = tmp_path / "tn-site"
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    return out, v2


GENERATED = dt.datetime(2026, 10, 21, 1, 25, 5, tzinfo=dt.UTC)  # 2026-10-20 evening CT


def tn_freshness_problems(
    html: str, state: dict[str, Any], today: dt.date
) -> list[str]:
    text = _text(html)
    problems: list[str] = []
    week_start = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    if f"This week: the week of {week_start}" not in text:
        problems.append(f"this week is not the week of {week_start}")
    if "last read 2026-10-15 13:31 UTC" not in text:
        problems.append("last good read time missing")
    if state["checks"]["last_attempt_ok"] is False:
        if "The check on 2026-10-21 01:25 UTC failed" not in text:
            problems.append("failed check time missing")
        if "last good read" not in text:
            problems.append("failed check does not point at the last good read")
    m = re.search(r"dates in it run from (\S+) to (\S+?)\.? ", text + " ")
    if not m:
        problems.append("date range missing")
    else:
        periods = [
            p["period"]
            for w in _tn_waters(state)
            for p in w["plants"]
            if p["period"]["precision"] != "month"
        ]
        if m.group(1) != min(p["start"] for p in periods):
            problems.append(f"range start {m.group(1)}")
        if m.group(2) != max(p["end"] for p in periods):
            problems.append(f"range end {m.group(2)}")
    # Owner copy rules apply to the sentences this change writes (a real water
    # is named "Covington First Baptist Church Pond", so not the whole page).
    start = text.find("TWRA's data was last read")
    notice = text[start : text.find("This week:", start)] if start != -1 else ""
    if BANNED_WORDS.search(notice):
        problems.append("banned word")
    return problems


def _tn_waters(state: dict[str, Any]) -> list[dict[str, Any]]:
    return state["_waters"]


def test_tennessee_hub_reports_the_real_week_and_what_the_failed_check_means(
    tmp_path: Path,
):
    out, v2 = _tn_site(tmp_path, GENERATED)
    state = next(s for s in v2["states"] if s["code"] == "TN")
    state = {**state, "_waters": [w for w in v2["waters"] if w["state"] == "TN"]}
    html = (out / "tn" / "index.html").read_text("utf-8")
    assert tn_freshness_problems(html, state, dt.date(2026, 10, 20)) == []
    # The snapshot keeps the truth about the fetch: as_of stays the last good read.
    assert state["as_of"] == "2026-10-15"
    assert state["checks"]["last_success_at"] == "2026-10-15T13:31:10Z"
    assert state["current_week"]["start"] == "2026-10-18"


def test_tennessee_water_page_reports_the_failed_check_with_its_time(tmp_path: Path):
    out, _ = _tn_site(tmp_path, GENERATED)
    html = (out / "tn/water/little-river-blount-county/index.html").read_text("utf-8")
    text = _text(html)
    assert "last read 2026-10-15 13:31 UTC" in text
    assert "The check on 2026-10-21 01:25 UTC failed" in text
    assert "Next scheduled: week of 2026-10-25" in text


def test_tennessee_upcoming_window_starts_today_not_at_the_last_good_read(
    tmp_path: Path,
):
    out, _ = _tn_site(tmp_path, GENERATED)
    html = (out / "tn" / "index.html").read_text("utf-8")
    section = _section(html, "<h2>Coming up")
    whens = [c[0] for c in _row_cells(section)]
    assert whens
    # Nothing in the coming-up table may be a date that has already passed.
    for when in whens:
        start = when.removeprefix("week of ")
        assert start > "2026-10-20", when
    # A day-precision stocking later this week is in this week's table.
    this_week = [c[2] for c in _row_cells(_section(html, "<h2>This week"))]
    assert "2026-10-22" in this_week


def test_negative_control_tennessee_check_rejects_the_old_display(tmp_path: Path):
    out, v2 = _tn_site(tmp_path, GENERATED)
    state = next(s for s in v2["states"] if s["code"] == "TN")
    state = {**state, "_waters": [w for w in v2["waters"] if w["state"] == "TN"]}
    path = out / "tn" / "index.html"
    good = path.read_text("utf-8")
    assert tn_freshness_problems(good, state, dt.date(2026, 10, 20)) == []
    stale = good.replace(
        "This week: the week of 2026-10-18", "This week: the week of 2026-10-11"
    )
    assert stale != good
    assert tn_freshness_problems(stale, state, dt.date(2026, 10, 20))
    old = good.replace(
        "The check on 2026-10-21 01:25 UTC failed", "The most recent check failed"
    )
    assert old != good
    assert tn_freshness_problems(old, state, dt.date(2026, 10, 20))
