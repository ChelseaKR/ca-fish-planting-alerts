"""Water page titles and meta descriptions.

A search result shows about 60 characters of a title and about 155 of a
description. These tests build the site from the real CDFW fixture and pin
what the audit of 2026-10-20 asked for: titles within the limit (or as short
as the water's name allows), no county in a title unless two waters share the
name, both search words in the title when the name leaves room, descriptions
that lead with the schedule and the last-listed date, no "None listed"
sentence, and no two pages with the same title or description.

Each negative control builds a doctored copy of the checker's input, asserts
the doctoring changed it, and then asserts the checker flagged it.
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, locations, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
SUFFIX = f" | {site.SITE_NAME}"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    root = tmp_path_factory.mktemp("water-meta")
    snap = cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=root / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    names = Counter(w["name"] for w in snap["waters"])
    usgs = locations.load_usgs_lake_names(cli.DEFAULT_LOCATIONS_PATH)
    pages: dict[str, dict[str, Any]] = {}
    for w in snap["waters"]:
        page = (root / "site" / "water" / w["slug"] / "index.html").read_text(
            encoding="utf-8"
        )
        title = re.search(r"<title>([^<]+)</title>", page).group(1)
        desc = re.search(r'<meta name="description" content="([^"]+)">', page).group(1)
        h1 = re.search(r"<h1>([^<]+)</h1>", page).group(1)
        lede = re.search(r'<p class="lede">(.*?)</p>', page, re.S).group(1)
        pages[w["slug"]] = {
            "name": w["name"],
            "usgs": site.usgs_lake_name(w["name"], usgs.get(w["cdfw_stock_id"])),
            "h1": htmllib.unescape(h1),
            "lede": " ".join(htmllib.unescape(lede).split()),
            "shared": names[w["name"]] > 1,
            "place": f"{w['name']} ({site.county_phrase(w['counties'])})",
            "counties": w["counties"],
            "title": htmllib.unescape(title),
            "description": htmllib.unescape(desc),
        }
    assert len(pages) > 20
    return pages


def _title_problems(slug: str, p: dict[str, Any]) -> list[str]:
    t, name = p["title"], p["name"]
    problems: list[str] = []
    base = p["place"] if p["shared"] else name
    if p["usgs"]:
        base = base if p["shared"] else f"{name} ({p['usgs']})"
        if p["usgs"] not in t:
            problems.append(f"{slug}: title lacks the USGS name: {t!r}")
    floor = f"{base} stocking schedule{SUFFIX}"
    if len(t) > site.WATER_TITLE_MAX and len(t) > len(floor):
        problems.append(f"{slug}: title over {site.WATER_TITLE_MAX}: {t!r}")
    if not t.endswith(SUFFIX) or name not in t:
        problems.append(f"{slug}: title lacks the name or the brand: {t!r}")
    if "stocking" not in t:
        problems.append(f"{slug}: title lacks 'stocking': {t!r}")
    both_fit = (
        len(f"{name} stocking and planting schedule{SUFFIX}") <= site.WATER_TITLE_MAX
        and not p["shared"]
        and not p["usgs"]
    )
    if both_fit and "planting schedule" not in t:
        problems.append(f"{slug}: title lacks 'planting schedule': {t!r}")
    if ("County" in t) != p["shared"]:
        problems.append(f"{slug}: county in title must match shared name: {t!r}")
    return problems


def _description_problems(slug: str, p: dict[str, Any]) -> list[str]:
    d, name = p["description"], p["name"]
    problems: list[str] = []
    if len(d) > site.WATER_DESCRIPTION_MAX:
        problems.append(f"{slug}: description over limit: {len(d)}")
    if "None listed" in d:
        problems.append(f"{slug}: negative sentence in description: {d!r}")
    if "stocking schedule:" not in d[:110] or not d.startswith(name):
        problems.append(f"{slug}: description does not lead with the schedule: {d!r}")
    if "planting" not in d:
        problems.append(f"{slug}: description lacks 'planting': {d!r}")
    if not re.search(r"scheduled (this week|the week of \d{4}-\d{2}-\d{2})|no week", d):
        problems.append(f"{slug}: description lacks a schedule or date: {d!r}")
    return problems


def check(pages: dict[str, dict[str, Any]]) -> list[str]:
    """Every way a water page's title or description can be wrong."""
    problems: list[str] = []
    for slug, p in pages.items():
        problems += _title_problems(slug, p) + _description_problems(slug, p)
    titles = Counter(p["title"] for p in pages.values())
    descs = Counter(p["description"] for p in pages.values())
    problems += [f"duplicate title: {t!r}" for t, n in titles.items() if n > 1]
    problems += [f"duplicate description: {d!r}" for d, n in descs.items() if n > 1]
    return problems


