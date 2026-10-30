"""Winter on the record (DECISIONS 0040): the county pages' "Winter plants"
section and the home page's statewide winter block.

Every number comes from the weeks CDFW listed in the snapshot; removed
entries do not count. A winter is shown only when the record covers it from
its November 1, so a county with no listed water is a fact about the record,
never a gap read as absence. Pages are read with html.parser."""

from __future__ import annotations

import copy
import datetime as dt
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
BANNED = {"only", "first", "best", "top", "typically", "usually", "expect", "likely"}

WINTER_A = ["2025-11-02", "2025-12-07", "2026-01-11", "2026-02-22"]
WINTER_B = ["2025-12-07"]
OUTSIDE = ["2025-10-26", "2026-03-01", "2026-04-05"]


def _plants(weeks: list[str], status: str) -> list[dict[str, Any]]:
    return [
        {
            "week": {
                "start": d,
                "end": (dt.date.fromisoformat(d) + dt.timedelta(days=6)).isoformat(),
                "label": f"week of {d}",
            },
            "species": "Trout",
            "status": status,
        }
        for d in weeks
    ]


def _w(
    wid: str, weeks: list[str], removed: list[str] | None = None, county: str = "Inyo"
) -> dict[str, Any]:
    return {
        "id": wid,
        "slug": wid,
        "name": wid.title(),
        "counties": [county],
        "plants": _plants(weeks, "listed") + _plants(removed or [], "removed"),
    }


# ---- which winter


def test_the_latest_complete_winter_ends_before_the_current_week() -> None:
    w = site.latest_complete_winter("2026-10-25", "2025-09-14")
    assert w is not None
    assert (w["start"], w["end"]) == ("2025-11-01", "2026-03-01")
    assert w["label"] == "November 2025 through February 2026"
    # 2026-03-01 is a Sunday, so the rollover that shows this winter is that week.
    assert w["shown_from"] == "2026-03-01"
    # In February the winter in progress is not complete: the one before it is shown.
    feb = site.latest_complete_winter("2027-02-21", "2024-09-01")
    assert feb is not None and feb["start"] == "2025-11-01"
    mar = site.latest_complete_winter("2027-03-07", "2024-09-01")
    assert mar is not None and mar["start"] == "2026-11-01"
    assert mar["shown_from"] == "2027-03-07"  # 2027-03-01 is a Monday


def test_a_winter_the_record_does_not_cover_is_not_shown() -> None:
    assert site.latest_complete_winter("2026-10-25", "2025-11-01") is not None
    assert site.latest_complete_winter("2026-10-25", "2025-11-02") is None
    assert site.latest_complete_winter("2026-10-25", "") is None
    assert site.latest_complete_winter("", "2025-09-14") is None


# ---- county and home views


SEASON = site.latest_complete_winter("2026-10-25", "2025-09-14")


def test_county_winter_counts_listed_weeks_in_the_winter_alone() -> None:
    members = [
        _w("alpha", WINTER_A + OUTSIDE),
        _w("bravo", WINTER_B, removed=["2026-01-11", "2026-02-01"]),
        _w("charlie", OUTSIDE),
    ]
    view = site._county_winter(members, SEASON)
    assert view is not None
    assert view["rows"] == [
        {"slug": "alpha", "name": "Alpha", "weeks": 4},
        {"slug": "bravo", "name": "Bravo", "weeks": 1},
    ]
    assert view["week_count"] == 4  # 2025-12-07 is shared
    # Control: counting removed entries as listed must change bravo's count,
    # or the assertion above proves nothing.
    sabotaged = [_w("bravo", [*WINTER_B, "2026-01-11", "2026-02-01"])]
    got = site._county_winter(sabotaged, SEASON)
    assert got is not None and got["rows"][0]["weeks"] == 3


def test_county_winter_is_empty_not_zero_and_none_without_a_season() -> None:
    view = site._county_winter([_w("charlie", OUTSIDE)], SEASON)
    assert view is not None and view["rows"] == []
    assert site._county_winter([_w("alpha", WINTER_A)], None) is None


def test_home_winter_counts_waters_and_orders_counties() -> None:
    waters = [
        _w("alpha", WINTER_A, county="Inyo"),
        _w("bravo", WINTER_B, county="Inyo"),
        _w("delta", WINTER_B, county="Fresno"),
        _w("echo", OUTSIDE, county="Alpine"),
    ]
    links = {
        c: {"name": c, "slug": site.county_slug(c)}
        for c in ("Inyo", "Fresno", "Alpine")
    }
    view = site._home_winter(waters, SEASON, links)
    assert view is not None
    assert (view["water_count"], view["county_count"]) == (3, 2)
    assert [(c["name"], c["count"]) for c in view["counties"]] == [
        ("Inyo", 2),
        ("Fresno", 1),
    ]
    assert site._home_winter([waters[3]], SEASON, links) is None
    assert site._home_winter(waters, None, links) is None


# ---- built pages


