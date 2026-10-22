"""By-month counts of listed weeks on water and county pages.

Every count comes from the weeks CDFW listed in the snapshot; removed entries
do not count. Pages are read with html.parser, never a pattern over markup,
and the snapshot is built from the pinned schedule fixture, not a daily data
file."""

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
BANNED = {
    "only",
    "first",
    "best",
    "top",
    "unique",
    "typically",
    "usually",
    "stocked",
    "planted",
    "colour",
    "centre",
}
# "forecast" itself appears in the disclaimer ("not a forecast"); a claim of
# prediction would use these.
PREDICTIVE = ("will be planted", "expect", "likely", "should see", "predict")

WATER_WEEKS = ["2025-09-14", "2025-09-21", "2026-04-05", "2026-04-12", "2026-04-19"]
REMOVED_WEEKS = ["2026-06-07", "2026-06-14"]


class _Block(HTMLParser):
    """Text and table cells inside the section with one class."""

    def __init__(self, cls: str) -> None:
        super().__init__()
        self.cls = cls
        self.depth = 0
        self.text: list[str] = []
        self.cells: list[str] = []
        self._cell = False
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "section":
            if self.depth:
                self.depth += 1
            elif dict(attrs).get("class") == self.cls:
                self.depth = 1
                self.found = True
        elif self.depth and tag in ("td", "th"):
            self._cell = True
            self.cells.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self.depth:
            self.depth -= 1
        elif tag in ("td", "th"):
            self._cell = False

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.text.append(data)
            if self._cell:
                self.cells[-1] += data


def _block(path: Path, cls: str) -> _Block:
    p = _Block(cls)
    p.feed(path.read_text(encoding="utf-8"))
    return p


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


def _w(weeks: list[str], removed: list[str] | None = None) -> dict[str, Any]:
    return {
        "region": "R1",
        "plants": _plants(weeks, "listed") + _plants(removed or [], "removed"),
    }


def _text(b: _Block) -> str:
    return " ".join(" ".join(b.text).split())


# ---- helpers


def test_month_counts_group_listed_weeks_by_start_month() -> None:
    assert site._month_counts(WATER_WEEKS) == [("2025-09", 2), ("2026-04", 3)]
    assert site._water_record(_w(WATER_WEEKS))["months"] == [
        ("2025-09", 2),
        ("2026-04", 3),
    ]


def test_removed_entries_do_not_count_with_a_negative_control() -> None:
    base = site._water_record(_w(WATER_WEEKS))["months"]
    assert site._water_record(_w(WATER_WEEKS, removed=REMOVED_WEEKS))["months"] == base
    # Control: the sabotage (removed weeks counted as listed) must change a
    # month's count, or the assertion above proves nothing.
    sabotaged = site._water_record(_w(WATER_WEEKS + REMOVED_WEEKS))["months"]
    assert dict(sabotaged)["2026-06"] == 2
    assert "2026-06" not in dict(base)
    assert sabotaged != base


def test_a_month_with_no_listed_week_is_absent_not_zero() -> None:
    months = dict(site._month_counts(WATER_WEEKS))
    assert "2025-12" not in months
    assert 0 not in months.values()


def test_below_three_weeks_shows_nothing() -> None:
    two = site._water_months(_w(WATER_WEEKS[:2]), recorded_since="2025-09-14")
    three = site._water_months(_w(WATER_WEEKS[:3]), recorded_since="2025-09-14")
    assert two is None
    assert three is not None and three["total"] == 3


def test_ties_name_every_month_and_the_peak_is_correct() -> None:
    view = site._water_months(
        _w(["2025-09-14", "2025-09-21", "2026-04-05", "2026-04-12"]),
        recorded_since="2025-09-14",
    )
    assert view is not None
    assert view["peak_tied"] and view["peak_months"] == "September 2025 and April 2026"
    assert view["peak_weeks"] == 2


# ---- built pages