def test_every_water_page_passes_the_checks(built):
    assert check(built) == []


def test_the_fixture_has_a_shared_name_and_a_nothing_current_water(built):
    assert any(p["shared"] for p in built.values())
    assert any("last scheduled" in p["description"] for p in built.values())


def test_a_shared_name_keeps_its_county_and_others_drop_it(built):
    for slug, p in built.items():
        for county in p["counties"]:
            assert (f"{county} County" in p["title"]) == p["shared"], slug


def test_a_lake_with_a_usgs_name_carries_both_names(built):
    paired = {s: p for s, p in built.items() if p["usgs"]}
    # The fixture's one such lake; Ralphine Lake's title is pinned below.
    assert paired["gregory-lake"]["usgs"] == "Lake Gregory"
    assert paired["gregory-lake"]["title"] == (
        "Gregory Lake (Lake Gregory) stocking schedule | Trout Truck"
    )
    for slug, p in paired.items():
        assert p["h1"].startswith(f"{p['name']} ({p['usgs']}, "), slug
        assert p["description"].startswith(f"{p['name']} ({p['usgs']}, "), slug
        assert f"The U.S. Geological Survey names it {p['usgs']}." in p["lede"], slug
    for slug, p in built.items():
        if not p["usgs"]:
            assert "Geological Survey" not in p["lede"], slug
            assert p["h1"].startswith(p["place"]), slug


def test_a_last_listed_water_leads_with_its_date(built):
    for slug, p in built.items():
        if "last scheduled" in p["description"]:
            assert re.search(
                r"stocking schedule: last scheduled the week of \d{4}-\d{2}-\d{2}\.",
                p["description"],
            ), slug


# ---- the builders on their own


def _view(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Ralphine Lake",
        "place": "Ralphine Lake (Sonoma County)",
        "shared_name": False,
        "species": "trout",
        "this_week": False,
        "next_listed_label": "",
        "last_listed_label": "week of 2026-04-05",
        "listed_week_count": 5,
        "usgs_name": "",
    }
    base.update(kw)
    base.setdefault("search_place", base["place"])
    return base


@pytest.mark.parametrize(
    ("name", "usgs", "expected"),
    [
        ("Ralphine Lake", "Lake Ralphine", "Lake Ralphine"),
        ("Ming Lake", "Lake Ming", "Lake Ming"),
        # Any other USGS match is not a second name for the page.
        ("Skinner Lake", "Skinner Reservoir", ""),
        ("Ralphine Lake", None, ""),
        ("Kings River", "Lake Kings", ""),
    ],
)
def test_usgs_lake_name_only_for_the_word_swapped_form(name, usgs, expected):
    assert site.usgs_lake_name(name, usgs) == expected


def test_title_with_a_usgs_name_carries_both_names():
    view = _view(
        usgs_name="Lake Ralphine",
        search_place="Ralphine Lake (Lake Ralphine, Sonoma County)",
    )
    assert (
        site._water_title(view)
        == "Ralphine Lake (Lake Ralphine) stocking schedule | Trout Truck"
    )
    assert site._water_description(
        view, source_week_label="week of 2026-10-18"
    ).startswith(
        "Ralphine Lake (Lake Ralphine, Sonoma County) trout stocking schedule: "
        "last scheduled the week of 2026-04-05."
    )


def test_title_for_a_name_that_fits_carries_both_words_and_the_species():
    assert (
        site._water_title(_view(name="Fish Lake"))
        == "Fish Lake trout stocking and planting schedule | Trout Truck"
    )


def test_title_drops_the_species_before_it_drops_planting():
    assert (
        site._water_title(_view())
        == "Ralphine Lake stocking and planting schedule | Trout Truck"
    )


def test_title_drops_words_for_a_long_name_but_never_the_name():
    long_name = "Russian River, Upper East Branch"
    title = site._water_title(_view(name=long_name))
    assert long_name in title
    assert title == f"{long_name} stocking schedule | Trout Truck"
    very_long = "Ralph Clark Regional Park Lake and Some More Words Here"
    assert site._water_title(_view(name=very_long)).startswith(very_long)


