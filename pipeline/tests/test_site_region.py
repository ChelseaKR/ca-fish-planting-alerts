"""Region pages (/region/<slug>/): one per CDFW region that has a water.

Built from the real CDFW fixture, then from a copy of its snapshot with one
plant moved into next week, so the next-week list is checked against a
change we made and proved applied. HTML and the JSON-LD block are read with
``html.parser`` only.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
DATA = Path(__file__).resolve().parents[1] / "data"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
ALLOWED_TYPES = {"WebSite", "CollectionPage", "BreadcrumbList", "ListItem", "State"}
BANNED_KEYS = {"startDate", "endDate", "eventStatus", "geo", "latitude", "longitude"}
BANNED_WORDS = ("only", "first", "stocked", "planted on")


class _Page(HTMLParser):
    """Title, description, canonical, h1s, JSON-LD text, breadcrumb names,
    visible main text, and the links inside each <h2> section's tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.h1: list[str] = []
        self.ld = ""
        self.crumbs: list[str] = []
        self.main_text: list[str] = []
        self.hrefs: list[str] = []
        self.section_links: dict[str, list[str]] = {}
        self._stack: list[str] = []
        self._in_main = False
        self._in_crumb = False
        self._h2 = ""
        self._in_table = False
        self._td = 0
        self._ld_on = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        self._stack.append(tag)
        if tag == "meta" and a.get("name") == "description":
            self.description = a.get("content", "")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href", "")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld_on = True
        elif tag == "a" and self._in_main:
            self._link(a.get("href", ""))
        else:
            self._structure(tag, a)

    def _structure(self, tag: str, a: dict[str, str]) -> None:
        if tag == "main":
            self._in_main = True
        elif tag == "nav" and a.get("aria-label") == "Breadcrumb":
            self._in_crumb = True
        elif tag == "table":
            self._in_table = True
        elif tag == "td":
            self._td += 1
        elif tag == "tr":
            self._td = 0

    def _link(self, href: str) -> None:
        self.hrefs.append(href)
        if self._in_table and self._td == 1:
            self.section_links.setdefault(self._h2, []).append(href)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag == "script":
            self._ld_on = False
        elif tag == "main":
            self._in_main = False
        elif tag == "nav":
            self._in_crumb = False
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        cur = self._stack[-1] if self._stack else ""
        if self._ld_on:
            self.ld += data
        elif cur == "title":
            self.title += data
        elif cur == "h1":
            self.h1.append(data)
        elif cur == "h2":
            self._h2 = data.strip()
        elif cur == "a" and self._in_crumb:
            self.crumbs.append(data)
        if self._in_main and cur not in ("script", "style"):
            self.main_text.append(data)


def parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def _run(root: Path) -> dict[str, Any]:
    # The committed history and aliases, so the fixture's rows match real
    # waters and the pages have real regions to list.
    for name in ("history.json", "aliases.json"):
        shutil.copy(DATA / name, root / name)
    return cli.run(
        fixture_path=str(MIDWEEK),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 18),
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("region")
    snap = _run(root)
    return root / "site", snap


def _expected_slugs(snap: dict[str, Any]) -> dict[str, str]:
    """code -> slug for regions that have a water and a county."""
    with_water = {w["region"] for w in snap["waters"]}
    return {
        r["code"]: site.region_slug(r["name"])
        for r in snap["regions"]
        if r["code"] in with_water
    }


def test_slugs_come_from_cdfw_labels():
    assert site.region_slug("Bay Delta Region (R3)") == "bay-delta"
    assert site.region_slug("North Central Region (R2)") == "north-central"
    assert site.region_slug("Inland Deserts Region (R6)") == "inland-deserts"
    assert site.region_display_name("South Coast Region (R5)") == "South Coast Region"


def test_a_page_per_region_with_a_water_and_nothing_else(built):
    out, snap = built
    slugs = _expected_slugs(snap)
    assert slugs
    built_dirs = sorted(p.name for p in (out / "region").iterdir())
    assert built_dirs == sorted(slugs.values())
    for r in snap["regions"]:
        assert r["name"].startswith(site.REGION_NAME_BY_CODE[r["code"]])


def test_meta_canonical_and_copy_rules(built):
    out, snap = built
    titles, descs = [], []
    for code, slug in _expected_slugs(snap).items():
        page = parse(out / "region" / slug / "index.html")
        assert 0 < len(page.title) <= 60, page.title
        assert 0 < len(page.description) <= 160, page.description
        assert page.canonical == f"{BASE_URL}/region/{slug}/"
        assert len(page.h1) == 1
        name = site.REGION_NAME_BY_CODE[code]
        assert name in page.title and name in page.description
        text = " ".join(page.main_text).lower() + page.title.lower()
        text += page.description.lower()
        for word in BANNED_WORDS:
            assert f" {word} " not in f" {text} ", (slug, word)
        titles.append(page.title)
        descs.append(page.description)
    assert len(set(titles)) == len(titles)
    assert len(set(descs)) == len(descs)


