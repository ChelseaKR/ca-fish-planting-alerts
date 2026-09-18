"""Search: county pages, internal links, structured data, sitemap lastmod and
the Search Console tag (docs/adr/0013).

Built from the two real CDFW fixtures, run in the order the scheduled job
would (2026-09-13, then 2026-09-17 fetched early on the 18th UTC), so the
"scheduled this week" and "next scheduled" branches and a real data change
between runs are all exercised. Every check reads the snapshot the site was
built from and compares the page with it: nothing on a page may be more
specific, or more hopeful, than the data.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

# Every schema.org type the site may emit. A new one is a decision to record
# in docs/adr/0013, not something that should slip in with a template edit.
ALLOWED_TYPES = {
    "WebSite",
    "WebPage",
    "CollectionPage",
    "BreadcrumbList",
    "ListItem",
    "BodyOfWater",
    "AdministrativeArea",
    "State",
    "PropertyValue",
    "Dataset",
    "DataDownload",
    "CreativeWork",
    "GovernmentOrganization",
    "Organization",
}
# A planting is a scheduled week, never a day or a time (CDFW publishes the
# week only, and every plant is subject to change): no Event, and none of the
# properties that would pin one to a date.
BANNED_KEYS = {
    "startDate",
    "endDate",
    "doorTime",
    "eventStatus",
    "geo",
    "latitude",
    "longitude",
}

_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _run(
    root: Path, fixture: Path, fetched_at: dt.datetime, today: dt.date, **extra: Any
) -> dict[str, Any]:
    return cli.run(
        fixture_path=str(fixture),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=fetched_at,
        run_today=today,
        **extra,
    )


def _run_fresh(root: Path, **extra: Any) -> dict[str, Any]:
    return _run(
        root,
        FRESH,
        dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 13),
        **extra,
    )


def _run_midweek(root: Path, **extra: Any) -> dict[str, Any]:
    return _run(
        root,
        MIDWEEK,
        dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        dt.date(2026, 9, 18),
        **extra,
    )


@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    root = tmp_path_factory.mktemp("seo-fresh")
    snap = _run_fresh(root)
    return root / "site", snap


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Any]]:
    """The site after both runs: the one most checks read."""
    root = tmp_path_factory.mktemp("seo-two-runs")
    _run_fresh(root)
    snap = _run_midweek(root)
    return root / "site", snap


def _html(out: Path, rel: str) -> str:
    return (out / rel / "index.html").read_text(encoding="utf-8")


def _ld(html: str) -> dict[str, Any] | None:
    blocks = _LD.findall(html)
    assert len(blocks) <= 1
    return json.loads(blocks[0]) if blocks else None


def _nodes(value: Any) -> list[dict[str, Any]]:
    """Every JSON object in a structured-data tree, nested ones included."""
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for v in value.values():
            found += _nodes(v)
    elif isinstance(value, list):
        for v in value:
            found += _nodes(v)
    return found


def _graph(html: str) -> dict[str, dict[str, Any]]:
    data = _ld(html)
    assert data is not None
    assert data["@context"] == "https://schema.org"
    return {n["@type"]: n for n in data["@graph"]}


def _visible_text(html: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script\b[^>]*>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _page_for(out: Path, url: str) -> Path:
    """The built file a same-site URL resolves to."""
    assert url.startswith(BASE_URL + "/"), url
    rel = url[len(BASE_URL) + 1 :].split("#", 1)[0]
    return out / rel / "index.html" if rel == "" or rel.endswith("/") else out / rel


def _county_waters(snap: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for w in snap["waters"]:
        for c in w["counties"]:
            by.setdefault(c, []).append(w)
    return by


def _hrefs(fragment: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', fragment)


def _section(html: str, start: str, end: str) -> str:
    i = html.index(start)
    return html[i : html.index(end, i + len(start))]


# ---- county pages


def test_the_fixtures_exercise_this_week_upcoming_and_nothing_current(built):
    """The checks below are only meaningful if the build has all three
    kinds of water; a fixture change that loses one must fail loudly."""
    _, snap = built
    week = snap["source_week"]["start"]
    starts = [
        {p["week"]["start"] for p in w["plants"] if p["status"] == "listed"}
        for w in snap["waters"]
    ]
    assert any(week in s for s in starts)
    assert any(any(x > week for x in s) and week not in s for s in starts)
    assert any(all(x < week for x in s) for s in starts)
    assert snap["this_week"]


def test_a_page_for_every_county_with_a_water_and_no_other(built):
    out, snap = built
    counties = _county_waters(snap)
    built_slugs = {d.name for d in (out / "county").iterdir() if d.is_dir()}
    assert built_slugs == {site.county_slug(c) for c in counties}
    index = _html(out, "county")
    for c in counties:
        assert f'href="../county/{site.county_slug(c)}/"' in index, c


def test_county_page_lists_exactly_its_waters_with_their_latest_week(built):
    out, snap = built
    week = snap["source_week"]["start"]
    for county, members in _county_waters(snap).items():
        html = _html(out, f"county/{site.county_slug(county)}")
        table = _section(html, "<h2>Every ", "</table>")
        rows = re.findall(
            r'<td><a href="\.\./\.\./water/([^/]+)/">[^<]*</a></td>\s*<td>([^<]*)</td>',
            table,
        )
        assert {slug for slug, _ in rows} == {w["slug"] for w in members}, county
        by_slug = {w["slug"]: w for w in members}
        for slug, cell in rows:
            listed = [
                p["week"]["start"]
                for p in by_slug[slug]["plants"]
                if p["status"] == "listed"
            ]
            latest = max(listed)
            expected = f"week of {latest}" + (" (upcoming)" if latest > week else "")
            assert cell == expected, (county, slug, cell)
        # most recently scheduled first
        starts = [cell.split(" ")[2] for _, cell in rows]
        assert starts == sorted(starts, reverse=True), county


def test_county_page_this_week_list_matches_the_snapshot(built):
    out, snap = built
    waters_by_id = {w["id"]: w for w in snap["waters"]}
    for county in _county_waters(snap):
        html = _html(out, f"county/{site.county_slug(county)}")
        section = _section(html, "<h2>Scheduled this week</h2>", "<h2>")
        expected = {
            waters_by_id[e["water_id"]]["slug"]
            for e in snap["this_week"]
            if county in waters_by_id[e["water_id"]]["counties"]
        }
        listed = {h.split("/")[-2] for h in _hrefs(section)}
        assert listed == expected, county
        if not expected:
            assert (
                f"No {county} County water is on CDFW's schedule for this week."
                in section
            )
            assert "not that there are no fish" in section


def test_county_titles_name_the_county_and_the_search_terms(built):
    out, snap = built
    titles = []
    for county in _county_waters(snap):
        html = _html(out, f"county/{site.county_slug(county)}")
        title = re.search(r"<title>([^<]+)</title>", html).group(1)
        h1 = re.search(r"<h1>([^<]+)</h1>", html).group(1)
        assert title.startswith(f"{county} County ") and "planting schedule" in title
        assert "fish plants this week" in title
        assert h1.startswith(f"{county} County ") and h1.endswith("planting schedule")
        titles.append(title)
    assert len(titles) == len(set(titles))


# ---- water pages: links from data, never invented


def test_water_page_links_its_county_pages_and_every_other_water_in_them(built):
    """ "Other waters" means sharing a county, the only proximity the snapshot
    supports (it has no locations). The list is exactly that set."""
    out, snap = built
    counties = _county_waters(snap)
    for w in snap["waters"]:
        html = _html(out, f"water/{w['slug']}")
        for c in w["counties"]:
            slug = site.county_slug(c)
            assert f'href="../../county/{slug}/">{c} County</a>' in html
            section = _section(
                html, f'<section aria-labelledby="others-{slug}">', "</section>"
            )
            linked = {h.split("/")[-2] for h in _hrefs(section) if "/water/" in h}
            expected = {s["slug"] for s in counties[c] if s["id"] != w["id"]}
            assert linked == expected, (w["slug"], c)
        assert "nearby" not in _visible_text(html).lower()


def test_absence_is_said_plainly_and_never_as_no_fish(built):
    out, snap = built
    week = snap["source_week"]["start"]
    checked = 0
    for w in snap["waters"]:
        text = _visible_text(_html(out, f"water/{w['slug']}"))
        listed = {p["week"]["start"] for p in w["plants"] if p["status"] == "listed"}
        current = any(s >= week for s in listed)
        plain = f"Nothing is on CDFW's schedule for {w['name']} this week or later."
        assert (plain in text) is (not current), w["slug"]
        if not current:
            assert "not that there are no fish" in text
            checked += 1
        if week in listed:
            assert (
                f"It is scheduled for planting this week, the week of {week}." in text
            )
    assert checked
    for f in out.rglob("*.html"):
        assert _no_fish_claims(f.read_text(encoding="utf-8")) == [], f


def _no_fish_claims(html: str) -> list[str]:
    """Every "no fish" on the page that is not the disclaimer "not that there
    are no fish"."""
    text = _visible_text(html).lower()
    return [
        text[max(0, m.start() - 30) : m.end() + 10]
        for m in re.finditer(r"no fish", text)
        if text[max(0, m.start() - 19) : m.start()] != "not that there are "
    ]


