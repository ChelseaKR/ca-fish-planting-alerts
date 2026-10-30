"""Thin water pages (DECISIONS 0041): a water page with fewer than two dated
stocking rows is noindex,follow, left out of sitemap.xml, carries no Amazon
gear block, and stays built and linked. A page with two or more keeps all
three. One function (cfpa.thin.is_thin) decides both rules, and these tests
check every water page of a five-state build against it, then sabotage the
threshold to show the build really follows it.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import pytest

from cfpa import cli, site, site_states, thin
from cfpa.states import SOURCES

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
BASE_PATH = urlsplit(BASE_URL).path  # /ca-fish-planting-alerts
NOINDEX = '<meta name="robots" content="noindex,follow">'
HREF = re.compile(r'href="([^"#]+)')


def _build(root: Path) -> Path:
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
        states_fetch=("TN", "MA", "MI", "NY"),
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("thin") / "b")


def _waters(out: Path) -> list[dict[str, Any]]:
    v2 = json.loads((out / "snapshot" / "v2.json").read_text(encoding="utf-8"))
    states = {s["code"]: s for s in v2["states"]}
    return [{**w, "_state": states[w["state"]]} for w in v2["waters"]]


def _path(w: dict[str, Any]) -> str:
    return str(w.get("site_path") or f"/water/{w['slug']}/")


def _sitemap(out: Path) -> set[str]:
    xml = (out / "sitemap.xml").read_text(encoding="utf-8")
    return set(re.findall(r"<loc>([^<]+)</loc>", xml))


AMAZON_HOSTS = frozenset({"amazon.com", "www.amazon.com"})


def _amazon_links(html: str) -> list[str]:
    """Links whose parsed host is exactly Amazon's (site.AMAZON_SEARCH_URL)."""
    return [
        h
        for h in HREF.findall(html)
        if urlsplit(h).scheme == "https" and urlsplit(h).hostname in AMAZON_HOSTS
    ]


def _page(out: Path, w: dict[str, Any]) -> str:
    return (out / _path(w).strip("/") / "index.html").read_text(encoding="utf-8")


def _gear_expected(w: dict[str, Any]) -> bool:
    """Whether a non-thin page carries the block: always in California; in
    another state when its terms and species allow it (DECISIONS 0039)."""
    if w["state"] == "CA":
        return True
    species = (
        "trout" if all("trout" in p["species"].lower() for p in w["plants"]) else "fish"
    )
    return site_states.gear_allowed(w["_state"], species)


# ---- the rule itself


def _v2(precision: str, status: str = "listed") -> dict[str, Any]:
    return {"period": {"precision": precision}, "status": status}


def _v1(status: str = "listed") -> dict[str, Any]:
    return {"week": {"start": "2026-10-04"}, "status": status}


def test_a_dated_row_is_a_stocking_with_a_date() -> None:
    assert thin.dated_rows([_v1(), _v1(), _v1("removed")]) == 2
    assert (
        thin.dated_rows([_v2("day", "reported"), _v2("week"), _v2("approximate")]) == 3
    )
    # A bare month is not a date; a dropped plant is not a stocking.
    assert thin.dated_rows([_v2("month"), _v2("week", "removed")]) == 0
    assert thin.dated_rows([]) == 0


@pytest.mark.parametrize(
    ("rows", "want"), [(0, True), (1, True), (2, False), (5, False)]
)
def test_the_threshold_is_two_dated_rows(rows: int, want: bool) -> None:
    assert thin.WATER_INDEX_MIN_DATED_ROWS == 2
    plants = [_v2("day", "reported")] * rows + [_v2("month"), _v2("week", "removed")]
    assert thin.is_thin(plants, "/tn/water/x/") is want


def test_a_page_people_find_stays_indexed_however_thin() -> None:
    (kept,) = thin.KEEP_INDEXED_PATHS
    assert thin.is_thin([], kept) is False
    assert thin.is_thin([], "/tn/water/some-other-water/") is True


