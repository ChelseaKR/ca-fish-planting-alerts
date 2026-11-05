"""Answer-first openings on a named set of pages (cfpa.answer_first,
DECISIONS 0046).

The fixture's current week lists nothing, so most tests here move the
fixture's snapshot to the week of 2026-04-19, when CDFW listed 29 of its
waters, and render that. The named pages are real site paths that the
fixture mostly lacks, so the rendering tests swap in fixture waters with the
same shape (a placed lake, a water with no point, a USGS "Lake X" name) by
patching ``ANSWER_FIRST_PAGES``.

The guard that matters most for the 2026-12-15 reading: every page outside
the list builds byte for byte as it does with no list at all, the plan's
control pages above all.
"""

from __future__ import annotations

import copy
import datetime as dt
import html as htmllib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from cfpa import answer_first, cli, locations, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
WEEK = "2026-04-19"

# Fixture waters standing in for the named pages, by shape.
STAND_INS: dict[str, frozenset[str]] = {
    "/": frozenset({"home_count"}),
    "/county/": frozenset({"counties_count"}),
    # This week: Silver Lake (listed 2025-10-26 before) and others.
    "/county/mono/": frozenset({"county_answer", "winter_first"}),
    # A USGS "Lake X" name, on this week's schedule.
    "/water/gregory-lake/": frozenset(
        {"name_first", "answer_lede", "last_season", "nearest_list", "nearest_status"}
    ),
    # Placed, nothing this week or next: matched by distance.
    "/water/lake-almanor/": frozenset({"nearest_status", "nearest_list"}),
    # No point; Mono County has waters this week: matched by county.
    "/water/owens-river-section-3/": frozenset({"nearest_status"}),
    # No point; nothing in Los Angeles County this week: matched by region.
    "/water/legg-lakes/": frozenset({"nearest_status"}),
}

STATUS_RE = re.compile(r'<section class="water-status".*?</section>', re.S)


def _text(fragment: str) -> str:
    plain = htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))
    plain = re.sub(r"\s+", " ", plain).strip()
    return re.sub(r"\( ", "(", re.sub(r" ([.,;:)])", r"\1", plain))


def _moved_to(v1: dict[str, Any], week: str) -> dict[str, Any]:
    """The snapshot as it would read with ``week`` as CDFW's current week."""
    snap = copy.deepcopy(v1)
    end = (dt.date.fromisoformat(week) + dt.timedelta(days=6)).isoformat()
    snap["source_week"] = {"start": week, "end": end, "label": f"week of {week}"}
    checked = (dt.date.fromisoformat(week) + dt.timedelta(days=1)).isoformat()
    snap["generated_at"] = f"{checked}T12:00:00Z"
    snap["source"]["fetched_at"] = f"{checked}T12:00:00Z"
    snap["this_week"] = []
    for w in snap["waters"]:
        # Seen when CDFW first listed it, as a daily run would have.
        for p in w["plants"]:
            seen = f"{min(p['week']['start'], checked)}T12:00:00Z"
            p["first_observed_at"] = p["last_observed_at"] = seen
        listed = [p for p in w["plants"] if p["status"] == "listed"]
        snap["this_week"] += [
            {"water_id": w["id"], "species": p["species"]}
            for p in listed
            if p["week"]["start"] == week
        ]
        past = [p["week"] for p in listed if p["week"]["start"] <= week]
        last = max(past, key=lambda x: x["start"]) if past else None
        w["last_listed_week"] = (
            {"start": last["start"], "label": last["label"]} if last else None
        )
    return snap


@pytest.fixture(scope="module")
def inputs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("answer-first-in")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=FIXTURES / "states",
    )
    snap_dir = root / "site" / "snapshot"
    v1 = json.loads((snap_dir / "v1.json").read_text(encoding="utf-8"))
    v2 = json.loads((snap_dir / "v2.json").read_text(encoding="utf-8"))
    return {
        "v1": v1,
        "moved": _moved_to(v1, WEEK),
        "v2": v2,
        "usgs": locations.load_usgs_lake_names(cli.DEFAULT_LOCATIONS_PATH),
    }


