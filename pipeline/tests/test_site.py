import datetime as dt
import re
from pathlib import Path

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"

DATE_ONLY_PHRASES = [
    re.compile(r"\bplanted on \d{4}-\d{2}-\d{2}", re.I),
    re.compile(r"\bstocked on \d{4}-\d{2}-\d{2}", re.I),
]


def _build_site(tmp_path: Path) -> Path:
    out = tmp_path / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.timezone.utc),
        run_today=dt.date(2026, 9, 13),
    )
    return out


def _all_html(out: Path) -> list[Path]:
    return sorted(out.rglob("*.html"))


def test_site_builds_expected_pages(tmp_path: Path):
    out = _build_site(tmp_path)
    assert (out / "index.html").exists()
    assert (out / "about" / "index.html").exists()
    assert (out / "sitemap.xml").exists()
    assert (out / "robots.txt").exists()
    assert (out / "assets" / "style.css").exists()
    assert (out / "snapshot" / "v1.json").exists()
    water_dirs = list((out / "water").iterdir())
    assert water_dirs
    for d in water_dirs:
        assert (d / "index.html").exists()
        assert (d / "feed.ics").exists()


def test_no_script_tag_anywhere_in_the_built_site(tmp_path: Path):
    """DECISIONS 0002: no analytics, no cookies, no third-party script.
    The strongest, simplest check: there is no <script> element at all."""
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        assert "<script" not in html.lower(), f"found <script> in {f}"


def test_no_external_origin_referenced_in_the_built_site(tmp_path: Path):
    """Every href/src must be relative, same-origin (start with '/', a
    fragment, or a relative path) except explicit, visible links to CDFW's
    own pages (attribution) which are content, not requests the browser
    makes automatically on page load."""
    out = _build_site(tmp_path)
    # tags whose target the *browser* fetches automatically -- these must
    # never point off-origin. <a href> to CDFW is fine (attribution, a click
    # the reader chooses); img/link/script/iframe are not checked for CDFW
    # exemption because none should exist pointing anywhere external.
    auto_fetch_re = re.compile(
        r'<(script|iframe|embed|object)[^>]*\bsrc="(https?://[^"]+)"', re.I
    )
    link_stylesheet_re = re.compile(
        r'<link[^>]+rel="stylesheet"[^>]+href="(https?://[^"]+)"', re.I
    )
    img_re = re.compile(r'<img[^>]+src="(https?://[^"]+)"', re.I)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        assert not auto_fetch_re.search(html), f"external auto-fetch tag in {f}"
        assert not link_stylesheet_re.search(html), f"external stylesheet in {f}"
        assert not img_re.search(html), f"external image in {f}"


def test_about_page_privacy_claims_match_reality(tmp_path: Path):
    out = _build_site(tmp_path)
    about = (out / "about" / "index.html").read_text(encoding="utf-8")
    assert "No cookies" in about or "no cookies" in about.lower()
    assert "No JavaScript runs" in about or "no javascript" in about.lower()


def test_no_plant_rendered_as_a_single_day_on_any_page(tmp_path: Path):
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        for pat in DATE_ONLY_PHRASES:
            assert not pat.search(html), f"found a day-granularity plant phrase in {f}"
        # every "week of" mention must carry a full date after it
        for m in re.finditer(r"week of ([^\s<,.]+)", html):
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", m.group(1)), (
                f"'week of' not followed by a full date in {f}: {m.group(0)!r}"
            )


def test_water_page_titles_and_first_paragraph_answer_the_query(tmp_path: Path):
    """The per-water page should answer '<water> trout stocking' from the
    title and first paragraph, from data -- the free discovery surface."""
    out = _build_site(tmp_path)
    for d in (out / "water").iterdir():
        html = (d / "index.html").read_text(encoding="utf-8")
        title = re.search(r"<title>([^<]+)</title>", html).group(1)
        h1 = re.search(r"<h1>([^<]+)</h1>", html).group(1)
        assert "stocking" in title.lower()
        assert "trout stocking" in h1.lower() or "stocking" in h1.lower()


def test_ics_events_are_week_long_not_single_day(tmp_path: Path):
    out = _build_site(tmp_path)
    any_checked = False
    for d in (out / "water").iterdir():
        ics = (d / "feed.ics").read_text(encoding="utf-8")
        starts = re.findall(r"DTSTART;VALUE=DATE:(\d{8})", ics)
        ends = re.findall(r"DTEND;VALUE=DATE:(\d{8})", ics)
        for s, e in zip(starts, ends):
            sd = dt.datetime.strptime(s, "%Y%m%d").date()
            ed = dt.datetime.strptime(e, "%Y%m%d").date()
            assert (ed - sd).days == 7  # DTEND is exclusive -> a 7-day span
            any_checked = True
        for summary in re.findall(r"SUMMARY:(.+)", ics):
            assert summary.startswith("week of ")
    assert any_checked


def test_canonical_and_og_tags_present(tmp_path: Path):
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        assert '<link rel="canonical" href="https://example.invalid' in html
        assert 'property="og:title"' in html
        assert 'property="og:url"' in html


def test_table_headers_have_scope_for_accessibility(tmp_path: Path):
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        for th in re.findall(r"<th\b[^>]*>", html):
            assert 'scope="col"' in th, f"<th> missing scope in {f}: {th}"


def test_no_bare_click_here_links(tmp_path: Path):
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        assert "click here" not in html.lower()