def test_no_fish_checker_is_not_vacuous(built):
    """Negative control: the disclaimer passes, a bare claim does not."""
    out, snap = built
    html = _html(out, f"water/{snap['waters'][0]['slug']}")
    sabotaged = html.replace("</main>", "<p>No fish this week.</p></main>", 1)
    assert sabotaged != html  # the sabotage landed
    assert _no_fish_claims(sabotaged)
    assert _no_fish_claims("<p>That means X, not that there are no fish.</p>") == []


# ---- structured data


def _structured_data_problems(data: Any) -> list[str]:
    problems = []
    for node in _nodes(data):
        kind = node.get("@type")
        if kind is not None and (kind not in ALLOWED_TYPES or "Event" in kind):
            problems.append(f"type {kind}")
        problems += [f"key {k}" for k in sorted(BANNED_KEYS & node.keys())]
    return problems


def test_every_structured_data_type_is_allowed_and_nothing_is_an_event(built):
    out, _ = built
    seen: set[str] = set()
    for f in out.rglob("*.html"):
        data = _ld(f.read_text(encoding="utf-8"))
        if data is None:
            continue
        assert _structured_data_problems(data) == [], f
        seen |= {n["@type"] for n in _nodes(data) if "@type" in n}
    # the allowlist is not wider than what is used
    assert seen == ALLOWED_TYPES


