"""Past-week pages (/week/YYYY-MM-DD/) and their index (/week/).

Everything is built from the pinned fixtures, never from the daily data files.
The expected page set is computed from the history file the run wrote, by a
different route than the site uses (history records, not the snapshot's
plants). HTML is read with html.parser, never with a regular expression.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site, weeks

WEEK_MIN = weeks.WEEK_INDEX_MIN_WATERS

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
BANNED_WORDS = {"only", "first", "best", "top", "unique", "stocked", "colour"}
BANNED_PHRASES = ("planted on", "stocked on")
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.canonicals: list[str] = []
        self.hrefs: list[str] = []
        self.ld: list[str] = []
        self.text: list[str] = []
        self.h1: list[str] = []
        self.crumbs: list[tuple[str, str]] = []
        self.water_hrefs: list[str] = []
        self._stack: list[str] = []
        self._ld = False
        self._crumb = False
        self._href = ""
        self._label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag not in {"meta", "link", "br", "img", "hr", "input"}:
            self._stack.append(tag)
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonicals.append(a.get("href", ""))
        if tag == "script" and a.get("type") == "application/ld+json":
            self._ld = True
        if tag == "nav" and a.get("aria-label") == "Breadcrumb":
            self._crumb = True
        if tag == "a":
            self._href = a.get("href", "")
            self._label = []
            self.hrefs.append(self._href)
            if self._href.startswith("../../water/"):
                self.water_hrefs.append(self._href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._crumb:
            self.crumbs.append(("".join(self._label).strip(), self._href))
        if tag == "nav":
            self._crumb = False
        if tag == "script":
            self._ld = False
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ld:
            self.ld.append(data)
            return
        top = self._stack[-1] if self._stack else ""
        if top == "title":
            self.title += data
            return
        if "head" in self._stack:
            return
        if top == "h1":
            self.h1.append(data)
        self._label.append(data)
        self.text.append(data)

    @property
    def visible(self) -> str:
        return " ".join("".join(self.text).split())


def _parse(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def _words(text: str) -> set[str]:
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return set(cleaned.split())


def _run(
    root: Path, fixture: str, fetched_at: dt.datetime, today: dt.date
) -> dict[str, Any]:
    return cli.run(
        fixture_path=str(FIXTURES / fixture),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url=BASE_URL,
        fixture_fetched_at=fetched_at,
        run_today=today,
    )


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, Any], Path]:
    root = tmp_path_factory.mktemp("weeks")
    _run(
        root,
        "schedule-fresh-2026-09-13.html",
        dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        dt.date(2026, 9, 13),
    )
    snap = _run(
        root,
        "schedule-midweek-2026-09-17.html",
        dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        dt.date(2026, 9, 18),
    )
    return root / "site", snap, root / "history.json"


def _expected_from_history(
    history_path: Path, snap: dict[str, Any]
) -> dict[str, set[str]]:
    """Week start -> water slugs, from the history file's own records: listed
    only, and only weeks that start before the snapshot's current week."""
    slug_by_stock = {w["cdfw_stock_id"]: w["slug"] for w in snap["waters"]}
    current = snap["source_week"]["start"]
    out: dict[str, set[str]] = {}
    for rec in json.loads(history_path.read_text(encoding="utf-8"))["plants"]:
        if rec["status"] == "listed" and rec["week_start"] < current:
            out.setdefault(rec["week_start"], set()).add(
                slug_by_stock[rec["cdfw_stock_id"]]
            )
    return out


def _week_dirs(out: Path) -> set[str]:
    base = out / "week"
    return {d.name for d in base.iterdir() if d.is_dir()} if base.exists() else set()


def _page_slugs(out: Path, start: str) -> set[str]:
    page = _parse(out / "week" / start / "index.html")
    return {h.split("/")[3] for h in page.water_hrefs}


