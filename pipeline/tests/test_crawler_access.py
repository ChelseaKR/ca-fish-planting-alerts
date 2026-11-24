"""What a search or AI-answer crawler may do with every page the site offers.

ChatGPT sent 59 of the site's 122 engaged visits in the 28 days to 2026-11-17,
and Bing, Yahoo and DuckDuckGo sent 13. Until now the only crawler any test
named was Bingbot, and only at the site root (``indexnow.check_robots``).
These checks run on the real fixture build:

- robots.txt lets each crawler below fetch every page in the sitemap;
- no sitemap page tells a crawler not to keep or quote it;
- every page Bing may index is in the sitemap, because the sitemap is the
  only list IndexNow picks from (``indexnow.cmd_select``).

The last one fails the day a page is held out of Google alone (a ``googlebot``
tag and no sitemap entry) with nothing else telling Bing about it. It names
the pages and the remedy.

robots.txt is read the way RFC 9309 says: the group that names the crawler,
else ``*``; within it the longest matching rule wins, and Allow wins a tie.
``urllib.robotparser`` takes the first match instead, which is not what Bing,
Google or OpenAI do.
"""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from cfpa import cli
from cfpa import indexnow as ix

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE = "https://trouttruck.example"

# Bing's crawler; OpenAI's search crawler, its fetcher for a user's question
# and its training crawler; Perplexity's and Anthropic's crawlers. Names as
# each company publishes them.
CRAWLERS = (
    "bingbot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "GPTBot",
    "PerplexityBot",
    "ClaudeBot",
)
# A robots meta value that stops a crawler keeping or quoting the page. Bing
# documents nocache and noarchive as limits on its chat answers.
QUOTE_LIMITS = ("noarchive", "nocache", "nosnippet", "max-snippet:0")
# Meta names a search or AI crawler reads. ``googlebot`` is not one of them:
# a tag for Google alone leaves the page open to everyone else.
META_NAMES = {"robots", *(c.lower() for c in CRAWLERS)}


