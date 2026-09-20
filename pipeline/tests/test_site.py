import copy
import datetime as dt
import json
import re
from pathlib import Path

from cfpa import cli, site

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
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
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


def test_no_executable_script_anywhere_in_the_built_site(tmp_path: Path):
    """With no GA4 measurement ID (``_build_site`` passes none), the site has
    no analytics, no cookies and no third-party script (DECISIONS 0011).
    The only <script> element allowed is one schema.org JSON-LD block per
    page (docs/adr/0013), which a browser never executes, and which must
    parse as JSON. The with-ID build is covered in test_site_analytics.py."""
    out = _build_site(tmp_path)
    ld_open = re.compile(r'<script type="application/ld\+json">', re.I)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        openings = len(re.findall(r"<script\b", html, re.I))
        data_blocks = ld_open.findall(html)
        assert openings == len(data_blocks) <= 1, f"executable <script> in {f}"
        for body in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        ):
            json.loads(body)


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
    # the no-analytics build; test_site_analytics.py covers the GA4 copy
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
    """The per-water page should answer '<water> trout stocking' and
    '<water> trout planting schedule' from the title, h1 and description,
    from data -- the free discovery surface. The title says "planting
    schedule", the h1 "stocking schedule", so both wordings are on the page."""
    out = _build_site(tmp_path)
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    for w in snap["waters"]:
        html = _water_html(out, w["slug"])
        title = re.search(r"<title>([^<]+)</title>", html).group(1)
        h1 = re.search(r"<h1>([^<]+)</h1>", html).group(1)
        description = re.search(
            r'<meta name="description" content="([^"]+)">', html
        ).group(1)
        species = site.species_phrase({p["species"] for p in w["plants"]})
        where = site.county_phrase(w["counties"])
        assert f"{species} planting schedule" in title
        assert f"{species} stocking schedule" in h1
        for text in (title, h1, description):
            assert w["name"].replace("'", "&#39;") in text, (w["slug"], text)
            assert where in text, (w["slug"], text)
        assert "stocking" in description and "planting schedule" in description


def test_ics_events_are_week_long_not_single_day(tmp_path: Path):
    out = _build_site(tmp_path)
    any_checked = False
    for d in (out / "water").iterdir():
        ics = (d / "feed.ics").read_text(encoding="utf-8")
        starts = re.findall(r"DTSTART;VALUE=DATE:(\d{8})", ics)
        ends = re.findall(r"DTEND;VALUE=DATE:(\d{8})", ics)
        for s, e in zip(starts, ends, strict=True):
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
        assert (
            "current\n  week was the week of 2026-09-13" in html
            or "week was the week of 2026-09-13" in html
        )


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
        assert f"({site.county_phrase(w['counties'])})" in title
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
    banned = re.compile(
        r"\b(the only|only place|only app|first app|the first|no one else|nobody else|the app for)\b",
        re.I,
    )
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


def test_every_page_carries_the_brand_and_the_search_terms(tmp_path: Path):
    """DECISIONS 0010: the brand is "Trout Truck", but nobody searches for
    it, so every title and meta description keeps "trout planting" or
    "stocking" next to it, and every page still credits CDFW as the source."""
    out = _build_site(tmp_path)
    # "planting schedule" rather than "trout planting": the three
    # catfish-only park lakes say "catfish planting schedule" (their pages
    # must not claim trout), and every description still says "stocking".
    search_terms = re.compile(r"trout planting|planting schedule|stocking", re.I)
    for f in _all_html(out):
        html = f.read_text(encoding="utf-8")
        title = re.search(r"<title>([^<]+)</title>", html).group(1)
        description = re.search(
            r'<meta name="description" content="([^"]+)">', html
        ).group(1)
        assert "Trout Truck" in title, f
        assert '<meta property="og:site_name" content="Trout Truck">' in html, f
        assert "CA Trout Planting Alerts" not in html, f
        if f.name != "404.html":  # noindex: never shown in search results
            assert search_terms.search(title), (f, title)
            assert search_terms.search(description), (f, description)
        assert "Data: California Department of Fish and Wildlife" in html, f


