"""The California water pages' holiday line to /gifts/ (DECISIONS 0072).

From 2026-11-27 through 2026-12-26, by build date, each California water page
that carries the gear block ends that block with one internal link to the
gift guide, in the words Chelsea approved on 2026-11-15. No other page has it:
not the home page (which has its own line, 0047), county pages, /county/,
/gear/, or another state's water page. Outside the window, and in any build
without /gifts/, no page has it. These tests render the real site, with
Tennessee, Massachusetts and Michigan on, and read it as text. The negative
controls assert that each sabotage changed the file before they assert the
checker noticed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site, thin

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

LINE_ID = 'id="gift-guide-water-link"'
# The approved line, exactly as a California water page renders it.
LINE = (
    '<p id="gift-guide-water-link">Shopping for someone who fishes? '
    '<a href="../../gifts/">Gift ideas for a trout angler</a>, a short list of '
    "practical items. That page&rsquo;s links are affiliate links to Amazon.</p>"
)
FIRST_DAY = dt.date(2026, 11, 27)
LAST_DAY = dt.date(2026, 12, 26)
GEAR_SECTION = re.compile(r'<section class="gear".*?</section>', re.S)


@pytest.fixture(scope="module")
def snapshots(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any]:
    """The v1 and v2 snapshots of a fixture run with three other states on."""
    root = tmp_path_factory.mktemp("water-gift-snap")
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=FIXTURES / "states",
    )
    v1 = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    v2 = json.loads((out / "snapshot" / "v2.json").read_text(encoding="utf-8"))
    return v1, v2


def _build(
    root: Path,
    snaps: tuple[Any, Any],
    day: dt.date,
    gift_guide: bool | None = None,
) -> Path:
    out = root / "site"
    v1, v2 = snaps
    site.build_site(
        v1,
        out,
        base_url=BASE_URL,
        snapshot_v2=v2,
        build_date=day,
        gift_guide=gift_guide,
    )
    return out


@pytest.fixture(scope="module")
def first_day(
    tmp_path_factory: pytest.TempPathFactory, snapshots: tuple[Any, Any]
) -> Path:
    return _build(tmp_path_factory.mktemp("gift-line-first"), snapshots, FIRST_DAY)


def _california_water_pages_with_gear(out: Path, v1: dict[str, Any]) -> set[Path]:
    """Every California water page that carries the gear block: all but the
    thin ones (DECISIONS 0041), read from the snapshot the build used."""
    pages = set()
    for w in v1["waters"]:
        path = f"/water/{w['slug']}/"
        if not thin.is_thin(w["plants"], path):
            pages.add(out / "water" / w["slug"] / "index.html")
    return pages


def _line_problems(out: Path, v1: dict[str, Any], *, expect_on: bool) -> list[str]:
    """Every way the build breaks the rule: on, the exact line once inside
    the gear block of every California water page that has one, and the
    /gifts/ page it names exists; off, no page has it. In both, no page that
    is not a California water page has it."""
    want = _california_water_pages_with_gear(out, v1) if expect_on else set()
    found: list[str] = []
    if expect_on and not want:
        found.append("no California water page carries the gear block")
    if expect_on and not (out / "gifts" / "index.html").exists():
        found.append("the line is on but /gifts/ was not built")
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".xml", ".txt", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        has = LINE_ID in text or "Shopping for someone who fishes" in text
        rel = path.relative_to(out)
        if path not in want:
            if has:
                found.append(f"{rel} has the line")
            continue
        sections = GEAR_SECTION.findall(text)
        if text.count(LINE_ID) != 1 or len(sections) != 1:
            found.append(f"{rel} lacks the line or has it more than once")
        elif LINE not in sections[0]:
            found.append(f"{rel} does not have the exact line inside its gear block")
    return found


# ---- the window ----


def test_the_window_is_2026_11_27_through_2026_12_26_by_build_date() -> None:
    assert site.WATER_GIFT_LINK_FIRST_DAY == FIRST_DAY
    assert site.WATER_GIFT_LINK_LAST_DAY == LAST_DAY
    shown = site.water_gift_link_shown
    for day in (FIRST_DAY, dt.date(2026, 12, 1), LAST_DAY):
        assert shown(day, gift_guide=True), day
    for day in (
        dt.date(2026, 11, 26),
        dt.date(2026, 12, 27),
        dt.date(2026, 11, 15),
        dt.date(2027, 1, 1),
        dt.date(2027, 11, 27),  # a year is part of the date: not every year
        dt.date(2027, 12, 1),
    ):
        assert not shown(day, gift_guide=True), day
    # Never without /gifts/ in the same build.
    assert not shown(dt.date(2026, 12, 1), gift_guide=False)


def test_on_the_first_day_only_california_water_pages_have_the_line(
    first_day: Path, snapshots: tuple[Any, Any]
) -> None:
    assert _line_problems(first_day, snapshots[0], expect_on=True) == []
    # The build really has the pages that must not carry it.
    for must_exist in (
        first_day / "index.html",
        first_day / "county" / "index.html",
        first_day / "gear" / "index.html",
        first_day / "gifts" / "index.html",
    ):
        assert must_exist.exists(), must_exist
    assert list((first_day / "county").glob("*/index.html"))
    for code in ("tn", "ma", "mi"):
        state_waters = list((first_day / code / "water").glob("*/index.html"))
        assert state_waters, code
        assert any('class="gear"' in p.read_text("utf-8") for p in state_waters)


def test_the_last_day_has_the_line(tmp_path: Path, snapshots: tuple[Any, Any]) -> None:
    out = _build(tmp_path, snapshots, LAST_DAY)
    assert _line_problems(out, snapshots[0], expect_on=True) == []


@pytest.mark.parametrize(
    "day",
    [dt.date(2026, 11, 26), dt.date(2026, 12, 27), dt.date(2027, 11, 27)],
    ids=["day-before", "day-after", "next-year"],
)
def test_outside_the_window_no_page_has_the_line(
    tmp_path: Path, snapshots: tuple[Any, Any], day: dt.date
) -> None:
    out = _build(tmp_path, snapshots, day)
    assert _line_problems(out, snapshots[0], expect_on=False) == []
    # The water pages still carry their gear block: the line alone is gone.
    assert any(
        'class="gear"' in p.read_text("utf-8")
        for p in (out / "water").glob("*/index.html")
    )


def test_a_build_without_the_gift_guide_has_no_line(
    tmp_path: Path, snapshots: tuple[Any, Any]
) -> None:
    out = _build(tmp_path, snapshots, dt.date(2026, 12, 1), gift_guide=False)
    assert not (out / "gifts").exists()
    assert _line_problems(out, snapshots[0], expect_on=False) == []


def test_the_link_is_internal_and_its_page_exists(
    first_day: Path, snapshots: tuple[Any, Any]
) -> None:
    """Like the home page's line (0047): a plain link to our own page, no
    tag, no sponsored rel and no gear_click label, which belong to the
    Amazon links the gift page itself carries."""
    page = next(
        iter(sorted(_california_water_pages_with_gear(first_day, snapshots[0])))
    )
    html = page.read_text(encoding="utf-8")
    para = re.search(r'<p id="gift-guide-water-link">.*?</p>', html, re.S)
    assert para is not None
    anchors = re.findall(r"<a\b[^>]*>", para.group(0))
    assert anchors == ['<a href="../../gifts/">']
    assert (page.parent / "../../gifts/index.html").resolve().exists()
    assert "affiliate links to Amazon" in para.group(0)


def test_the_line_is_the_last_thing_in_the_gear_block(
    first_day: Path, snapshots: tuple[Any, Any]
) -> None:
    page = next(
        iter(sorted(_california_water_pages_with_gear(first_day, snapshots[0])))
    )
    section = GEAR_SECTION.search(page.read_text(encoding="utf-8"))
    assert section is not None
    assert re.search(re.escape(LINE) + r"\s*</section>$", section.group(0))


# ---- negative controls ----


def _sabotage(path: Path, old: str, new: str) -> None:
    before = path.read_text(encoding="utf-8")
    assert old in before, f"sabotage target missing: {old!r}"
    after = before.replace(old, new, 1)
    assert after != before
    path.write_text(after, encoding="utf-8")


@pytest.fixture
def sabotaged(tmp_path: Path, snapshots: tuple[Any, Any]) -> Path:
    out = _build(tmp_path, snapshots, FIRST_DAY)
    assert _line_problems(out, snapshots[0], expect_on=True) == []
    return out


def test_control_the_line_on_a_county_page_is_noticed(
    sabotaged: Path, snapshots: tuple[Any, Any]
) -> None:
    county = sorted((sabotaged / "county").glob("*/index.html"))[0]
    _sabotage(county, "</section>", LINE + "</section>")
    problems = _line_problems(sabotaged, snapshots[0], expect_on=True)
    assert any(p.startswith("county/") and "has the line" in p for p in problems)


def test_control_the_line_on_another_states_water_page_is_noticed(
    sabotaged: Path, snapshots: tuple[Any, Any]
) -> None:
    tn = next(
        p
        for p in sorted((sabotaged / "tn" / "water").glob("*/index.html"))
        if 'class="gear"' in p.read_text("utf-8")
    )
    _sabotage(tn, "</section>", LINE + "</section>")
    problems = _line_problems(sabotaged, snapshots[0], expect_on=True)
    assert any(p.startswith("tn/water/") for p in problems), problems


def test_control_a_missing_line_is_noticed(
    sabotaged: Path, snapshots: tuple[Any, Any]
) -> None:
    page = sorted(_california_water_pages_with_gear(sabotaged, snapshots[0]))[0]
    _sabotage(page, LINE, "")
    problems = _line_problems(sabotaged, snapshots[0], expect_on=True)
    assert any("lacks the line" in p for p in problems), problems


def test_control_changed_wording_is_noticed(
    sabotaged: Path, snapshots: tuple[Any, Any]
) -> None:
    page = sorted(_california_water_pages_with_gear(sabotaged, snapshots[0]))[0]
    _sabotage(page, "a short list of practical items", "the best gifts")
    problems = _line_problems(sabotaged, snapshots[0], expect_on=True)
    assert any("exact line" in p for p in problems), problems


def test_control_the_line_outside_the_window_is_noticed(
    first_day: Path, snapshots: tuple[Any, Any]
) -> None:
    # The first-day build, read as if it were dated outside the window.
    problems = _line_problems(first_day, snapshots[0], expect_on=False)
    assert problems
    assert all(p.startswith("water/") for p in problems), problems
    assert len(problems) == len(
        _california_water_pages_with_gear(first_day, snapshots[0])
    )
