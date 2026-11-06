"""The national chrome (DECISIONS 0050, plan N3).

A build with more than one state says so in the shared parts of the site:
the header line, the California pages' nav, and the openings of the about,
support, gear and 404 pages. Every state those pages name comes from v2,
never from a hand-typed list, so these tests build twice with different
states and check that the words follow the data. California's URLs, the
home page's title and H1, and the /county/ title do not change.

A California-only build keeps the old chrome byte for byte; that is
test_snapshot_v2's test_a_california_only_v2_leaves_every_california_page_unchanged.
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
REPO = Path(__file__).resolve().parents[2]
V1_SCHEMA = REPO / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"

_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _run(root: Path, states: tuple[str, ...]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=V1_SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states" if states else None,
        states_fetch=states,
        states_fixtures=STATE_FIXTURES if states else None,
    )
    return root / "site"


@pytest.fixture(scope="module")
def five(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("five"), ("TN", "MA", "MI", "NY"))


@pytest.fixture(scope="module")
def two(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("two"), ("TN",))


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _run(tmp_path_factory.mktemp("plain"), ())


def _page(out: Path, rel: str) -> str:
    path = out / rel / "index.html" if rel else out / "index.html"
    return path.read_text("utf-8")


def _text(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script\b[^>]*>", " ", html, flags=re.S | re.I)
    html = re.sub(r"</?(?:a|strong|em|code)\b[^>]*>", "", html)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", htmllib.unescape(html)).strip()


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    assert m
    return htmllib.unescape(m.group(1))


def _h1(html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    assert m
    return _text(m.group(1))


def _tagline(html: str) -> str:
    m = re.search(r'<span class="site-tagline">(.*?)</span>', html, re.S)
    assert m
    return htmllib.unescape(m.group(1))


def _nav(html: str) -> list[tuple[str, str]]:
    m = re.search(r'<nav aria-label="Primary">(.*?)</nav>', html, re.S)
    assert m
    return [
        (htmllib.unescape(label), href)
        for href, label in re.findall(r'<a href="([^"]*)">(.*?)</a>', m.group(1))
    ]


def _graph(html: str) -> dict[str, dict[str, Any]]:
    [block] = _LD.findall(html)
    return {n["@type"]: n for n in json.loads(block)["@graph"]}


def _v2_states(out: Path) -> list[dict[str, Any]]:
    v2 = json.loads((out / "snapshot" / "v2.json").read_text("utf-8"))
    states: list[dict[str, Any]] = v2["states"]
    return states


# ---- header and nav


def test_california_and_site_wide_pages_carry_the_national_header(five: Path):
    for rel in ("", "county", "about", "support", "privacy", "terms", "gear", "states"):
        html = _page(five, rel)
        assert _tagline(html) == site.HEADER_TAGLINE_NATIONAL, rel
    home = _page(five, "")
    assert _nav(home) == [
        ("California this week", "./"),
        ("California counties", "./county/"),
        ("All states", "./states/"),
        ("About & privacy", "./about/"),
    ]
    water = next((five / "water").iterdir()) / "index.html"
    assert _nav(water.read_text("utf-8"))[0] == ("California this week", "../../")


def test_another_states_pages_keep_their_own_header(five: Path):
    html = _page(five, "tn")
    assert _tagline(html) == "Tennessee trout stocking"
    assert _nav(html)[0] == ("Tennessee this week", "../tn/")


def test_control_a_california_only_build_keeps_the_old_header(plain: Path):
    """Negative control: the national words appear only when v2 has more
    than one state, so the check above is not passing on a constant."""
    home = _page(plain, "")
    assert _tagline(home) == "California trout planting & stocking schedule"
    assert [label for label, _ in _nav(home)] == [
        "This week",
        "By county",
        "About & privacy",
    ]
    for f in plain.rglob("*.html"):
        assert site.HEADER_TAGLINE_NATIONAL not in f.read_text("utf-8"), f


# ---- what stays the same


def test_california_titles_and_h1s_do_not_change(five: Path, plain: Path):
    for rel in ("", "county"):
        assert _title(_page(five, rel)) == _title(_page(plain, rel)), rel
        assert _h1(_page(five, rel)) == _h1(_page(plain, rel)), rel
    assert _title(_page(five, "county")).startswith("California ")
    # Every California URL the plain build has, the national build has too.
    ca = {
        p.relative_to(plain).as_posix()
        for p in plain.rglob("index.html")
        if p.parts[len(plain.parts)] in ("water", "county", "region", "species", "week")
    }
    assert ca
    missing = {p for p in ca if not (five / p).is_file()}
    assert not missing


def test_site_wide_titles_carry_the_national_tagline(five: Path, plain: Path):
    for rel in ("about", "privacy", "support", "terms"):
        assert _title(_page(five, rel)).endswith(f", {site.SITE_TAGLINE_NATIONAL}")
        assert _title(_page(plain, rel)).endswith(f", {site.SITE_TAGLINE}")
    assert _title((five / "404.html").read_text("utf-8")).endswith(
        site.SITE_TAGLINE_NATIONAL
    )


# ---- the states named come from v2


def _names_in_about(out: Path) -> str:
    text = _text(_page(out, "about"))
    m = re.search(r"It carries (.*?) today", text)
    assert m, "the about page names the states it carries"
    return m.group(1)


def test_the_about_page_names_exactly_the_states_in_v2(five: Path, two: Path):
    for out in (five, two):
        names = [s["name"] for s in _v2_states(out)]
        assert _names_in_about(out) == site._join_names(names)
    # Negative control: the two builds differ, so the sentence is not a
    # fixed string that happens to match one of them.
    assert _names_in_about(five) != _names_in_about(two)
    assert "Michigan" in _names_in_about(five)
    assert "Michigan" not in _names_in_about(two)


def test_the_faq_names_each_agency_from_v2_and_matches_its_json_ld(
    five: Path, two: Path
):
    for out in (five, two):
        html = _page(out, "support")
        visible = _text(html)
        faq = _graph(html)["FAQPage"]["mainEntity"]
        assert faq[0]["name"] == "Where does the data come from?"
        for s in _v2_states(out):
            agency = f"{s['agency']['name']} ({s['agency']['short_name']})"
            assert agency in faq[0]["acceptedAnswer"]["text"], agency
        heads = [_text(h) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)]
        for q in faq:
            assert q["name"] in heads, q["name"]
            assert q["acceptedAnswer"]["text"] in visible, q["name"]
        assert "Will my state be added?" in heads
    assert "Michigan" not in _text(_page(two, "support"))


def test_control_the_faq_match_notices_drift(five: Path):
    html = _page(five, "support")
    answer = _graph(html)["FAQPage"]["mainEntity"][0]["acceptedAnswer"]["text"]
    drifted = answer.replace("Tennessee", "Oregon")
    assert drifted != answer
    assert drifted not in _text(html)


def test_the_gear_license_line_links_each_other_states_agency_from_v2(five: Path):
    html = _page(five, "gear")
    assert _h1(html) == site.GEAR_GUIDE_TITLE_NATIONAL
    assert "California" not in _h1(html)
    hrefs = re.findall(r'<a href="([^"]+)">', html)
    for s in _v2_states(five):
        if s["code"] != "CA":
            assert s["agency"]["url"] in hrefs, s["code"]
    assert site.CDFW_LICENSE_URL in hrefs
    ld = _graph(html)["WebPage"]["about"]
    assert [a["name"] for a in ld] == [s["name"] for s in _v2_states(five)]


def test_the_gear_holiday_section_is_untouched():
    """DECISIONS 0043: the gifts section stays state-neutral and in season."""
    tpl = (Path(site.__file__).parent / "templates" / "gear.html.jinja").read_text()
    gifts = tpl.split('<h2 id="gifts">', 1)[1].split("{% endif %}", 1)[0]
    assert "national" not in gifts


def test_the_home_website_description_is_national(five: Path, plain: Path):
    assert (
        "state wildlife agencies" in _graph(_page(five, ""))["WebSite"]["description"]
    )
    assert "CDFW" in _graph(_page(plain, ""))["WebSite"]["description"]


def test_the_404_example_path_is_a_real_state_path(five: Path):
    text = _text((five / "404.html").read_text("utf-8"))
    m = re.search(r"such as (\w+)/water/<name>/", text)
    assert m
    assert (five / m.group(1) / "water").is_dir()


# ---- copy rules


_COVERAGE = re.compile(r"\b(all 50 states|every state|nationwide|all states)\b", re.I)


def _headings(html: str) -> list[str]:
    return [_text(h) for h in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.S)]


def test_no_new_chrome_claims_coverage_in_a_title_or_heading(five: Path):
    for rel in ("", "about", "support", "gear", "privacy", "terms"):
        html = _page(five, rel)
        for line in (_title(html), _tagline(html), *_headings(html)):
            assert not _COVERAGE.search(line), (rel, line)


def test_control_the_coverage_check_notices_a_claim():
    assert _COVERAGE.search("Trout stocking from every state's agency")
    assert not _COVERAGE.search(site.HEADER_TAGLINE_NATIONAL)


def test_the_new_words_avoid_the_banned_words():
    banned = {"only", "first", "best", "top", "unique"}
    new = " ".join(
        [
            site.HEADER_TAGLINE_NATIONAL,
            site.SITE_TAGLINE_NATIONAL,
            site.GEAR_GUIDE_TITLE_NATIONAL,
            site.GEAR_GUIDE_DESCRIPTION_NATIONAL,
            *(
                f"{q} {a}"
                for q, a in site._support_faq("x", national=site._national(_fake_v2()))[
                    :3
                ]
            ),
        ]
    )
    words = {w.strip(".,;:()\"'").lower() for w in new.split()}
    assert not words & banned, words & banned
    # Negative control: the scan sees a banned word once one is there.
    assert {"only"} <= {w.lower() for w in (new + " only").split()} & banned


def _fake_v2() -> dict[str, Any]:
    return {
        "states": [
            {
                "code": c,
                "name": n,
                "agency": {"name": f"{n} agency", "short_name": c, "url": "u"},
            }
            for c, n in (("CA", "California"), ("TN", "Tennessee"))
        ]
    }


def test_national_is_none_for_one_state_and_follows_v2_otherwise():
    assert site._national(None) is None
    one = _fake_v2()
    one["states"] = one["states"][:1]
    assert site._national(one) is None
    nat = site._national(_fake_v2())
    assert nat is not None
    assert nat["names_text"] == "California and Tennessee"
    assert nat["example_seg"] == "tn"
