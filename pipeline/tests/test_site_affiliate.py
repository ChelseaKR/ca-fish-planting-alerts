"""Amazon Associates gear links (DECISIONS 0029, 0030, 0039, 0040).

The links are on California water and county pages, the home page, the
/county/ index, the /gear/ guide, and
another state's water pages when that state's terms permit commercial reuse,
and nowhere else: not in the other pages, not in structured data, feeds or
the snapshot, and not in the iOS or Android sources. Wherever one appears it
carries rel="sponsored nofollow noopener", and the page carries Amazon's
disclosure wording and a non-endorsement sentence naming the agency whose
data the page shows. The tag comes
from one constant. ``_problems`` is the checker; the negative controls
sabotage a built site and assert the checker notices, after asserting the
sabotage really changed the file.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from cfpa import cli, site, site_states, thin
from cfpa.states import SOURCES

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


def _is_gear_page(out: Path, path: Path) -> bool:
    """The "What to bring" guide (DECISIONS 0030)."""
    return path.relative_to(out).parts == ("gear", "index.html")


def _is_county_page(out: Path, path: Path) -> bool:
    """A California county page (DECISIONS 0039), not the /county/ index."""
    rel = path.relative_to(out).parts
    return len(rel) == 3 and rel[0] == "county" and rel[2] == "index.html"


def _is_home_or_county_index(out: Path, path: Path) -> bool:
    """The home page or the /county/ index (DECISIONS 0040)."""
    return path.relative_to(out).parts in (("index.html",), ("county", "index.html"))


def _state_agency(out: Path, path: Path) -> str | None:
    """The agency short name for another state's water page, else None."""
    rel = path.relative_to(out).parts
    if len(rel) == 4 and rel[1] == "water" and rel[3] == "index.html":
        source = SOURCES.get(rel[0].upper())
        if source is not None and source.code != "CA":
            return source.agency_short_name
    return None


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
    agency = _state_agency(out, path)
    allowed = (
        _is_water_page(out, path)
        or _is_gear_page(out, path)
        or _is_county_page(out, path)
        or _is_home_or_county_index(out, path)
        or agency is not None
    )
    if links and not allowed:
        found.append(f"{name}: affiliate link outside a water page")
    for href, rel in links:
        found += _link_problems(name, href, rel)
    prose = page.prose()
    if links and site.AMAZON_ASSOCIATE_DISCLOSURE not in prose:
        found.append(f"{name}: no Amazon disclosure")
    want = ENDORSEMENT if agency is None else site.gear_endorsement(agency)
    if links and want not in prose:
        found.append(f"{name}: no agency non-endorsement sentence")
    if links and agency is not None and "CDFW" in prose:
        found.append(f"{name}: a non-California page names CDFW")
    if links and "costs you nothing extra" not in prose:
        found.append(f"{name}: no plain affiliate sentence")
    for kind, block in _script_blocks(path.read_text(encoding="utf-8")):
        if kind == "application/ld+json" and "amazon" in block.lower():
            found.append(f"{name}: structured data names Amazon")
    return found


class _Scripts(HTMLParser):
    """Collects each <script> element's type and text, as a browser would split them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[tuple[str | None, str]] = []
        self._type: str | None = None
        self._open = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self._open = True
            self._type = dict(attrs).get("type")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._open:
            self.blocks.append((self._type, "".join(self._text)))
            self._open = False

    def handle_data(self, data: str) -> None:
        if self._open:
            self._text.append(data)


def _script_blocks(html: str) -> list[tuple[str | None, str]]:
    parser = _Scripts()
    parser.feed(html)
    parser.close()
    return parser.blocks


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


def _thin_paths(out: Path) -> set[Path]:
    """The index.html of every thin water page (DECISIONS 0041), from the
    build's own snapshot: these carry no gear block."""
    v2 = json.loads((out / "snapshot" / "v2.json").read_text(encoding="utf-8"))
    found = set()
    for w in v2["waters"]:
        path = w.get("site_path") or f"/water/{w['slug']}/"
        if thin.is_thin(w["plants"], path):
            found.add(out / path.strip("/") / "index.html")
    return found


def test_every_water_page_has_the_gear_block_and_its_disclosure(built: Path) -> None:
    """Every water page but a thin one (DECISIONS 0041), which has none."""
    thin_pages = _thin_paths(built)
    waters = [
        p
        for p in built.rglob("index.html")
        if _is_water_page(built, p) and p not in thin_pages
    ]
    # One fixture fetch gives most California waters a single week.
    assert waters and len(thin_pages) > 30
    for path in thin_pages:
        assert not [h for h, _ in _parse(path).anchors if _is_amazon(h)], path
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
        scripts = _script_blocks(path.read_text(encoding="utf-8"))
        assert "amazon" not in "".join(text for _, text in scripts).lower()


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
    html = _water_file(built).read_text(encoding="utf-8")
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


