"""The "What to bring" guide at /gear/ (DECISIONS 0030).

The page is the one place besides a California water page that carries
Amazon search links. These tests render the real site and read it with
html.parser (never a regex over tags or scripts). Every Amazon link must be a
tagged search with the sponsored rel values and the click-event labels, the
disclosure must sit before the first link and after the last, and no Amazon
link may appear anywhere that is not a web page. Each negative control
asserts that its sabotage changed the file before it asserts the checker
noticed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
REPO = Path(__file__).resolve().parents[2]
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."
ENDORSEMENT = (
    "The links are Trout Truck's, not CDFW's, and CDFW does not endorse them or Amazon."
)
REQUIRED_REL = {"sponsored", "nofollow", "noopener"}
# Copy rules: no superlatives, first/only claims, money, ratings, uniqueness,
# and never "stocked" or "planted on" for a schedule fact.
FORBIDDEN = re.compile(
    r"\b(only|first|best|top|cheap\w*|deal\w*|rated|unique\w*|stocked|"
    r"planted on|guarantee\w*)\b|[$%★]",
    re.I,
)
# British spellings that would break the American-English rule.
BRITISH = re.compile(
    r"\b(colour|favour|flavour|neighbour|grey|metre|litre|centre)\w*", re.I
)


def _build(root: Path, **extra: object) -> Path:
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
    return _build(tmp_path_factory.mktemp("gear-guide"))


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self.meta: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.title = ""
        self.ld: list[str] = []
        self.imgs = 0
        self.h1: list[str] = []
        self.crumbs: list[str] = []
        self.events: list[tuple[str, str]] = []  # ("a"|"text", value) in order
        self._stack: list[str] = []
        self._ld_open = False
        self._skip = 0
        self._in_crumb = False
        self._crumb_text: list[str] = []
        self._in_title = False
        self._in_h1 = False
        self._h1_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "a":
            self.anchors.append(a)
            self.events.append(("a", a.get("href", "")))
        elif tag in {"meta", "link", "img"}:
            self._head_tag(tag, a)
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self._h1_text = []
        elif tag == "nav" and a.get("aria-label") == "Breadcrumb":
            self._in_crumb = True
        elif tag == "li" and self._in_crumb:
            self._crumb_text = []
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld_open = True
            self.ld.append("")
        elif tag in {"script", "style"}:
            self._skip += 1

    def _head_tag(self, tag: str, a: dict[str, str]) -> None:
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonicals.append(a.get("href", ""))
        elif tag == "img":
            self.imgs += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
            self.h1.append("".join(self._h1_text).strip())
        elif tag == "nav" and self._in_crumb:
            self._in_crumb = False
        elif tag == "li" and self._in_crumb:
            self.crumbs.append("".join(self._crumb_text).strip())
        elif tag == "script" and self._ld_open:
            self._ld_open = False
        elif tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._ld_open:
            self.ld[-1] += data
        elif self._in_title:
            self.title += data
        elif not self._skip:
            self.events.append(("text", data))
            if self._in_h1:
                self._h1_text.append(data)
            if self._in_crumb:
                self._crumb_text.append(data)

    def prose(self) -> str:
        return re.sub(
            r"\s+", " ", " ".join(v for k, v in self.events if k == "text")
        ).strip()


def _parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    p.close()
    return p


def _is_amazon(href: str) -> bool:
    host = urlsplit(href).hostname or ""
    return host == "amazon.com" or host.endswith(".amazon.com")


def _link_problems(a: dict[str, str]) -> list[str]:
    href = a["href"]
    parts = urlsplit(href)
    found: list[str] = []
    if parse_qs(parts.query).get("tag") != [site.AMAZON_ASSOCIATE_TAG]:
        found.append(f"wrong or missing tag: {href}")
    if parts.path != "/s":
        found.append(f"not a search link: {href}")
    if not set(a.get("rel", "").split()) >= REQUIRED_REL:
        found.append(f"rel {a.get('rel')!r}: {href}")
    labels = (
        a.get("data-ga-event"),
        a.get("data-ga-placement"),
        a.get("data-ga-type"),
    )
    if labels != ("gear_click", "gear_guide", "amazon_search"):
        found.append(f"click-event labels missing or wrong: {href}")
    return found


def _disclosure_problems(page: _Page) -> list[str]:
    """The disclosure sits before the first link and after the last one."""
    seq = page.events
    link_idx = [i for i, (k, v) in enumerate(seq) if k == "a" and _is_amazon(v)]
    disc_idx = [
        i
        for i, (k, v) in enumerate(seq)
        if k == "text" and DISCLOSURE in re.sub(r"\s+", " ", v)
    ]
    if not disc_idx:
        return ["no Amazon disclosure"]
    found: list[str] = []
    if link_idx and min(disc_idx) > min(link_idx):
        found.append("disclosure does not come before the first link")
    if link_idx and max(disc_idx) < max(link_idx):
        found.append("disclosure does not come after the last link")
    return found


def _gear_problems(out: Path) -> list[str]:
    """Every way the guide breaks the affiliate rules."""
    page = _parse(out / "gear" / "index.html")
    amazon = [a for a in page.anchors if _is_amazon(a.get("href", ""))]
    found: list[str] = [] if amazon else ["no Amazon link on the page"]
    for a in amazon:
        found += _link_problems(a)
    found += _disclosure_problems(page)
    prose = page.prose()
    if ENDORSEMENT not in prose:
        found.append("no agency non-endorsement sentence")
    if "costs you nothing extra" not in prose:
        found.append("no plain affiliate sentence")
    if page.imgs:
        found.append("the guide carries an image")
    if any("amazon" in blob.lower() for blob in page.ld):
        found.append("structured data names Amazon")
    return found


def _outside_problems(out: Path) -> list[str]:
    """Amazon anywhere that is not a California water or county page, the
    home page, the /county/ index or the guide (DECISIONS 0029, 0030, 0039,
    0040). This build has no other state."""
    found: list[str] = []
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out).parts
        allowed = path.suffix == ".html" and (
            rel in (("gear", "index.html"), ("index.html",), ("county", "index.html"))
            or (
                len(rel) == 3
                and rel[0] in ("water", "county")
                and rel[2] == "index.html"
            )
        )
        if allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if path.suffix == ".html":
            page = _parse(path)
            if any(_is_amazon(a.get("href", "")) for a in page.anchors):
                found.append(f"{path.relative_to(out)}: Amazon link")
        elif "amazon" in text:
            found.append(f"{path.relative_to(out)}: names Amazon")
    return found


def test_the_guide_page_is_built_and_clean(built: Path) -> None:
    assert (built / "gear" / "index.html").exists()
    assert _gear_problems(built) == []
    assert _outside_problems(built) == []


def test_every_configured_link_is_on_the_page_once(built: Path) -> None:
    page = _parse(built / "gear" / "index.html")
    hrefs = [a["href"] for a in page.anchors if _is_amazon(a.get("href", ""))]
    expected = [
        site.amazon_search_url(terms)
        for pairs in site.GEAR_GUIDE_LINKS.values()
        for _, terms in pairs
    ]
    assert len(expected) >= 15
    assert sorted(hrefs) == sorted(expected)
    # Terms are generic categories: no brand list sneaks in through the search.
    for pairs in site.GEAR_GUIDE_LINKS.values():
        for label, terms in pairs:
            assert not FORBIDDEN.search(label + " " + terms), (label, terms)


def test_title_description_canonical_h1_and_breadcrumb(built: Path) -> None:
    page = _parse(built / "gear" / "index.html")
    assert page.title == (
        f"{site.GEAR_GUIDE_TITLE} | Trout Truck, CA trout planting schedule"
    )
    assert page.meta["description"] == site.GEAR_GUIDE_DESCRIPTION
    assert page.canonicals == [f"{BASE_URL}/gear/"]
    assert page.h1 == [site.GEAR_GUIDE_TITLE]
    assert page.crumbs == ["Trout Truck", "What to bring"]
    graph = json.loads(page.ld[0])["@graph"]
    crumb = next(n for n in graph if n["@type"] == "BreadcrumbList")
    assert [i["name"] for i in crumb["itemListElement"]] == page.crumbs
    assert crumb["itemListElement"][-1]["item"] == f"{BASE_URL}/gear/"


def test_title_and_description_are_unique_across_the_site(built: Path) -> None:
    seen: dict[str, str] = {}
    for path in sorted(built.rglob("*.html")):
        if path.name == "404.html":
            continue
        page = _parse(path)
        for key, value in (
            ("title", page.title),
            ("description", page.meta.get("description", "")),
        ):
            token = f"{key}:{value}"
            rel = path.relative_to(built).as_posix()
            assert token not in seen, (rel, seen.get(token))
            seen[token] = rel


def test_the_guide_is_in_the_sitemap_once(built: Path) -> None:
    sitemap = (built / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap.count(f"<loc>{BASE_URL}/gear/</loc>") == 1


def test_footer_and_water_pages_link_to_the_guide(built: Path) -> None:
    pages = sorted(built.rglob("*.html"))
    assert len(pages) > 30
    for path in pages:
        page = _parse(path)
        hrefs = [a.get("href", "") for a in page.anchors]
        assert any(h.endswith("gear/") for h in hrefs), path
    water = next(iter(sorted((built / "water").glob("*/index.html"))))
    texts = _parse(water).prose()
    assert "More gear ideas" in texts


def test_the_guide_copy_follows_the_copy_rules(built: Path) -> None:
    prose = _parse(built / "gear" / "index.html").prose()
    assert len(prose) > 2000
    assert not FORBIDDEN.search(prose), FORBIDDEN.search(prose)
    assert not BRITISH.search(prose), BRITISH.search(prose)
    assert "not legal advice" in prose
    assert "scheduled" in prose


def test_the_license_link_goes_to_cdfw(built: Path) -> None:
    page = _parse(built / "gear" / "index.html")
    assert site.CDFW_LICENSE_URL in [a.get("href") for a in page.anchors]
    assert urlsplit(site.CDFW_LICENSE_URL).hostname == "wildlife.ca.gov"


def test_the_tag_comes_from_the_one_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(site, "AMAZON_ASSOCIATE_TAG", "changed-21")
    out = _build(tmp_path)
    html = (out / "gear" / "index.html").read_text(encoding="utf-8")
    assert "tag=changed-21" in html
    assert "trouttruck-20" not in html


def test_no_app_source_has_an_amazon_link_or_the_guide() -> None:
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


# ---- negative controls ----


def _sabotage(path: Path, old: str, new: str) -> None:
    before = path.read_text(encoding="utf-8")
    assert old in before, "the sabotage target is not in the page"
    after = before.replace(old, new)
    assert after != before
    path.write_text(after, encoding="utf-8")


@pytest.mark.parametrize(
    ("old", "new", "expect"),
    [
        (f'rel="{site.AFFILIATE_LINK_REL}"', 'rel="noopener"', "rel "),
        ("tag=trouttruck-20", "tag=someone-else-20", "wrong or missing tag"),
        ('data-ga-event="gear_click"', 'data-ga-event="other"', "click-event labels"),
        (DISCLOSURE, "", "no Amazon disclosure"),
    ],
)
def test_control_each_rule_is_noticed(
    tmp_path: Path, old: str, new: str, expect: str
) -> None:
    out = _build(tmp_path)
    assert _gear_problems(out) == []
    _sabotage(out / "gear" / "index.html", old, new)
    assert any(expect in p for p in _gear_problems(out))


def test_control_a_disclosure_only_at_the_end_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    page = out / "gear" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert html.count(DISCLOSURE) == 2
    # Remove the top disclosure only; the one after the links stays.
    page.write_text(html.replace(DISCLOSURE, "", 1), encoding="utf-8")
    assert page.read_text(encoding="utf-8").count(DISCLOSURE) == 1
    problems = _gear_problems(out)
    assert any("before the first link" in p for p in problems), problems


def test_control_an_amazon_link_on_the_about_page_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    assert _outside_problems(out) == []
    link = f'<a href="https://www.amazon.com/s?k=x&amp;tag={site.AMAZON_ASSOCIATE_TAG}">x</a>'
    _sabotage(out / "about" / "index.html", "</main>", link + "</main>")
    assert any("about/index.html: Amazon link" in p for p in _outside_problems(out))


def test_control_amazon_in_the_sitemap_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(out / "sitemap.xml", "</urlset>", "<!-- amazon --></urlset>")
    assert any("sitemap.xml" in p for p in _outside_problems(out))


def test_control_an_image_on_the_guide_is_noticed(tmp_path: Path) -> None:
    out = _build(tmp_path)
    _sabotage(out / "gear" / "index.html", "</main>", '<img src="x.jpg"></main>')
    assert any("image" in p for p in _gear_problems(out))


def test_control_the_copy_check_notices_a_banned_word() -> None:
    sample = "the best rod, stocked on 2026-09-13, only $20"
    assert FORBIDDEN.search(sample)
    assert BRITISH.search("a colour chart")