def test_the_page_set_equals_the_independent_computation_from_history(built):
    out, snap, history = built
    expected = _expected_from_history(history, snap)
    # Not vacuous: the fixtures give several past weeks.
    assert len(expected) >= 3
    assert _week_dirs(out) == set(expected)
    for start, slugs in expected.items():
        assert _page_slugs(out, start) == slugs, start


def test_the_current_week_has_no_page_and_the_home_page_is_linked(built):
    out, snap, _ = built
    current = snap["source_week"]["start"]
    assert current not in _week_dirs(out)
    assert not any(d > current for d in _week_dirs(out))
    page = _parse(out / "week" / sorted(_week_dirs(out))[0] / "index.html")
    assert "../../" in page.hrefs  # the home page


def test_removed_entries_are_excluded(built, tmp_path: Path):
    """Mark every plant of one past week's first water removed: the sabotage
    must apply, and the water must leave that page (and the page must go when
    nothing is left)."""
    out, snap, history = built
    expected = _expected_from_history(history, snap)
    start = max(expected, key=lambda s: len(expected[s]))
    assert len(expected[start]) >= 2
    mutated = copy.deepcopy(snap)
    victim = next(
        w
        for w in mutated["waters"]
        if w["slug"] in expected[start]
        and any(p["week"]["start"] == start for p in w["plants"])
    )
    hit = 0
    for p in victim["plants"]:
        if p["week"]["start"] == start:
            p["status"] = "removed"
            hit += 1
    assert hit >= 1  # the sabotage applied
    assert not any(
        p["status"] == "listed" and p["week"]["start"] == start
        for p in victim["plants"]
    )
    site.build_site(mutated, tmp_path / "site", base_url=BASE_URL)
    assert victim["slug"] in _page_slugs(out, start)  # the unmodified build has it
    assert _page_slugs(tmp_path / "site", start) == expected[start] - {victim["slug"]}

    # A week whose every entry is removed has no page at all.
    for w in mutated["waters"]:
        for p in w["plants"]:
            if p["week"]["start"] == start:
                p["status"] = "removed"
    assert not any(
        p["status"] == "listed" and p["week"]["start"] == start
        for w in mutated["waters"]
        for p in w["plants"]
    )
    site.build_site(mutated, tmp_path / "site2", base_url=BASE_URL)
    assert start not in _week_dirs(tmp_path / "site2")
    assert start in _week_dirs(out)


def test_no_week_page_is_empty(built):
    out, _, _ = built
    for start in _week_dirs(out):
        page = _parse(out / "week" / start / "index.html")
        assert page.water_hrefs, start
        assert "listed 0 " not in page.visible


def test_a_snapshot_with_no_past_week_writes_no_week_pages(built, tmp_path: Path):
    _, snap, _ = built
    mutated = copy.deepcopy(snap)
    current = mutated["source_week"]["start"]
    for w in mutated["waters"]:
        for p in w["plants"]:
            if p["week"]["start"] < current:
                p["status"] = "removed"
    assert not weeks.week_entries(mutated)
    site.build_site(mutated, tmp_path / "site", base_url=BASE_URL)
    assert not (tmp_path / "site" / "week").exists()
    sitemap = (tmp_path / "site" / "sitemap.xml").read_text(encoding="utf-8")
    assert "/week/" not in sitemap
    home = _parse(tmp_path / "site" / "index.html")
    assert "./week/" not in home.hrefs


def test_each_page_names_the_week_the_count_and_the_source(built):
    out, snap, history = built
    expected = _expected_from_history(history, snap)
    for start, slugs in expected.items():
        page = _parse(out / "week" / start / "index.html")
        n = len(slugs)
        noun = "water" if n == 1 else "waters"
        assert page.h1 == [f"CDFW planting schedule: week of {start}"]
        assert (
            f"CDFW's schedule listed {n} {noun} for the week of {start}" in page.visible
        )
        assert "CDFW's schedule for that week" in page.visible
        assert "subject to change" in page.visible
        assert "scheduled, not confirmed" in page.visible
        # Each listed water appears under every county it is in, linked.
        by_slug = {w["slug"]: w for w in snap["waters"]}
        assert len(page.water_hrefs) == sum(
            max(len(by_slug[s]["counties"]), 1) for s in slugs
        )