def _with_block(pages: list[Path]) -> Path:
    """The first page that carries the gear block: a thin water page has
    none (DECISIONS 0041), so a sabotage aimed at one would not apply."""
    return next(p for p in pages if 'class="gear"' in p.read_text(encoding="utf-8"))


def _water_file(out: Path) -> Path:
    return _with_block(sorted((out / "water").glob("*/index.html")))


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


def test_control_an_affiliate_link_on_the_about_page_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    link = f'<a href="https://www.amazon.com/s?k=x&amp;tag={TAG}" rel="{site.AFFILIATE_LINK_REL}">x</a>'
    _sabotage(out / "about" / "index.html", "</main>", link + "</main>")
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


def _states_build(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
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
    return root / "site"


@pytest.fixture(scope="module")
def built_states(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _states_build(tmp_path_factory.mktemp("affiliate-states") / "b")


def _gear_section(path: Path) -> str:
    m = re.search(
        r'<section class="gear".*?</section>', path.read_text(encoding="utf-8"), re.S
    )
    assert m, path
    return m.group(0)


def test_the_states_build_follows_every_rule(built_states: Path) -> None:
    assert list((built_states / "states").rglob("index.html"))
    assert _problems(built_states) == []


def test_other_states_water_pages_carry_the_block_naming_their_agency(
    built_states: Path,
) -> None:
    """DECISIONS 0039: TN, MA and MI permit commercial reuse and are trout
    only, so each water page carries the block with its own agency's name."""
    thin_pages = _thin_paths(built_states)
    for code in ("tn", "ma", "mi"):
        agency = SOURCES[code.upper()].agency_short_name
        pages = [
            p
            for p in sorted((built_states / code / "water").glob("*/index.html"))
            if p not in thin_pages
        ]
        assert pages, code
        for path in pages:
            page = _parse(path)
            links = [h for h, _ in page.anchors if _is_amazon(h)]
            assert len(links) == len(site.GEAR_CATEGORIES), path
            assert site.gear_endorsement(agency) in page.prose(), path
            block = _gear_section(path)
            assert 'data-ga-placement="state_water"' in block
            # The /gear/ guide is about California waters: not offered here.
            assert "gear/" not in block.replace("#gear-heading", "")


def test_state_hubs_and_the_states_index_carry_no_affiliate_link(
    built_states: Path,
) -> None:
    hubs = [built_states / "states" / "index.html"] + [
        built_states / code / "index.html" for code in ("tn", "ma", "mi")
    ]
    for path in hubs:
        assert path.exists(), path
        assert not [h for h, _ in _parse(path).anchors if _is_amazon(h)], path


def test_every_county_page_has_the_gear_block(built: Path) -> None:
    pages = [p for p in built.rglob("index.html") if _is_county_page(built, p)]
    assert len(pages) > 5
    for path in pages:
        page = _parse(path)
        links = [h for h, _ in page.anchors if _is_amazon(h)]
        assert len(links) == len(site.GEAR_CATEGORIES), path
        assert DISCLOSURE in page.prose()
        assert ENDORSEMENT in page.prose()
        block = _gear_section(path)
        assert 'data-ga-placement="county"' in block
        assert not FORBIDDEN_COPY.search(re.sub(r"<[^>]+>", " ", block))


def _gear_labels(path: Path) -> list[str]:
    block = _gear_section(path)
    return re.findall(r'data-ga-type="amazon_search">([^<]+)</a>', block)


def test_the_home_page_and_county_index_carry_the_block(built: Path) -> None:
    """DECISIONS 0040. The fixture's week starts in September, so the home
    page has the fixed four and no cold-weather search."""
    fixed = [label for label, _ in site.GEAR_CATEGORIES]
    for rel, placement in (("index.html", "home"), ("county/index.html", "counties")):
        path = built / rel
        page = _parse(path)
        assert len([h for h, _ in page.anchors if _is_amazon(h)]) == len(fixed), rel
        assert DISCLOSURE in page.prose() and ENDORSEMENT in page.prose()
        block = _gear_section(path)
        assert f'data-ga-placement="{placement}"' in block
        assert not FORBIDDEN_COPY.search(re.sub(r"<[^>]+>", " ", block))
        assert _gear_labels(path) == fixed


def test_cold_month_gear_is_added_in_winter_weeks_only() -> None:
    fixed = [g["label"] for g in site.gear_links()]
    cold = [g["label"] for g in site.gear_links(cold_months=True)]
    assert cold == fixed + [label for label, _ in site.COLD_MONTH_GEAR]
    for label, terms in site.COLD_MONTH_GEAR:
        assert not FORBIDDEN_COPY.search(label + " " + terms)
    for week, winter in (
        ("2026-11-01", True),
        ("2026-12-27", True),
        ("2027-01-03", True),
        ("2027-02-28", True),
        ("2027-03-07", False),
        ("2026-10-25", False),
        ("2026-09-13", False),
    ):
        assert site.is_winter_week(week) is winter, week
    assert site.is_winter_week("") is False


def test_a_winter_week_adds_the_cold_month_search_to_the_home_page_only(
    tmp_path: Path,
) -> None:
    """A build whose current CDFW week starts in December: the home page gets
    the extra search, and water and county pages keep the fixed four."""
    v1 = _build(tmp_path / "src")
    snap = json.loads((v1 / "snapshot" / "v1.json").read_text("utf-8"))
    snap["source_week"] = {
        **snap["source_week"],
        "start": "2026-12-06",
        "end": "2026-12-12",
        "label": "week of 2026-12-06",
    }
    out = tmp_path / "winter"
    site.build_site(snap, out, base_url=BASE_URL)
    cold = [label for label, _ in site.COLD_MONTH_GEAR]
    assert _gear_labels(out / "index.html")[-len(cold) :] == cold
    for path in (out / "county" / "index.html", _water_file(out)):
        assert not set(cold) & set(_gear_labels(path)), path
    assert _problems(out) == []


def _src(state: str) -> dict[str, Any]:
    return {
        "license": {"sources": [{"commercial_reuse": state}]},
    }


def test_gear_is_allowed_only_for_permitted_trout_data() -> None:
    assert site_states.gear_allowed(_src("permitted"), "trout")
    assert site_states.gear_allowed(_src("permitted"), "Rainbow Trout")
    assert not site_states.gear_allowed(_src("unknown"), "trout")
    assert not site_states.gear_allowed(_src("not-permitted"), "trout")
    assert not site_states.gear_allowed(_src("permitted"), "fish")
    assert not site_states.gear_allowed({"license": {"sources": []}}, "trout")
    assert not site_states.gear_allowed({}, "trout")
    mixed = {
        "license": {
            "sources": [
                {"commercial_reuse": "permitted"},
                {"commercial_reuse": "unknown"},
            ]
        }
    }
    assert not site_states.gear_allowed(mixed, "trout")


def test_control_a_state_whose_terms_are_unknown_gets_no_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The license gate decides a real build, and the sabotage applies."""
    import dataclasses

    tn = SOURCES["TN"]
    unknown = tuple(
        dataclasses.replace(lic, commercial_reuse="unknown")
        for lic in tn.license_sources
    )
    monkeypatch.setitem(SOURCES, "TN", dataclasses.replace(tn, license_sources=unknown))
    out = _states_build(tmp_path / "b")
    v2 = (out / "snapshot" / "v2.json").read_text(encoding="utf-8")
    assert '"commercial_reuse": "unknown"' in v2 or '"commercial_reuse":"unknown"' in v2
    thin_pages = _thin_paths(out)
    tn_pages = sorted((out / "tn" / "water").glob("*/index.html"))
    # Pages that would carry the block but for the terms (not thin ones).
    assert set(tn_pages) - thin_pages
    for path in tn_pages:
        assert not [h for h, _ in _parse(path).anchors if _is_amazon(h)], path
    ma_pages = [
        p
        for p in sorted((out / "ma" / "water").glob("*/index.html"))
        if p not in thin_pages
    ]
    assert ma_pages
    assert [h for h, _ in _parse(ma_pages[0]).anchors if _is_amazon(h)]


def test_control_cdfw_named_on_a_state_page_is_noticed(tmp_path: Path) -> None:
    out = _states_build(tmp_path / "b")
    assert _problems(out) == []
    page = _with_block(sorted((out / "tn" / "water").glob("*/index.html")))
    _sabotage(page, "not TWRA&#39;s, and TWRA does", "not CDFW&#39;s, and CDFW does")
    found = _problems(out)
    assert any("non-endorsement" in p for p in found)
    assert any("names CDFW" in p for p in found)


def test_control_a_link_on_a_state_hub_is_noticed(tmp_path: Path) -> None:
    out = _states_build(tmp_path / "b")
    link = (
        f'<a href="https://www.amazon.com/s?k=x&amp;tag={TAG}" '
        f'rel="{site.AFFILIATE_LINK_REL}">x</a>'
    )
    _sabotage(out / "tn" / "index.html", "</main>", link + "</main>")
    assert any("outside a water page" in p for p in _problems(out))


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