def test_structured_data_checker_catches_an_event_and_a_date(built):
    """Negative control: a planting written as an Event with a startDate,
    and a water given coordinates, are both caught."""
    out, snap = built
    data = _ld(_html(out, f"water/{snap['waters'][0]['slug']}"))
    assert _structured_data_problems(data) == []
    sabotaged = copy.deepcopy(data)
    sabotaged["@graph"].append(
        {"@type": "Event", "name": "Trout plant", "startDate": "2026-09-13"}
    )
    sabotaged["@graph"][-2]["geo"] = {"latitude": 0, "longitude": 0}
    assert sabotaged != data  # the sabotage landed
    assert set(_structured_data_problems(sabotaged)) == {
        "type Event",
        "key startDate",
        "key geo",
        "key latitude",
        "key longitude",
    }


def test_pages_without_structured_data(built):
    out, _ = built
    for rel in ("privacy", "support"):
        assert _ld(_html(out, rel)) is None
    assert _ld((out / "404.html").read_text(encoding="utf-8")) is None


def test_home_page_carries_the_website_and_only_it_does(built):
    out, _ = built
    g = _graph(_html(out, ""))
    assert set(g) == {"WebSite"}
    assert g["WebSite"]["@id"] == f"{BASE_URL}/#website"
    assert g["WebSite"]["url"] == f"{BASE_URL}/"
    assert g["WebSite"]["name"] == site.SITE_NAME
    # no sitelinks search box: Google retired it, and the site has no search
    assert "potentialAction" not in g["WebSite"]
    for f in out.rglob("*.html"):
        if f != out / "index.html":
            data = _ld(f.read_text(encoding="utf-8"))
            assert not any(n.get("@type") == "WebSite" for n in _nodes(data)), f


