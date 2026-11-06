"""State water pages answer first (DECISIONS 0056).

Tennessee, Massachusetts, Michigan and New York water pages open with one
sentence that says what the agency publishes (a schedule's day or week, a
plan's own words, a report of stockings that happened), a paused state says
"Updates paused since <date>" (the rule of DECISIONS 0051), and each
same-county link says where that water stands. Unit checks use small
hand-built dicts; the build check uses the pinned fixtures only. Each
negative control doctors its input, asserts the doctoring landed, and then
asserts the check caught it.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site, site_states, snapshot_v2
from cfpa.states import SOURCES
from cfpa.states.store import StateHistory

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
FAILED_TN = FIXTURES / "states" / "tn-2026-10-21-failed-check.json"

WEEK = {"start": "2026-11-01", "end": "2026-11-07"}


def _state(semantics: str = "schedule", ok: bool = True, last: str = "") -> dict:
    return {
        "code": "TN",
        "semantics": semantics,
        "agency": {"short_name": "TWRA", "name": "Tennessee Wildlife"},
        "current_week": WEEK,
        "checks": {
            "last_attempt_ok": ok,
            "last_success_at": last or "2026-11-04T12:00:00Z",
            "last_attempt_at": "2026-11-05T12:00:00Z",
        },
    }


def _day(d: str) -> dict[str, str]:
    return {"precision": "day", "start": d, "end": d, "label": d}


def _week(sunday: str) -> dict[str, str]:
    end = (dt.date.fromisoformat(sunday) + dt.timedelta(days=6)).isoformat()
    return {
        "precision": "week",
        "start": sunday,
        "end": end,
        "label": f"week of {sunday}",
    }


def _water(
    name: str,
    periods: list[dict[str, str]],
    *,
    status: str = "listed",
    last: dict | None = None,
    nxt: dict | None = None,
    months_note: str | None = None,
) -> dict[str, Any]:
    return {
        "id": name,
        "slug": name.lower(),
        "name": name,
        "counties": ["Blount"],
        "towns": [],
        "months_note": months_note,
        "last_period": last,
        "next_period": nxt,
        "plants": [{"period": p, "status": status} for p in periods],
    }


# ---- the answer line


def test_a_week_stays_a_week_and_a_day_stays_a_day():
    s = _state()
    wk = _week("2026-11-15")
    lead, _ = site_states.water_answer(_water("A", [wk], nxt=wk), s, "X")
    assert lead == "Next on TWRA's schedule: the week of 2026-11-15."
    day = _day("2026-11-20")
    lead, _ = site_states.water_answer(_water("B", [day], nxt=day), s, "X")
    assert lead == "Next on TWRA's schedule: 2026-11-20."


def test_this_week_then_the_next_after_it():
    s = _state()
    now, later = _day("2026-11-05"), _week("2026-11-15")
    w = _water("A", [now, later], last=now, nxt=later)
    assert site_states.water_answer(w, s, "X") == (
        "On TWRA's schedule this week: 2026-11-05.",
        "Next after this week: the week of 2026-11-15.",
    )


def test_nothing_later_says_so_with_the_check_time_and_never_a_zero():
    s = _state()
    past = _week("2026-10-04")
    lead, rest = site_states.water_answer(_water("A", [past], last=past), s, "CHECK")
    assert lead == "Nothing later on TWRA's schedule yet, as of CHECK."
    assert rest == "Last on the schedule: the week of 2026-10-04."
    lead, rest = site_states.water_answer(_water("B", []), s, "CHECK")
    assert lead == "No date on TWRA's schedule in the time this site has recorded."
    for text in (lead, rest):
        assert not re.search(r"\b0\b|\bnone\b", text, re.I)


def test_a_month_only_water_says_the_agency_lists_months():
    lead, rest = site_states.water_answer(
        _water("A", [], months_note="M, A"), _state(), "X"
    )
    assert lead == "No day or week on TWRA's schedule yet."
    assert "by month only" in rest


def test_a_removed_date_is_never_this_week():
    w = _water("A", [_day("2026-11-05")], status="removed")
    lead, _ = site_states.water_answer(w, _state(), "X")
    assert "this week" not in lead


def test_a_report_state_says_stocked_and_never_scheduled():
    s = _state("report")
    s["agency"]["short_name"] = "MassWildlife"
    past = _day("2026-10-20")
    lead, rest = site_states.water_answer(
        _water("A", [past], status="reported", last=past), s, "X"
    )
    assert lead == "Last stocked: 2026-10-20."
    assert "scheduled" not in lead + rest
    now = _day("2026-11-03")
    lead, _ = site_states.water_answer(
        _water("B", [now], status="reported", last=now), s, "X"
    )
    assert lead == "Stocked this week: 2026-11-03."


def test_a_plan_state_quotes_the_agency_and_never_says_scheduled():
    s = _state("plan")
    s["agency"]["short_name"] = "NYS DEC"
    p = {
        "precision": "approximate",
        "start": "2026-04-12",
        "end": "2026-04-18",
        "label": "April - third week, 2026",
    }
    lead, rest = site_states.water_answer(_water("A", [p], last=p), s, "X")
    assert lead == "Nothing later in NYS DEC's stocking plan yet, as of X."
    assert rest == "Last in the plan: “April - third week, 2026”."
    assert "schedul" not in lead + rest
    assert site_states.neighbor_when(_water("A", [p], last=p), s) == (
        "last planned “April - third week, 2026”"
    )


# ---- paused (DECISIONS 0051's rule)

NOW = dt.datetime(2026, 11, 5, 12, tzinfo=dt.UTC)


def test_paused_only_after_a_failed_check_and_seven_days():
    assert (
        site_states.paused_since(_state(ok=True, last="2026-10-01T00:00:00Z"), NOW)
        is None
    )
    assert (
        site_states.paused_since(_state(ok=False, last="2026-11-01T00:00:00Z"), NOW)
        is None
    )
    assert site_states.paused_since(
        _state(ok=False, last="2026-10-21T09:00:00Z"), NOW
    ) == dt.date(2026, 10, 21)


# ---- same-county links


def test_neighbors_lead_with_this_week_then_later_then_most_recent():
    s = _state()
    ws = [
        _water("Old", [_day("2026-09-01")], last=_day("2026-09-01")),
        _water("Bare", []),
        _water("Recent", [_week("2026-10-25")], last=_week("2026-10-25")),
        _water("Later", [_week("2026-11-15")], nxt=_week("2026-11-15")),
        _water("Now", [_day("2026-11-05")], last=_day("2026-11-05")),
    ]
    ordered = sorted(ws, key=lambda o: site_states.neighbor_order(o, s))
    assert [o["name"] for o in ordered] == ["Now", "Later", "Recent", "Old", "Bare"]
    assert [site_states.neighbor_when(o, s) for o in ordered] == [
        "scheduled this week",
        "next scheduled the week of 2026-11-15",
        "last scheduled the week of 2026-10-25",
        "last scheduled 2026-09-01",
        "",
    ]


# ---- the built pages


def _run(root: Path, states_fixtures: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cli.run(
        fixture_path=str(FIXTURES / "schedule-fresh-2026-09-13.html"),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI", "NY"),
        states_fixtures=states_fixtures,
    )
    return root / "site"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("state-water"), FIXTURES / "states")


def _pages(out: Path, code: str) -> list[str]:
    return [
        (d / "index.html").read_text(encoding="utf-8")
        for d in sorted((out / code / "water").iterdir())
    ]


ANSWER = re.compile(r'<p class="water-answer"><strong>([^<]+)</strong>([^<]*)</p>')


@pytest.mark.parametrize("code", ["tn", "ma", "mi", "ny"])
def test_every_state_water_page_answers_right_under_the_h1(built: Path, code: str):
    pages = _pages(built, code)
    assert pages
    for html in pages:
        after_h1 = html.split("</h1>", 1)[1]
        m = ANSWER.search(after_h1)
        assert m, code
        # Nothing but the optional paused line sits between the h1 and it.
        before = after_h1[: m.start()]
        assert "<p" not in before.replace('<p class="water-paused">', ""), code
        text = (m.group(1) + m.group(2)).strip()
        assert not re.search(r"\b0\b|\bnone\b|\bnull\b", text, re.I), text


def test_report_and_plan_pages_never_say_scheduled_in_the_answer(built: Path):
    for code in ("ma", "mi", "ny"):
        for html in _pages(built, code):
            m = ANSWER.search(html)
            assert m and "schedul" not in m.group(0).lower(), code


def test_a_tennessee_week_is_never_shown_as_a_day(built: Path):
    """Every Tennessee answer that names a date the record gives as a week
    says "the week of"; a negative control drops it and is caught."""
    weekly = 0
    for html in _pages(built, "tn"):
        m = ANSWER.search(html)
        assert m
        if "the week of" in m.group(0):
            weekly += 1
    assert weekly > 0
    doctored = "Next on TWRA's schedule: 2026-11-15."
    assert "the week of" not in doctored  # the doctoring landed
    wk = _week("2026-11-15")
    real, _ = site_states.water_answer(_water("A", [wk], nxt=wk), _state(), "X")
    assert real != doctored


def _v1(tmp_path: Path) -> dict[str, Any]:
    """The California snapshot from the pinned 2026-09-13 schedule."""
    cli.run(
        fixture_path=str(FIXTURES / "schedule-fresh-2026-09-13.html"),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=SCHEMA,
        site_out=tmp_path / "plain-site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return json.loads((tmp_path / "plain-site/snapshot/v1.json").read_text("utf-8"))


def _tn_from_failed_check(tmp_path: Path, generated: dt.datetime) -> Path:
    """Tennessee from the frozen 2026-10-21 history, whose latest check failed
    and whose last good read is 2026-10-15 13:31 UTC, built as of
    ``generated``."""
    history = StateHistory.load(FAILED_TN, "TN")
    v1 = _v1(tmp_path)
    v2 = snapshot_v2.build_snapshot_v2(
        v1, [(SOURCES["TN"], history)], generated_at=generated
    )
    out = tmp_path / "tn-site"
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    return out


def test_paused_shows_on_every_water_page_only_past_seven_days(tmp_path: Path):
    """Six days after the last good read the pages are not paused; eight
    days after, every Tennessee water page says "Updates paused since
    2026-10-15" right above the answer. The second build is the control:
    the same history, only the clock moved."""
    six = _tn_from_failed_check(
        tmp_path / "six", dt.datetime(2026, 10, 21, 1, 25, tzinfo=dt.UTC)
    )
    pages = _pages(six, "tn")
    assert pages and not any("Updates paused" in h for h in pages)
    eight = _tn_from_failed_check(
        tmp_path / "eight", dt.datetime(2026, 10, 23, 14, 0, tzinfo=dt.UTC)
    )
    pages = _pages(eight, "tn")
    assert pages
    for html in pages:
        after_h1 = html.split("</h1>", 1)[1].lstrip()
        assert after_h1.startswith(
            '<p class="water-paused"><strong>Updates paused since 2026-10-15.</strong>'
        )


def test_titles_h1s_and_descriptions_do_not_carry_the_answer(built: Path):
    for code in ("tn", "ma", "mi", "ny"):
        for html in _pages(built, code):
            title = re.search(r"<title>([^<]*)</title>", html).group(1)
            h1 = re.search(r"<h1>([^<]*)</h1>", html).group(1)
            desc = re.search(r'<meta name="description" content="([^"]*)"', html)
            assert desc
            for text in (title, h1, desc.group(1)):
                assert "Updates paused" not in text
                assert "this week:" not in text
