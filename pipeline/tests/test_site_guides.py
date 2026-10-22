"""The /guide/ pages: plain explanations built from the snapshot and from
CDFW pages named in the copy.

HTML is read with html.parser, never with a regular expression over tags.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from cfpa import cli, guides, site

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
SLUGS = [g.slug for g in guides.GUIDES]
# The words the site's copy rules forbid (brief 2026-10-21 and the species
# page rules), checked as whole words.
BANNED_WORDS = {"only", "first", "best", "top", "unique", "stocked", "colour"}
BANNED_PHRASES = ("planted on", "stocked on")
CDFW_HOSTS = {"nrm.dfg.ca.gov", "wildlife.ca.gov", "www.wildlife.ca.gov"}


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.links: list[str] = []
        self.ld: list[str] = []
        self.text: list[str] = []
        self.crumbs: list[tuple[str, str]] = []
        self._stack: list[str] = []
        self._ld = False
        self._crumb = False
        self._href = ""
        self._label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag not in {"meta", "link", "br", "img", "hr", "input"}:
            self._stack.append(tag)
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonicals.append(a.get("href", ""))
        if tag == "script" and a.get("type") == "application/ld+json":
            self._ld = True
        if tag == "nav" and a.get("aria-label") == "Breadcrumb":
            self._crumb = True
        if tag == "a":
            self._href = a.get("href", "")
            self._label = []
            self.links.append(self._href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._crumb:
            self.crumbs.append(("".join(self._label).strip(), self._href))
        if tag == "nav":
            self._crumb = False
        if tag == "script":
            self._ld = False
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ld:
            self.ld.append(data)
            return
        top = self._stack[-1] if self._stack else ""
        if top == "title":
            self.title += data
            return
        if "head" in self._stack:
            return
        self._label.append(data)
        self.text.append(data)

    @property
    def visible(self) -> str:
        return " ".join("".join(self.text).split())


def _parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("guides")
    snap = cli.run(
        fixture_path=str(FIXTURES / "schedule-midweek-2026-09-17.html"),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 18),
    )
    return root / "site", snap


def _guide_pages(out: Path) -> dict[str, _Page]:
    return {s: _parse(out / "guide" / s / "index.html") for s in SLUGS}


def test_an_index_and_every_guide_are_built(built):
    out, _ = built
    assert len(SLUGS) == 3 and len(set(SLUGS)) == 3
    assert (out / "guide" / "index.html").exists()
    for s in SLUGS:
        assert (out / "guide" / s / "index.html").exists()
    on_disk = {d.name for d in (out / "guide").iterdir() if d.is_dir()}
    assert on_disk == set(SLUGS)


def test_titles_and_descriptions_are_distinct_and_fit_a_result(built):
    out, _ = built
    pages = {"": _parse(out / "guide" / "index.html"), **_guide_pages(out)}
    titles = [p.title for p in pages.values()]
    descs = [p.meta["description"] for p in pages.values()]
    assert len(set(titles)) == len(titles) == 4
    assert len(set(descs)) == len(descs)
    other = {
        _parse(out / "index.html").title,
        _parse(out / "about" / "index.html").title,
    }
    assert not (set(titles) & other)
    for p in pages.values():
        assert 0 < len(p.title) <= 62, p.title
        assert 60 <= len(p.meta["description"]) <= 160, p.meta["description"]
        assert p.title.endswith(site.SITE_NAME) or site.SITE_NAME in p.title


def test_each_page_has_one_canonical_that_is_its_own_url(built):
    out, _ = built
    expected = {"": f"{BASE_URL}/guide/"} | {s: f"{BASE_URL}/guide/{s}/" for s in SLUGS}
    for s, url in expected.items():
        rel = Path("guide") / s / "index.html"
        assert _parse(out / rel).canonicals == [url]


def test_breadcrumb_structured_data_mirrors_the_visible_trail(built):
    out, _ = built
    for s in SLUGS:
        page = _guide_pages(out)[s]
        data = json.loads("".join(page.ld))
        nodes = {n["@type"]: n for n in data["@graph"]}
        assert set(nodes) == {"WebPage", "BreadcrumbList"}
        crumbs = nodes["BreadcrumbList"]["itemListElement"]
        assert [c["position"] for c in crumbs] == [1, 2, 3]
        assert [c["name"] for c in crumbs] == [n for n, _ in page.crumbs]
        assert crumbs[-1]["item"] == f"{BASE_URL}/guide/{s}/"
        assert crumbs[1]["item"] == f"{BASE_URL}/guide/"
        assert "Event" not in json.dumps(data)


def test_the_index_is_linked_from_the_home_page_and_every_footer(built):
    out, _ = built
    home = _parse(out / "index.html")
    assert "./guide/" in home.links
    for s in SLUGS[:3]:
        assert f"./guide/{s}/" in home.links
    for rel, prefix in (
        ("county/index.html", "../"),
        ("about/index.html", "../"),
        ("species/trout/index.html", "../../"),
        ("guide/index.html", "../"),
    ):
        assert f"{prefix}guide/" in _parse(out / rel).links, rel
    # The 404 page uses root-relative links.
    assert any(h.endswith("/guide/") for h in _parse(out / "404.html").links)


def test_every_guide_is_in_the_sitemap_once(built):
    out, _ = built
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    for u in [f"{BASE_URL}/guide/"] + [f"{BASE_URL}/guide/{s}/" for s in SLUGS]:
        assert locs.count(u) == 1, u


def test_internal_links_resolve_and_reach_county_region_and_species_pages(built):
    out, _ = built
    for s, page in _guide_pages(out).items():
        base = out / "guide" / s
        internal = [
            h
            for h in page.links
            if h and not urlsplit(h).scheme and not h.startswith("#")
        ]
        for h in internal:
            target = (base / urlsplit(h).path).resolve()
            assert (target / "index.html").exists() or target.is_file(), (s, h)
    reads = _guide_pages(out)["how-to-read-the-schedule"].links
    assert any(h.startswith("../../county/") for h in reads)
    assert any(h.startswith("../../region/") for h in reads)
    assert any(h.startswith("../../species/") for h in reads)


def test_external_links_go_to_cdfw_pages_and_nowhere_else(built):
    out, _ = built
    for s, page in _guide_pages(out).items():
        for h in page.links:
            parts = urlsplit(h)
            if parts.scheme:
                assert parts.scheme == "https" and parts.hostname in CDFW_HOSTS, (s, h)
    # The three pages that quote CDFW name the day they were read.
    for s in SLUGS:
        assert guides.CDFW_READ_ON in _guide_pages(out)[s].visible, s


def test_no_product_links_no_affiliate_wording(built):
    out, _ = built
    for s, page in _guide_pages(out).items():
        text = page.visible.lower()
        assert not ({"amazon", "affiliate", "sponsored"} & _words(text)), s
        assert not any("amazon" in h or "tag=" in h for h in page.links), s


def _words(text: str) -> set[str]:
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return set(cleaned.split())


def test_copy_rules_scheduled_never_a_day_and_no_superlatives(built):
    out, _ = built
    for s, page in _guide_pages(out).items():
        text = page.visible + " " + page.meta["description"] + " " + page.title
        assert not (_words(text) & BANNED_WORDS), (s, _words(text) & BANNED_WORDS)
        for phrase in BANNED_PHRASES:
            assert phrase not in text.lower(), (s, phrase)
        # American English.
        assert not ({"colour", "favourite", "licence"} & _words(text)), s
    assert "scheduled" in _guide_pages(out)["scheduled-vs-confirmed"].visible.lower()
    assert "not confirmed" in _guide_pages(out)["how-to-read-the-schedule"].visible


def test_negative_control_the_word_scan_can_fail():
    probe = "The best only way to see stocked fish"
    assert _words(probe) & BANNED_WORDS == {"best", "only", "stocked"}
    assert not (_words("A plan is scheduled, not confirmed") & BANNED_WORDS)


def test_counts_in_the_copy_match_the_snapshot(built):
    out, snap = built
    entries = [p for w in snap["waters"] for p in w["plants"]]
    removed = sum(1 for p in entries if p["status"] != "listed")
    # The fixture must exercise both a removed week and a listed one.
    assert entries and removed < len(entries)
    text = _guide_pages(out)["scheduled-vs-confirmed"].visible
    assert f"{len(entries)} plant entries have been on CDFW's schedule" in text
    verb = "was" if removed == 1 else "were"
    assert f"and {removed} {verb} later removed" in text
    plant = _guide_pages(out)["what-is-a-trout-plant"].visible
    assert f"{len(snap['waters'])} waters are in this site's record" in plant
    read = _guide_pages(out)["how-to-read-the-schedule"].visible
    since = min(p["week"]["start"] for p in entries)
    assert f"the week of {since}" in read


def test_negative_control_the_count_check_notices_a_changed_number(built, tmp_path):
    _, snap = built
    mutated = json.loads(json.dumps(snap))
    plant = mutated["waters"][0]["plants"][0]
    plant["status"] = "removed"
    # The sabotage applied: exactly one entry is removed now.
    removed = sum(
        1 for w in mutated["waters"] for p in w["plants"] if p["status"] != "listed"
    )
    assert removed == 1
    site.build_site(mutated, tmp_path / "site", base_url=BASE_URL)
    page = _parse(tmp_path / "site" / "guide" / "scheduled-vs-confirmed" / "index.html")
    assert "and 1 was later removed" in page.visible


class _Headings(HTMLParser):
    """Collects h2 ids and the visible text of the section after each."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.sections: dict[str, list[str]] = {}
        self.links: dict[str, list[str]] = {}
        self._cur = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "h2":
            self._cur = a.get("id", "")
            self.ids.append(self._cur)
            self.sections[self._cur] = []
            self.links[self._cur] = []
        if tag == "a" and self._cur:
            self.links[self._cur].append(a.get("href", ""))

    def handle_data(self, data: str) -> None:
        if self._cur:
            self.sections[self._cur].append(data)