def test_title_for_a_shared_name_keeps_the_county():
    title = site._water_title(
        _view(name="Silver Lake", place="Silver Lake (Lassen County)", shared_name=True)
    )
    assert title.startswith("Silver Lake (Lassen County) ")


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        (
            {},
            "Ralphine Lake (Sonoma County) trout stocking schedule: last scheduled "
            "the week of 2026-04-05. CDFW planting history, 5 weeks on record, and "
            "a calendar feed.",
        ),
        (
            {"this_week": True, "last_listed_label": ""},
            "Ralphine Lake (Sonoma County) trout stocking schedule: scheduled this "
            "week, the week of 2026-10-18. CDFW planting history and a calendar "
            "feed.",
        ),
        (
            {
                "this_week": True,
                "next_listed_label": "week of 2026-10-25",
                "last_listed_label": "",
            },
            "Ralphine Lake (Sonoma County) trout stocking schedule: scheduled this "
            "week, the week of 2026-10-18, and next the week of 2026-10-25. CDFW "
            "planting history.",
        ),
        (
            {"next_listed_label": "week of 2026-11-01", "last_listed_label": ""},
            "Ralphine Lake (Sonoma County) trout stocking schedule: next scheduled "
            "the week of 2026-11-01. CDFW planting history, 5 weeks on record, and "
            "a calendar feed.",
        ),
        (
            {"last_listed_label": "", "listed_week_count": 0},
            "Ralphine Lake (Sonoma County) trout stocking schedule: no week "
            "currently listed. CDFW planting history, 0 weeks on record, and a "
            "calendar feed.",
        ),
    ],
)
def test_description_wording_for_each_state(kw, expected):
    got = site._water_description(_view(**kw), source_week_label="week of 2026-10-18")
    assert got == expected
    assert len(got) <= site.WATER_DESCRIPTION_MAX


# ---- negative controls


def _doctor(pages, slug, **changes):
    doctored = {k: dict(v) for k, v in pages.items()}
    doctored[slug].update(changes)
    return doctored


def test_negative_control_catches_an_over_length_title(built):
    slug = next(s for s, p in built.items() if not p["shared"])
    long_title = "A" * 70 + SUFFIX
    doctored = _doctor(built, slug, title=long_title)
    assert doctored != built  # the sabotage landed
    assert any("title over" in m for m in check(doctored))


def test_negative_control_catches_an_over_length_description(built):
    slug = next(iter(built))
    doctored = _doctor(built, slug, description=built[slug]["description"] + "x" * 40)
    assert doctored != built
    assert any("description over" in m for m in check(doctored))


def test_negative_control_catches_a_duplicate_title(built):
    a, b = list(built)[:2]
    doctored = _doctor(built, b, title=built[a]["title"])
    assert doctored != built
    assert any("duplicate title" in m for m in check(doctored))


def test_negative_control_catches_a_duplicate_description(built):
    a, b = list(built)[:2]
    doctored = _doctor(built, b, description=built[a]["description"])
    assert doctored != built
    assert any("duplicate description" in m for m in check(doctored))


def test_negative_control_catches_a_missing_key_word(built):
    slug = next(s for s, p in built.items() if not p["shared"])
    title = built[slug]["title"].replace("stocking", "stoking")
    doctored = _doctor(built, slug, title=title)
    assert doctored != built
    assert any("lacks 'stocking'" in m for m in check(doctored))
    desc = built[slug]["description"].replace("planting", "planning")
    doctored = _doctor(built, slug, description=desc)
    assert doctored != built
    assert any("lacks 'planting'" in m for m in check(doctored))


def test_negative_control_catches_the_old_negative_sentence(built):
    slug = next(iter(built))
    doctored = _doctor(
        built,
        slug,
        description=built[slug]["description"][:-1]
        + " None listed this week or later.",
    )
    assert doctored != built
    assert any("negative sentence" in m for m in check(doctored))


def test_negative_control_catches_a_county_in_a_unique_title(built):
    slug = next(s for s, p in built.items() if not p["shared"])
    p = built[slug]
    doctored = _doctor(
        built,
        slug,
        title=f"{p['name']} ({p['counties'][0]} County) stocking schedule{SUFFIX}",
    )
    assert doctored != built
    assert any("county in title" in m for m in check(doctored))
