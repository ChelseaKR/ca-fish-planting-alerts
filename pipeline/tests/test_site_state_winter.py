"""A state hub's winter section (DECISIONS 0070).

A schedule or plan state's hub lists every water its own data gives a date
for from November through February, each date at the agency's precision.
The section, its line in the meta description and its line in llms.txt
exist only when the data lists at least one water that winter, so an empty
file never reads as "no winter stocking". Each built-page check runs on the
real committed Tennessee history (a failed check, 2026-10-21) and, as a
negative control, on a build whose winter the data does not reach."""

from __future__ import annotations

import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, llms, site, site_states, snapshot_v2
from cfpa.states import SOURCES
from cfpa.states.store import StateHistory

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO = Path(__file__).resolve().parents[2]
V1_SCHEMA = REPO / "schema" / "snapshot.v1.json"
COMMITTED_TN = FIXTURES / "states" / "tn-2026-10-21-failed-check.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
BANNED = re.compile(
    r"\b(only|first|best|expect|likely|usually|typically|stocked on|planted on)\b",
    re.I,
)

# 2026-11-20, mid-morning in Tennessee: inside the 2026-27 winter.
IN_WINTER = dt.datetime(2026, 11, 20, 15, 0, tzinfo=dt.UTC)
# 2027-06-01: the hub shows the 2027-28 winter, which the 2026-10-15 file
# does not reach (its newest date is 2026-12-24).
PAST_THE_FILE = dt.datetime(2027, 6, 1, 15, 0, tzinfo=dt.UTC)


# ---- the window --------------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "first", "last", "shown_from"),
    [
        ("2026-11-14", "2026-11-01", "2027-02-28", "2026-03-01"),
        ("2027-01-10", "2026-11-01", "2027-02-28", "2026-03-01"),
        ("2027-02-28", "2026-11-01", "2027-02-28", "2026-03-01"),
        ("2027-03-01", "2027-11-01", "2028-02-29", "2027-03-01"),
        ("2027-10-31", "2027-11-01", "2028-02-29", "2027-03-01"),
        ("2028-02-29", "2027-11-01", "2028-02-29", "2027-03-01"),
    ],
)
def test_the_window_is_november_through_february_and_moves_on_march_1(
    today: str, first: str, last: str, shown_from: str
):
    got = site_states.winter_window(dt.date.fromisoformat(today))
    assert [d.isoformat() for d in got] == [first, last, shown_from]


# ---- which rows ---------------------------------------------------------------


def _period(precision: str, start: str, end: str | None = None) -> dict[str, str]:
    label = {
        "day": start,
        "week": f"week of {start}",
        "month": f"TBD {start[5:7]}/{start[:4]}",
    }[precision]
    return {"precision": precision, "start": start, "end": end or start, "label": label}


def _water(slug: str, *plants: tuple[dict[str, str], str]) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "counties": ["Knox"],
        "towns": [],
        "region": None,
        "plants": [{"period": p, "status": s} for p, s in plants],
    }


STATE = {"semantics": "schedule", "regions": []}
TODAY = dt.date(2026, 11, 14)


def test_rows_are_the_winter_dates_by_start_never_a_removed_one():
    waters = [
        _water(
            "edge-pond",
            (_period("day", "2026-10-31"), "listed"),  # the day before: out
            (_period("week", "2026-11-01", "2026-11-07"), "listed"),  # in
            (_period("day", "2027-02-28"), "listed"),  # the last day: in
            (_period("day", "2027-03-01"), "listed"),  # the day after: out
        ),
        _water(
            "dropped-creek",
            (_period("day", "2026-12-09"), "removed"),
        ),
        _water(
            "month-lake",
            (_period("month", "2026-12-01", "2026-12-31"), "listed"),
        ),
    ]
    got = site_states.winter_schedule(STATE, waters, TODAY)
    assert got is not None
    assert got["label"] == "November 2026 to February 2027"
    assert [r["slug"] for r in got["waters"]] == ["edge-pond", "month-lake"]
    assert got["waters"][0]["whens"] == ["week of 2026-11-01", "2027-02-28"]
    # A month stays a month: the agency set no day.
    assert got["waters"][1]["whens"] == ["TBD 12/2026 (day not set yet)"]
    assert (got["water_count"], got["date_count"]) == (2, 3)


