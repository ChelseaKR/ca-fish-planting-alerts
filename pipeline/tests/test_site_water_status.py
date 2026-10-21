"""The status block at the top of every water page: when the water was last
on CDFW's schedule, whether it is on this week's or next week's, and how many
weeks it appeared in the recorded history. Every date is a recorded week;
nothing is estimated (_water_status in site.py)."""

from __future__ import annotations

import copy
import datetime as dt
import html as htmllib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
CHECKED_ON = "2026-09-13"
WEEK = "2026-09-13"
NEXT_WEEK = "2026-09-20"

# Owner copy rules: "scheduled" and "on the schedule", never "stocked" or
# "planted on"; no "only" or "first"; American English; no endorsement claim.
FORBIDDEN = re.compile(
    r"\b(stocked|stocking|planted on|only|first|endorse\w*|approved|official\w*"
    r"|colour|centre|organis\w+|favour\w*|neighbour\w*|programme)\b",
    re.I,
)
STATUS_RE = re.compile(r'<section class="water-status".*?</section>', re.S)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    tmp = tmp_path_factory.mktemp("water-status")
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


def _block(html: str) -> str:
    m = STATUS_RE.search(html)
    assert m, "no water-status block"
    return m.group(0)


def _text(fragment: str) -> str:
    plain = htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", plain).strip()


def _listed(w: dict[str, Any]) -> list[str]:
    return sorted({p["week"]["start"] for p in w["plants"] if p["status"] == "listed"})


def _first_water(snap: dict[str, Any], pred: Any) -> dict[str, Any]:
    for w in snap["waters"]:
        if pred(_listed(w)):
            return w
    raise AssertionError("the fixture has no water of this kind")


def _with_weeks(
    snap: dict[str, Any], weeks: list[str], status: str = "listed"
) -> dict[str, Any]:
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
        p["status"] = status
        plants.append(p)
    w["plants"] = plants
    past = [x for x in weeks if x <= WEEK and status == "listed"]
    w["last_listed_week"] = (
        {"start": max(past), "label": f"week of {max(past)}"} if past else None
    )
    return mod


def _render(snap: dict[str, Any], tmp_path: Path) -> Path:
    out = tmp_path / "site"
    site.build_site(snap, out, base_url=BASE_URL)
    return out


def _problems(out: Path) -> list[str]:
    """Everything wrong with the block on every water page of a build."""
    found: list[str] = []
    for page in sorted((out / "water").glob("*/index.html")):
        html = page.read_text(encoding="utf-8")
        m = STATUS_RE.search(html)
        if not m:
            found.append(f"{page.parent.name}: no status block")
            continue
        found += _block_problems(page.parent.name, html, m.group(0))
    return found


def _block_problems(name: str, html: str, block: str) -> list[str]:
    found: list[str] = []
    text = _text(block)
    if bad := FORBIDDEN.search(text):
        found.append(f"{name}: forbidden word {bad.group(0)!r}")
    if "<script" in block.lower() or " title=" in block:
        found.append(f"{name}: script or tooltip-only content")
    if 'aria-labelledby="water-status-heading"' not in block or (
        'id="water-status-heading"' not in block
    ):
        found.append(f"{name}: heading is not wired to the section")
    if html.index("<h1>") > html.index("water-status"):
        found.append(f"{name}: block is above the h1")
    if html.count('id="water-status-heading"') != 1:
        found.append(f"{name}: duplicate heading id")
    if len(re.findall(r"<dt>", block)) != len(re.findall(r"<dd>", block)):
        found.append(f"{name}: dt/dd mismatch")
    for d in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text):
        dt.date.fromisoformat(d)
    if not re.search(
        r"Last on the schedule (The week of \d{4}-\d{2}-\d{2}|This week|"
        r"Not before this week|Not on CDFW's schedule)",
        text,
    ):
        found.append(f"{name}: no last-on-schedule answer")
    return found


def test_every_water_page_has_the_block_and_is_clean(built) -> None:
    out, snap = built
    assert len(list((out / "water").glob("*/index.html"))) == len(snap["waters"])
    assert _problems(out) == []


def test_block_is_plain_html_in_the_water_template_by_one_include() -> None:
    tpl = (Path(site.__file__).parent / "templates" / "water.html.jinja").read_text(
        encoding="utf-8"
    )
    assert tpl.count('{% include "_water_status.html.jinja" %}') == 1