# ---- the calendar's name says what the page says ------------------------


def _plant(species: str, start: str, status: str = "listed") -> dict:
    end = (dt.date.fromisoformat(start) + dt.timedelta(days=6)).isoformat()
    return {
        "week": {"start": start, "end": end, "label": f"week of {start}"},
        "species": species,
        "status": status,
        "last_observed_at": "2026-09-13T12:00:00Z",
    }


def _ics_water(water_id: str, name: str, plants: list[dict]) -> dict:
    return {"id": water_id, "name": name, "plants": plants}


def _ics_lines(ics: str, prefix: str) -> list[str]:
    return [ln for ln in ics.splitlines() if ln.startswith(prefix)]


def test_calendar_name_says_the_species_the_water_is_scheduled_for():
    """A catfish-only water's calendar used to be named "... trout planting
    schedule" while its own page said catfish. The feed names now follow
    species_phrase, the function the page uses, from the same plants."""
    base = "https://example.invalid/water/x/"
    catfish = _ics_water(
        "cdfw-7351", "MacArthur Park Lake", [_plant("Catfish", "2026-09-13")]
    )
    trout = _ics_water("cdfw-1", "Eagle Lake", [_plant("Trout", "2026-09-13")])
    mixed = _ics_water(
        "cdfw-2",
        "Lake Perris",
        [_plant("Trout", "2026-09-13"), _plant("Catfish", "2026-09-20")],
    )
    assert _ics_lines(
        site.build_water_ics(water=catfish, base_url=base), "X-WR-CALNAME"
    ) == ["X-WR-CALNAME:MacArthur Park Lake catfish planting schedule"]
    # A trout-only water's feed name is exactly what it was before.
    assert _ics_lines(
        site.build_water_ics(water=trout, base_url=base), "X-WR-CALNAME"
    ) == ["X-WR-CALNAME:Eagle Lake trout planting schedule"]
    assert _ics_lines(
        site.build_water_ics(water=mixed, base_url=base), "X-WR-CALNAME"
    ) == ["X-WR-CALNAME:Lake Perris trout and catfish planting schedule"]


def test_calendar_name_counts_a_removed_week_like_the_page_does():
    """The page's species comes from every plant on record, removed weeks
    included; the feed name must agree with the page, not with the events."""
    water = _ics_water(
        "cdfw-3",
        "Some Lake",
        [_plant("Trout", "2026-09-13", "removed"), _plant("Catfish", "2026-09-20")],
    )
    ics = site.build_water_ics(water=water, base_url="https://example.invalid/w/")
    assert "X-WR-CALNAME:Some Lake trout and catfish planting schedule" in ics
    assert ics.count("BEGIN:VEVENT") == 1  # only the listed week is an event


def test_calendar_identity_does_not_change_with_the_species_wording():
    """Subscribers' calendar apps key events on UID (and treat the feed as the
    same calendar by its URL). The UIDs and PRODID are pinned as literals, so
    a change to any of them fails here instead of duplicating events in
    people's calendars."""
    base = "https://example.invalid/water/x/"
    catfish = _ics_water(
        "cdfw-7351",
        "MacArthur Park Lake",
        [_plant("Catfish", "2026-09-13"), _plant("Catfish", "2026-09-20")],
    )
    mixed = _ics_water(
        "cdfw-2",
        "Lake Perris",
        [_plant("Trout", "2026-09-13"), _plant("Catfish", "2026-09-13")],
    )
    ics = site.build_water_ics(water=catfish, base_url=base)
    assert _ics_lines(ics, "UID:") == [
        "UID:cdfw-7351-2026-09-13-catfish@ca-fish-planting-alerts.invalid",
        "UID:cdfw-7351-2026-09-20-catfish@ca-fish-planting-alerts.invalid",
    ]
    assert _ics_lines(ics, "PRODID:") == [
        "PRODID:-//ca-fish-planting-alerts//snapshot v1//EN"
    ]
    assert _ics_lines(site.build_water_ics(water=mixed, base_url=base), "UID:") == [
        "UID:cdfw-2-2026-09-13-trout@ca-fish-planting-alerts.invalid",
        "UID:cdfw-2-2026-09-13-catfish@ca-fish-planting-alerts.invalid",
    ]


