"""Atom feeds: conforming documents, stable ids, data-derived timestamps,
scheduled-not-confirmed wording, autodiscovery, and no sitemap entries.

Built from the pinned CDFW fixtures, never from daily-rewritten data. The
Atom check is an offline RFC 4287 subset (xml.etree plus assertions on the
required elements); no dependency is added for it.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

import pytest

from cfpa import cli, feeds

FIXTURES = Path(__file__).parent / "fixtures"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
NS = {"a": feeds.ATOM_NS}
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _build(root: Path, fixture: Path, fetched: dt.datetime, today: dt.date) -> Path:
    out = root / "site"
    cli.run(
        fixture_path=str(fixture),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=fetched,
        run_today=today,
    )
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("feeds")
    return _build(
        root,
        MIDWEEK,
        dt.datetime(2026, 9, 17, 23, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 17),
    )


def _from_text(text: str) -> ET.Element:
    parser = ET.XMLParser()
    parser.feed(text)
    return parser.close()


def _parse_xml(path: Path) -> ET.Element:
    return _from_text(path.read_text(encoding="utf-8"))


def assert_valid_atom(path: Path, site_root: Path | None = None) -> ET.Element:
    """RFC 4287 section 4.1 required elements, the ones this site emits."""
    root = _parse_xml(path)
    assert root.tag == f"{{{feeds.ATOM_NS}}}feed"
    for tag in ("id", "title", "updated"):
        assert root.find(f"a:{tag}", NS) is not None, f"{path.name}: feed {tag}"
    assert RFC3339.match(root.findtext("a:updated", namespaces=NS) or "")
    # author at feed level covers every entry (4.1.1)
    assert root.find("a:author/a:name", NS) is not None
    selfs = [
        link
        for link in root.findall("a:link", NS)
        if link.get("rel") == "self" and link.get("type") == feeds.FEED_MEDIA_TYPE
    ]
    assert len(selfs) == 1
    if site_root is not None:
        assert (
            selfs[0].get("href")
            == f"{BASE_URL}/{path.relative_to(site_root).as_posix()}"
        )
        assert root.findtext("a:id", namespaces=NS) == selfs[0].get("href")
    ids = [root.findtext("a:id", namespaces=NS)]
    for entry in root.findall("a:entry", NS):
        for tag in ("id", "title", "updated"):
            assert entry.find(f"a:{tag}", NS) is not None, f"{path.name}: entry {tag}"
        assert RFC3339.match(entry.findtext("a:updated", namespaces=NS) or "")
        assert (
            entry.find("a:summary", NS) is not None
            or entry.find("a:content", NS) is not None
        )
        assert entry.find("a:link[@rel='alternate']", NS) is not None
        ids.append(entry.findtext("a:id", namespaces=NS))
    assert len(ids) == len(set(ids)), "duplicate ids"
    return root


def _all_feeds(out: Path) -> list[Path]:
    return sorted((out / "feeds").rglob("*.atom"))


def test_every_feed_is_valid_atom(site: Path) -> None:
    found = _all_feeds(site)
    assert len(found) > 3
    for path in found:
        assert_valid_atom(path, site)


def test_feed_set_matches_pages(site: Path) -> None:
    regions = {p.name for p in (site / "region").iterdir() if p.is_dir()}
    counties = {p.name for p in (site / "county").iterdir() if p.is_dir()}
    assert {p.stem for p in (site / "feeds" / "region").glob("*.atom")} == regions
    assert {p.stem for p in (site / "feeds" / "county").glob("*.atom")} == counties
    assert (site / "feeds" / "this-week.atom").exists()


def test_statewide_entries_match_the_home_page(site: Path) -> None:
    root = assert_valid_atom(site / "feeds" / "this-week.atom")
    entries = root.findall("a:entry", NS)
    assert entries
    # Each entry is one water with a page, and the region feeds partition it.
    regional = 0
    for path in (site / "feeds" / "region").glob("*.atom"):
        regional += len(_parse_xml(path).findall("a:entry", NS))
    assert regional == len(entries)
    for e in entries:
        link = e.find("a:link", NS)
        assert link is not None
        href = link.get("href")
        assert href is not None and href.startswith(f"{BASE_URL}/water/")
        slug = href.removeprefix(f"{BASE_URL}/water/").rstrip("/")
        assert (site / "water" / slug / "index.html").exists()


def test_wording_is_scheduled_not_confirmed(site: Path) -> None:
    text = (site / "feeds" / "this-week.atom").read_text(encoding="utf-8")
    assert "Scheduled, not confirmed" in text
    assert "California Department of Fish and Wildlife" in text
    assert "<rights>" in text
    low = text.lower()
    for banned in ("stocked on", "planted on", "confirmed plant", " best ", " top "):
        assert banned not in low


def test_rebuild_next_day_leaves_feeds_unchanged(tmp_path: Path) -> None:
    """Timestamps come from the data, not the build clock: a rebuild a day
    later, with the same schedule, writes byte-identical feeds."""
    run = tmp_path / "run"
    first = _build(
        run,
        MIDWEEK,
        dt.datetime(2026, 9, 17, 23, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 17),
    )
    before = {p.relative_to(first): p.read_bytes() for p in _all_feeds(first)}
    assert before
    second = _build(
        run,
        MIDWEEK,
        dt.datetime(2026, 9, 18, 6, 30, tzinfo=dt.UTC),
        dt.date(2026, 9, 18),
    )
    after = {p.relative_to(second): p.read_bytes() for p in _all_feeds(second)}
    assert after == before
    root = _parse_xml(second / "feeds" / "this-week.atom")
    entries = root.findall("a:entry", NS)
    assert entries
    newest = max(e.findtext("a:updated", namespaces=NS) or "" for e in entries)
    assert root.findtext("a:updated", namespaces=NS) == newest
    # The data's own time: before the second build ever ran.
    assert newest < "2026-09-18T06:30:00Z"


def test_new_week_means_new_entry_ids(tmp_path: Path) -> None:
    """The id is permalink plus week: the same water next week is a new
    entry, never an edit of this week's."""
    out = _build(
        tmp_path,
        MIDWEEK,
        dt.datetime(2026, 9, 17, 23, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 17),
    )
    root = _parse_xml(out / "feeds" / "this-week.atom")
    for e in root.findall("a:entry", NS):
        entry_id = e.findtext("a:id", namespaces=NS) or ""
        assert entry_id.endswith("/#2026-09-13"), entry_id