def test_no_winter_row_means_no_section_never_an_empty_one():
    waters = [_water("spring-pond", (_period("day", "2027-04-02"), "listed"))]
    assert site_states.winter_schedule(STATE, waters, TODAY) is None
    # Control: the same water with one winter date does get a section, so
    # the None above is about the dates, not the shape of the input.
    waters[0]["plants"].append(
        {"period": _period("day", "2027-01-09"), "status": "listed"}
    )
    assert site_states.winter_schedule(STATE, waters, TODAY) is not None


def test_a_report_state_never_gets_a_winter_section():
    """A report holds stockings already made, never future dates."""
    waters = [_water("report-pond", (_period("day", "2026-11-03"), "reported"))]
    report = {**STATE, "semantics": "report"}
    assert site_states.winter_schedule(report, waters, TODAY) is None
    assert site_states.winter_schedule(STATE, waters, TODAY) is not None  # control


# ---- the built hub ---------------------------------------------------------------


class _Visible(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._skip += tag in ("script", "style")

    def handle_endtag(self, tag: str) -> None:
        self._skip -= tag in ("script", "style")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _text(html: str) -> str:
    p = _Visible()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


@pytest.fixture(scope="module")
def v1(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("v1")
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp / "history.json",
        aliases_path=tmp / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=tmp / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    data: dict[str, Any] = json.loads(
        (tmp / "site/snapshot/v1.json").read_text("utf-8")
    )
    return data


def _build(
    v1: dict[str, Any], tmp: Path, generated: dt.datetime
) -> tuple[Path, dict[str, Any]]:
    history = StateHistory.load(COMMITTED_TN, "TN")
    v2 = snapshot_v2.build_snapshot_v2(
        v1, [(SOURCES["TN"], history)], generated_at=generated
    )
    out = tmp / "site"
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    return out, v2


def _section(html: str) -> str:
    i = html.index('<h2 id="winter">')
    return html[i : html.index("<h2>", i)]


def _description(html: str) -> str:
    m = re.search(r'<meta name="description" content="([^"]*)"', html)
    assert m
    return m.group(1).replace("&#39;", "'")


def _expected_slugs(v2: dict[str, Any], today: dt.date) -> set[str]:
    """The Tennessee waters with a winter row, computed from the snapshot
    without the code under test."""
    first, last, _ = site_states.winter_window(today)
    return {
        w["slug"]
        for w in v2["waters"]
        if w["state"] == "TN"
        and any(
            p["status"] != "removed"
            and first.isoformat() <= p["period"]["start"] <= last.isoformat()
            for p in w["plants"]
        )
    }


def _wording_problems(section: str, n: int) -> list[str]:
    text = _text(section)
    wanted = {
        f"lists {n} Tennessee waters": "water count missing",
        "not confirmed stockings": "schedule caveat missing",
        "The latest check failed": "failed check not said",
    }
    problems = [msg for phrase, msg in wanted.items() if phrase not in text]
    # Owner copy rules apply to the sentences this section writes, not to
    # the agency's water names (a real one is "Covington First Baptist
    # Church Pond").
    prose = _text(section[: section.index("<table>")])
    if BANNED.search(prose):
        problems.append(f"banned word: {BANNED.search(prose)}")
    return problems


def winter_problems(html: str, v2: dict[str, Any], today: dt.date) -> list[str]:
    """What the hub's winter section gets wrong against the snapshot."""
    first, last, _ = site_states.winter_window(today)
    expected = _expected_slugs(v2, today)
    if not expected:
        return ["the test data has no winter row"]
    problems: list[str] = []
    section = _section(html)
    shown = set(re.findall(r'<td><a href="water/([^/"]+)/">', section))
    if shown != expected:
        problems.append(f"waters differ: {sorted(shown ^ expected)[:5]}")
    body = re.sub(r"<caption.*?</caption>", "", section, flags=re.S)
    problems += [
        f"date outside the winter: {d}"
        for d in re.findall(r"\d{4}-\d{2}-\d{2}", body)
        if not first.isoformat() <= d <= last.isoformat() and d != "2026-10-15"
    ]
    problems += _wording_problems(section, len(expected))
    desc = _description(html)
    if f"winter dates at {len(expected)} waters through" not in desc:
        problems.append("description does not name the winter")
    if len(desc) > site_states.HUB_DESCRIPTION_MAX:
        problems.append("description too long")
    return problems


def test_the_hub_lists_every_winter_water_from_the_snapshot(
    v1: dict[str, Any], tmp_path: Path
):
    out, v2 = _build(v1, tmp_path, IN_WINTER)
    html = (out / "tn" / "index.html").read_text("utf-8")
    assert winter_problems(html, v2, dt.date(2026, 11, 20)) == []
    text = _text(_section(html))
    assert (
        "Winter trout stocking on TWRA's schedule: November 2026 to February 2027"
        in text
    )
    assert "as last read 2026-10-15 13:31 UTC" in text
    assert (
        '<a href="https://www.tn.gov/twra/fishing/trout-information-stockings.html">'
        in _section(html)
    )
    # The section sits after "Coming up" and before the water index.
    assert html.index("<h2>Coming up") < html.index('id="winter"')
    assert html.index('id="winter"') < html.index("<h2>Every Tennessee water")


def test_negative_control_the_check_rejects_a_sabotaged_section(
    v1: dict[str, Any], tmp_path: Path
):
    out, v2 = _build(v1, tmp_path, IN_WINTER)
    good = (out / "tn" / "index.html").read_text("utf-8")
    today = dt.date(2026, 11, 20)
    assert winter_problems(good, v2, today) == []
    row = re.search(
        r"<tr><td><a href=\"water/[^\"]+/\">.*?</tr>\n", _section(good), re.S
    )
    assert row
    dropped = good.replace(row.group(0), "", 1)
    assert dropped != good
    assert winter_problems(dropped, v2, today)
    reworded = good.replace("not confirmed stockings, and TWRA", "stockings, and TWRA")
    assert reworded != good
    assert winter_problems(reworded, v2, today)


def test_with_no_winter_in_the_data_the_hub_has_no_section_and_its_old_description(
    v1: dict[str, Any], tmp_path: Path
):
    out, v2 = _build(v1, tmp_path, PAST_THE_FILE)
    tn = next(s for s in v2["states"] if s["code"] == "TN")
    waters = [w for w in v2["waters"] if w["state"] == "TN"]
    # The sabotage applied: this build's winter is beyond the file.
    assert site_states.winter_schedule(tn, waters, dt.date(2027, 6, 1)) is None
    html = (out / "tn" / "index.html").read_text("utf-8")
    assert 'id="winter"' not in html
    assert "Winter" not in _text(html).replace("Winter here", "")
    assert _description(html) == (
        "Where Tennessee Wildlife Resources Agency has scheduled trout stocking "
        "in Tennessee: this week, what is coming up, and the stocking history of "
        f"all {tn['waters_count']} waters."
    )
    assert "#winter" not in (out / "llms.txt").read_text("utf-8")


def test_llms_txt_points_at_the_winter_section_with_the_hubs_numbers(
    v1: dict[str, Any], tmp_path: Path
):
    out, _ = _build(v1, tmp_path, IN_WINTER)
    line = next(
        ln
        for ln in (out / "llms.txt").read_text("utf-8").split("\n")
        if ln.startswith("- [Tennessee]")
    )
    n = len(
        re.findall(
            r'<td><a href="water/', _section((out / "tn/index.html").read_text("utf-8"))
        )
    )
    assert (
        f"Winter ({BASE}/tn/#winter): the {n} waters on TWRA's schedule from "
        "November 2026 through February 2027, each date as TWRA gives it." in line
    )


def test_a_plan_hub_line_says_plan_never_schedule():
    hub = {
        "name": "New York",
        "url": f"{BASE}/ny/",
        "agency_name": "New York State Department of Environmental Conservation",
        "agency_short": "NYS DEC",
        "semantics": "plan",
        "water_count": 3,
        "manual": False,
        "manual_sentence": "",
        "attempt_failed": False,
        "fetched_label": "2026-11-14 13:21 UTC",
        "attempt_label": "2026-11-14 13:21 UTC",
        "winter": {
            "water_count": 2,
            "first_label": "November 2026",
            "end_label": "February 2027",
        },
    }
    line = llms._hub_line(hub)
    assert "the 2 waters on NYS DEC's plan from November 2026" in line
    assert "schedule" not in line.split("Winter")[1]
    assert "Winter" not in llms._hub_line({**hub, "winter": None})  # control