def test_this_week_lists_match_the_snapshot(built):
    out, snap = built
    by_id = {w["id"]: w for w in snap["waters"]}
    checked = 0
    for code, slug in _expected_slugs(snap).items():
        page = parse(out / "region" / slug / "index.html")
        want = sorted(
            f"../../water/{by_id[e['water_id']]['slug']}/"
            for e in snap["this_week"]
            if by_id[e["water_id"]]["region"] == code
        )
        got = sorted(page.section_links.get("Scheduled this week", []))
        assert got == want, slug
        checked += len(want)
    assert checked > 0  # the fixture really schedules waters this week


def test_next_week_list_follows_a_change_we_made(built, tmp_path):
    _, snap = built
    mod = copy.deepcopy(snap)
    next_week = dt.date.fromisoformat(mod["source_week"]["start"]) + dt.timedelta(
        days=7
    )
    target = next(
        w for w in mod["waters"] if w["plants"] and w["region"] in {"R2", "R6", "R1"}
    )
    plant = target["plants"][0]
    plant["status"] = "listed"
    plant["week"] = {
        "start": next_week.isoformat(),
        "end": (next_week + dt.timedelta(days=6)).isoformat(),
        "label": f"week of {next_week.isoformat()}",
    }
    # The sabotage applied: the snapshot we render now says next week.
    assert target["plants"][0]["week"]["start"] == next_week.isoformat()
    assert snap != mod
    out = tmp_path / "site"
    site.build_site(mod, out, base_url=BASE_URL)
    slug = site.region_slug(
        next(r["name"] for r in mod["regions"] if r["code"] == target["region"])
    )
    page = parse(out / "region" / slug / "index.html")
    assert f"../../water/{target['slug']}/" in page.section_links.get(
        "Scheduled the week after", []
    )
    # And the unmodified snapshot does not list it there.
    base_page = parse(built[0] / "region" / slug / "index.html")
    assert f"../../water/{target['slug']}/" not in base_page.section_links.get(
        "Scheduled the week after", []
    )


def test_links_in_and_out(built):
    out, snap = built
    slugs = _expected_slugs(snap)
    home = parse(out / "index.html")
    counties = parse(out / "county" / "index.html")
    for slug in slugs.values():
        assert f"./region/{slug}/" in home.hrefs or f"region/{slug}/" in home.hrefs
        assert f"../region/{slug}/" in counties.hrefs
    # every county page links to its region page
    for county in snap["counties"]:
        cdir = out / "county" / site.county_slug(county["name"])
        if not cdir.exists():
            continue
        page = parse(cdir / "index.html")
        slug = slugs[county["region"]]
        assert f"../../region/{slug}/" in page.hrefs, county["name"]
    # every internal href on a region page resolves to a built file
    for slug in slugs.values():
        page = parse(out / "region" / slug / "index.html")
        for href in page.hrefs:
            if href.startswith(("http", "#")):
                continue
            target = (out / "region" / slug / href).resolve()
            assert target.is_file() or (target / "index.html").is_file(), href


def test_sitemap_has_each_region_page_with_a_lastmod(built):
    out, snap = built
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    for slug in _expected_slugs(snap).values():
        loc = f"<loc>{BASE_URL}/region/{slug}/</loc><lastmod>"
        assert loc in sitemap


def test_structured_data_reuses_existing_types_and_mirrors_breadcrumb(built):
    out, snap = built
    for slug in _expected_slugs(snap).values():
        page = parse(out / "region" / slug / "index.html")
        data = json.loads(page.ld)
        types = {n["@type"] for n in data["@graph"]}
        assert types <= ALLOWED_TYPES
        assert "CollectionPage" in types and "BreadcrumbList" in types

        def keys(v: Any) -> set[str]:
            if isinstance(v, dict):
                return set(v) | {k for x in v.values() for k in keys(x)}
            if isinstance(v, list):
                return {k for x in v for k in keys(x)}
            return set()

        assert not keys(data) & BANNED_KEYS
        crumb = next(n for n in data["@graph"] if n["@type"] == "BreadcrumbList")
        assert [i["name"] for i in crumb["itemListElement"]] == page.crumbs
        assert crumb["itemListElement"][-1]["item"] == f"{BASE_URL}/region/{slug}/"