def test_empty_week_is_a_valid_feed_dated_by_the_week() -> None:
    xml = feeds.build_feed(
        entries=[],
        base_url=BASE_URL,
        path="feeds/this-week.atom",
        title="t",
        subtitle="s",
        page_url=f"{BASE_URL}/",
        week_label="week of 2026-09-13",
        week_start="2026-09-13",
        site_name="Trout Truck",
        attribution_text="Data: CDFW.",
    )
    root = _from_text(xml)
    assert root.findtext("a:updated", namespaces=NS) == "2026-09-13T00:00:00Z"
    assert root.findall("a:entry", NS) == []


def test_special_characters_are_escaped() -> None:
    entry = feeds.FeedEntry(
        water_id="cdfw-1",
        slug="a-b",
        name='A & B <Lake> "x"',
        counties=["Inyo"],
        species="trout",
        updated="2026-09-13T01:02:03Z",
    )
    xml = feeds.build_feed(
        entries=[entry],
        base_url=BASE_URL,
        path="feeds/this-week.atom",
        title="t",
        subtitle="s",
        page_url=f"{BASE_URL}/",
        week_label="week of 2026-09-13",
        week_start="2026-09-13",
        site_name="Trout Truck",
        attribution_text="Data: CDFW.",
    )
    parsed = _from_text(xml)
    assert 'A & B <Lake> "x"' in (
        parsed.findtext("a:entry/a:title", namespaces=NS) or ""
    )


class _Head(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.alternates: list[dict[str, str | None]] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag == "link" and d.get("rel") == "alternate":
            self.alternates.append(d)
        if tag == "a" and (d.get("href") or "").endswith(".atom"):
            self.links.append(d["href"] or "")


def _parse(path: Path) -> _Head:
    p = _Head()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def test_autodiscovery_and_subscribe_link_resolve(site: Path) -> None:
    pages = [site / "index.html"]
    pages += sorted((site / "region").glob("*/index.html"))
    pages += sorted((site / "county").glob("*/index.html"))
    for page in pages:
        head = _parse(page)
        assert len(head.alternates) == 1, page
        href = head.alternates[0]["href"] or ""
        assert head.alternates[0]["type"] == "application/atom+xml"
        assert (page.parent / href).resolve().exists(), (page, href)
        # Visible mention: a plain same-site link to the same file.
        assert head.links == [href], page
    # Pages with no matching feed advertise none.
    for page in (site / "about" / "index.html", site / "privacy" / "index.html"):
        assert _parse(page).alternates == []


def test_feeds_are_not_in_the_sitemap(site: Path) -> None:
    sitemap = (site / "sitemap.xml").read_text(encoding="utf-8")
    assert ".atom" not in sitemap
    assert "/feeds/" not in sitemap
    assert _all_feeds(site)


def test_privacy_page_still_true_with_feeds(site: Path) -> None:
    privacy = (site / "privacy" / "index.html").read_text(encoding="utf-8")
    assert "Atom feeds (.atom)" in privacy
    assert "does not know" in privacy
    # The feed links carry no analytics event attributes.
    for page in (site / "index.html", *(site / "county").glob("*/index.html")):
        assert "data-ga-event" not in "".join(
            line
            for line in page.read_text(encoding="utf-8").splitlines()
            if ".atom" in line
        )


def test_negative_control_validator_catches_a_missing_updated(tmp_path: Path) -> None:
    good = feeds.build_feed(
        entries=[],
        base_url=BASE_URL,
        path="feeds/x.atom",
        title="t",
        subtitle="s",
        page_url=f"{BASE_URL}/",
        week_label="week of 2026-09-13",
        week_start="2026-09-13",
        site_name="Trout Truck",
        attribution_text="a",
    )
    bad = good.replace("<updated>2026-09-13T00:00:00Z</updated>", "")
    assert bad != good, "sabotage did not apply"
    path = tmp_path / "x.atom"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(AssertionError):
        assert_valid_atom(path)
    path.write_text(good, encoding="utf-8")
    assert_valid_atom(path)
