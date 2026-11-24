"""California water pages carry their data date where a machine reads it.

ChatGPT sent Trout Truck 56 engaged visits in the 28 days to 2026-11-18, and
37 of them landed on California water pages, the one water-page family whose
structured data had no ``dateModified``. Now:

- the page's WebPage node has ``dateModified``, and it is the page's sitemap
  ``lastmod`` (the day its data last changed, ``site._water_lastmod``), the
  value Tennessee's water pages already carry;
- the dates printed under "Last on the schedule" and after "as of" are in
  ``<time datetime>``, with the same words a reader saw before.

Tennessee's pages are not touched: they keep their own ``dateModified`` and
gain no ``<time>`` element. Built from the pinned fixtures (California plus
Tennessee).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
V1_SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
LOC = re.compile(r"<url><loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?</url>")
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
TIME = re.compile(r'<time datetime="([^"]+)">([^<]*)</time>')
# A water in the fixture's sitemap (indexed, not thin).
PINNED = "legg-lakes"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("ca-water-dates")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN",),
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


def _sitemap(site_dir: Path) -> dict[str, str | None]:
    text = re.sub(r"\s+", "", (site_dir / "sitemap.xml").read_text("utf-8"))
    return dict(LOC.findall(text))


def _web_page(html: str) -> dict[str, Any]:
    for block in LD.findall(html):
        doc = json.loads(block)
        for node in doc.get("@graph", [doc]):
            if node.get("@type") == "WebPage":
                return dict(node)
    raise AssertionError("no WebPage node")


def _ca_water_pages(site_dir: Path) -> dict[str, str]:
    return {
        p.parent.name: p.read_text("utf-8")
        for p in sorted((site_dir / "water").glob("*/index.html"))
    }


def _status_block(html: str) -> str:
    m = re.search(r'<section class="water-status".*?</section>', html, re.S)
    assert m, "no status block"
    return m.group(0)


# ---- dateModified ------------------------------------------------------------


def test_the_pinned_page_carries_its_sitemap_lastmod(built: Path) -> None:
    url = f"{BASE}/water/{PINNED}/"
    lastmod = _sitemap(built)[url]
    assert lastmod == "2026-09-13"
    node = _web_page((built / "water" / PINNED / "index.html").read_text("utf-8"))
    assert node["url"] == url
    assert node["dateModified"] == lastmod


def test_every_california_water_page_is_dated_and_agrees_with_the_sitemap(
    built: Path,
) -> None:
    """Indexed pages: the sitemap's lastmod. Thin pages (noindex, out of the
    sitemap; DECISIONS 0041) carry the same computed date and say noindex."""
    sitemap = _sitemap(built)
    pages = _ca_water_pages(built)
    assert len(pages) > 10
    in_sitemap = 0
    for slug, html in pages.items():
        node = _web_page(html)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", node["dateModified"]), slug
        url = f"{BASE}/water/{slug}/"
        if url in sitemap:
            in_sitemap += 1
            assert node["dateModified"] == sitemap[url], slug
        else:
            assert '<meta name="robots" content="noindex' in html, slug
    assert in_sitemap >= 2


def test_the_date_is_the_function_the_sitemap_uses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Negative control: move ``_water_lastmod`` and both the sitemap and
    the page move with it, together, because they read one value."""
    monkeypatch.setattr(site, "_water_lastmod", lambda *a, **k: "2001-02-03")
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=tmp_path / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=tmp_path / "states",
        states_fixtures=FIXTURES / "states",
    )
    url = f"{BASE}/water/{PINNED}/"
    html = (tmp_path / "site" / "water" / PINNED / "index.html").read_text("utf-8")
    assert _sitemap(tmp_path / "site")[url] == "2001-02-03"
    assert _web_page(html)["dateModified"] == "2001-02-03"


# ---- <time datetime> ---------------------------------------------------------


def test_the_pinned_status_block_wraps_its_dates_and_keeps_its_words(
    built: Path,
) -> None:
    block = _status_block((built / "water" / PINNED / "index.html").read_text("utf-8"))
    assert (
        "<dd>The week of "
        '<time datetime="2025-10-12">2025-10-12</time>, which began 336 days '
        "ago as of the schedule check on "
        '<time datetime="2026-09-13">2026-09-13</time>.</dd>'
    ) in block
    as_of = (
        "<dd>Not on CDFW&#39;s schedule yet, as of "
        '<time datetime="2026-09-13T12:00Z">2026-09-13 12:00 UTC</time>.</dd>'
    )
    assert block.count(as_of) == 2
    # The words a reader sees are the words the page had before.
    plain = TIME.sub(r"\2", block)
    assert (
        "<dd>The week of 2025-10-12, which began 336 days ago as of the "
        "schedule check on 2026-09-13.</dd>"
    ) in plain
    assert (
        plain.count(
            "<dd>Not on CDFW&#39;s schedule yet, as of 2026-09-13 12:00 UTC.</dd>"
        )
        == 2
    )


def test_every_time_element_says_what_its_text_says(built: Path) -> None:
    """On every California water page: a date's datetime is the printed date,
    and the "as of" minute's datetime is the printed minute in UTC. Every
    <time> is in the status block, and nowhere else on the page."""
    seen = 0
    for slug, html in _ca_water_pages(built).items():
        block = _status_block(html)
        assert len(TIME.findall(html)) == len(TIME.findall(block)), slug
        for value, text in TIME.findall(block):
            seen += 1
            if "T" in value:
                printed = dt.datetime.strptime(text, "%Y-%m-%d %H:%M UTC")
                assert value == printed.strftime("%Y-%m-%dT%H:%MZ"), slug
            else:
                assert value == text, slug
                dt.date.fromisoformat(value)
        assert "Last on the schedule" in block
    assert seen > 0


def test_time_dates_escapes_what_it_does_not_wrap() -> None:
    out = str(site._time_dates("A <b> & 2026-01-04, not 2026-1-4."))
    assert out == (
        'A &lt;b&gt; &amp; <time datetime="2026-01-04">2026-01-04</time>, not 2026-1-4.'
    )
    assert str(site._time_dates("No date here.")) == "No date here."


def test_time_tag_without_a_machine_value_is_just_the_words() -> None:
    assert str(site._time_tag("", "2026-09-13 12:00 UTC")) == "2026-09-13 12:00 UTC"
    assert str(site._time_tag("2026-09-13T12:00Z", "a <b>")) == (
        '<time datetime="2026-09-13T12:00Z">a &lt;b&gt;</time>'
    )
    assert site._fmt_dt_attr("2026-11-19T13:23:45Z") == "2026-11-19T13:23Z"
    assert site._fmt_dt("2026-11-19T13:23:45Z") == "2026-11-19 13:23 UTC"


# ---- Tennessee is not touched --------------------------------------------------


def test_tennessee_pages_gain_no_time_element_and_keep_their_date(
    built: Path,
) -> None:
    sitemap = _sitemap(built)
    pages = sorted((built / "tn").rglob("index.html"))
    assert len(pages) > 50
    for page in pages:
        html = page.read_text("utf-8")
        assert "<time" not in html, page
        assert "lakenotice" not in html.lower(), page
    water = [p for p in pages if p.parent.parent.name == "water"]
    assert water
    for page in water:
        node = _web_page(page.read_text("utf-8"))
        url = node["url"]
        if url in sitemap:
            assert node["dateModified"] == sitemap[url]
