"""Species pages (/species/trout/, /species/catfish/): this week's and next
week's scheduled waters, built from the snapshot's plants and nothing else.

Every check compares a page with the snapshot it was built from, computed here
by a different route than the site uses. HTML is read with html.parser, never
with a regular expression over tags.
"""

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
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"


_VOID = {"meta", "link", "br", "img", "hr", "input"}


class _Page(HTMLParser):
    """Visible text, headings, links and the JSON-LD block of one page."""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, link text)
        self.ld: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.title = ""
        self.h1: list[str] = []
        self.breadcrumb: list[tuple[str, str]] = []
        self._stack: list[str] = []
        self._href = ""
        self._link_text: list[str] = []
        self._in_crumb = False
        self._ld_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag not in _VOID:
            self._stack.append(tag)
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonicals.append(a.get("href", ""))
        if tag == "script" and a.get("type") == "application/ld+json":
            self._ld_script = True
        if tag == "nav" and a.get("aria-label") == "Breadcrumb":
            self._in_crumb = True
        if tag == "a":
            self._href = a.get("href", "")
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if tag == "a":
            text = "".join(self._link_text).strip()
            self.links.append((self._href, text))
            if self._in_crumb:
                self.breadcrumb.append((text, self._href))
        if tag == "nav":
            self._in_crumb = False
        if tag == "script":
            self._ld_script = False
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ld_script:
            self.ld.append(data)
            return
        top = self._stack[-1] if self._stack else ""
        if top == "title":
            self.title += data
            return
        if "head" in self._stack:
            return
        if top == "h1":
            self.h1.append(data)
        self._link_text.append(data)
        self.text.append(data)

    @property
    def visible(self) -> str:
        return " ".join("".join(self.text).split())


def _parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def _run(
    root: Path, fixture: str, fetched_at: dt.datetime, today: dt.date
) -> dict[str, Any]:
    return cli.run(
        fixture_path=str(FIXTURES / fixture),
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
    root = tmp_path_factory.mktemp("species")
    _run(
        root,
        "schedule-fresh-2026-09-13.html",
        dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 13),
    )
    snap = _run(
        root,
        "schedule-midweek-2026-09-17.html",
        dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        dt.date(2026, 9, 18),
    )
    return root / "site", snap


def _next_start(snap: dict[str, Any]) -> str:
    return (
        dt.date.fromisoformat(snap["source_week"]["start"]) + dt.timedelta(days=7)
    ).isoformat()


def _expected_slugs(snap: dict[str, Any], species: str, start: str) -> set[str]:
    return {
        w["slug"]
        for w in snap["waters"]
        for p in w["plants"]
        if p["status"] == "listed"
        and p["species"] == species
        and p["week"]["start"] == start
    }


