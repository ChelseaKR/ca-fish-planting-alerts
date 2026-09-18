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


def _build_site(tmp_path: Path, **extra) -> Path:
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
        **extra,
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
            # a feed cannot confirm a plant happened: "scheduled", never
            # "planted"/"stocked"
            assert " scheduled at " in summary
            assert "planted" not in summary.lower() and "stocked" not in summary.lower()
    assert any_checked


def test_canonical_and_og_tags_present(tmp_path: Path):
    out = _build_site(tmp_path)
    for f in _all_html(out):
        if f.name == "404.html":
            continue  # see test_404_page_is_noindex_and_links_root_relative
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


def _water_html(out: Path, slug: str) -> str:
    return (out / "water" / slug / "index.html").read_text(encoding="utf-8")


def test_water_listed_only_for_next_week_is_not_described_as_having_nothing_scheduled(
    tmp_path: Path,
):
    """Real case from the 2026-09-13 page: Halsey Forebay's only listing is
    the week of 2026-09-20 (after the page's current week). The page used to
    say "No planting has been scheduled ... in the period this site has
    observed" directly above a table listing that week."""
    out = _build_site(tmp_path)
    html = _water_html(out, "halsey-forebay")
    assert "week of 2026-09-20" in html
    assert "Next scheduled: the week of 2026-09-20." in html
    assert "No planting" not in html


def test_water_page_says_when_the_schedule_was_last_checked(tmp_path: Path):
    """A static page can't know it has gone stale; saying when the data was
    fetched is what keeps an old build from reading as current."""
    out = _build_site(tmp_path)
    for d in (out / "water").iterdir():
        html = (d / "index.html").read_text(encoding="utf-8")
        assert "schedule was last checked 2026-09-13 12:00 UTC" in html
        assert "current\n  week was the week of 2026-09-13" in html or "week was the week of 2026-09-13" in html


def test_water_titles_are_unique_and_name_the_county(tmp_path: Path):
    """Five CDFW names are shared by 2-3 waters each (e.g. three Silver
    Lakes); without the county their pages would have identical titles."""
    import json

    out = _build_site(tmp_path)
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    titles = []
    for w in snap["waters"]:
        html = _water_html(out, w["slug"])
        title = re.search(r"<title>([^<]+)</title>", html).group(1)
        assert f"({', '.join(w['counties'])})" in title
        titles.append(title)
    assert len(titles) == len(set(titles))


def test_sitemap_lastmod_is_when_data_changed_not_the_build_date(tmp_path: Path):
    """The fixture was fetched 2026-09-13 but the build runs today; a
    lastmod of the build date on every URL is one search engines ignore."""
    out = _build_site(tmp_path)
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    lastmods = re.findall(r"<lastmod>([^<]+)</lastmod>", sitemap)
    assert lastmods
    assert set(lastmods) == {"2026-09-13"}
    for page in ("privacy", "support", "about"):
        assert f"/{page}/</loc>" in sitemap
    assert "404" not in sitemap


def test_app_is_not_linked_until_it_has_an_app_store_url(tmp_path: Path):
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        assert "apps.apple.com" not in html
        assert "Get the iOS app" not in html
    about = (out / "about" / "index.html").read_text(encoding="utf-8")
    assert "not in the App Store yet" in about


def test_app_store_url_and_support_email_render_when_configured(tmp_path: Path):
    url = "https://apps.apple.com/us/app/id0000000000"  # shape only; not a real listing
    out = _build_site(tmp_path, app_store_url=url, support_email="help@example.invalid")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert f'<a href="{url}">Get the iOS app</a>' in index
    assert "not in the App Store yet" not in (out / "about" / "index.html").read_text(
        encoding="utf-8"
    )
    for page in ("support", "privacy"):
        html = (out / page / "index.html").read_text(encoding="utf-8")
        assert 'href="mailto:help@example.invalid"' in html


def test_privacy_page_covers_the_site_and_the_app(tmp_path: Path):
    out = _build_site(tmp_path)
    html = (out / "privacy" / "index.html").read_text(encoding="utf-8")
    assert "Data Not Collected" in html
    assert "no push service" in html.lower()
    assert "handled\n      entirely by Apple" in html or "entirely by Apple" in html
    assert "GitHub Pages" in html


def test_404_page_is_noindex_and_links_root_relative(tmp_path: Path):
    out = _build_site(tmp_path)
    html = (out / "404.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex">' in html
    assert 'rel="canonical"' not in html
    # served at any depth, so no ./ or ../ links; same origin, so no scheme
    assert 'href="/ca-fish-planting-alerts/assets/style.css"' in html
    assert 'href="./' not in html and 'href="../' not in html


def test_no_uniqueness_claims_in_site_copy(tmp_path: Path):
    """Other California stocking-alert products exist (checked 2026-09-17),
    so the copy must not claim to be the only or first one."""
    out = _build_site(tmp_path)
    banned = re.compile(r"\b(the only|only place|only app|first app|the first|no one else|nobody else)\b", re.I)
    for f in _all_html(out):
        text = re.sub(r"<[^>]+>", " ", f.read_text(encoding="utf-8"))
        m = banned.search(text)
        assert not m, f"uniqueness claim {m.group(0)!r} in {f}"


def test_every_page_says_it_is_not_affiliated_with_cdfw(tmp_path: Path):
    """The site republishes a state agency's schedule; it must not read as
    CDFW's own page."""
    out = _build_site(tmp_path)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        assert "not affiliated with or endorsed by CDFW" in html, f