def test_breadcrumbs_mirror_the_visible_trail_and_resolve_to_built_pages(built):
    out, snap = built
    pages = [f"water/{w['slug']}" for w in snap["waters"]]
    pages += [f"county/{site.county_slug(c)}" for c in _county_waters(snap)]
    pages.append("county")
    for rel in pages:
        html = _html(out, rel)
        crumbs = _graph(html)["BreadcrumbList"]["itemListElement"]
        assert [c["position"] for c in crumbs] == list(range(1, len(crumbs) + 1))
        assert all(c["@type"] == "ListItem" and c["name"] and c["item"] for c in crumbs)
        canonical = re.search(r'<link rel="canonical" href="([^"]+)">', html).group(1)
        assert crumbs[-1]["item"] == canonical
        for c in crumbs:
            assert _page_for(out, c["item"]).exists(), (rel, c["item"])
        nav = _section(html, '<nav aria-label="Breadcrumb"', "</nav>")
        visible = re.findall(r"<a [^>]*>([^<]+)</a>", nav)
        assert visible == [c["name"].replace("'", "&#39;") for c in crumbs], rel
        assert nav.count('aria-current="page"') == 1


def test_water_structured_data_states_only_what_the_snapshot_has(built):
    out, snap = built
    for w in snap["waters"]:
        page_url = f"{BASE_URL}/water/{w['slug']}/"
        g = _graph(_html(out, f"water/{w['slug']}"))
        assert set(g) == {"WebPage", "BreadcrumbList", "BodyOfWater"}
        water = g["BodyOfWater"]
        assert water["@id"] == f"{page_url}#water"
        assert g["WebPage"]["about"] == {"@id": water["@id"]}
        assert water["name"] == w["name"]
        assert water["hasMap"] == w["cdfw_map_url"]
        assert water["identifier"]["value"] == str(w["cdfw_stock_id"])
        assert [p["name"] for p in water["containedInPlace"]] == [
            f"{c} County" for c in w["counties"]
        ]
        others = [n for n in w["aliases"] if n != w["name"]]
        assert water.get("alternateName", []) == others
        # the snapshot has no location for any water, so no coordinates
        assert w["location"] is None
        assert not {"geo", "address", "latitude", "longitude"} & water.keys()
        crumbs = [c["name"] for c in g["BreadcrumbList"]["itemListElement"]]
        assert crumbs == [
            site.SITE_NAME,
            "Counties",
            f"{w['counties'][0]} County",
            w["name"],
        ]


def test_dataset_describes_the_history_with_cdfw_as_source_and_no_unchosen_licence(
    built,
):
    out, snap = built
    g = _graph(_html(out, "about"))
    assert set(g) == {"Dataset"}
    ds = g["Dataset"]
    # Google's Dataset requirements: name, and a description of 50-5000 chars
    assert ds["name"]
    assert 50 <= len(ds["description"]) <= 5000
    assert ds["url"] == f"{BASE_URL}/about/#data"
    assert 'id="data"' in _html(out, "about")
    [download] = ds["distribution"]
    assert download["contentUrl"] == f"{BASE_URL}/snapshot/v1.json"
    assert download["encodingFormat"] == "application/json"
    assert (out / "snapshot" / "v1.json").exists()
    weeks = [p["week"] for w in snap["waters"] for p in w["plants"]]
    assert (
        ds["temporalCoverage"]
        == f"{min(x['start'] for x in weeks)}/{max(x['end'] for x in weeks)}"
    )
    assert ds["creditText"] == snap["attribution"]["text"]
    assert ds["isBasedOn"]["url"] == snap["source"]["url"]
    assert (
        ds["isBasedOn"]["creator"]["name"]
        == "California Department of Fish and Wildlife"
    )
    assert ds["isBasedOn"]["license"] == "https://wildlife.ca.gov/Conditions-of-Use"
    # CC-BY belongs to a different CDFW dataset; no licence is claimed for
    # the compiled history until the owner chooses one
    assert site.DATASET_LICENSE_URL == ""
    assert "license" not in ds
    assert "creativecommons" not in json.dumps(ds).lower()
    # "the week the data changed", not the build date
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    home = re.search(
        rf"<loc>{re.escape(BASE_URL)}/</loc><lastmod>([^<]+)</lastmod>", sitemap
    )
    assert ds["dateModified"] == home.group(1)