def _render(
    inputs: dict[str, Any],
    out: Path,
    pages: Mapping[str, frozenset[str]],
    *,
    snapshot: str = "moved",
) -> Path:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(answer_first, "ANSWER_FIRST_PAGES", pages)
        site.build_site(
            inputs[snapshot],
            out,
            base_url=BASE_URL,
            snapshot_v2=inputs["v2"],
            usgs_lake_names=inputs["usgs"],
            build_date=dt.date(2026, 4, 20),
        )
    return out


@pytest.fixture(scope="module")
def plain(inputs: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(inputs, tmp_path_factory.mktemp("af-plain") / "site", {})


@pytest.fixture(scope="module")
def treated(inputs: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(inputs, tmp_path_factory.mktemp("af-treated") / "site", STAND_INS)


@pytest.fixture(scope="module")
def real_list(inputs: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(
        inputs,
        tmp_path_factory.mktemp("af-real") / "site",
        answer_first.ANSWER_FIRST_PAGES,
    )


def _page(out: Path, path: str) -> str:
    return (out / path.strip("/") / "index.html").read_text(encoding="utf-8")


def _changed(a: Path, b: Path) -> set[str]:
    """Every file whose bytes differ between two builds, by relative path."""
    files_a = {p.relative_to(a) for p in a.rglob("*") if p.is_file()}
    files_b = {p.relative_to(b) for p in b.rglob("*") if p.is_file()}
    assert files_a == files_b
    return {str(f) for f in files_a if (a / f).read_bytes() != (b / f).read_bytes()}


def _page_file(path: str) -> str:
    return f"{path.strip('/')}/index.html".lstrip("/")


def _sitemap_changes(a: Path, b: Path) -> set[str]:
    def rows(out: Path) -> dict[str, str]:
        xml = (out / "sitemap.xml").read_text(encoding="utf-8")
        return dict(re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", xml))

    ra, rb = rows(a), rows(b)
    assert set(ra) == set(rb)
    return {u[len(BASE_URL) :] for u in ra if ra[u] != rb[u]}


# ---- which pages change


def test_the_list_is_the_plan_and_never_a_control() -> None:
    assert set(answer_first.ANSWER_FIRST_PAGES) == {
        "/",
        "/county/",
        "/county/fresno/",
        "/water/ralphine-lake/",
        "/water/collins-lake/",
        "/water/skinner-lake/",
        "/water/shadow-cliff-lake/",
    }
    assert {
        "/county/los-angeles/",
        "/county/sacramento/",
        "/water/mojave-narrows-regional-park-lake/",
        "/water/halsey-forebay/",
        "/water/lake-hemet/",
        "/water/portal-forebay/",
        "/tn/",
    } == answer_first.CONTROL_PATHS
    assert not set(answer_first.ANSWER_FIRST_PAGES) & answer_first.CONTROL_PATHS
    assert answer_first.features("/water/halsey-forebay/") == frozenset()


def test_only_the_listed_pages_change(plain: Path, treated: Path) -> None:
    changed = _changed(plain, treated)
    allowed = {_page_file(p) for p in STAND_INS} | {"sitemap.xml"}
    assert changed <= allowed, sorted(changed - allowed)
    # Not vacuous: every stand-in page did change.
    assert {_page_file(p) for p in STAND_INS} <= changed
    assert _sitemap_changes(plain, treated) <= set(STAND_INS)


def test_the_control_pages_do_not_change(plain: Path, real_list: Path) -> None:
    """The plan's controls build byte for byte with and without the list,
    as do the sitemap rows for them. The fixture has three of the seven."""
    present = [
        p for p in answer_first.CONTROL_PATHS if (plain / _page_file(p)).exists()
    ]
    assert {"/county/los-angeles/", "/water/halsey-forebay/", "/tn/"} <= set(present)
    for path in present:
        assert _page(plain, path) == _page(real_list, path), path
    changed = _changed(plain, real_list)
    assert not {_page_file(p) for p in answer_first.CONTROL_PATHS} & changed
    assert not _sitemap_changes(plain, real_list) & answer_first.CONTROL_PATHS
    allowed = {_page_file(p) for p in answer_first.ANSWER_FIRST_PAGES}
    assert changed <= allowed | {"sitemap.xml"}


# Words that appear on a page only through answer_first. With no list, no page
# carries any of them, so a change that leaks past the list's gate shows here
# even though it would leave both builds above equal.
ANSWER_FIRST_MARKERS = (
    "CDFW (DFG) fish planting schedule",
    "Nearest water",
    "On CDFW's schedule this week in",
    'id="near-heading"',
    "on CDFW's schedule)",
    "In the city of",
    "was also on the schedule the",
    "Measured in a straight line",
)


def test_no_page_outside_the_list_carries_answer_first_words(
    plain: Path, real_list: Path
) -> None:
    pages = sorted(plain.rglob("*.html"))
    assert len(pages) > 50
    for page in pages:
        html = page.read_text(encoding="utf-8")
        for marker in ANSWER_FIRST_MARKERS:
            assert marker not in html, (page, marker)
    for path in answer_first.CONTROL_PATHS:
        f = real_list / _page_file(path)
        if f.exists():
            html = f.read_text(encoding="utf-8")
            assert not [m for m in ANSWER_FIRST_MARKERS if m in html], path


def test_the_markers_are_what_the_treated_pages_say(treated: Path) -> None:
    """Each marker is live: some stand-in page carries it, so the test above
    is not passing on words that are never written."""
    every = "".join(_page(treated, p) for p in STAND_INS)
    missing = [
        m
        for m in ANSWER_FIRST_MARKERS
        # The fixture has no "<county> City" water; the builder test covers it.
        if m not in every and m != "In the city of"
    ]
    assert missing == []


# ---- the home page and /county/


def test_home_leads_with_cdfw_dfg_and_this_weeks_count(
    treated: Path, inputs: dict[str, Any]
) -> None:
    html = _page(treated, "/")
    snap = inputs["moved"]
    ids = {e["water_id"] for e in snap["this_week"]}
    by_id = {w["id"]: w for w in snap["waters"]}
    counties = {c for i in ids for c in by_id[i]["counties"]}
    h1 = _text(re.search(r"<h1>(.*?)</h1>", html, re.S).group(1))
    assert h1 == f"CDFW (DFG) fish planting schedule this week: week of {WEEK}"
    lede = _text(re.search(r'<p class="lede">(.*?)</p>', html, re.S).group(1))
    assert lede.startswith(
        f"CDFW has {len(ids)} waters in {len(counties)} counties on its fish "
        f"planting schedule this week, the week of {WEEK}. CDFW was the "
        "Department of Fish and Game (DFG) before 2013."
    )
    assert 'href="./county/">by county</a>' in html
    # The most recent earlier week with a page.
    assert 'href="./week/2026-04-12/">' in html
    # The title stays, so one element changes.
    assert "<title>California trout planting schedule this week" in html


def test_county_index_opens_with_the_count_and_a_link_home(
    treated: Path, plain: Path
) -> None:
    lede = re.search(r'<p class="lede">(.*?)</p>', _page(treated, "/county/"), re.S)
    text = _text(lede.group(1))
    assert re.match(
        rf"This week, the week of {WEEK}, \d+ waters in \d+ counties are on "
        r"CDFW's schedule; see this week's list\.",
        text,
    )
    assert '<a href="../">this week\'s list</a>' in lede.group(1)
    h1 = re.search(r"<h1>(.*?)</h1>", _page(plain, "/county/")).group(1)
    assert h1 == re.search(r"<h1>(.*?)</h1>", _page(treated, "/county/")).group(1)


def test_an_empty_week_says_so_in_words(inputs: dict[str, Any], tmp_path: Path) -> None:
    out = _render(inputs, tmp_path / "site", STAND_INS, snapshot="v1")
    text = _text(_page(out, "/county/"))
    assert (
        "This week, the week of 2026-09-13, CDFW's schedule lists no plants; "
        "see the waters it scheduled next and most recently." in text
    )
    assert "0 waters" not in _text(_page(out, "/"))
    # No this-week line on a water page when nothing is on the schedule.
    block = STATUS_RE.search(_page(out, "/water/lake-almanor/")).group(0)
    assert "this week in" not in block
    assert "Nearest" not in block


# ---- a county page


def test_county_page_leads_with_this_weeks_waters_and_the_week_before(
    treated: Path,
) -> None:
    html = _page(treated, "/county/mono/")
    lede = re.search(r'<p class="lede">(.*?)</p>', html, re.S).group(1)
    text = _text(lede)
    assert text.startswith(f"This week (week of {WEEK}), CDFW has ")
    assert "Mono County waters on its trout planting schedule:" in text
    assert "Silver Lake was also on the schedule the week of 2025-10-26." in text
    assert '<a href="../../week/2025-10-26/">week of 2025-10-26</a>' in lede
    assert '<a href="../../">week of 2026-04-19</a>' in lede
    # The existing opening follows, unchanged.
    assert "waters in Mono County have been on the California" in text


def test_county_winter_moves_up_only_in_winter(treated: Path, plain: Path) -> None:
    """April is not winter, so the section keeps its place on both builds."""
    for out in (plain, treated):
        html = _page(out, "/county/mono/")
        assert html.find("Scheduled for later weeks") < html.find("Recently on")


# ---- water pages


def test_name_first_title_h1_and_answer(treated: Path, plain: Path) -> None:
    html = _page(treated, "/water/gregory-lake/")
    assert (
        "<title>Lake Gregory trout stocking schedule (San Bernardino County)"
        " | Trout Truck</title>"
    ) in html
    h1 = _text(re.search(r"<h1>(.*?)</h1>", html).group(1))
    assert (
        h1 == "Lake Gregory (Gregory Lake on CDFW's schedule) trout stocking schedule"
    )
    answer = _text(html[html.index("</h1>") : html.index('class="water-status"')])
    assert answer.startswith(
        f"CDFW has Lake Gregory on its trout planting schedule this week, the "
        f"week of {WEEK}."
    )
    # The record starts 2025-09-14, after April 2025: no "last spring" line.
    assert "Last spring" not in answer
    assert "<title>Gregory Lake (Lake Gregory)" in _page(plain, "/water/gregory-lake/")


def test_nearest_by_distance_in_the_status_block(
    treated: Path, inputs: dict[str, Any]
) -> None:
    block = _text(STATUS_RE.search(_page(treated, "/water/lake-almanor/")).group(0))
    m = re.search(
        r"Nearest water on CDFW's schedule this week (.+?) \((\w[\w ]*) County\), "
        r"about (\d+) miles away\. Measured in a straight line between U\.S\. "
        r"Geological Survey points; (\d+) of this week's waters have no point",
        block,
    )
    assert m, block
    coords = site.water_coords(inputs["v2"])
    snap = inputs["moved"]
    ids = {e["water_id"] for e in snap["this_week"]}
    scheduled = [w for w in snap["waters"] if w["id"] in ids]
    placed = [w for w in scheduled if w["slug"] in coords]
    here = coords["lake-almanor"]
    nearest = min(
        placed, key=lambda w: answer_first.miles_between(here, coords[w["slug"]])
    )
    assert m.group(1) == nearest["name"]
    assert int(m.group(3)) == answer_first.rounded_miles(here, coords[nearest["slug"]])
    assert int(m.group(4)) == len(scheduled) - len(placed)


def test_nearest_list_replaces_the_region_list_within_its_radius(
    treated: Path, plain: Path
) -> None:
    html = _page(treated, "/water/lake-almanor/")
    section = re.search(
        r'<section aria-labelledby="near-heading">.*?</section>', html, re.S
    ).group(0)
    miles = [int(x) for x in re.findall(r"about (\d+) miles\)", section)]
    assert miles == sorted(miles)
    assert 0 < len(miles) <= answer_first.NEAREST_LIST_MAX
    assert max(miles) <= answer_first.NEAREST_LIST_MILES
    assert "region-related-heading" not in html
    assert "region-related-heading" in _page(plain, "/water/lake-almanor/")


def test_a_water_with_no_point_is_matched_by_county_then_region(
    treated: Path,
) -> None:
    by_county = _text(
        STATUS_RE.search(_page(treated, "/water/owens-river-section-3/")).group(0)
    )
    assert "On CDFW's schedule this week in Mono County " in by_county
    assert "Nearest" not in by_county
    assert "miles" not in by_county
    by_region = _text(STATUS_RE.search(_page(treated, "/water/legg-lakes/")).group(0))
    assert (
        "On CDFW's schedule this week in the South Coast Region Reyes Creek "
        "(Ventura County)." in by_region
    )


def test_the_status_line_is_only_for_none_scheduled(treated: Path) -> None:
    """Gregory Lake is on this week's schedule, so no other water is offered
    in its status block."""
    block = STATUS_RE.search(_page(treated, "/water/gregory-lake/")).group(0)
    assert "Nearest" not in block
    assert "this week in" not in block


def test_treated_pages_keep_the_status_block_rules(treated: Path) -> None:
    forbidden = re.compile(r"\b(stocked|planted on|only|first|0 waters)\b", re.I)
    for path in STAND_INS:
        if not path.startswith("/water/"):
            continue
        html = _page(treated, path)
        block = STATUS_RE.search(html).group(0)
        assert not forbidden.search(_text(block)), path
        assert len(re.findall(r"<dt>", block)) == len(re.findall(r"<dd>", block))
        assert html.index("<h1>") < html.index("water-status"), path
        assert "<ul" not in block
        assert not re.search(r"<ul[^>]*>\s*</ul>", html), path


def test_lastmod_counts_the_rollover_for_a_this_week_line(
    plain: Path, treated: Path
) -> None:
    changed = _sitemap_changes(plain, treated)
    # Legg Lakes has two dated rows, so it is in the sitemap (Lake Almanor,
    # with one, is not: cfpa.thin).
    assert "/water/legg-lakes/" in changed
    xml = (treated / "sitemap.xml").read_text(encoding="utf-8")
    legg = re.search(r"water/legg-lakes/</loc><lastmod>([^<]+)<", xml).group(1)
    assert legg == WEEK


# ---- the builders on their own


def _w(
    slug: str,
    weeks: list[str],
    *,
    counties: tuple[str, ...] = ("Fresno",),
    region: str = "R4",
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": slug,
        "slug": slug,
        "name": name or slug.replace("-", " ").title(),
        "counties": list(counties),
        "region": region,
        "plants": [
            {"week": {"start": d}, "status": "listed", "species": "Trout"}
            for d in weeks
        ],
    }


def test_scheduled_near_by_distance_and_its_unranked_count() -> None:
    here = _w("here", [])
    a, b, c = _w("a", [WEEK]), _w("b", [WEEK]), _w("c", [WEEK])
    coords = {
        "here": [38.0, -122.0, "w"],
        "a": [38.0, -121.0, "w"],
        "b": [38.0, -122.2, "w"],
    }
    near = answer_first.scheduled_near(
        here, [a, b, c, here], coords=coords, region_name="Central Region"
    )
    assert near is not None
    assert [r["slug"] for r in near["waters"]] == ["b", "a"]
    assert near["basis"] == "distance"
    assert near["unranked"] == 1


def test_scheduled_near_falls_back_to_county_then_region_then_nothing() -> None:
    here = _w("here", [], counties=("Yuba",), region="R2")
    same_county = _w("x", [WEEK], counties=("Yuba",), region="R2")
    same_region = _w("y", [WEEK], counties=("Nevada",), region="R2")
    elsewhere = _w("z", [WEEK], counties=("Kern",), region="R4")
    kw: dict[str, Any] = {"coords": {}, "region_name": "North Central Region"}
    county = answer_first.scheduled_near(here, [same_county, same_region], **kw)
    assert county is not None
    assert (county["basis"], county["where"]) == ("county", "Yuba County")
    region = answer_first.scheduled_near(here, [same_region, elsewhere], **kw)
    assert region is not None
    assert (region["basis"], region["where"]) == ("region", "the North Central Region")
    assert [r["slug"] for r in region["waters"]] == ["y"]
    assert answer_first.scheduled_near(here, [elsewhere], **kw) is None
    assert answer_first.scheduled_near(here, [], **kw) is None
    # A placed water with no placed water to compare falls back the same way.
    placed_kw: dict[str, Any] = {
        "coords": {"here": [39.0, -121.0, "w"]},
        "region_name": "North Central Region",
    }
    fallback = answer_first.scheduled_near(here, [same_county], **placed_kw)
    assert fallback is not None
    assert fallback["basis"] == "county"


def test_shortened_cuts_counts_and_drops_far_waters() -> None:
    near = {
        "basis": "distance",
        "where": "",
        "unranked": 0,
        "waters": [
            {"slug": s, "miles": m} for s, m in (("a", 10), ("b", 150), ("c", 400))
        ],
    }
    short = answer_first.shortened(near, 5, max_miles=200)
    assert short is not None
    assert [r["slug"] for r in short["waters"]] == ["a", "b"]
    one = answer_first.shortened(near, 1)
    assert one is not None
    assert (len(one["waters"]), one["more"]) == (1, 2)
    far = {**near, "waters": [{"slug": "c", "miles": 400}]}
    assert answer_first.shortened(far, 5, max_miles=200) is None
    assert answer_first.shortened(None, 5) is None


def test_rounded_miles_is_to_the_nearest_five_and_never_zero() -> None:
    assert answer_first.rounded_miles([38.0, -122.0], [38.0, -122.0]) == 5
    assert (
        answer_first.rounded_miles([38.45481, -122.66708], [37.61407, -121.73498]) == 75
    )


@pytest.mark.parametrize(
    ("week", "since", "expected"),
    [
        (
            "2026-11-01",
            "2025-09-14",
            ("fall", "October through December 2025", ["2025-10-26", "2025-12-07"]),
        ),
        ("2026-02-08", "2025-09-14", None),  # the record does not cover Jan 2025
        ("2027-02-07", "2025-09-14", ("winter", "January through March 2026", [])),
        ("2026-11-01", "", None),
    ],
)
def test_last_season(week: str, since: str, expected: Any) -> None:
    w = _w("w", ["2025-09-28", "2025-10-26", "2025-12-07", "2026-04-05"])
    got = answer_first.last_season(w, source_week_start=week, recorded_since=since)
    if expected is None:
        assert got is None
    else:
        assert got == dict(zip(("season", "label", "weeks"), expected, strict=True))


def test_water_answer_kinds() -> None:
    def kind(weeks: list[str]) -> Any:
        return answer_first.water_answer(_w("w", weeks), source_week_start=WEEK)

    assert kind([WEEK, "2026-01-04"]) == {"kind": "this_week", "week": WEEK}
    assert kind(["2026-01-04", "2026-05-03"]) == {"kind": "next", "week": "2026-05-03"}
    assert kind(["2026-01-04"]) == {"kind": "last", "week": "2026-01-04"}
    assert kind([]) is None


def test_county_answer_this_week_before_latest_other_and_city() -> None:
    members = [
        _w("kings", ["2026-04-05", WEEK]),
        _w("shaver", ["2026-03-29", "2026-04-12"]),
        _w("old", ["2025-10-05"]),
        _w("woodward", ["2026-03-01"], name="Fresno City Woodward Park Lake"),
    ]
    got = answer_first.county_answer("Fresno", members, source_week_start=WEEK)
    assert got["this_week"] == [
        {"slug": "kings", "name": "Kings", "before": "2026-04-05"}
    ]
    assert got["latest_other"] == {
        "slug": "shaver",
        "name": "Shaver",
        "week": "2026-04-12",
    }
    assert got["city"] == {
        "slug": "woodward",
        "name": "Woodward Park Lake",
        "week": "2026-03-01",
    }
    # The city water on this week's schedule is already named, so no city line.
    members[3] = _w("woodward", [WEEK], name="Fresno City Woodward Park Lake")
    again = answer_first.county_answer("Fresno", members, source_week_start=WEEK)
    assert again["city"] is None
    assert [w["slug"] for w in again["this_week"]] == ["woodward", "kings"]
    assert again["this_week"][0]["before"] == ""
    # Nothing listed anywhere: no rows, no zero.
    empty = answer_first.county_answer("Fresno", [_w("x", [])], source_week_start=WEEK)
    assert empty == {"this_week": [], "latest_other": None, "city": None}


def test_week_count_counts_each_water_and_county_once() -> None:
    by_id = {
        "a": {"counties": ["Kern", "Tulare"]},
        "b": {"counties": ["Kern"]},
    }
    entries = [
        {"water_id": "a", "species": "Trout"},
        {"water_id": "a", "species": "Catfish"},
        {"water_id": "b", "species": "Trout"},
    ]
    assert answer_first.week_count(entries, by_id) == {"waters": 2, "counties": 2}
    assert answer_first.week_count([], by_id) == {"waters": 0, "counties": 0}


def test_page_helpers() -> None:
    assert answer_first.for_page("/", "home_count", {"x": 1}) == {"x": 1}
    assert answer_first.for_page("/", "counties_count", {"x": 1}) is None
    assert answer_first.rollover_dates("/county/fresno/", WEEK) == [WEEK]
    assert answer_first.rollover_dates("/county/los-angeles/", WEEK) == []
