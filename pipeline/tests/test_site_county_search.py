"""County and water pages as search landing pages (roadmap Stage 1: county
pages rank for "trout planting schedule <county>", so they get attention
first).

A county page's meta description answers the query from the snapshot; the
page lists its most recent earlier weeks, each linked to its /week/ page; it
links the other counties of its CDFW region; and it carries the app line.
A water page's history rows link their /week/ pages. Built from the two real
CDFW fixtures in the order the scheduled job runs them, as in
test_site_seo.py, and every check compares the page with that snapshot.
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"


def _run(root: Path, fixture: Path, fetched_at: dt.datetime, today: dt.date) -> Any:
    return cli.run(
        fixture_path=str(fixture),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=fetched_at,
        run_today=today,
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("county-search")
    _run(
        root,
        FRESH,
        dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 13),
    )
    snap = _run(
        root,
        MIDWEEK,
        dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        dt.date(2026, 9, 18),
    )
    return root / "site", snap


def _by_county(snap: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for w in snap["waters"]:
        for c in w["counties"]:
            by.setdefault(c, []).append(w)
    return by


def _page(out: Path, rel: str) -> str:
    return (out / rel / "index.html").read_text(encoding="utf-8")


def _description(page: str) -> str:
    m = re.search(r'<meta name="description" content="([^"]*)"', page)
    assert m
    return htmllib.unescape(m.group(1))


def _section(page: str, start: str) -> str:
    """From ``start`` to the next plain <h2>, as tests/test_display_fixes.py
    reads a county page."""
    i = page.index(start)
    j = page.find("<h2>", i + len(start))
    return page[i : j if j != -1 else len(page)]


def _resolves(out: Path, page_rel: str, href: str) -> bool:
    target = (out / page_rel / href).resolve()
    return (target / "index.html").is_file() if href.endswith("/") else target.is_file()


def _listed(w: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in w["plants"] if p["status"] == "listed"]


# ---- the meta description


def test_county_description_says_what_the_schedule_says(built):
    out, snap = built
    week = snap["source_week"]["start"]
    label = snap["source_week"]["label"]
    branches = set()
    descriptions = []
    for county, members in _by_county(snap).items():
        d = _description(_page(out, f"county/{site.county_slug(county)}"))
        descriptions.append(d)
        assert len(d) <= site.COUNTY_DESCRIPTION_MAX, (county, d)
        assert d.startswith(f"{county} County ") and "stocking schedule" in d, d
        now = {
            w["name"] for w in members for p in _listed(w) if p["week"]["start"] == week
        }
        later = sorted(
            (p["week"]["start"], w["name"])
            for w in members
            for p in _listed(w)
            if p["week"]["start"] > week
        )
        past = [
            p["week"]["start"]
            for w in members
            for p in _listed(w)
            if p["week"]["start"] < week
        ]
        if now:
            branches.add("this week")
            assert f"scheduled this week, the {label}, at " in d, d
            assert any(n in d for n in now), d
        else:
            # The current week's date is printed only when a water is listed
            # for it (the lastmod rule, docs/adr/0013).
            assert label not in d, d
            if later:
                branches.add("next")
                assert (
                    f"none scheduled this week; next the week of {later[0][0]}, at "
                    in d
                )
                assert any(n in d for s, n in later if s == later[0][0]), d
            elif past:
                branches.add("last")
                assert (
                    f"nothing scheduled this week or later; last scheduled the week of "
                    f"{max(past)}." in d
                ), d
            else:
                assert "no week currently listed." in d
        # Never a zero for an absence, never "no fish".
        assert " 0 " not in d and "no fish" not in d
    assert len(descriptions) == len(set(descriptions))
    assert branches == {"this week", "next", "last"}


def _describe(**kw: Any) -> str:
    base: dict[str, Any] = {
        "species": "trout",
        "water_count": 3,
        "this_week_names": [],
        "source_week_label": "week of 2026-09-13",
        "next_week": "",
        "next_names": [],
        "last_week": "",
    }
    base.update(kw)
    return site._county_description("Inyo", **base)


def test_description_counts_the_names_that_do_not_fit():
    names = [f"Very Long Creek Name Number {i}, Middle Fork" for i in range(9)]
    d = _describe(this_week_names=names)
    assert len(d) <= site.COUNTY_DESCRIPTION_MAX
    assert names[0] in d
    assert re.search(r" and \d+ more\.", d), d


def test_description_falls_back_to_a_count_when_no_name_fits():
    d = _describe(this_week_names=["X" * 200, "Y" * 200])
    assert len(d) <= site.COUNTY_DESCRIPTION_MAX
    assert "at 2 waters." in d


def test_description_for_a_county_with_no_listed_week():
    assert _describe(water_count=1) == (
        "Inyo County trout stocking schedule: no week currently listed. "
        "CDFW planting history for the water."
    )


# ---- recently on the schedule


def _expected_recent(
    members: list[dict[str, Any]], week: str
) -> list[tuple[str, str, str]]:
    rows = [
        (p["week"]["start"], w["slug"], p["species"])
        for w in members
        for p in _listed(w)
        if p["week"]["start"] < week
    ]
    keep = sorted({r[0] for r in rows}, reverse=True)[: site.COUNTY_RECENT_WEEKS]
    return sorted(r for r in rows if r[0] in keep)


_RECENT_ROW = re.compile(
    r'<tr>\s*<td><a href="([^"]+)">week of (\d{4}-\d{2}-\d{2})</a></td>\s*'
    r'<td><a href="\.\./\.\./water/([^/]+)/">[^<]*</a></td>\s*<td>([^<]*)</td>'
)


def recent_problems(
    out: Path, page: str, county: str, members: list[dict[str, Any]], week: str
) -> list[str]:
    section = _section(page, "<h2>Recently on the schedule</h2>")
    found = _RECENT_ROW.findall(section)
    problems = []
    got = sorted((start, slug, species) for _, start, slug, species in found)
    if got != _expected_recent(members, week):
        problems.append(f"{county}: rows {got}")
    rel = f"county/{site.county_slug(county)}"
    for href, start, _, _ in found:
        if href != f"../../week/{start}/" or not _resolves(out, rel, href):
            problems.append(f"{county}: week link {href} does not resolve")
    if not found and (
        f"No {county} County water was on CDFW's schedule in any earlier week recorded here."
        not in section
    ):
        problems.append(f"{county}: no rows and no plain absence sentence")
    return problems


def test_recent_weeks_match_the_snapshot_and_link_built_week_pages(built):
    out, snap = built
    week = snap["source_week"]["start"]
    with_rows = without_rows = 0
    for county, members in _by_county(snap).items():
        page = _page(out, f"county/{site.county_slug(county)}")
        assert recent_problems(out, page, county, members, week) == []
        if _expected_recent(members, week):
            with_rows += 1
        else:
            without_rows += 1
    assert with_rows and without_rows  # both shapes are exercised


def test_negative_control_recent_weeks_check_catches_a_dropped_row(built):
    out, snap = built
    week = snap["source_week"]["start"]
    county, members = next(
        (c, m) for c, m in _by_county(snap).items() if _expected_recent(m, week)
    )
    good = _page(out, f"county/{site.county_slug(county)}")
    row = _RECENT_ROW.search(_section(good, "<h2>Recently on the schedule</h2>"))
    assert row
    bad = good.replace(row.group(0), "<tr>", 1)
    assert bad != good
    assert recent_problems(out, bad, county, members, week)


def _plant(
    start: str, status: str = "listed", species: str = "Trout"
) -> dict[str, Any]:
    return {"week": {"start": start}, "status": status, "species": species}


def test_recent_weeks_keep_the_latest_four_and_skip_removed_and_current():
    w = {
        "id": "a",
        "slug": "a",
        "name": "A",
        "plants": [
            _plant("2026-09-13"),  # the current week: shown above, not here
            _plant("2026-09-06", status="removed"),
            *(_plant(f"2026-08-{d:02d}") for d in (2, 9, 16, 23, 30)),
        ],
    }
    view = site._county_recent_weeks([w], source_week_start="2026-09-13")
    assert view["week_count"] == 4
    assert [r["week"] for r in view["rows"]] == [
        "2026-08-30",
        "2026-08-23",
        "2026-08-16",
        "2026-08-09",
    ]
    empty = site._county_recent_weeks([w], source_week_start="2026-08-02")
    assert empty == {"rows": [], "week_count": 0}


# ---- links to the region's other counties


def test_county_links_exactly_the_other_counties_of_its_region(built):
    out, snap = built
    region_of = {c["name"]: c["region"] for c in snap["counties"]}
    counties = _by_county(snap)
    linked_any = False
    for county in counties:
        rel = f"county/{site.county_slug(county)}"
        page = _page(out, rel)
        expected = {
            site.county_slug(o)
            for o in counties
            if o != county
            and region_of.get(county)
            and region_of.get(o) == region_of.get(county)
        }
        if not expected:
            assert "<h2>More counties in the " not in page
            continue
        section = _section(page, "<h2>More counties in the ")
        hrefs = re.findall(r'href="(\.\./\.\./county/([^/]+)/)"', section)
        assert {slug for _, slug in hrefs} == expected, county
        assert all(_resolves(out, rel, h) for h, _ in hrefs)
        linked_any = True
    assert linked_any


# ---- the app line


def test_every_county_page_has_the_app_line_and_no_store_link_before_launch(built):
    out, snap = built
    for county in _by_county(snap):
        page = _page(out, f"county/{site.county_slug(county)}")
        assert (
            f"favorite {county} County water is scheduled for a new week is on its way"
            in page
        )
        assert 'href="../../about/#app"' in page
        assert "apps.apple.com" not in page


# ---- water history rows link their week pages


_HISTORY_CELL = re.compile(
    r"<tr>\s*<td>(.*?)</td>\s*<td>[^<]*</td>\s*<td>[^<]*</td>", re.S
)


def test_water_history_links_exactly_its_past_listed_weeks(built):
    out, snap = built
    week = snap["source_week"]["start"]
    unlinked_seen = False
    for w in snap["waters"]:
        rel = f"water/{w['slug']}"
        page = _page(out, rel)
        i = page.index("<h2>Planting history</h2>")
        table = page[i : page.index("</table>", i)]
        cells = _HISTORY_CELL.findall(table)
        assert len(cells) == len(w["plants"]), w["slug"]
        linked = set()
        for cell in cells:
            m = re.fullmatch(
                r'<a href="(\.\./\.\./week/(\d{4}-\d{2}-\d{2})/)">week of \2</a>', cell
            )
            if m:
                assert _resolves(out, rel, m.group(1)), m.group(1)
                linked.add(m.group(2))
            else:
                assert "<a " not in cell
                unlinked_seen = True
        assert linked == {
            p["week"]["start"] for p in _listed(w) if p["week"]["start"] < week
        }
    assert unlinked_seen  # the fixture has current and later weeks too