def test_every_built_feed_is_named_for_the_species_on_its_own_page(tmp_path: Path):
    out = _build_site(tmp_path)
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    seen = set()
    for w in snap["waters"]:
        species = site.species_phrase({p["species"] for p in w["plants"]})
        ics = (out / "water" / w["slug"] / "feed.ics").read_text(encoding="utf-8")
        assert _ics_lines(ics, "X-WR-CALNAME") == [
            f"X-WR-CALNAME:{site._ics_escape(w['name'])} {species} planting schedule"
        ], w["slug"]
        assert f"{species} stocking schedule" in _water_html(out, w["slug"])
        seen.add(species)
    assert {"trout", "catfish"} <= seen  # a catfish-only water is in the build


# ---- the history table says what its statuses mean ----------------------


def _status_cells(html: str) -> list[str]:
    table = re.search(r"<table\b.*?</table>", html, re.S).group(0)
    return [
        re.sub(r"\s+", " ", m).strip()
        for m in re.findall(
            r"<tr>\s*<td>[^<]*</td>\s*<td>[^<]*</td>\s*<td>([^<]*)</td>", table
        )
    ]


def test_history_table_uses_plain_words_and_the_snapshot_keeps_raw_values(
    tmp_path: Path,
):
    out = _build_site(tmp_path)
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    statuses = {p["status"] for w in snap["waters"] for p in w["plants"]}
    assert statuses == {"listed"}  # this fixture has no removed week
    for w in snap["waters"]:
        html = _water_html(out, w["slug"])
        cells = _status_cells(html)
        assert len(cells) == len(w["plants"]) > 0
        assert set(cells) == {"Scheduled"}, w["slug"]
        # The raw values are never a reader-facing status, and a water with
        # no changed week carries no explanation of one.
        assert "<td>listed</td>" not in html and "<td>removed</td>" not in html
        assert "Schedule changed" not in html
        assert 'id="status-note"' not in html and "aria-describedby" not in html


def test_a_removed_week_reads_schedule_changed_and_the_page_says_what_that_means(
    tmp_path: Path,
):
    out = _build_site(tmp_path)
    snap = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    changed = copy.deepcopy(snap)
    target = changed["waters"][0]
    target["plants"][0]["status"] = "removed"
    assert changed != snap  # the sabotage landed
    other = changed["waters"][1]["slug"]
    out2 = tmp_path / "changed-site"
    site.build_site(
        changed, out2, base_url="https://example.invalid/ca-fish-planting-alerts"
    )

    html = _water_html(out2, target["slug"])
    cells = _status_cells(html)
    assert cells.count("Schedule changed") == 1
    assert cells.count("Scheduled") == len(target["plants"]) - 1
    # Words carry the meaning: not a color, not an icon, and no script.
    assert "<td>removed</td>" not in html and "<td>listed</td>" not in html
    note = re.search(r'<p class="muted" id="status-note">(.*?)</p>', html, re.S)
    assert note, "the explanation is missing"
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", note.group(1))).strip()
    assert text == (
        "Schedule changed means CDFW listed that week earlier and later "
        "removed it from its schedule. CDFW's plans can change."
    )
    # The table is tied to the explanation for assistive technology.
    assert re.search(r'<table aria-describedby="status-note">', html)
    # The week-of wording holds: never "planted" or "stocked" in the note.
    assert "planted" not in text.lower() and "stocked" not in text.lower()
    # A neighbor with no changed week is unaffected.
    assert "status-note" not in _water_html(out2, other)
