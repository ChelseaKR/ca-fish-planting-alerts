"""No two pages share a <title>.

New York's plan lists a river once per town section ("Ausable River - West
Branch" in Jay, North Elba and Wilmington, all Essex County), and each
section has its own page and URL. Their titles, h1s and descriptions used to
name only the county, so 134 pages shared a title with another page. A water
whose name and county another water of its state shares now names its town
too, the same town its URL slug carries, and the build refuses any site in
which two pages still share a title (site.check_unique_titles).

The negative controls doctor a copy of the checker's input, assert the
doctoring changed it, and then assert the checker refused it.
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from cfpa import cli, site, site_states

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
NY_SECTION = "ny/water/fishkill-creek-beekman-dutchess-county/index.html"


def _titles(root: Path) -> Counter[str]:
    out: Counter[str] = Counter()
    for path in root.rglob("*.html"):
        m = re.search(r"<title>(.*?)</title>", path.read_text(encoding="utf-8"), re.S)
        if m:
            out[htmllib.unescape(" ".join(m.group(1).split()))] += 1
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("unique-titles")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url="https://example.invalid",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI", "NY"),
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


def test_every_page_title_is_unique(built: Path) -> None:
    titles = _titles(built)
    assert len(titles) > 1000
    assert [t for t, n in titles.items() if n > 1] == []


def test_a_shared_ny_name_carries_its_town(built: Path) -> None:
    page = (built / NY_SECTION).read_text(encoding="utf-8")
    assert (
        "<title>Fishkill Creek trout stocking plan (Beekman, Dutchess County, NY)"
        in page
    )
    assert (
        "<h1>Fishkill Creek trout stocking plan (Beekman, Dutchess County, New York)</h1>"
        in page
    )
    assert 'content="Fishkill Creek, Beekman, Dutchess County, New York trout' in page


def test_an_unshared_name_keeps_its_county_only(built: Path) -> None:
    pages = sorted((built / "ny" / "water").glob("*/index.html"))
    titles = [
        re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8")).group(1)
        for p in pages
    ]
    # Most New York waters are listed once; their titles are unchanged.
    plain = [t for t in titles if re.search(r"\(\w[\w .']* County, NY\)", t)]
    assert len(plain) > len(titles) // 2


def test_shared_names_finds_only_repeats() -> None:
    waters = [
        {"name": "A Creek", "counties": ["Essex"], "towns": ["Jay"]},
        {"name": "A Creek", "counties": ["Essex"], "towns": ["Keene"]},
        {"name": "A Creek", "counties": ["Clinton"], "towns": ["Jay"]},
        {"name": "B Pond", "counties": ["Essex"], "towns": ["Jay"]},
    ]
    assert site_states.shared_names(waters) == {("A Creek", ("Essex",))}


def test_place_phrase_names_the_town_only_when_asked() -> None:
    w = {"counties": ["Essex"], "towns": ["North Elba"]}
    assert site_states.place_phrase(w, "New York") == "Essex County, New York"
    assert (
        site_states.place_phrase(w, "New York", with_towns=True)
        == "North Elba, Essex County, New York"
    )
    no_town = {"counties": ["Essex"], "towns": []}
    assert (
        site_states.place_phrase(no_town, "New York", with_towns=True)
        == "Essex County, New York"
    )


def test_check_passes_the_real_build(built: Path) -> None:
    pages = list(built.rglob("*.html"))
    site.check_unique_titles(built, pages)


def test_negative_control_a_repeated_title_is_refused(
    built: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "site"
    shutil.copytree(built / "ny", copy / "ny")
    a = copy / NY_SECTION
    b = copy / "ny/water/fishkill-creek-fishkill-dutchess-county/index.html"
    title_a = re.search(r"<title>.*?</title>", a.read_text(encoding="utf-8")).group(0)
    before = b.read_text(encoding="utf-8")
    after = re.sub(r"<title>.*?</title>", lambda _: title_a, before, count=1)
    assert after != before
    b.write_text(after, encoding="utf-8")
    pages = list(copy.rglob("*.html"))
    with pytest.raises(ValueError, match="1 page title"):
        site.check_unique_titles(copy, pages)


def test_negative_control_titles_without_towns_are_refused(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the town qualifier switched off, the build itself fails."""
    monkeypatch.setattr(site_states, "shared_names", lambda waters: set())
    root = tmp_path
    with pytest.raises(ValueError, match="used by more than one page"):
        cli.run(
            fixture_path=str(FRESH),
            history_path=root / "history.json",
            aliases_path=root / "aliases.json",
            schema_path=SCHEMA_PATH,
            site_out=root / "site",
            base_url="https://example.invalid",
            fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
            run_today=dt.date(2026, 9, 13),
            states_dir=root / "states",
            states_fetch=("NY",),
            states_fixtures=FIXTURES / "states",
        )
