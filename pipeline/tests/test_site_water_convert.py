"""The first phone screen of a California water page answers the visit
(DECISIONS 0054): a one-line schedule answer and the calendar subscribe
action sit inside the status block, and each same-county water's link says
where that water stands, with the waters on this week's schedule first.

Measured before the change (GA4, 28 days to 2026-11-05): 164 sessions
landed on /water/ pages, 60 engaged, and most engaged landings viewed one
page; the subscribe link sat below the lede and the county lists."""

from __future__ import annotations

import copy
import datetime as dt
import html as htmllib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
WEEK = "2026-09-13"
CHECKED_LABEL = "2026-09-13 12:00 UTC"
STATUS_RE = re.compile(r'<section class="water-status".*?</section>', re.S)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("water-convert")
    out = tmp / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp / "history.json",
        aliases_path=tmp / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    return out, snap


def _page(out: Path, slug: str) -> str:
    return (out / "water" / slug / "index.html").read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    plain = htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", plain).strip()


def _answer(html: str) -> str:
    m = re.search(r'<p class="water-answer">(.*?)</p>', html, re.S)
    assert m, "no answer line"
    return _text(m.group(1))


def _listed(w: dict[str, Any]) -> list[str]:
    return sorted({p["week"]["start"] for p in w["plants"] if p["status"] == "listed"})


def _with_weeks(snap: dict[str, Any], weeks: list[str]) -> dict[str, Any]:
    """A copy of the snapshot whose first water has exactly these weeks."""
    mod = copy.deepcopy(snap)
    w = mod["waters"][0]
    template = copy.deepcopy(w["plants"][0])
    plants = []
    for start in weeks:
        p = copy.deepcopy(template)
        end = dt.date.fromisoformat(start) + dt.timedelta(days=6)
        p["week"] = {
            "start": start,
            "end": end.isoformat(),
            "label": f"week of {start}",
        }
        p["status"] = "listed"
        plants.append(p)
    w["plants"] = plants
    past = [x for x in weeks if x <= WEEK]
    w["last_listed_week"] = (
        {"start": max(past), "label": f"week of {max(past)}"} if past else None
    )
    return mod


def _render(snap: dict[str, Any], tmp_path: Path) -> Path:
    out = tmp_path / "site"
    site.build_site(snap, out, base_url=BASE_URL)
    return out


def _answer_problems(out: Path) -> list[str]:
    found = []
    for page in sorted((out / "water").glob("*/index.html")):
        html = page.read_text(encoding="utf-8")
        block = STATUS_RE.search(html)
        if not block or 'class="water-answer"' not in block.group(0):
            found.append(f"{page.parent.name}: no answer in the status block")
            continue
        text = _answer(block.group(0))
        if not text.endswith("."):
            found.append(f"{page.parent.name}: answer is not a sentence")
        if re.search(r"\b0\b|\bnone\b|\bn/a\b|\bunknown\b", text, re.I):
            found.append(f"{page.parent.name}: absence shown as a value: {text!r}")
        if "calendar_subscribe_click" not in block.group(0):
            found.append(f"{page.parent.name}: subscribe action not in the block")
    return found


def test_every_water_page_answers_and_offers_subscribe_in_the_status_block(
    built,
) -> None:
    out, _ = built
    assert _answer_problems(out) == []


def test_negative_control_a_zero_answer_is_caught(built, tmp_path: Path) -> None:
    out, _ = built
    page = next(iter(sorted((out / "water").glob("*/index.html"))))
    html = page.read_text(encoding="utf-8")
    sabotaged = re.sub(
        r'(<p class="water-answer">).*?(</p>)',
        r"\g<1>0\g<2>",
        html,
        count=1,
        flags=re.S,
    )
    assert sabotaged != html  # the sabotage applied
    copy_dir = tmp_path / "water" / page.parent.name
    copy_dir.mkdir(parents=True)
    (copy_dir / "index.html").write_text(sabotaged, encoding="utf-8")
    assert _answer_problems(tmp_path)


def test_subscribe_comes_before_the_lede_and_the_history(built) -> None:
    out, snap = built
    for w in snap["waters"][:20]:
        html = _page(out, w["slug"])
        sub = html.index('data-ga-type="webcal"')
        assert sub < html.index('<p class="lede">'), w["slug"]
        assert sub < html.index("<h2>Planting history</h2>"), w["slug"]
        assert html.count('data-ga-event="calendar_subscribe_click"') == 3


def test_past_water_says_nothing_current_and_its_last_week(built) -> None:
    out, snap = built
    w = next(w for w in snap["waters"] if _listed(w) and max(_listed(w)) < WEEK)
    last = max(_listed(w))
    days = (dt.date.fromisoformat(WEEK) - dt.date.fromisoformat(last)).days
    unit = "day" if days == 1 else "days"
    assert _answer(_page(out, w["slug"])) == (
        f"Not on CDFW's schedule for this week or later yet, as of {CHECKED_LABEL}. "
        f"It was last on the schedule the week of {last}, {days} {unit} before "
        "that check."
    )