def _week_slugs(out: Path, species_slug: str) -> tuple[set[str], set[str]]:
    """(this week, next week) water slugs on a built species page, taken from
    the text of each section by walking the parsed document in order."""

    class Walker(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.section = ""
            self.found: dict[str, set[str]] = {"this-week": set(), "next-week": set()}

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            a = {k: v or "" for k, v in attrs}
            if tag == "h2":
                self.section = a.get("id", "other")
            if tag == "a" and self.section in self.found:
                href = a.get("href", "")
                if href.startswith("../../water/"):
                    self.found[self.section].add(href.split("/")[3])

    w = Walker()
    w.feed((out / "species" / species_slug / "index.html").read_text(encoding="utf-8"))
    return w.found["this-week"], w.found["next-week"]


def test_a_page_exists_for_each_species_in_the_data_and_no_other(built):
    out, snap = built
    in_data = {
        p["species"]
        for w in snap["waters"]
        for p in w["plants"]
        if p["status"] == "listed"
    }
    # The fixtures must carry both species the real data has.
    assert in_data == {"Trout", "Catfish"}
    on_disk = {d.name for d in (out / "species").iterdir()}
    assert on_disk == {site.species_slug(s) for s in in_data} == {"trout", "catfish"}


def test_this_week_and_next_week_match_the_snapshot(built):
    out, snap = built
    for species in ("Trout", "Catfish"):
        this_week, next_week = _week_slugs(out, site.species_slug(species))
        assert this_week == _expected_slugs(snap, species, snap["source_week"]["start"])
        assert next_week == _expected_slugs(snap, species, _next_start(snap))
    # Not vacuous: the trout page has both a this-week and a next-week water.
    trout_this, trout_next = _week_slugs(out, "trout")
    assert trout_this
    assert trout_next


def test_negative_control_an_injected_plant_moves_the_page(built, tmp_path: Path):
    """Add a catfish plant for next week to a snapshot, assert the sabotage
    applied, and see it on the catfish page and not on the unmodified build."""
    out, snap = built
    nxt = _next_start(snap)
    mutated = copy.deepcopy(snap)
    water = next(
        w
        for w in mutated["waters"]
        if w["slug"] not in _expected_slugs(snap, "Catfish", nxt)
    )
    start = dt.date.fromisoformat(nxt)
    water["plants"].append(
        {
            "week": {
                "start": nxt,
                "end": (start + dt.timedelta(days=6)).isoformat(),
                "label": f"week of {nxt}",
            },
            "species": "Catfish",
            "status": "listed",
            "first_observed_at": "2026-09-18T03:10:18Z",
            "last_observed_at": "2026-09-18T03:10:18Z",
        }
    )
    # The sabotage applied: the mutated snapshot now expects the water.
    assert water["slug"] in _expected_slugs(mutated, "Catfish", nxt)
    assert water["slug"] not in _expected_slugs(snap, "Catfish", nxt)
    # A plant two weeks out is neither this week nor next week.
    far = (start + dt.timedelta(days=7)).isoformat()
    other = next(w for w in mutated["waters"] if w["slug"] != water["slug"])
    other["plants"].append(
        {
            **copy.deepcopy(water["plants"][-1]),
            "week": {"start": far, "end": far, "label": f"week of {far}"},
        }
    )
    assert far in {p["week"]["start"] for p in other["plants"]}
    site.build_site(mutated, tmp_path / "site", base_url=BASE_URL)
    this_week, next_week = _week_slugs(tmp_path / "site", "catfish")
    assert water["slug"] in next_week
    assert other["slug"] not in this_week | next_week
    _, original_next = _week_slugs(out, "catfish")
    assert water["slug"] not in original_next


def test_a_species_with_no_listed_plant_gets_no_page_and_a_new_one_gets_one(
    built, tmp_path: Path
):
    _, snap = built
    mutated = copy.deepcopy(snap)
    for w in mutated["waters"]:
        for p in w["plants"]:
            if p["species"] == "Catfish":
                p["status"] = "removed"
    mutated["waters"][0]["plants"].append(
        {**copy.deepcopy(mutated["waters"][0]["plants"][0]), "species": "Walleye"}
    )
    assert not any(
        p["species"] == "Catfish" and p["status"] == "listed"
        for w in mutated["waters"]
        for p in w["plants"]
    )
    site.build_site(mutated, tmp_path / "site", base_url=BASE_URL)
    on_disk = {d.name for d in (tmp_path / "site" / "species").iterdir()}
    assert on_disk == {"trout", "walleye"}


@pytest.mark.parametrize("slug", ["trout", "catfish"])
def test_seo_surface_title_description_canonical_breadcrumb_ld(built, slug):
    out, _ = built
    page = _parse(out / "species" / slug / "index.html")
    url = f"{BASE_URL}/species/{slug}/"
    assert page.canonicals == [url]
    assert page.title == (
        f"California {slug} stocking schedule: this week and next | Trout Truck"
    )
    desc = page.meta["description"]
    assert slug in desc
    assert len(desc) <= 165
    assert page.h1 == [f"California {slug} stocking schedule: this week and next"]
    # Breadcrumb: visible trail mirrors the structured data.
    ld = json.loads("".join(page.ld))
    types = {n["@type"]: n for n in ld["@graph"]}
    assert set(types) == {"CollectionPage", "BreadcrumbList"}
    ld_trail = [
        (i["name"], i["item"]) for i in types["BreadcrumbList"]["itemListElement"]
    ]
    assert ld_trail == [
        ("Trout Truck", f"{BASE_URL}/"),
        (f"{slug.title()} schedule", url),
    ]
    assert [n for n, _ in page.breadcrumb] == [n for n, _ in ld_trail]
    assert types["CollectionPage"]["url"] == url
    # No Event or date-pinning keys, as everywhere else.
    assert "Event" not in json.dumps(ld)
    for key in ("startDate", "endDate", "eventStatus", "geo"):
        assert key not in json.dumps(ld)


def test_titles_and_descriptions_are_unique_across_the_site(built):
    out, _ = built
    pages = [_parse(p) for p in sorted(out.rglob("index.html"))]
    titles = [p.title for p in pages]
    species_titles = [t for t in titles if "stocking schedule: this week and next" in t]
    assert len(species_titles) == 2
    assert all(titles.count(t) == 1 for t in species_titles)
    descs = [p.meta.get("description", "") for p in pages]
    for p in pages:
        if "this week and next" in p.title:
            assert descs.count(p.meta["description"]) == 1


def test_sitemap_lists_both_species_pages_with_a_lastmod(built):
    out, snap = built
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    for slug in ("trout", "catfish"):
        entry = f"<url><loc>{BASE_URL}/species/{slug}/</loc><lastmod>"
        assert entry in sitemap
        lastmod = sitemap.split(entry)[1].split("</lastmod>")[0]
        assert len(lastmod) == 10
        assert lastmod <= snap["generated_at"][:10]


def test_every_link_on_a_species_page_resolves_to_a_built_page(built):
    out, _ = built
    for slug in ("trout", "catfish"):
        page = _parse(out / "species" / slug / "index.html")
        internal = [h for h, _ in page.links if h and not h.startswith(("http", "#"))]
        assert internal
        for href in internal:
            target = (out / "species" / slug / href).resolve()
            assert (target / "index.html").exists(), href
        assert any(h.startswith("../../water/") for h in internal)
        assert any(h.startswith("../../county/") for h in internal)


def test_home_and_county_index_link_to_the_species_pages(built):
    out, _ = built
    for rel, prefix in (("", "./species/"), ("county", "../species/")):
        page = _parse(out / rel / "index.html")
        hrefs = {h for h, _ in page.links}
        assert f"{prefix}trout/" in hrefs
        assert f"{prefix}catfish/" in hrefs


@pytest.mark.parametrize("slug", ["trout", "catfish"])
def test_copy_rules_scheduled_never_stocked_and_no_superlatives(built, slug):
    out, _ = built
    page = _parse(out / "species" / slug / "index.html")
    text = page.visible.lower() + " " + page.meta["description"].lower()
    for banned in (
        "planted on",
        "stocked on",
        " stocked ",
        "only",
        "first",
        "unique",
        "colour",
        "favourite",
    ):
        assert banned not in text, banned
    assert "scheduled" in text
    assert "not confirmed" in text


def test_negative_control_the_copy_check_can_fail():
    """The banned-word scan is real: a page that says "stocked" trips it."""
    probe = _Page()
    probe.feed("<html><body><main><p>Waters stocked this week</p></main></body></html>")
    assert " stocked " in probe.visible.lower() + " "


def test_an_empty_week_is_said_plainly_and_never_as_no_fish(built, tmp_path: Path):
    """A species with nothing this week or next says so in the wording the
    rest of the site uses;
    the sentence must be the repository's own disclaimer."""
    _, snap = built
    mutated = copy.deepcopy(snap)
    for w in mutated["waters"]:
        for p in w["plants"]:
            if p["species"] == "Catfish":
                p["status"] = "removed"
    mutated["waters"][0]["plants"].append(
        {**copy.deepcopy(mutated["waters"][0]["plants"][0]), "species": "Walleye"}
    )
    # The sabotage applied: the new species has no plant this week or next.
    assert _expected_slugs(mutated, "Walleye", snap["source_week"]["start"]) == set()
    assert _expected_slugs(mutated, "Walleye", _next_start(snap)) == set()
    site.build_site(mutated, tmp_path / "site", base_url=BASE_URL)
    text = _parse(tmp_path / "site" / "species" / "walleye" / "index.html").visible
    assert "not that there are no fish" in text
    assert "no fish" not in text.replace("not that there are no fish", "")