def _groups(robots: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    in_agents = False
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not in_agents:
                groups.append(([], []))
            groups[-1][0].append(value.lower())
            in_agents = True
        elif key in ("allow", "disallow"):
            in_agents = False
            if groups and value:
                groups[-1][1].append((key, value))
        else:
            in_agents = False
    return groups


def _rules(robots: str, crawler: str) -> list[tuple[str, str]]:
    groups = _groups(robots)
    name = crawler.lower()
    named = [g for g in groups if any(a != "*" and a in name for a in g[0])]
    chosen = named or [g for g in groups if "*" in g[0]]
    return [rule for g in chosen for rule in g[1]]


def may_fetch(robots: str, crawler: str, path: str) -> bool:
    best_kind, best_len = "allow", -1
    for kind, pattern in _rules(robots, crawler):
        regex = re.escape(pattern).replace(r"\*", ".*")
        if regex.endswith(r"\$"):
            regex = regex[:-2] + "$"
        if re.match(regex, path) is None:
            continue
        if len(pattern) > best_len or (len(pattern) == best_len and kind == "allow"):
            best_kind, best_len = kind, len(pattern)
    return best_kind == "allow"


def blocked(robots: str, urls: list[str]) -> list[str]:
    return [
        f"{crawler} may not fetch {url}"
        for crawler in CRAWLERS
        for url in urls
        if not may_fetch(robots, crawler, urlsplit(url).path or "/")
    ]


class _Metas(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            a = dict(attrs)
            self.found.append(((a.get("name") or "").lower(), a.get("content") or ""))


def crawler_metas(html: str) -> list[tuple[str, str]]:
    """(name, content) of each meta tag a search or AI crawler reads."""
    parser = _Metas()
    parser.feed(html)
    return [(n, c.lower().replace(" ", "")) for n, c in parser.found if n in META_NAMES]


def quote_limits(html: str) -> list[str]:
    return [
        f"{name}: {limit}"
        for name, content in crawler_metas(html)
        for limit in QUOTE_LIMITS
        if limit in content.split(",")
    ]


def bing_may_index(html: str) -> bool:
    return not any("noindex" in content for _, content in crawler_metas(html))


def kept_from_bing(site: Path, base_url: str) -> list[str]:
    """Pages Bing may index that IndexNow can never announce."""
    listed = set(ix.parse_sitemap((site / "sitemap.xml").read_text(encoding="utf-8")))
    out = []
    for page in sorted(site.rglob("*.html")):
        rel = page.relative_to(site).as_posix().removesuffix("index.html")
        url = f"{base_url}/{rel}"
        if url not in listed and bing_may_index(page.read_text(encoding="utf-8")):
            out.append(url)
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("crawlers")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE,
        legacy_site_out=None,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return root / "site"


@pytest.fixture(scope="module")
def sitemap_urls(site: Path) -> list[str]:
    urls = sorted(ix.parse_sitemap((site / "sitemap.xml").read_text(encoding="utf-8")))
    assert len(urls) > 20, "the build's sitemap is nearly empty, so this proves nothing"
    return urls


def test_each_crawler_may_fetch_every_sitemap_page(site, sitemap_urls):
    robots = (site / "robots.txt").read_text(encoding="utf-8")
    assert blocked(robots, sitemap_urls) == []


@pytest.mark.parametrize(
    ("robots", "shut_out", "still_in"),
    [
        # A group that names one crawler replaces "*" for it.
        (
            "User-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n",
            {"OAI-SearchBot"},
            {"bingbot", "ChatGPT-User", "GPTBot", "PerplexityBot", "ClaudeBot"},
        ),
        # The longest rule wins, so "Allow: /" does not save a blocked folder.
        (
            "User-agent: *\nAllow: /\nDisallow: /water/\n",
            set(CRAWLERS),
            set(),
        ),
        # Blocking the training crawlers leaves the search and answer ones in.
        (
            "User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n\n"
            "User-agent: *\nAllow: /\n",
            {"GPTBot", "ClaudeBot"},
            {"bingbot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot"},
        ),
        # A wildcard rule with an end anchor.
        (
            "User-agent: bingbot\nDisallow: /wat*/*/$\n",
            {"bingbot"},
            {"OAI-SearchBot", "ChatGPT-User", "GPTBot", "PerplexityBot", "ClaudeBot"},
        ),
    ],
)
def test_a_robots_file_that_shuts_a_crawler_out_is_reported(
    sitemap_urls, robots, shut_out, still_in
):
    problems = blocked(robots, sitemap_urls)
    named = {p.split(" ", 1)[0] for p in problems}
    assert named == shut_out
    assert named.isdisjoint(still_in)


def test_the_longest_rule_wins_and_allow_wins_a_tie():
    robots = "User-agent: *\nDisallow: /water/\nAllow: /water/open/\nAllow: /tn/\nDisallow: /tn/\n"
    assert not may_fetch(robots, "bingbot", "/water/shadow-cliff-lake/")
    assert may_fetch(robots, "bingbot", "/water/open/lake/")
    assert may_fetch(robots, "bingbot", "/tn/")
    assert may_fetch(robots, "bingbot", "/county/alameda/")
    assert may_fetch("", "bingbot", "/anything/")


def test_no_sitemap_page_limits_keeping_or_quoting_it(site, sitemap_urls):
    for url in sitemap_urls:
        page = ix.page_file(site, BASE, url)
        assert page is not None
        assert quote_limits(page.read_text(encoding="utf-8")) == [], url


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ('<meta name="robots" content="noarchive">', ["robots: noarchive"]),
        ('<meta name="bingbot" content="index, NOCACHE">', ["bingbot: nocache"]),
        ('<meta content="nosnippet" name="robots">', ["robots: nosnippet"]),
        ('<meta name="robots" content="max-snippet:0">', ["robots: max-snippet:0"]),
        ('<meta name="robots" content="max-snippet:160">', []),
        ('<meta name="googlebot" content="noarchive">', []),
        ('<meta name="description" content="nocache">', []),
    ],
)
def test_a_quote_limit_is_reported_only_where_a_crawler_reads_it(meta, expected):
    assert quote_limits(f"<html><head>{meta}</head><body></body></html>") == expected


def test_every_page_bing_may_index_is_in_the_sitemap_indexnow_picks_from(site):
    assert kept_from_bing(site, BASE) == [], (
        "These pages carry no robots noindex, so Bing and the assistants that "
        "read it may index them, but they are not in sitemap.xml, and "
        "sitemap.xml is the only list indexnow.cmd_select picks from. Nothing "
        "would tell Bing when they change. Give IndexNow a list that includes "
        "them (and Bing a sitemap that does) before taking them out."
    )


def test_a_page_held_from_google_alone_and_left_out_of_the_sitemap_is_reported(
    site, tmp_path
):
    listed = ix.parse_sitemap((site / "sitemap.xml").read_text(encoding="utf-8"))
    held = tmp_path / "site"
    for sub in ("held", "thin"):
        (held / sub).mkdir(parents=True)
    (held / "sitemap.xml").write_text(
        (site / "sitemap.xml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for url in listed:
        page = ix.page_file(held, BASE, url)
        assert page is not None
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("<html><head></head></html>", encoding="utf-8")
    (held / "held" / "index.html").write_text(
        '<html><head><meta name="googlebot" content="noindex,follow"></head></html>',
        encoding="utf-8",
    )
    (held / "thin" / "index.html").write_text(
        '<html><head><meta name="robots" content="noindex,follow"></head></html>',
        encoding="utf-8",
    )
    assert kept_from_bing(held, BASE) == [f"{BASE}/held/"]