def test_this_week_and_a_later_week(built, tmp_path: Path) -> None:
    _, snap = built
    mod = _with_weeks(snap, ["2026-08-30", WEEK, "2026-09-27"])
    out = _render(mod, tmp_path)
    assert _answer(_page(out, mod["waters"][0]["slug"])) == (
        f"On CDFW's schedule this week, the week of {WEEK}, and again the week "
        "of 2026-09-27."
    )


def test_upcoming_with_and_without_a_past_week(built, tmp_path: Path) -> None:
    _, snap = built
    mod = _with_weeks(snap, ["2026-08-30", "2026-09-20"])
    out = _render(mod, tmp_path / "a")
    assert _answer(_page(out, mod["waters"][0]["slug"])) == (
        "Next on CDFW's schedule: the week of 2026-09-20. Before that, it was "
        "last on the schedule the week of 2026-08-30."
    )
    mod = _with_weeks(snap, ["2026-09-20"])
    out = _render(mod, tmp_path / "b")
    assert _answer(_page(out, mod["waters"][0]["slug"])) == (
        "Next on CDFW's schedule: the week of 2026-09-20."
    )


def _county_items(html: str, slug: str) -> list[str]:
    sec = html.split(f'<section aria-labelledby="others-{slug}">', 1)[1]
    sec = sec.split("</section>", 1)[0]
    return [_text(li) for li in re.findall(r"<li>(.*?)</li>", sec, re.S)]


def _order_problems(out: Path, snap: dict[str, Any]) -> tuple[int, list[str]]:
    """(lists checked, problems): every same-county list must run scheduled
    this week, then next scheduled, then last scheduled newest first."""
    checked, found = 0, []
    for w in snap["waters"]:
        html = _page(out, w["slug"])
        for c in w["counties"]:
            items = _county_items(html, site.county_slug(c))
            groups = []
            for item in items:
                if item.endswith(", scheduled this week"):
                    groups.append(0)
                elif ", next scheduled the week of " in item:
                    groups.append(1)
                elif ", last scheduled the week of " in item:
                    groups.append(2)
                else:
                    groups.append(3)
            past = [
                i.rsplit("last scheduled the week of ", 1)[1]
                for i, g in zip(items, groups, strict=True)
                if g == 2
            ]
            if groups != sorted(groups) or past != sorted(past, reverse=True):
                found.append(f"{w['slug']} / {c}: {items}")
            checked += 1
    return checked, found


def _mixed_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """A copy where every water of the busiest county has a different
    pattern: some this week, some next, some past weeks of different ages,
    so name order and schedule order disagree."""
    mod = copy.deepcopy(snap)
    by_county: dict[str, list[dict[str, Any]]] = {}
    for w in mod["waters"]:
        for c in w["counties"]:
            by_county.setdefault(c, []).append(w)
    county = max(by_county, key=lambda c: len(by_county[c]))
    members = sorted(by_county[county], key=lambda w: w["name"])
    assert len(members) >= 4
    patterns = [["2026-08-16"], ["2026-08-30"], ["2026-09-20"], [WEEK]]
    for n, w in enumerate(members):
        weeks = patterns[n % len(patterns)]
        template = copy.deepcopy(w["plants"][0])
        plants = []
        for start in weeks:
            p = copy.deepcopy(template)
            end = dt.date.fromisoformat(start) + dt.timedelta(days=6)
            p["week"] = {
                "start": start,
                "end": end.isoformat(),
                "label": f"week of {start}",
            }
            p["status"] = "listed"
            plants.append(p)
        w["plants"] = plants
        past = [x for x in weeks if x <= WEEK]
        w["last_listed_week"] = (
            {"start": max(past), "label": f"week of {max(past)}"} if past else None
        )
    return mod


def test_county_links_say_where_each_water_stands_current_first(
    built, tmp_path: Path
) -> None:
    out, snap = built
    checked, found = _order_problems(out, snap)
    assert checked and found == []
    mod = _mixed_snapshot(snap)
    out = _render(mod, tmp_path)
    checked, found = _order_problems(out, mod)
    assert checked and found == []
    texts = " ".join(
        f.read_text(encoding="utf-8") for f in (out / "water").glob("*/index.html")
    )
    for phrase in (
        ", scheduled this week",
        ", next scheduled the week of ",
        ", last scheduled the week of ",
    ):
        assert phrase in texts, phrase


def test_negative_control_name_order_is_caught(
    built, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the old name order the check above fails, so it can fail."""
    _, snap = built
    monkeypatch.setattr(
        site, "_sibling_order", lambda ctx, s: (0, 0, s["name"], s["slug"])
    )
    mod = _mixed_snapshot(snap)
    out = _render(mod, tmp_path)
    _, found = _order_problems(out, mod)
    assert found
