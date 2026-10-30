"""No two pages share a <title>, and a repeat never stops the build.

New York's plan lists a river once per town section ("Ausable River - West
Branch" in Jay, North Elba and Wilmington, all Essex County), and each
section has its own page and URL. Their titles, h1s and descriptions used to
name only the county, so 134 pages shared a title with another page. A water
whose name and county another water of its state shares now names its town
too, the same town its URL slug carries.

Should two water pages still match after that, each gets a short stable
qualifier (the agency's water ID, else the water's id) and the build warns
and goes on (site_states.qualifiers). Any other repeat is caught last by
site.ensure_unique_titles, which appends each page's path to its title,
warns, and goes on. The owner's rule (2026-10-29): a repeated title never
blocks the daily publish.

The synthetic collisions are checked to have happened (a warning, a changed
title) before the result is checked, so a fallback that silently did nothing
cannot pass.
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site, site_states

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
NY_SECTION = "ny/water/fishkill-creek-beekman-dutchess-county/index.html"
NY_OTHER = "ny/water/fishkill-creek-fishkill-dutchess-county/index.html"


def _titles(root: Path) -> Counter[str]:
    out: Counter[str] = Counter()
    for path in root.rglob("*.html"):
        m = re.search(r"<title>(.*?)</title>", path.read_text(encoding="utf-8"), re.S)
        if m:
            out[htmllib.unescape(" ".join(m.group(1).split()))] += 1
    return out


def _run(root: Path, states: tuple[str, ...]) -> Path:
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
        states_fetch=states,
        states_fixtures=FIXTURES / "states",
    )
    return root / "site"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("unique-titles"), ("TN", "MA", "MI", "NY"))


# (c) the final output


def test_every_page_title_is_unique(built: Path) -> None:
    titles = _titles(built)
    assert len(titles) > 1000
    assert [t for t, n in titles.items() if n > 1] == []


# (a) the town rule alone gives today's titles, with no fallback used


def test_a_shared_ny_name_carries_its_town(built: Path) -> None:
    page = (built / NY_SECTION).read_text(encoding="utf-8")
    assert (
        "<title>Fishkill Creek trout stocking plan (Beekman, Dutchess County, NY)"
        " | Trout Truck</title>" in page
    )
    assert (
        "<h1>Fishkill Creek trout stocking plan (Beekman, Dutchess County, New York)</h1>"
        in page
    )
    assert 'content="Fishkill Creek, Beekman, Dutchess County, New York trout' in page


def test_no_fallback_qualifier_on_todays_data(built: Path) -> None:
    titles = _titles(built)
    assert not [t for t in titles if "water ID" in t or re.search(r"\(ny-", t)]
    assert not [t for t in titles if t.endswith("/)")]


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


# (b) a synthetic collision is told apart, with a warning, and the build succeeds


def test_qualifiers_prefer_the_agency_id_then_the_stable_id() -> None:
    def w(i: str, source: str | None) -> dict[str, Any]:
        return {"id": i, "source_id": source}

    keys = {i: ("same",) for i in ("a", "b", "c", "d")} | {"e": ("alone",)}
    with_ids = site_states.qualifiers(
        {k: keys[k] for k in ("a", "b", "e")}, [w("a", "1"), w("b", "2"), w("e", "3")]
    )
    assert with_ids == {"a": "water ID 1", "b": "water ID 2"}
    no_ids = site_states.qualifiers(
        {k: keys[k] for k in ("c", "d")}, [w("c", None), w("d", "9")]
    )
    assert no_ids == {"c": "c", "d": "d"}


def test_town_rule_off_falls_back_warns_and_builds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With the town rule switched off, New York's river sections collide
    again. The build still succeeds, warns, and no two titles match."""
    monkeypatch.setattr(site_states, "shared_names", lambda waters: set())
    out = _run(tmp_path, ("NY",))
    err = capsys.readouterr().err
    assert "would still share a title" in err
    assert "/ny/water/fishkill-creek-beekman-dutchess-county/ ->" in err
    page = (out / NY_SECTION).read_text(encoding="utf-8")
    m = re.search(r"<title>(.*?)</title>", page)
    assert m is not None
    assert "ny-dutchess-beekman-fishkill-creek" in m.group(1)
    assert "ny-dutchess-beekman-fishkill-creek" in re.search(
        r"<h1>(.*?)</h1>", page
    ).group(1)
    assert [t for t, n in _titles(out).items() if n > 1] == []


def test_last_guard_appends_paths_warns_and_does_not_raise(
    built: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy = tmp_path / "site"
    shutil.copytree(built / "ny", copy / "ny")
    a, b = copy / NY_SECTION, copy / NY_OTHER
    title_a = re.search(r"<title>.*?</title>", a.read_text(encoding="utf-8")).group(0)
    before = b.read_text(encoding="utf-8")
    after = re.sub(r"<title>.*?</title>", lambda _: title_a, before, count=1)
    assert after != before
    b.write_text(after, encoding="utf-8")
    assert [t for t, n in _titles(copy).items() if n > 1] != []

    changed = site.ensure_unique_titles(copy, list(copy.rglob("*.html")))

    assert sorted(changed) == [
        "ny/water/fishkill-creek-beekman-dutchess-county/",
        "ny/water/fishkill-creek-fishkill-dutchess-county/",
    ]
    assert "2 page(s) shared a <title>" in capsys.readouterr().err
    assert "(ny/water/fishkill-creek-fishkill-dutchess-county/)</title>" in (
        b.read_text(encoding="utf-8")
    )
    assert [t for t, n in _titles(copy).items() if n > 1] == []


def test_last_guard_changes_nothing_on_the_real_build(built: Path) -> None:
    pages = list(built.rglob("*.html"))
    before = {p: p.read_bytes() for p in pages}
    assert site.ensure_unique_titles(built, pages) == []
    assert all(p.read_bytes() == before[p] for p in pages)
