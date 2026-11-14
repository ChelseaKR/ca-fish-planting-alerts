"""The gift guide at /gifts/ (DECISIONS 0047), built from 2026-11-27.

0042 allows no new page family until 2026-11-27, so a build dated before
``GIFT_GUIDE_FROM`` must carry no trace of the page. Switched on, the page follows the /gear/ rules (0030): tagged Amazon search links with
the sponsored rel values and click labels, Amazon's disclosure sentence
before the first link and after the last, the CDFW non-endorsement sentence,
no image, price, brand or rating. These tests render the real site and read
it with html.parser. Each negative control asserts that its sabotage changed
the file before it asserts the checker noticed.
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

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."
ENDORSEMENT = (
    "The links are Trout Truck's, not CDFW's, and CDFW does not endorse them or Amazon."
)
REQUIRED_REL = {"sponsored", "nofollow", "noopener"}
BUILD_DAY = dt.date(2026, 11, 27)
# The /gear/ copy rules, plus "sale" and "discount": no superlative, money,
# rating or uniqueness claim, and never "stocked" or "planted on".
FORBIDDEN = re.compile(
    r"\b(only|first|best|top|cheap\w*|deal\w*|rated|unique\w*|stocked|"
    r"planted on|guarantee\w*|sale|discount\w*)\b|[$%★]",
    re.I,
)
BRITISH = re.compile(
    r"\b(colour|favour|flavour|neighbour|grey|metre|litre|centre)\w*", re.I
)


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self.events: list[tuple[str, str]] = []
        self.canonicals: list[str] = []
        self.h1: list[str] = []
        self.title = ""
        self.ld: list[str] = []
        self.imgs = 0
        self.text: list[str] = []
        self._ld_open = False
        self._skip = 0
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "a":
            self.anchors.append(a)
            self.events.append(("a", a.get("href", "")))
        elif tag == "img":
            self.imgs += 1
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonicals.append(a.get("href", ""))
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self.h1.append("")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld_open = True
            self.ld.append("")
        elif tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "script" and self._ld_open:
            self._ld_open = False
        elif tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._ld_open:
            self.ld[-1] += data
            return
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1[-1] += data
        self.text.append(data)
        self.events.append(("text", data))

    def prose(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text))


def _parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    p.close()
    return p


def _is_amazon(href: str) -> bool:
    host = urlsplit(href).hostname or ""
    return host == "amazon.com" or host.endswith(".amazon.com")


def _anchor_problems(a: dict[str, str]) -> list[str]:
    """One Amazon link: tagged search, sponsored rel, gift-guide labels."""
    href = a["href"]
    parts = urlsplit(href)
    found: list[str] = []
    if parse_qs(parts.query).get("tag") != [site.AMAZON_ASSOCIATE_TAG]:
        found.append(f"wrong or missing tag: {href}")
    if parts.path != "/s":
        found.append(f"not a search link: {href}")
    if not set(a.get("rel", "").split()) >= REQUIRED_REL:
        found.append(f"rel {a.get('rel')!r}: {href}")
    labels = (a.get("data-ga-event"), a.get("data-ga-placement"), a.get("data-ga-type"))
    if labels != ("gear_click", "gift_guide", "amazon_search"):
        found.append(f"click-event labels missing or wrong: {href}")
    return found


def _disclosure_problems(page: _Page) -> list[str]:
    """The disclosure sits before the first link and after the last one."""
    link_idx = [i for i, (k, v) in enumerate(page.events) if k == "a" and _is_amazon(v)]
    disc_idx = [
        i
        for i, (k, v) in enumerate(page.events)
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


def _copy_problems(page: _Page) -> list[str]:
    """Required sentences present; no image, banned word or British spelling."""
    prose = page.prose()
    found = [
        problem
        for needed, problem in (
            (ENDORSEMENT, "no agency non-endorsement sentence"),
            ("costs you nothing extra", "no plain affiliate sentence"),
            ("check the current price", "no check-the-current-price sentence"),
            ("Affiliate links", "no affiliate label"),
        )
        if needed not in prose
    ]
    if page.imgs:
        found.append("the page carries an image")
    if any("amazon" in blob.lower() for blob in page.ld):
        found.append("structured data names Amazon")
    if m := FORBIDDEN.search(prose):
        found.append(f"banned word: {m.group(0)!r}")
    if m := BRITISH.search(prose):
        found.append(f"British spelling: {m.group(0)!r}")
    return found


def _gift_problems(out: Path) -> list[str]:
    """Every way /gifts/ breaks the affiliate and copy rules."""
    page = _parse(out / "gifts" / "index.html")
    amazon = [a for a in page.anchors if _is_amazon(a.get("href", ""))]
    found: list[str] = []
    if not 8 <= len(amazon) <= 12:
        found.append(f"{len(amazon)} Amazon links, not 8 to 12")
    for a in amazon:
        found += _anchor_problems(a)
    return found + _disclosure_problems(page) + _copy_problems(page)


def _trace_problems(out: Path) -> list[str]:
    """Any trace of the gift guide in a build that should not have one."""
    found: list[str] = []
    if (out / "gifts").exists():
        found.append("gifts/ was written")
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".xml", ".txt", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "gifts/" in text or "Gifts for trout anglers" in text:
            found.append(f"{path.relative_to(out)} mentions the gift guide")
    return found


@pytest.fixture(scope="module")
def default_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("gifts-default")
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
    )
    return out


@pytest.fixture(scope="module")
def snapshot(default_build: Path) -> dict[str, Any]:
    text = (default_build / "snapshot" / "v1.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def _build(root: Path, snap: dict[str, Any], gift_guide: bool | None) -> Path:
    out = root / "site"
    site.build_site(
        snap, out, base_url=BASE_URL, build_date=BUILD_DAY, gift_guide=gift_guide
    )
    return out


@pytest.fixture(scope="module")
def on(tmp_path_factory: pytest.TempPathFactory, snapshot: dict[str, Any]) -> Path:
    return _build(tmp_path_factory.mktemp("gifts-on"), snapshot, True)


@pytest.fixture(scope="module")
def off(tmp_path_factory: pytest.TempPathFactory, snapshot: dict[str, Any]) -> Path:
    return _build(tmp_path_factory.mktemp("gifts-off"), snapshot, False)


# ---- off by default ----


def test_the_page_turns_on_by_build_date_on_2026_11_27() -> None:
    assert dt.date(2026, 11, 27) == site.GIFT_GUIDE_FROM
    assert site.gift_guide_live_or_default(None, dt.date(2026, 11, 26)) is False
    assert site.gift_guide_live_or_default(None, dt.date(2026, 11, 27)) is True
    assert site.gift_guide_live_or_default(None, dt.date(2027, 1, 15)) is True
    assert site.gift_guide_live_or_default(True, dt.date(2026, 11, 1)) is True
    assert site.gift_guide_live_or_default(False, dt.date(2026, 11, 27)) is False


def test_a_default_build_has_no_trace_of_the_guide(
    default_build: Path, off: Path
) -> None:
    assert _trace_problems(default_build) == []
    assert _trace_problems(off) == []


def test_the_build_date_is_the_one_switch(
    tmp_path: Path, snapshot: dict[str, Any]
) -> None:
    out = _build(tmp_path / "on-the-day", snapshot, None)
    assert (out / "gifts" / "index.html").exists()
    assert _gift_problems(out) == []

    day_before = tmp_path / "day-before" / "site"
    site.build_site(
        snapshot,
        day_before,
        base_url=BASE_URL,
        build_date=dt.date(2026, 11, 26),
    )
    assert not (day_before / "gifts").exists()
    assert _trace_problems(day_before) == []


def test_on_changes_only_the_new_page_home_privacy_and_sitemap(
    on: Path, off: Path
) -> None:
    def files(root: Path) -> dict[str, bytes]:
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }

    a, b = files(off), files(on)
    assert set(b) - set(a) == {"gifts/index.html"}
    assert set(a) <= set(b)
    changed = {k for k in a if a[k] != b[k]}
    assert changed == {"index.html", "privacy/index.html", "sitemap.xml"}


# ---- the page, switched on ----


def test_the_page_follows_the_affiliate_and_copy_rules(on: Path) -> None:
    assert _gift_problems(on) == []


def test_every_item_is_on_the_page_once_with_its_reason(on: Path) -> None:
    page = _parse(on / "gifts" / "index.html")
    hrefs = [a["href"] for a in page.anchors if _is_amazon(a.get("href", ""))]
    prose = page.prose()
    items = site.gift_guide_items()
    assert 8 <= len(items) <= 12
    assert len({g["label"] for g in items}) == len(items)
    for g in items:
        assert hrefs.count(g["url"]) == 1, g["label"]
        assert g["why"] in prose, g["label"]
        assert g["label"] in prose


def test_title_canonical_h1_and_sitemap(on: Path) -> None:
    page = _parse(on / "gifts" / "index.html")
    assert page.h1 == ["Gifts for trout anglers"]
    assert page.title.startswith("Gifts for trout anglers | Trout Truck")
    assert page.canonicals == [f"{BASE_URL}/gifts/"]
    sitemap = (on / "sitemap.xml").read_text(encoding="utf-8")
    assert sitemap.count(f"<loc>{BASE_URL}/gifts/</loc>") == 1
    assert "amazon" not in sitemap.lower()


def test_the_title_is_unique_across_the_site(on: Path) -> None:
    mine = _parse(on / "gifts" / "index.html").title
    for path in on.rglob("*.html"):
        if path.parts[-2:] != ("gifts", "index.html"):
            assert _parse(path).title != mine, path


def test_the_license_link_goes_to_cdfw(on: Path) -> None:
    page = _parse(on / "gifts" / "index.html")
    assert site.CDFW_LICENSE_URL in [a.get("href") for a in page.anchors]


def test_the_home_page_link_is_short_internal_and_disclosed(on: Path) -> None:
    home = _parse(on / "index.html")
    links = [a for a in home.anchors if a.get("href") == "./gifts/"]
    assert len(links) == 1
    # An internal link: no tag, no Amazon address on the home page for it.
    assert not _is_amazon(links[0]["href"])
    html = (on / "index.html").read_text(encoding="utf-8")
    para = re.search(r'<p id="gift-guide-link">.*?</p>', html, re.S)
    assert para is not None
    assert "affiliate links" in para.group(0)


def test_the_privacy_page_names_the_gift_page(on: Path) -> None:
    assert "Gifts for trout anglers" in _parse(on / "privacy" / "index.html").prose()


def test_no_app_source_has_the_gift_guide() -> None:
    repo = Path(__file__).resolve().parents[2]
    for top in ("ios", "android"):
        for path in (repo / top).rglob("*"):
            if path.is_file() and path.suffix in {".swift", ".kt", ".kts", ".xml"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                assert "gifts/" not in text, path
                assert site.AMAZON_ASSOCIATE_TAG not in text, path


# ---- negative controls ----


def _sabotage(path: Path, old: str, new: str, count: int = -1) -> None:
    before = path.read_text(encoding="utf-8")
    assert old in before, f"sabotage target missing: {old!r}"
    after = before.replace(old, new, count)
    assert after != before
    path.write_text(after, encoding="utf-8")


def _copy_on(on: Path, tmp_path: Path) -> Path:
    out = tmp_path / "site"
    (out / "gifts").mkdir(parents=True)
    src = (on / "gifts" / "index.html").read_text(encoding="utf-8")
    (out / "gifts" / "index.html").write_text(src, encoding="utf-8")
    return out


def _first_url_html() -> str:
    return site.gift_guide_items()[0]["url"].replace("&", "&amp;")


@pytest.mark.parametrize(
    ("old", "new", "expect"),
    [
        ('rel="sponsored nofollow noopener"', 'rel="noopener"', "rel "),
        ("tag=trouttruck-20", "tag=someone-else-20", "wrong or missing tag"),
        ("amazon.com/s?", "amazon.com/dp/B000?", "not a search link"),
        ('data-ga-placement="gift_guide"', 'data-ga-placement="x"', "click-event"),
        (DISCLOSURE, "Thanks.", "no Amazon disclosure"),
        ("costs you nothing extra", "costs you", "no plain affiliate sentence"),
        ("check the current price", "look", "no check-the-current-price"),
        ("does not endorse them", "endorses them", "no agency non-endorsement"),
        ("<ul>", '<img src="x.png" alt=""><ul>', "carries an image"),
        ("Practical ideas", "The best", "banned word"),
        ("Practical ideas", "Grey", "British spelling"),
        ("Practical ideas", "From $9", "banned word"),
    ],
)
def test_control_each_rule_is_noticed(
    on: Path, tmp_path: Path, old: str, new: str, expect: str
) -> None:
    out = _copy_on(on, tmp_path)
    _sabotage(out / "gifts" / "index.html", old, new)
    problems = _gift_problems(out)
    assert any(expect in p for p in problems), problems


def test_control_a_disclosure_only_at_the_end_is_noticed(
    on: Path, tmp_path: Path
) -> None:
    out = _copy_on(on, tmp_path)
    _sabotage(out / "gifts" / "index.html", DISCLOSURE, "", count=1)
    problems = _gift_problems(out)
    assert "disclosure does not come before the first link" in problems, problems


def test_control_too_few_links_is_noticed(on: Path, tmp_path: Path) -> None:
    out = _copy_on(on, tmp_path)
    path = out / "gifts" / "index.html"
    html = path.read_text(encoding="utf-8")
    kept = re.sub(
        r"<li><a href=\"https://www\.amazon\.com/s\?[^<]*</a>[^<]*</li>", "", html
    )
    assert kept != html
    path.write_text(kept, encoding="utf-8")
    assert any("Amazon links, not 8 to 12" in p for p in _gift_problems(out))


def test_control_the_trace_check_notices_the_page(on: Path) -> None:
    problems = _trace_problems(on)
    assert "gifts/ was written" in problems
    assert any(p.startswith("index.html") for p in problems), problems
    assert any(p.startswith("sitemap.xml") for p in problems), problems


def test_control_the_first_url_is_escaped_in_the_page(on: Path) -> None:
    # Guards the sabotage helpers above: they rely on the rendered href.
    assert _first_url_html() in (on / "gifts" / "index.html").read_text(
        encoding="utf-8"
    )