def test_dataset_licence_appears_only_when_configured(fresh, tmp_path):
    _, snap = fresh
    licence = "https://creativecommons.org/licenses/by/4.0/"
    site.build_site(
        snap, tmp_path / "s", base_url=BASE_URL, dataset_license_url=licence
    )
    assert _graph(_html(tmp_path / "s", "about"))["Dataset"]["license"] == licence


def test_a_water_name_cannot_break_out_of_the_structured_data(fresh, tmp_path):
    _, snap = fresh
    hostile = copy.deepcopy(snap)
    name = 'Evil Lake</script><script>alert("x")</script>'
    hostile["waters"][0]["name"] = name
    hostile["waters"][0]["aliases"] = [name]
    out = tmp_path / "s"
    site.build_site(hostile, out, base_url=BASE_URL)
    html = _html(out, f"water/{hostile['waters'][0]['slug']}")
    assert len(re.findall(r"<script\b", html, re.I)) == 1  # the JSON-LD block only
    assert _graph(html)["BodyOfWater"]["name"] == name
    assert "</script><script>" not in html


# ---- sitemap and robots.txt


def test_sitemap_lists_every_indexable_page_exactly_once(built):
    out, _ = built
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
    assert len(locs) == len(set(locs))
    pages = {
        f"{BASE_URL}/{f.parent.relative_to(out).as_posix()}/".replace(
            f"{BASE_URL}/./", f"{BASE_URL}/"
        )
        for f in out.rglob("index.html")
    }
    assert set(locs) == pages
    assert "404" not in sitemap


def test_sitemap_lastmod_follows_the_data_not_the_build(built, fresh):
    """Between the two runs CDFW added 29 plants. A page's lastmod moves to
    the day that change was fetched (2026-09-18 UTC) only if its data
    changed; every other page keeps the first run's date. No lastmod is the
    day the tests run."""
    out, snap = built
    fresh_out, _ = fresh
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    lastmod = dict(re.findall(r"<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>", sitemap))
    assert set(lastmod.values()) <= {"2026-09-13", "2026-09-18"}
    fresh_ids = {
        w["id"]
        for w in json.loads(
            (fresh_out / "snapshot" / "v1.json").read_text(encoding="utf-8")
        )["waters"]
    }
    counties = _county_waters(snap)
    week = snap["source_week"]["start"]
    changed = {
        w["id"]
        for w in snap["waters"]
        if any(p["first_observed_at"].startswith("2026-09-18") for p in w["plants"])
    }
    assert changed  # the fixture pair really changes some waters
    new_waters = {w["id"] for w in snap["waters"]} - fresh_ids
    unchanged_seen = False
    for w in snap["waters"]:
        url = f"{BASE_URL}/water/{w['slug']}/"
        gained_sibling = any(
            s["id"] in new_waters
            for c in w["counties"]
            for s in counties[c]
            if s["id"] != w["id"]
        )
        rollover_from = (dt.date.fromisoformat(week) - dt.timedelta(days=7)).isoformat()
        near = any(
            p["status"] == "listed" and p["week"]["start"] >= rollover_from
            for p in w["plants"]
        )
        if w["id"] in changed or gained_sibling:
            assert lastmod[url] == "2026-09-18", w["slug"]
        elif near:
            assert lastmod[url] == week, w["slug"]  # the rollover rule
        else:
            assert lastmod[url] == "2026-09-13", w["slug"]
            unchanged_seen = True
    assert unchanged_seen
    for c, members in counties.items():
        url = f"{BASE_URL}/county/{site.county_slug(c)}/"
        expected = (
            "2026-09-18" if any(m["id"] in changed for m in members) else "2026-09-13"
        )
        assert lastmod[url] == expected, c
    assert lastmod[f"{BASE_URL}/"] == "2026-09-18"