def test_seo_surface_title_description_canonical_breadcrumb_ld(built):
    out, _, _ = built
    for start in sorted(_week_dirs(out)):
        page = _parse(out / "week" / start / "index.html")
        url = f"{BASE_URL}/week/{start}/"
        assert page.canonicals == [url]
        assert page.title == f"CDFW planting schedule, week of {start} | Trout Truck"
        assert len(page.title) < 60
        desc = page.meta["description"]
        assert start in desc
        assert "planting schedule" in desc and "planting schedule" in page.title
        assert len(desc) < 155
        ld = json.loads("".join(page.ld))
        nodes = {n["@type"]: n for n in ld["@graph"]}
        assert set(nodes) == {"CollectionPage", "BreadcrumbList"}
        assert nodes["CollectionPage"]["url"] == url
        trail = [
            (i["name"], i["item"]) for i in nodes["BreadcrumbList"]["itemListElement"]
        ]
        assert trail == [
            ("Trout Truck", f"{BASE_URL}/"),
            ("Weeks", f"{BASE_URL}/week/"),
            (f"Week of {start}", url),
        ]
        assert [n for n, _ in page.crumbs] == [n for n, _ in trail]
        blob = json.dumps(ld)
        for key in ("Event", "startDate", "endDate", "eventStatus"):
            assert key not in blob


def test_the_longest_possible_title_and_description_fit():
    assert len(weeks.week_title("2026-09-06", site.SITE_NAME)) < 60
    assert len(weeks.week_description("2026-09-06", 999)) < 155


def test_the_index_lists_every_page_most_recent_to_oldest_with_counts(built):
    out, snap, history = built
    expected = _expected_from_history(history, snap)
    page = _parse(out / "week" / "index.html")
    assert page.canonicals == [f"{BASE_URL}/week/"]
    assert page.h1 == ["CDFW planting schedule by week"]
    linked = [h for h in page.hrefs if h.startswith("../week/2")]
    assert linked == [f"../week/{s}/" for s in sorted(expected, reverse=True)]
    assert "../" in page.hrefs  # this week is the home page
    assert len(page.title) < 60 and len(page.meta["description"]) < 155
    for start, slugs in expected.items():
        assert f"Week of {start} {len(slugs)}" in page.visible


def test_titles_and_descriptions_are_unique_across_all_page_kinds(built):
    out, _, _ = built
    seen_t: dict[str, Path] = {}
    seen_d: dict[str, Path] = {}
    for path in sorted(out.rglob("index.html")):
        page = _parse(path)
        for value, seen in (
            (page.title, seen_t),
            (page.meta.get("description", ""), seen_d),
        ):
            assert value, path
            assert value not in seen, (path, seen[value])
            seen[value] = path
    # Every page of every kind was scanned, the new ones among them.
    assert len(seen_t) == len(list(out.rglob("index.html"))) > len(_week_dirs(out)) + 50


def test_negative_control_the_uniqueness_scan_can_fail(built, tmp_path: Path):
    out, _, _ = built
    start = sorted(_week_dirs(out))[0]
    copy_dir = tmp_path / "dup"
    copy_dir.mkdir()
    src = (out / "week" / start / "index.html").read_text(encoding="utf-8")
    (copy_dir / "index.html").write_text(src, encoding="utf-8")
    a, b = _parse(out / "week" / start / "index.html"), _parse(copy_dir / "index.html")
    assert a.title == b.title  # the sabotage applied: a duplicate title exists
    assert [a.title, b.title].count(a.title) == 2