class _Section(HTMLParser):
    """Text and table cells inside the <section> with one class."""

    def __init__(self, cls: str) -> None:
        super().__init__()
        self.cls = cls
        self.depth = 0
        self.found = False
        self.text: list[str] = []
        self.cells: list[str] = []
        self.hrefs: list[str] = []
        self._cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "section":
            if self.depth:
                self.depth += 1
            elif a.get("class") == self.cls:
                self.depth, self.found = 1, True
        elif self.depth and tag == "td":
            self._cell = True
            self.cells.append("")
        elif self.depth and tag == "a":
            self.hrefs.append(a.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self.depth:
            self.depth -= 1
        elif tag == "td":
            self._cell = False

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.text.append(data)
            if self._cell:
                self.cells[-1] += data


def _section(path: Path, cls: str) -> _Section:
    p = _Section(cls)
    p.feed(path.read_text(encoding="utf-8"))
    return p


def _text(s: _Section) -> str:
    return " ".join(" ".join(s.text).split())


@pytest.fixture(scope="module")
def v1(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("winter-src")
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp / "history.json",
        aliases_path=tmp / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=tmp / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return json.loads((tmp / "site" / "snapshot" / "v1.json").read_text("utf-8"))


def _like(
    template: dict[str, Any], weeks: list[str], status: str
) -> list[dict[str, Any]]:
    out = []
    for p in _plants(weeks, status):
        full = copy.deepcopy(template)
        full.update(p)
        out.append(full)
    return out


def _pinned(v1: dict[str, Any], *, with_earlier_record: bool) -> dict[str, Any]:
    """The fixture snapshot with water 0 given four winter weeks and water 1
    one. With ``with_earlier_record`` the record starts 2025-09-14 (it covers
    the winter); without, water 0's earliest week is the winter's second, so
    the record does not cover it from November 1."""
    snap = copy.deepcopy(v1)
    ws = snap["waters"]
    t = ws[0]["plants"][0]
    weeks = ["2025-09-14", *WINTER_A] if with_earlier_record else WINTER_A[1:]
    ws[0]["plants"] = _like(t, weeks, "listed") + ws[0]["plants"]
    ws[1]["plants"] = (
        _like(t, WINTER_B if with_earlier_record else [], "listed") + ws[1]["plants"]
    )
    return snap


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory, v1: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    snap = _pinned(v1, with_earlier_record=True)
    out = tmp_path_factory.mktemp("winter-site") / "site"
    site.build_site(snap, out, base_url=BASE)
    return out, snap


def _county_path(out: Path, county: str) -> Path:
    return out / "county" / site.county_slug(county) / "index.html"


def test_county_pages_list_last_winter_from_the_snapshot(
    built: tuple[Path, dict[str, Any]],
) -> None:
    out, snap = built
    season = site.latest_complete_winter(snap["source_week"]["start"], "2025-09-14")
    assert season is not None
    counties = sorted({c for w in snap["waters"] for c in w["counties"]})
    with_rows = 0
    for county in counties:
        members = [w for w in snap["waters"] if county in w["counties"]]
        expected = site._county_winter(members, season)
        assert expected is not None
        s = _section(_county_path(out, county), "county-winter")
        assert s.found, county
        text = _text(s)
        assert "November 2025 through February 2026" in text
        if expected["rows"]:
            with_rows += 1
            got = [(s.cells[i], int(s.cells[i + 1])) for i in range(0, len(s.cells), 2)]
            assert got == [(r["name"], r["weeks"]) for r in expected["rows"]], county
            assert "not a forecast" in text
            assert "0" not in s.cells[1::2]
        else:
            assert f"No {county} County water was on CDFW's schedule" in text
            assert "not that there are no fish" in text
        words = {w.strip(".,;:()'\"").lower() for w in text.split()}
        assert not words & BANNED, (county, words & BANNED)
    assert with_rows >= 1


def test_the_home_page_names_last_winters_counties(
    built: tuple[Path, dict[str, Any]],
) -> None:
    out, snap = built
    s = _section(out / "index.html", "home-winter")
    assert s.found
    text = _text(s)
    assert "November 2025 through February 2026" in text
    assert "not a forecast" in text
    w0, w1 = snap["waters"][0], snap["waters"][1]
    n = len({w0["id"], w1["id"]})
    assert f"listed {n} California waters" in text
    for c in set(w0["counties"]) | set(w1["counties"]):
        assert f"county/{site.county_slug(c)}/#winter" in " ".join(s.hrefs)


def test_no_winter_block_when_the_record_does_not_cover_it(
    tmp_path: Path, v1: dict[str, Any]
) -> None:
    """The record made to begin after November 1, 2025 (every earlier week
    dropped): no winter block anywhere, rather than a winter read as empty."""
    snap = _pinned(v1, with_earlier_record=False)
    for w in snap["waters"]:
        kept = [p for p in w["plants"] if p["week"]["start"] > "2025-11-01"]
        # A water left with no plant keeps one week inside the record.
        w["plants"] = kept or _like(w["plants"][0], ["2025-11-09"], "listed")
    starts = [p["week"]["start"] for w in snap["waters"] for p in w["plants"]]
    assert starts and min(starts) > "2025-11-01"
    out = tmp_path / "site"
    site.build_site(snap, out, base_url=BASE)
    assert not _section(out / "index.html", "home-winter").found
    pages = list(out.glob("county/*/index.html"))
    assert pages
    for page in pages:
        assert not _section(page, "county-winter").found, page
    # Control: the covered build of the same fixture does show the blocks.
    covered = tmp_path / "covered"
    site.build_site(_pinned(v1, with_earlier_record=True), covered, base_url=BASE)
    assert _section(covered / "index.html", "home-winter").found