def _names_section(html: str) -> tuple[str, list[str], list[str]]:
    h = _Headings()
    h.feed(html)
    return " ".join("".join(h.sections["names"]).split()), h.links["names"], h.ids


def test_names_section_explains_the_aliases_with_an_anchor(built):
    out, _ = built
    html = (out / "guide" / "what-is-a-trout-plant" / "index.html").read_text("utf-8")
    text, links, ids = _names_section(html)
    assert ids.count("names") == 1
    assert ids.index("names") < ids.index("criteria")  # existing anchors kept
    for needle in (
        "CDFW",
        "California Department of Fish and Wildlife",
        "planting",
        "stocking",
        "Hatchery trout",
        "scheduled",
    ):
        assert needle in text, needle
    assert "https://wildlife.ca.gov/" in links
    # One sentence links back to the weekly schedule (the site root).
    assert "../../" in links
    assert not (_words(text) & BANNED_WORDS)
    # The former-name claim has no CDFW source read, so it must stay out.
    assert "DFG" not in text and "formerly" not in text.lower()


def test_names_section_leaves_title_h1_and_description_alone(built):
    out, _ = built
    page = _guide_pages(out)["what-is-a-trout-plant"]
    g = next(x for x in guides.GUIDES if x.slug == "what-is-a-trout-plant")
    assert page.title.strip() == g.title.format(site=page.title.split("|")[-1].strip())
    assert page.meta["description"] == g.description
    assert g.h1 == "What is a trout plant?"


def test_negative_control_names_check_notices_a_missing_section(built, tmp_path):
    out, _ = built
    html = (out / "guide" / "what-is-a-trout-plant" / "index.html").read_text("utf-8")
    sabotaged = html.replace('id="names"', 'id="renamed"')
    assert sabotaged != html  # the sabotage applied
    with pytest.raises(KeyError):
        _names_section(sabotaged)
    dirty = html.replace("Hatchery trout", "Only the best hatchery trout")
    assert dirty != html
    assert _words(_names_section(dirty)[0]) & BANNED_WORDS