def test_copy_rules_across_both_page_kinds(built):
    out, _, _ = built
    paths = [out / "week" / "index.html"] + [
        out / "week" / s / "index.html" for s in _week_dirs(out)
    ]
    for path in paths:
        page = _parse(path)
        text = page.visible + " " + page.meta["description"] + " " + page.title
        assert not (_words(text) & BANNED_WORDS), (path, _words(text) & BANNED_WORDS)
        for phrase in BANNED_PHRASES:
            assert phrase not in text.lower(), (path, phrase)
        assert not ({"colour", "favourite", "licence", "centre"} & _words(text))
        assert "confirmed" not in text.lower().replace("not confirmed", "")


def test_negative_control_the_word_scan_can_fail():
    probe = "The best only way to see stocked fish"
    assert _words(probe) & BANNED_WORDS == {"best", "only", "stocked"}
    assert not (_words("CDFW's schedule listed 3 waters; not confirmed") & BANNED_WORDS)


def test_the_sitemap_has_exactly_the_new_urls_with_a_lastmod_from_the_data(built):
    out, snap, history = built
    expected = _expected_from_history(history, snap)
    root = ET.fromstring((out / "sitemap.xml").read_text(encoding="utf-8"))
    entries = {
        u.findtext("s:loc", namespaces=SITEMAP_NS): u.findtext(
            "s:lastmod", namespaces=SITEMAP_NS
        )
        for u in root.findall("s:url", SITEMAP_NS)
    }
    week_urls = {u for u in entries if u.startswith(f"{BASE_URL}/week/")}
    indexed = {s for s, slugs in expected.items() if len(slugs) >= WEEK_MIN}
    assert indexed and indexed != set(expected)  # both sides are non-empty
    assert week_urls == {f"{BASE_URL}/week/"} | {
        f"{BASE_URL}/week/{s}/" for s in indexed
    }
    # lastmod for a week: the most recent to oldest_observed_at / removal date among the
    # history records of that week, computed here from the history file.
    records = json.loads(history.read_text(encoding="utf-8"))["plants"]
    for start in indexed:
        dates = [
            r["first_observed_at"][:10] for r in records if r["week_start"] == start
        ]
        dates += [
            r["last_observed_at"][:10]
            for r in records
            if r["week_start"] == start and r["status"] == "removed"
        ]
        assert entries[f"{BASE_URL}/week/{start}/"] == max(dates), start
    index_mod = entries[f"{BASE_URL}/week/"]
    assert index_mod is not None
    assert index_mod <= snap["generated_at"][:10]


def test_a_past_week_page_does_not_change_when_only_the_day_does(built, tmp_path: Path):
    """Rebuild the same data a week later with only the freshness fields
    moved: every past-week page keeps its visible text, title, description and
    structured data, and its sitemap lastmod."""
    out, snap, _ = built
    later = copy.deepcopy(snap)
    later["generated_at"] = "2026-09-19T03:10:18Z"
    later["source"]["fetched_at"] = "2026-09-19T03:10:18Z"
    assert later["source"]["fetched_at"] != snap["source"]["fetched_at"]
    # Both sides go through build_site, so neither has the open-data link
    # that only cli.run's build adds.
    site.build_site(snap, tmp_path / "base", base_url=BASE_URL)
    site.build_site(later, tmp_path / "site", base_url=BASE_URL)
    assert _week_dirs(tmp_path / "site") == _week_dirs(out)
    for start in _week_dirs(out):
        a = _parse(tmp_path / "base" / "week" / start / "index.html")
        b = _parse(tmp_path / "site" / "week" / start / "index.html")
        assert (a.visible, a.title, a.meta["description"], a.ld) == (
            b.visible,
            b.title,
            b.meta["description"],
            b.ld,
        )

    def lastmods(root: Path) -> dict[str | None, str | None]:
        tree = ET.fromstring((root / "sitemap.xml").read_text(encoding="utf-8"))
        return {
            u.findtext("s:loc", namespaces=SITEMAP_NS): u.findtext(
                "s:lastmod", namespaces=SITEMAP_NS
            )
            for u in tree.findall("s:url", SITEMAP_NS)
            if "/week/" in (u.findtext("s:loc", namespaces=SITEMAP_NS) or "")
        }

    assert lastmods(tmp_path / "site") == lastmods(tmp_path / "base")
    assert lastmods(tmp_path / "base")