def test_water_with_history_gets_its_real_last_week_and_days_ago(built) -> None:
    out, snap = built
    w = _first_water(snap, lambda ls: any(d < WEEK for d in ls) and WEEK not in ls)
    last = max(d for d in _listed(w) if d <= WEEK)
    days = (dt.date.fromisoformat(CHECKED_ON) - dt.date.fromisoformat(last)).days
    text = _text(_block(_page(out, w["slug"])))
    unit = "day" if days == 1 else "days"
    assert (
        f"Last on the schedule The week of {last}, which began {days} {unit} ago "
        f"as of the schedule check on {CHECKED_ON}."
    ) in text
    assert f"This week, the week of {WEEK} Not on CDFW's schedule." in text


def test_water_on_this_weeks_schedule_says_so(built, tmp_path: Path) -> None:
    _, snap = built
    mod = _with_weeks(snap, ["2026-08-30", WEEK])
    out = _render(mod, tmp_path)
    text = _text(_block(_page(out, mod["waters"][0]["slug"])))
    assert f"Last on the schedule This week, the week of {WEEK}." in text
    assert f"This week, the week of {WEEK} On CDFW's schedule." in text
    assert f"Next week, the week of {NEXT_WEEK} Not on CDFW's schedule." in text
    assert "On the schedule in 2 weeks" in text


def test_water_on_next_weeks_schedule_says_so(built, tmp_path: Path) -> None:
    _, snap = built
    mod = _with_weeks(snap, ["2026-09-06", NEXT_WEEK])
    out = _render(mod, tmp_path)
    text = _text(_block(_page(out, mod["waters"][0]["slug"])))
    assert "Last on the schedule The week of 2026-09-06, which began 7 days ago" in text
    assert f"This week, the week of {WEEK} Not on CDFW's schedule." in text
    assert f"Next week, the week of {NEXT_WEEK} On CDFW's schedule." in text


def test_weeks_on_schedule_matches_the_record_for_every_water(built) -> None:
    out, snap = built
    since = min(p["week"]["start"] for w in snap["waters"] for p in w["plants"])
    for w in snap["waters"]:
        text = _text(_block(_page(out, w["slug"])))
        n = len(_listed(w))
        word = "week" if n == 1 else "weeks"
        assert (
            f"On the schedule in {n} {word}, counting the weeks we have "
            f"recorded since the week of {since}."
        ) in text, w["slug"]


def test_water_with_no_history_says_exactly_what_is_known(
    built, tmp_path: Path
) -> None:
    _, snap = built
    since = min(p["week"]["start"] for w in snap["waters"] for p in w["plants"])
    mod = _with_weeks(snap, ["2026-09-06"], status="removed")
    out = _render(mod, tmp_path)
    text = _text(_block(_page(out, mod["waters"][0]["slug"])))
    assert (
        "Last on the schedule Not on CDFW's schedule in the weeks we have "
        f"recorded since the week of {since}."
    ) in text
    assert f"This week, the week of {WEEK} Not on CDFW's schedule." in text
    assert "On the schedule in 0 weeks" in text
    assert "ago" not in text  # no date, so no "days ago" is invented


def test_water_listed_only_after_this_week_is_not_called_absent(
    built, tmp_path: Path
) -> None:
    _, snap = built
    mod = _with_weeks(snap, [NEXT_WEEK])
    out = _render(mod, tmp_path)
    text = _text(_block(_page(out, mod["waters"][0]["slug"])))
    assert "Last on the schedule Not before this week" in text
    assert f"Next week, the week of {NEXT_WEEK} On CDFW's schedule." in text
    assert "ago" not in text


def test_a_week_beyond_next_week_is_shown_as_later_not_as_next(
    built, tmp_path: Path
) -> None:
    _, snap = built
    mod = _with_weeks(snap, ["2026-10-04"])
    out = _render(mod, tmp_path)
    text = _text(_block(_page(out, mod["waters"][0]["slug"])))
    assert f"Next week, the week of {NEXT_WEEK} Not on CDFW's schedule." in text
    assert "Later on the schedule The week of 2026-10-04." in text


def test_days_ago_counts_from_the_schedule_check_not_the_build_clock(
    built, tmp_path: Path
) -> None:
    out, snap = built
    w = _first_water(snap, lambda ls: any(d < WEEK for d in ls) and WEEK not in ls)
    later_check = copy.deepcopy(snap)
    later_check["source"]["fetched_at"] = "2026-09-16T12:00:00Z"
    html_a = _page(out, w["slug"])
    html_b = _page(_render(later_check, tmp_path), w["slug"])
    last = max(d for d in _listed(w) if d <= WEEK)
    base = (dt.date(2026, 9, 13) - dt.date.fromisoformat(last)).days
    assert f"began {base} " in _text(_block(html_a))
    assert f"began {base + 3} " in _text(_block(html_b))