def test_no_lastmod_is_the_build_date(fresh):
    """The fixture was fetched 2026-09-13; the build runs on whatever day the
    tests do. A constant build-date lastmod is the crawl-budget lie."""
    out, _ = fresh
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    lastmods = set(re.findall(r"<lastmod>([^<]+)</lastmod>", sitemap))
    assert lastmods == {"2026-09-13"}
    assert f"{BASE_URL}/county/</loc><lastmod>2026-09-13" in sitemap


def test_robots_txt_points_at_the_sitemap(fresh):
    out, _ = fresh
    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert f"Sitemap: {BASE_URL}/sitemap.xml" in robots.splitlines()
    assert "Disallow: /" not in robots


# ---- Google Search Console verification (owner-set token)


def test_committed_verification_token_is_empty_or_well_formed():
    value = site.GOOGLE_SITE_VERIFICATION
    assert value == "" or site.google_site_verification_or_none(value) == value


@pytest.mark.parametrize("value", [None, ""])
def test_unset_verification_token_means_none(value):
    assert site.google_site_verification_or_none(value) is None


@pytest.mark.parametrize(
    "value",
    [
        '<meta name="google-site-verification" content="abcDEF123_-xyz0987654">',
        "abcDEF123 xyz0987654",
        '"abcDEF123_-xyz0987654"',
        "short",
    ],
)
def test_malformed_verification_token_is_refused(value):
    with pytest.raises(ValueError):
        site.google_site_verification_or_none(value)


def test_no_verification_tag_unless_configured(built):
    out, _ = built
    for f in out.rglob("*.html"):
        assert "google-site-verification" not in f.read_text(encoding="utf-8"), f


def test_verification_tag_goes_on_the_home_page_only(tmp_path, monkeypatch):
    verification = "abcDEF123_-xyz0987654321ABCdef-_ghiJKL0987"
    monkeypatch.setattr(site, "GOOGLE_SITE_VERIFICATION", verification)
    argv = [
        "--fixture", str(FRESH),
        "--fixture-fetched-at", "2026-09-13T12:00:00Z",
        "--run-today", "2026-09-13",
        "--history", str(tmp_path / "history.json"),
        "--aliases", str(tmp_path / "aliases.json"),
        "--site-out", str(tmp_path / "site"),
        "--base-url", BASE_URL,
    ]  # fmt: skip
    assert cli.main(argv) == 0
    out = tmp_path / "site"
    home = _html(out, "")
    assert f'<meta name="google-site-verification" content="{verification}">' in home
    assert home.index("google-site-verification") < home.index("</head>")
    for f in out.rglob("*.html"):
        if f != out / "index.html":
            assert "google-site-verification" not in f.read_text(encoding="utf-8"), f


def test_cli_refuses_a_malformed_committed_token_before_writing_anything(
    tmp_path, monkeypatch, capsys
):
    bad = '<meta name="google-site-verification" content="abc">'
    monkeypatch.setattr(site, "GOOGLE_SITE_VERIFICATION", bad)
    assert bad == site.GOOGLE_SITE_VERIFICATION  # the sabotage landed
    argv = ["--fixture", str(FRESH), "--run-today", "2026-09-13", "--history", str(tmp_path / "h.json"),
            "--aliases", str(tmp_path / "a.json"), "--site-out", str(tmp_path / "site")]  # fmt: skip
    assert cli.main(argv) == 1
    assert "run refused" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