@pytest.fixture(scope="module")
def v1(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("seasonal-src")
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
    """Plants shaped like a real snapshot plant, with these weeks and status."""
    out = []
    for p in _plants(weeks, status):
        full = copy.deepcopy(template)
        full.update(p)
        out.append(full)
    return out


def _pinned(v1: dict[str, Any]) -> dict[str, Any]:
    """The fixture snapshot with water 0 given five listed and two removed
    weeks, water 1 given two listed weeks, water 2 given only removed entries, and the
    earliest recorded week pinned to 2025-09-14."""
    snap = copy.deepcopy(v1)
    ws = snap["waters"]
    t = ws[0]["plants"][0]
    ws[0]["plants"] = _like(t, WATER_WEEKS, "listed") + _like(
        t, REMOVED_WEEKS, "removed"
    )
    ws[1]["plants"] = _like(t, ["2026-04-05", "2026-04-12"], "listed")
    ws[2]["plants"] = _like(t, REMOVED_WEEKS, "removed")
    return snap


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory, v1: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    snap = _pinned(v1)
    out = tmp_path_factory.mktemp("seasonal-site") / "site"
    site.build_site(snap, out, base_url=BASE)
    return out, snap


def _water_page(out: Path, w: dict[str, Any]) -> Path:
    return out / "water" / w["slug"] / "index.html"


def test_water_page_table_and_sentence(built: tuple[Path, dict[str, Any]]) -> None:
    out, snap = built
    b = _block(_water_page(out, snap["waters"][0]), "water-months")
    assert b.found
    assert b.cells == [
        "Month",
        "Weeks on the schedule",
        "September 2025",
        "2",
        "April 2026",
        "3",
    ]
    text = _text(b)
    assert "In the weeks recorded here, since the week of 2025-09-14" in text
    assert "for 5 weeks across 2 months" in text
    assert "April 2026 has the highest count, with 3 weeks" in text
    assert "not a forecast" in text
    assert "June 2026" not in text  # removed entries are not counted


def test_thin_and_empty_waters_show_no_block(
    built: tuple[Path, dict[str, Any]],
) -> None:
    out, snap = built
    for w in snap["waters"][1:3]:
        assert not _block(_water_page(out, w), "water-months").found


def test_county_page_months_sum_the_counties_waters(
    built: tuple[Path, dict[str, Any]],
) -> None:
    out, snap = built
    w0 = snap["waters"][0]
    county = w0["counties"][0]
    expected: dict[str, int] = {}
    members = [w for w in snap["waters"] if county in w["counties"]]
    for w in members:
        for p in w["plants"]:
            if p["status"] == "listed":
                expected[p["week"]["start"][:7]] = (
                    expected.get(p["week"]["start"][:7], 0) + 1
                )
    b = _block(
        out / "county" / site.county_slug(county) / "index.html", "county-months"
    )
    total = sum(expected.values())
    if total < site.MIN_WEEKS_FOR_MONTHS:
        assert not b.found
        return
    assert b.found
    cells = b.cells[2:]
    got = {cells[i]: int(cells[i + 1]) for i in range(0, len(cells), 2)}
    assert got == {site._month_label(k): v for k, v in sorted(expected.items())}
    text = _text(b)
    assert "since the week of 2025-09-14" in text
    assert f"{county} County had {total} listed" in text
    assert "not a forecast" in text


def test_pages_say_different_things(built: tuple[Path, dict[str, Any]]) -> None:
    out, snap = built
    # Same-shape sentence differs by water and by county name.
    a = _text(_block(_water_page(out, snap["waters"][0]), "water-months"))
    assert snap["waters"][0]["name"] in a


def test_copy_rules_on_every_rendered_block(built: tuple[Path, dict[str, Any]]) -> None:
    out, _ = built
    seen = 0
    for page in list(out.glob("water/*/index.html")) + list(
        out.glob("county/*/index.html")
    ):
        for cls in ("water-months", "county-months"):
            b = _block(page, cls)
            if not b.found:
                continue
            seen += 1
            words = {w.strip(".,;:()'\"").lower() for w in _text(b).split()}
            assert not words & BANNED, (page, words & BANNED)
            low = _text(b).lower()
            assert not [p for p in PREDICTIVE if p in low], page
            assert "since the week of 2025-09-14" in low or "since the week of" in low
            assert "0 weeks" not in low
    assert seen >= 2
