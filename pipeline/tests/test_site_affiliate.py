"""Amazon Associates gear links (DECISIONS 0029).

The links are on California water pages and nowhere else: not in the other
pages, not in structured data, feeds or the snapshot, and not in the iOS or
Android sources. Wherever one appears it carries rel="sponsored nofollow
noopener" and the page carries Amazon's disclosure wording. The tag comes
from one constant. ``_problems`` is the checker; the negative controls
sabotage a built site and assert the checker notices, after asserting the
sabotage really changed the file.
"""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
REPO = Path(__file__).resolve().parents[2]
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

TAG = "trouttruck-20"
DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."
ENDORSEMENT = (
    "The links are Trout Truck's, not CDFW's, and CDFW does not endorse them or Amazon."
)
REQUIRED_REL = {"sponsored", "nofollow", "noopener"}
# Copy rules: no superlatives, no first/only claims, no money or ratings.
FORBIDDEN_COPY = re.compile(
    r"\b(only|first|best|top|cheap\w*|deal\w*|rated)\b|[$%★]", re.I
)


def _build(root: Path, **extra: Any) -> Path:
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        **extra,
    )
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("affiliate"))


@pytest.fixture(scope="module")
def built_live(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The same site with the App Store switch on and analytics configured."""
    return _build(
        tmp_path_factory.mktemp("affiliate-live"),
        app_store_live=True,
        ga4_measurement_id="G-TEST123456",
    )


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[str, str]] = []  # (href, rel)
        self.other_urls: list[str] = []  # any non-anchor attribute naming Amazon
        self.text: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "a":
            self.anchors.append((a.get("href", ""), a.get("rel", "")))
        else:
            for v in a.values():
                if "amazon" in v.lower():
                    self.other_urls.append(v)
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.text.append(data)

    def prose(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text))


def _parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def _is_amazon(href: str) -> bool:
    host = urlsplit(href).hostname or ""
    return host == "amazon.com" or host.endswith(".amazon.com")


def _is_water_page(out: Path, path: Path) -> bool:
    rel = path.relative_to(out).parts
    return len(rel) == 3 and rel[0] == "water" and rel[2] == "index.html"


def _link_problems(name: str, href: str, rel: str) -> list[str]:
    found: list[str] = []
    q = parse_qs(urlsplit(href).query)
    if q.get("tag") != [site.AMAZON_ASSOCIATE_TAG]:
        found.append(f"{name}: wrong or missing tag in {href}")
    if not set(rel.split()) >= REQUIRED_REL:
        found.append(f"{name}: rel {rel!r} on {href}")
    if urlsplit(href).path != "/s":
        found.append(f"{name}: not a search link: {href}")
    return found


def _page_problems(out: Path, path: Path) -> list[str]:
    name = path.relative_to(out).as_posix()
    page = _parse(path)
    links = [(h, r) for h, r in page.anchors if _is_amazon(h)]
    found: list[str] = []
    if page.other_urls:
        found.append(f"{name}: Amazon URL outside an anchor: {page.other_urls}")
    if links and not _is_water_page(out, path):
        found.append(f"{name}: affiliate link outside a water page")
    for href, rel in links:
        found += _link_problems(name, href, rel)
    prose = page.prose()
    if links and site.AMAZON_ASSOCIATE_DISCLOSURE not in prose:
        found.append(f"{name}: no Amazon disclosure")
    if links and ENDORSEMENT not in prose:
        found.append(f"{name}: no agency non-endorsement sentence")
    if links and "costs you nothing extra" not in prose:
        found.append(f"{name}: no plain affiliate sentence")
    for block in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        path.read_text(encoding="utf-8"),
        re.S,
    ):
        if "amazon" in block.lower():
            found.append(f"{name}: structured data names Amazon")
    return found


def _problems(out: Path) -> list[str]:
    """Every way the built site breaks the affiliate rules."""
    pages = sorted(out.rglob("*.html"))
    assert pages
    found: list[str] = []
    for path in pages:
        found += _page_problems(out, path)
    # Nothing else carries Amazon: feeds, data, sitemap.
    data_suffixes = {".json", ".ics", ".xml", ".txt", ".css", ".js"}
    for path in sorted(out.rglob("*")):
        if not (path.is_file() and path.suffix in data_suffixes):
            continue
        if "amazon" in path.read_text(encoding="utf-8").lower():
            found.append(f"{path.relative_to(out)}: names Amazon")
    return found


def test_the_constants_are_the_ones_the_owner_chose() -> None:
    assert site.AMAZON_ASSOCIATE_TAG == TAG
    assert site.AMAZON_ASSOCIATE_DISCLOSURE == DISCLOSURE
    assert set(site.AFFILIATE_LINK_REL.split()) == REQUIRED_REL


def test_a_clean_build_has_no_problems(built: Path) -> None:
    assert _problems(built) == []


def test_every_water_page_has_the_gear_block_and_its_disclosure(built: Path) -> None:
    waters = [p for p in built.rglob("index.html") if _is_water_page(built, p)]
    assert len(waters) > 30
    for path in waters:
        page = _parse(path)
        links = [h for h, _ in page.anchors if _is_amazon(h)]
        assert len(links) == len(site.GEAR_CATEGORIES), path
        assert "Gear for this water" in page.prose()
        assert DISCLOSURE in page.prose()
        assert ENDORSEMENT in page.prose()


def test_the_links_are_amazon_searches_with_the_tag(built: Path) -> None:
    html = (built / "water").glob("*/index.html")
    first = _parse(next(iter(sorted(html))))
    links = [h for h, _ in first.anchors if _is_amazon(h)]
    for href in links:
        parts = urlsplit(href)
        assert parts.scheme == "https"
        assert parts.hostname == "www.amazon.com"
        assert parts.path == "/s"
        q = parse_qs(parts.query)
        assert set(q) == {"k", "tag"}
        assert q["tag"] == [TAG]
        assert q["k"][0]


def test_the_tag_comes_from_one_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(site, "AMAZON_ASSOCIATE_TAG", "changed-21")
    out = _build(tmp_path)
    text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.html"))
    assert "tag=changed-21" in text
    assert TAG not in text
    assert _problems(out) == []


def test_no_affiliate_link_outside_water_pages_with_everything_switched_on(
    built_live: Path,
) -> None:
    assert _problems(built_live) == []
    privacy = _parse(built_live / "privacy" / "index.html")
    assert not [h for h, _ in privacy.anchors if _is_amazon(h)]
    assert DISCLOSURE in privacy.prose()
    # The click event is for the App Store only; nothing was added for Amazon.
    for path in built_live.rglob("*.html"):
        assert (
            "amazon"
            not in "".join(
                re.findall(
                    r"<script>(.*?)</script>", path.read_text(encoding="utf-8"), re.S
                )
            ).lower()
        )


def test_the_privacy_page_states_the_relationship_in_both_builds(
    built: Path, built_live: Path
) -> None:
    for out in (built, built_live):
        prose = _parse(out / "privacy" / "index.html").prose()
        assert "Gear links" in prose
        assert "affiliate links" in prose
        assert "nothing extra" in prose
        assert "never in the iOS app" in prose
        assert DISCLOSURE in prose
        assert ENDORSEMENT in prose


def test_the_gear_and_privacy_copy_makes_no_superlative_or_price_claim(
    built: Path,
) -> None:
    water = next(iter(sorted((built / "water").glob("*/index.html"))))
    html = water.read_text(encoding="utf-8")
    block = re.search(r'<section class="gear".*?</section>', html, re.S)
    assert block
    copy = re.sub(r"<[^>]+>", " ", block.group(0))
    privacy = (built / "privacy" / "index.html").read_text(encoding="utf-8")
    sec = re.search(r'<h2 id="affiliate">.*?<h2 id="app">', privacy, re.S)
    assert sec
    for text in (copy, re.sub(r"<[^>]+>", " ", sec.group(0))):
        assert not FORBIDDEN_COPY.search(text), FORBIDDEN_COPY.search(text)
    for label, terms in site.GEAR_CATEGORIES:
        assert not FORBIDDEN_COPY.search(label + " " + terms)


def test_no_app_source_names_amazon_or_the_tag() -> None:
    checked = 0
    for top in ("ios", "android"):
        for path in (REPO / top).rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".swift",
                ".kt",
                ".java",
                ".xml",
                ".plist",
                ".json",
                ".strings",
                ".xcstrings",
                ".gradle",
                ".kts",
                ".md",
            }:
                continue
            checked += 1
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            assert "amazon.com" not in text, path
            assert "trouttruck-20" not in text, path
    assert checked > 20


# ---- negative controls: each sabotage must apply, and must be noticed ----


def _water_file(out: Path) -> Path:
    return next(iter(sorted((out / "water").glob("*/index.html"))))


def _sabotage(path: Path, old: str, new: str) -> None:
    before = path.read_text(encoding="utf-8")
    assert old in before, "the sabotage target is not in the page"
    after = before.replace(old, new)
    assert after != before
    path.write_text(after, encoding="utf-8")


def test_control_a_missing_rel_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    assert _problems(out) == []
    _sabotage(_water_file(out), f'rel="{site.AFFILIATE_LINK_REL}"', 'rel="noopener"')
    assert any("rel" in p for p in _problems(out))


def test_control_a_missing_disclosure_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(_water_file(out), DISCLOSURE, "")
    assert any("no Amazon disclosure" in p for p in _problems(out))


def test_control_a_wrong_tag_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(_water_file(out), f"tag={TAG}", "tag=someone-else-20")
    assert any("wrong or missing tag" in p for p in _problems(out))


def test_control_an_affiliate_link_on_the_home_page_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    link = f'<a href="https://www.amazon.com/s?k=x&amp;tag={TAG}" rel="{site.AFFILIATE_LINK_REL}">x</a>'
    _sabotage(out / "index.html", "</main>", link + "</main>")
    assert any("outside a water page" in p for p in _problems(out))


def test_control_amazon_in_the_snapshot_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(out / "snapshot" / "v1.json", '"waters"', '"amazon": 1, "waters"')
    assert any("snapshot/v1.json" in p for p in _problems(out))


def test_control_an_amazon_image_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(
        _water_file(out),
        "</main>",
        '<img src="https://m.media-amazon.com/x.jpg"></main>',
    )
    assert any("outside an anchor" in p for p in _problems(out))


def test_the_about_page_does_not_claim_no_ads_without_the_affiliate_note(
    built_live: Path,
) -> None:
    about = _parse(built_live / "about" / "index.html").prose()
    assert "no ads on this site" in about
    assert "affiliate links to Amazon" in about


def test_the_other_states_pages_carry_no_affiliate_link(tmp_path: Path) -> None:
    """Report-state water pages are not California water pages: no links."""
    root = tmp_path / "states-build"
    root.mkdir()
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
    out = root / "site"
    assert list((out / "states").rglob("index.html"))
    assert _problems(out) == []


def test_the_endorsement_sentence_names_the_pages_agency() -> None:
    assert site.gear_endorsement("CDFW") == ENDORSEMENT
    assert "TWRA does not endorse them or Amazon." in site.gear_endorsement("TWRA")


def test_control_a_missing_non_endorsement_sentence_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    assert _problems(out) == []
    _sabotage(_water_file(out), "does not endorse them or Amazon.", "")
    assert any("non-endorsement" in p for p in _problems(out))


def test_control_a_wrong_agency_in_the_sentence_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(
        _water_file(out), "not CDFW&#39;s, and CDFW does", "not FWS&#39;s, and FWS does"
    )
    assert any("non-endorsement" in p for p in _problems(out))
