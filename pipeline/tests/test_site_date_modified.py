"""A page's JSON-LD dateModified is its sitemap lastmod, and nothing else.

ChatGPT and other answer engines send Trout Truck most of its engaged visits
(GA4, 90 days to 2026-11-09). Their crawlers read the sitemap and the page's
structured data; when the two carry a date it must be the same date: the day
the page's data last changed, never the build date. A page with no data date
(about, gear, privacy) carries no dateModified at all.

California water pages are not wired yet: their render function is being
reworked in the water-convert branch (DECISIONS 0054), and they get the same
one-line change after it merges. The check below covers every page that has
both a sitemap lastmod and a dateModified, so that change is tested here too.

Built from the pinned fixtures (California plus Tennessee).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli
from cfpa.site import _ld_page

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
V1_SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
BUILD_DAY = dt.date(2026, 9, 13)
PAGE_TYPES = {"WebPage", "CollectionPage"}
LOC = re.compile(r"<url><loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?</url>")


class _LdScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._in = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self._in = True
            self.blocks.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in = False

    def handle_data(self, data: str) -> None:
        if self._in:
            self.blocks[-1] += data


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("date-modified")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=BUILD_DAY,
        states_dir=root / "states",
        states_fetch=("TN",),
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


def _sitemap(site: Path) -> dict[str, str | None]:
    text = re.sub(r"\s+", "", (site / "sitemap.xml").read_text("utf-8"))
    return {loc: mod for loc, mod in LOC.findall(text)}


def _page_node(html: Path) -> dict[str, Any] | None:
    p = _LdScripts()
    p.feed(html.read_text("utf-8"))
    for block in p.blocks:
        doc = json.loads(block)
        for node in doc.get("@graph", [doc]):
            if node.get("@type") in PAGE_TYPES:
                return node
    return None


def _nodes(site: Path) -> dict[str, dict[str, Any]]:
    """page URL -> its WebPage/CollectionPage node, for every built page."""
    out: dict[str, dict[str, Any]] = {}
    for html in site.rglob("index.html"):
        node = _page_node(html)
        if node is not None:
            out[node["url"]] = node
    return out


def _mismatches(
    nodes: dict[str, dict[str, Any]],
    sitemap: dict[str, str | None],
    noindex: set[str],
) -> list[str]:
    """Every dateModified that is not its page's sitemap lastmod. A thin page
    (noindex,follow, out of the sitemap; DECISIONS 0041) keeps its data date:
    an assistant can still follow a link to it, and ChatGPT has."""
    bad = []
    for url, node in nodes.items():
        if "dateModified" not in node:
            continue
        if url not in sitemap:
            if url not in noindex:
                bad.append(f"{url}: dated, but neither in the sitemap nor noindex")
            continue
        if sitemap[url] != node["dateModified"]:
            bad.append(f"{url}: {node['dateModified']} vs sitemap {sitemap[url]}")
    return bad


def _noindex(site: Path) -> set[str]:
    out = set()
    for html in site.rglob("index.html"):
        text = html.read_text("utf-8")
        if re.search(r'<meta name="robots" content="noindex', text):
            node = _page_node(html)
            if node is not None:
                out.add(node["url"])
    return out


def test_every_date_modified_is_the_pages_sitemap_lastmod(built: Path) -> None:
    sitemap = _sitemap(built)
    nodes = _nodes(built)
    dated = [u for u, n in nodes.items() if "dateModified" in n]
    assert dated, "no page carries dateModified"
    assert _mismatches(nodes, sitemap, _noindex(built)) == []


def test_negative_control_a_wrong_date_is_caught(built: Path) -> None:
    sitemap = _sitemap(built)
    nodes = _nodes(built)
    noindex = _noindex(built)
    url = next(u for u, n in nodes.items() if "dateModified" in n and u in sitemap)
    sabotaged = {**nodes, url: {**nodes[url], "dateModified": "2099-01-01"}}
    assert _mismatches(sabotaged, sitemap, noindex) == [
        f"{url}: 2099-01-01 vs sitemap {sitemap[url]}"
    ]


def test_negative_control_a_dated_page_outside_the_sitemap_must_be_noindex(
    built: Path,
) -> None:
    sitemap = _sitemap(built)
    nodes = _nodes(built)
    noindex = _noindex(built)
    thin = next(u for u, n in nodes.items() if "dateModified" in n and u not in sitemap)
    assert thin in noindex
    assert _mismatches(nodes, sitemap, noindex - {thin}) == [
        f"{thin}: dated, but neither in the sitemap nor noindex"
    ]


@pytest.mark.parametrize(
    "prefix",
    ["/county/", "/region/", "/species/", "/tn/water/"],
)
def test_each_wired_family_carries_it_on_every_sitemap_page(
    built: Path, prefix: str
) -> None:
    sitemap = _sitemap(built)
    nodes = _nodes(built)
    urls = [u for u in sitemap if u.startswith(f"{BASE}{prefix}")]
    assert urls, f"the fixture build has no {prefix} page in the sitemap"
    missing = [u for u in urls if "dateModified" not in nodes[u]]
    assert missing == []


def test_the_state_hub_carries_it(built: Path) -> None:
    sitemap = _sitemap(built)
    node = _nodes(built)[f"{BASE}/tn/"]
    assert node["dateModified"] == sitemap[f"{BASE}/tn/"]


def test_a_page_without_a_data_date_says_nothing() -> None:
    node = _ld_page(
        "WebPage",
        page_url=f"{BASE}/about/",
        name="About",
        base_url=BASE,
        about={"@type": "State", "name": "California"},
    )
    assert "dateModified" not in node
    for empty in ("", None):
        node = _ld_page(
            "WebPage",
            page_url=f"{BASE}/about/",
            name="About",
            base_url=BASE,
            about={"@type": "State", "name": "California"},
            date_modified=empty,
        )
        assert "dateModified" not in node


def test_pages_with_no_sitemap_lastmod_carry_no_date_modified(built: Path) -> None:
    sitemap = _sitemap(built)
    nodes = _nodes(built)
    undated = [u for u, m in sitemap.items() if m is None and u in nodes]
    assert [u for u in undated if "dateModified" in nodes[u]] == []