def test_links_into_the_archive_exist_from_home_and_the_county_index(built):
    out, _, _ = built
    assert "./week/" in _parse(out / "index.html").hrefs
    assert "../week/" in _parse(out / "county" / "index.html").hrefs
    page = _parse(out / "week" / sorted(_week_dirs(out))[0] / "index.html")
    assert "../../week/" in page.hrefs
    assert "../../county/" in page.hrefs


class _Robots(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "robots":
            self.found.append(a.get("content") or "")


def _robots(path: Path) -> list[str]:
    r = _Robots()
    r.feed(path.read_text(encoding="utf-8"))
    return r.found


def _sitemap_locs(root: Path) -> set[str]:
    tree = ET.fromstring((root / "sitemap.xml").read_text(encoding="utf-8"))
    return {
        u.findtext("s:loc", namespaces=SITEMAP_NS) or ""
        for u in tree.findall("s:url", SITEMAP_NS)
    }


def test_the_threshold_constant_is_eight():
    assert weeks.WEEK_INDEX_MIN_WATERS == 8


def test_thin_weeks_are_noindex_follow_and_out_of_the_sitemap(built):
    out, snap, history = built
    expected = _expected_from_history(history, snap)
    locs = _sitemap_locs(out)
    thin = {s for s, v in expected.items() if len(v) < WEEK_MIN}
    full = set(expected) - thin
    assert thin and full
    for s in thin:
        page = out / "week" / s / "index.html"
        assert page.exists()  # still built and reachable
        assert _robots(page) == ["noindex,follow"], s
        assert f"{BASE_URL}/week/{s}/" not in locs
        assert f"../week/{s}/" in _parse(out / "week" / "index.html").hrefs
        assert _page_slugs(out, s) == expected[s]
    for s in full:
        assert _robots(out / "week" / s / "index.html") == [], s
        assert f"{BASE_URL}/week/{s}/" in locs
    # The index lists every week, thin or not, and is itself indexed.
    assert _robots(out / "week" / "index.html") == []
    assert f"{BASE_URL}/week/" in locs


def test_negative_control_a_week_at_the_threshold_is_indexed_and_one_below_is_not(
    built, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, snap, history = built
    expected = _expected_from_history(history, snap)
    start = max(expected, key=lambda s: len(expected[s]))
    n = len(expected[start])
    assert n >= 2
    url = f"{BASE_URL}/week/{start}/"
    # At the threshold: indexed and in the sitemap.
    monkeypatch.setattr(weeks, "WEEK_INDEX_MIN_WATERS", n)
    assert n == weeks.WEEK_INDEX_MIN_WATERS  # the sabotage applied
    site.build_site(copy.deepcopy(snap), tmp_path / "at", base_url=BASE_URL)
    assert _robots(tmp_path / "at" / "week" / start / "index.html") == []
    assert url in _sitemap_locs(tmp_path / "at")
    # One above the count: the same week is noindex,follow and not in the sitemap.
    monkeypatch.setattr(weeks, "WEEK_INDEX_MIN_WATERS", n + 1)
    assert n + 1 == weeks.WEEK_INDEX_MIN_WATERS  # the sabotage applied
    site.build_site(copy.deepcopy(snap), tmp_path / "below", base_url=BASE_URL)
    assert _robots(tmp_path / "below" / "week" / start / "index.html") == [
        "noindex,follow"
    ]
    assert url not in _sitemap_locs(tmp_path / "below")
    assert (tmp_path / "below" / "week" / start / "index.html").exists()