def test_meta_phrase_is_exposed_truthful_and_unused_by_the_description(
    built,
) -> None:
    out, snap = built
    w = _first_water(snap, lambda ls: any(d < WEEK for d in ls) and WEEK not in ls)
    last = max(d for d in _listed(w) if d <= WEEK)
    since = min(p["week"]["start"] for x in snap["waters"] for p in x["plants"])
    status = site._water_status(
        w, source_week_start=WEEK, checked_on=CHECKED_ON, recorded_since=since
    )
    days = (dt.date.fromisoformat(CHECKED_ON) - dt.date.fromisoformat(last)).days
    n_weeks = len(_listed(w))
    assert status["meta_phrase"] == (
        f"Last on CDFW's schedule the week of {last} "
        f"({days} {'day' if days == 1 else 'days'} ago); on the schedule "
        f"{n_weeks} {'week' if n_weeks == 1 else 'weeks'} since the week of {since}."
    )
    assert not FORBIDDEN.search(status["meta_phrase"])
    assert len(status["meta_phrase"]) <= 160
    empty = site._water_status(
        {"plants": []},
        source_week_start=WEEK,
        checked_on=CHECKED_ON,
        recorded_since=since,
    )
    assert empty["meta_phrase"] == (
        f"Not on CDFW's schedule in the weeks we have recorded since the week of {since}."
    )
    assert empty["last_week"] == "" and empty["days_ago"] is None
    # This change leaves the meta description to whoever owns it: the page's
    # description does not carry the phrase.
    desc = re.search(
        r'<meta name="description" content="([^"]+)">', _page(out, w["slug"])
    )
    assert desc and status["meta_phrase"] not in desc.group(1)


class _Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.tags.append(tag)


def test_block_markup_is_a_labelled_section_with_a_description_list(built) -> None:
    out, snap = built
    s = _Structure()
    s.feed(_block(_page(out, snap["waters"][0]["slug"])))
    assert s.tags[:2] == ["section", "h2"]
    assert "dl" in s.tags and "script" not in s.tags and "img" not in s.tags


# ---- negative controls: each first asserts its sabotage changed the file


def _sabotage(path: Path, old: str, new: str) -> None:
    before = path.read_text(encoding="utf-8")
    assert old in before, "the sabotage target is not in the page"
    after = before.replace(old, new)
    assert after != before
    path.write_text(after, encoding="utf-8")


@pytest.fixture()
def fresh_out(built, tmp_path: Path) -> tuple[Path, str]:
    out, snap = built
    copy_out = tmp_path / "copy"
    import shutil

    shutil.copytree(out, copy_out)
    assert _problems(copy_out) == []
    return copy_out, snap["waters"][0]["slug"]


def test_control_a_missing_block_is_noticed(fresh_out) -> None:
    out, slug = fresh_out
    page = out / "water" / slug / "index.html"
    html = page.read_text(encoding="utf-8")
    _sabotage(page, 'class="water-status"', 'class="elsewhere"')
    assert page.read_text(encoding="utf-8") != html
    assert any("no status block" in p for p in _problems(out))


def test_control_a_forbidden_word_is_noticed(fresh_out) -> None:
    out, slug = fresh_out
    _sabotage(
        out / "water" / slug / "index.html",
        "Last on the schedule",
        "Last stocked on the schedule",
    )
    assert any("forbidden word" in p for p in _problems(out))


def test_control_an_unwired_heading_is_noticed(fresh_out) -> None:
    out, slug = fresh_out
    _sabotage(
        out / "water" / slug / "index.html",
        'aria-labelledby="water-status-heading"',
        'aria-labelledby="nothing"',
    )
    assert any("not wired" in p for p in _problems(out))


def test_control_tooltip_only_content_is_noticed(fresh_out) -> None:
    out, slug = fresh_out
    _sabotage(
        out / "water" / slug / "index.html",
        "<dl>",
        '<dl title="hidden detail">',
    )
    assert any("tooltip" in p for p in _problems(out))


def test_control_a_wrong_date_fails_the_dates_test(built, tmp_path: Path) -> None:
    out, snap = built
    w = _first_water(snap, lambda ls: any(d < WEEK for d in ls) and WEEK not in ls)
    last = max(d for d in _listed(w) if d <= WEEK)
    page = tmp_path / "p.html"
    page.write_text(_page(out, w["slug"]), encoding="utf-8")
    _sabotage(page, f"The week of {last}, which", "The week of 2020-01-05, which")
    assert f"The week of {last}, which began" not in _text(
        _block(page.read_text(encoding="utf-8"))
    )