# ---- a real build: every water page, both sides


def test_the_build_has_pages_on_both_sides_in_every_state(built: Path) -> None:
    """The checks below can fail only if both kinds of page exist."""
    by_state: dict[str, set[bool]] = {}
    for w in _waters(built):
        by_state.setdefault(w["state"], set()).add(thin.is_thin(w["plants"], _path(w)))
    assert set(by_state) == {"CA", "TN", "MA", "MI", "NY"}
    assert all(sides == {True, False} for sides in by_state.values()), by_state


def test_every_water_page_follows_the_rule(built: Path) -> None:
    sitemap = _sitemap(built)
    for w in _waters(built):
        html = _page(built, w)
        url = f"{BASE_URL}{_path(w)}"
        links = _amazon_links(html)
        if thin.is_thin(w["plants"], _path(w)):
            assert NOINDEX in html, url
            assert url not in sitemap, url
            assert links == [], url
            assert "gear-heading" not in html, url
        else:
            assert "noindex" not in html, url
            assert url in sitemap, url
            if _gear_expected(w):
                assert len(links) == len(site.GEAR_CATEGORIES), url
                # Every page that keeps the links keeps the disclosure.
                assert site.AMAZON_ASSOCIATE_DISCLOSURE in html, url
                assert "costs you nothing extra" in html, url


def test_thin_pages_stay_built_and_linked(built: Path) -> None:
    """Noindex is for search engines; visitors still reach every page."""
    linked: set[str] = set()
    for page in built.rglob("*.html"):
        rel = page.relative_to(built).as_posix()
        page_url = f"{BASE_URL}/{rel}"
        for href in HREF.findall(page.read_text(encoding="utf-8")):
            linked.add(urlsplit(urljoin(page_url, href)).path)
    thin_pages = [w for w in _waters(built) if thin.is_thin(w["plants"], _path(w))]
    assert thin_pages
    for w in thin_pages:
        assert (built / _path(w).strip("/") / "index.html").exists()
        target = f"{BASE_PATH}{_path(w)}"
        assert target in linked or f"{target}index.html" in linked, _path(w)


def test_noindexed_water_pages_keep_their_canonical(built: Path) -> None:
    w = next(w for w in _waters(built) if thin.is_thin(w["plants"], _path(w)))
    assert f'<link rel="canonical" href="{BASE_URL}{_path(w)}">' in _page(built, w)


# ---- negative controls: the threshold really decides the build


def test_control_a_higher_threshold_noindexes_a_page_that_had_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: Path
) -> None:
    """A page with 2+ rows is indexed with links in the real build; with the
    threshold raised past its rows, the same page loses all three."""
    w = next(
        w
        for w in _waters(built)
        if w["state"] == "CA" and not thin.is_thin(w["plants"], _path(w))
    )
    url = f"{BASE_URL}{_path(w)}"
    before = _page(built, w)
    assert url in _sitemap(built) and _amazon_links(before) and NOINDEX not in before

    monkeypatch.setattr(thin, "WATER_INDEX_MIN_DATED_ROWS", 10_000)
    out = _build(tmp_path / "b")
    after = _page(out, w)
    assert NOINDEX in after
    assert url not in _sitemap(out)
    assert _amazon_links(after) == []


def test_control_a_zero_threshold_indexes_a_thin_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, built: Path
) -> None:
    w = next(
        w
        for w in _waters(built)
        if w["state"] == "TN" and thin.is_thin(w["plants"], _path(w))
    )
    url = f"{BASE_URL}{_path(w)}"
    assert NOINDEX in _page(built, w) and url not in _sitemap(built)

    monkeypatch.setattr(thin, "WATER_INDEX_MIN_DATED_ROWS", 0)
    out = _build(tmp_path / "b")
    after = _page(out, w)
    assert NOINDEX not in after
    assert url in _sitemap(out)
    assert len(_amazon_links(after)) == len(site.GEAR_CATEGORIES)
    assert SOURCES["TN"].agency_short_name in after
