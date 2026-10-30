"""The design-system restyle (2026-10-23) and the all-states index.

- Status badges are words from one table (site.STATUS_BADGE_WORDS and the
  three coverage words), never a number: ``_badge_problems`` is the checker.
- ``/states/`` lists all 50 states and DC, alphabetical: live states link to
  their pages, coming-soon states link nowhere, and every other state has
  exactly one link, to its agency's own page, and no other words than the
  template's: ``_coverage_problems`` is the checker. It is how the page is held
  to "never republish a state that is not covered".
- The two web fonts are first-party files, preloaded, with font-display: swap.

Each negative control sabotages a built page, asserts the sabotage changed
it, and asserts the checker notices.
"""

from __future__ import annotations

import datetime as dt
import html as html_mod
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from cfpa import cli, site, site_states, state_coverage
from cfpa.states import SOURCES

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

COVERAGE_WORDS = {"Live on Trout Truck", "Coming soon", "Not covered"}
BADGE_RE = re.compile(r'<span class="tt-badge tt-badge--(\w+)">(.*?)</span>', re.S)
CARD_RE = re.compile(r'<li class="tt-state[^"]*">(.*?)</li>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _build(root: Path, states: tuple[str, ...]) -> Path:
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=states,
        states_fixtures=FIXTURES / "states",
    )
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """California and Tennessee only: the site as production has it today."""
    return _build(tmp_path_factory.mktemp("ds"), ("TN",))


@pytest.fixture(scope="module")
def built_all(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Every state with a fixture: the coming-soon states have pages."""
    return _build(tmp_path_factory.mktemp("ds-all"), ("TN", "MA", "MI", "NY"))


def _text(fragment: str) -> str:
    return " ".join(html_mod.unescape(TAG_RE.sub("", fragment)).split())


def _search(pattern: str, text: str, flags: int = 0) -> re.Match[str]:
    m = re.search(pattern, text, flags)
    assert m is not None, pattern
    return m


def _pages(out: Path) -> dict[str, str]:
    return {
        str(p.relative_to(out)): p.read_text(encoding="utf-8")
        for p in sorted(out.rglob("*.html"))
    }


# ---- status badges


def _badge_problems(pages: dict[str, str]) -> list[str]:
    allowed = set(site.STATUS_BADGE_WORDS.values()) | COVERAGE_WORDS
    problems = []
    for name, text in pages.items():
        for state, word in BADGE_RE.findall(text):
            if word not in allowed:
                problems.append(f"{name}: badge {state!r} says {word!r}")
            if re.search(r"\d", word):
                problems.append(f"{name}: badge {state!r} has a number")
            # A coverage badge (/states/) borrows a status look; any other
            # badge must say its own state's word.
            if word not in COVERAGE_WORDS and word != site.STATUS_BADGE_WORDS.get(
                state
            ):
                problems.append(f"{name}: {state!r} badge says {word!r}")
    return problems


def test_status_words_are_words() -> None:
    assert site.STATUS_BADGE_WORDS == {
        "now": "This week",
        "next": "Next week",
        "none": "None scheduled",
    }


@pytest.mark.parametrize(
    ("this_week", "next_week", "state"),
    [
        (True, True, "now"),
        (True, False, "now"),
        (False, True, "next"),
        (False, False, "none"),
    ],
)
def test_schedule_status(this_week: bool, next_week: bool, state: str) -> None:
    assert site.schedule_status(this_week=this_week, next_week=next_week) == state


def test_every_badge_in_the_built_site_is_a_status_word(built: Path) -> None:
    pages = _pages(built)
    found = [m for t in pages.values() for m in BADGE_RE.findall(t)]
    # The checker saw badges of every kind: water pages, county pages, /states/.
    assert {s for s, _ in found} >= {"next", "none", "now"}
    assert _badge_problems(pages) == []


def test_negative_control_a_zero_badge_is_caught(built: Path) -> None:
    pages = _pages(built)
    name = next(n for n, t in pages.items() if "tt-badge--none" in t)
    sabotaged = pages[name].replace(">None scheduled</span>", ">0</span>", 1)
    assert sabotaged != pages[name]  # the sabotage applied
    assert _badge_problems({name: sabotaged})


def test_water_page_badge_matches_its_status_block(built: Path) -> None:
    pages = _pages(built)
    checked = 0
    for name, text in pages.items():
        if not name.startswith("water/") or "water-status" not in text:
            continue
        block = text.split('class="water-status"', 1)[1].split("</section>", 1)[0]
        state = BADGE_RE.search(block)
        assert state is not None, name
        this_week, next_week = re.findall(
            r"<dd>(On|Not on) CDFW&#39;s schedule\.</dd>", block
        )
        want = site.schedule_status(
            this_week=this_week == "On", next_week=next_week == "On"
        )
        assert state.group(1) == want, name
        checked += 1
    assert checked >= 30


def test_county_card_says_nothing_scheduled_in_words(built: Path) -> None:
    pages = _pages(built)
    states = set()
    for name, text in pages.items():
        if not re.fullmatch(r"county/[^/]+/index.html", name):
            continue
        card = text.split('class="tt-card"', 1)[1].split("</section>", 1)[0]
        state = BADGE_RE.search(card)
        assert state is not None, name
        states.add(state.group(1))
        words = _text(card)
        if state.group(1) == "none":
            assert "is on CDFW's schedule this week or next" in words, name
            assert "<li>" not in card
        else:
            assert re.search(
                r"\b[1-9]\d* waters? (is|are) on CDFW's schedule", words
            ), name
        assert not re.search(r"\b0 waters?\b", words), name
    assert states >= {"next", "none"}


def test_county_card_lists_at_most_five_waters() -> None:
    rows = [
        {"slug": f"w{i}", "name": f"Water {i}", "species": "Trout"} for i in range(7)
    ]
    card = site._county_card(rows, [], next_week_start="2026-09-20")
    assert card["state"] == "now"
    assert card["count"] == 7
    assert [w["slug"] for w in card["waters"]] == ["w0", "w1", "w2", "w3", "w4"]
    assert card["more"] == 2
    empty = site._county_card([], [], next_week_start="2026-09-20")
    assert empty == {
        "state": "none",
        "count": 0,
        "waters": [],
        "more": 0,
        "next_week": "2026-09-20",
        "also_next": False,
    }


# ---- /states/


def _expected_card(
    code: str, name: str, live: set[str]
) -> tuple[str, list[str] | None]:
    """A card's words and links, exactly as the template writes them. None for
    the links of a live card, which point at the state's own pages."""
    if code in live:
        return f"{name} Live on Trout Truck Open {name}'s schedule", None
    if code in state_coverage.COMING_SOON:
        return f"{name} Coming soon", []
    link = state_coverage.agency_link(code)
    if link.homepage_only:
        words = (
            f"{name} Not covered see {link.short}'s website: {link.agency} "
            "No stocking page could be confirmed, so this links to the agency's "
            "own site."
        )
    else:
        words = (
            f"{name} Not covered see the official schedule: {link.agency} "
            f"stocking page for {name}"
        )
    return words, [html_mod.escape(link.url, quote=True)]


def _coverage_problems(text: str, live: set[str]) -> list[str]:
    problems = []
    cards = CARD_RE.findall(text)
    names = [_text(c.split("</h3>", 1)[0]) for c in cards]
    if names != sorted(state_coverage.STATE_NAMES.values()):
        problems.append("the cards are not the 50 states and DC, alphabetical")
    by_name = dict(zip(names, cards, strict=True))
    for code, name in state_coverage.STATE_NAMES.items():
        card = by_name.get(name, "")
        hrefs = re.findall(r'href="([^"]*)"', card)
        words, links = _expected_card(code, name, live)
        # Exactly the template's words: no dates, waters, counts or summary.
        if _text(card) != words:
            problems.append(f"{code}: card says {_text(card)!r}")
        if links is None:
            ok = len(hrefs) == 1 and not urlsplit(hrefs[0]).scheme
            links = hrefs if ok else ["<one link to this site>"]
        if hrefs != links:
            problems.append(f"{code}: card links {hrefs}")
    return problems


def test_states_page_lists_every_state_with_production_coverage(built: Path) -> None:
    text = (built / "states" / "index.html").read_text(encoding="utf-8")
    assert len(CARD_RE.findall(text)) == 51
    assert _coverage_problems(text, {"CA", "TN"}) == []
    assert 'href="../">Open California' in text
    assert 'href="../tn/">Open Tennessee' in text
    assert text.count("Coming soon</span>") == 3


def test_a_coming_soon_state_turns_live_when_its_pages_exist(built_all: Path) -> None:
    text = (built_all / "states" / "index.html").read_text(encoding="utf-8")
    assert _coverage_problems(text, {"CA", "TN", "MA", "MI", "NY"}) == []
    assert "Coming soon</span>" not in text
    assert 'href="../ny/">Open New York' in text


def test_negative_control_copied_data_in_a_not_covered_card_is_caught(
    built: Path,
) -> None:
    text = (built / "states" / "index.html").read_text(encoding="utf-8")
    sabotaged = text.replace(
        "<h3>Oregon</h3>",
        "<h3>Oregon</h3><p>12 waters stocked the week of Oct 18</p>",
        1,
    )
    assert sabotaged != text  # the sabotage applied
    assert any(p.startswith("OR:") for p in _coverage_problems(sabotaged, {"CA", "TN"}))


def test_negative_control_a_second_link_in_a_not_covered_card_is_caught(
    built: Path,
) -> None:
    text = (built / "states" / "index.html").read_text(encoding="utf-8")
    sabotaged = text.replace(
        "<h3>Wyoming</h3>",
        '<h3>Wyoming</h3><a href="https://example.invalid/">x</a>',
        1,
    )
    assert sabotaged != text
    assert any(p.startswith("WY:") for p in _coverage_problems(sabotaged, {"CA", "TN"}))


def test_every_state_that_can_be_not_covered_has_an_agency_link() -> None:
    for code in state_coverage.STATE_NAMES:
        if code == "CA":
            continue  # the site itself
        link = state_coverage.agency_link(code)
        parts = urlsplit(link.url)
        assert parts.scheme == "https", code
        assert parts.netloc and "trouttruck" not in parts.netloc, code
        assert link.agency and link.short, code
    # Every state without a reader here has its own checked entry.
    assert set(state_coverage.AGENCY_LINKS) == (
        set(state_coverage.STATE_NAMES) - {"CA"} - set(SOURCES)
    )
    assert len(state_coverage.STATE_NAMES) == 51


def test_states_page_title_description_and_sitemap(built: Path) -> None:
    pages = _pages(built)
    text = pages["states/index.html"]
    title = _search(r"<title>(.*?)</title>", text).group(1)
    assert title == "Trout stocking schedule for all 50 states | Trout Truck"
    others = [
        n
        for n, t in pages.items()
        if n != "states/index.html" and f"<title>{title}</title>" in t
    ]
    assert others == []
    desc = _search(r'<meta name="description" content="([^"]*)"', text).group(1)
    assert len(html_mod.unescape(desc)) <= 160
    assert "Massachusetts, Michigan and New York coming soon" in html_mod.unescape(desc)
    sitemap = (built / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>{BASE_URL}/states/</loc>" in sitemap


# ---- fonts


def test_fonts_are_first_party_preloaded_and_swap(built: Path) -> None:
    css = (built / "assets" / "style.css").read_text(encoding="utf-8")
    assert css.count("@font-face{") == 2
    assert css.count("font-display:swap") == 2
    for name in site.FONT_FILES:
        assert f'url("fonts/{name}")' in css
        shipped = built / "assets" / "fonts" / name
        assert (
            shipped.read_bytes() == (site.TEMPLATES_DIR / "fonts" / name).read_bytes()
        )
        assert shipped.read_bytes()[:4] == b"wOF2"
    for name in site.FONT_LICENSE_FILES:
        assert "SIL Open Font License" in (built / "assets" / "fonts" / name).read_text(
            encoding="utf-8"
        )
    home = (built / "index.html").read_text(encoding="utf-8")
    for name in site.FONT_FILES:
        assert (
            f'<link rel="preload" href="./assets/fonts/{name}" as="font" '
            'type="font/woff2" crossorigin>'
        ) in home
    pages: dict[str, Any] = _pages(built)
    for text in pages.values():
        assert "fonts.googleapis.com" not in text
        assert "fonts.gstatic.com" not in text


# ---- gear block


def _gear_order_problems(pages: dict[str, str]) -> list[str]:
    problems = []
    for name, text in pages.items():
        for block in re.findall(r'<section class="gear".*?</section>', text, re.S):
            label = block.find(">Affiliate links</p>")
            disclosure = block.find(
                "As an Amazon Associate I earn from qualifying purchases."
            )
            first_link = block.find('rel="sponsored')
            if not 0 <= label < disclosure < first_link:
                problems.append(f"{name}: label, disclosure and links out of order")
    return problems


def test_gear_block_label_and_disclosure_come_before_the_links(built: Path) -> None:
    pages = _pages(built)
    blocks = sum(t.count('<section class="gear"') for t in pages.values())
    assert blocks > 30
    assert _gear_order_problems(pages) == []


def test_negative_control_a_disclosure_after_the_links_is_caught(built: Path) -> None:
    pages = _pages(built)
    name = next(n for n, t in pages.items() if '<section class="gear"' in t)
    text = pages[name]
    block = _search(r'<section class="gear".*?</section>', text, re.S).group(0)
    disclosure = _search(
        r'<p class="muted" id="gear-disclosure">.*?</p>', block, re.S
    ).group(0)
    moved = block.replace(disclosure, "").replace("</ul>", "</ul>" + disclosure, 1)
    sabotaged = text.replace(block, moved)
    assert sabotaged != text  # the sabotage applied
    assert _gear_order_problems({name: sabotaged})


# ---- a/an, and the carried-states table on a phone


@pytest.mark.parametrize(
    ("word", "article"),
    [
        ("Inyo", "an"),
        ("Alpine", "an"),
        ("El Dorado", "an"),
        ("Orange", "an"),
        ("Imperial", "an"),
        ("Modoc", "a"),
        ("Trinity", "a"),
        ("Eureka", "a"),
        ("Union", "a"),
        ("hour", "an"),
    ],
)
def test_indefinite_article_follows_the_first_sound(word: str, article: str) -> None:
    assert site.indefinite_article(word) == article


A_BEFORE_VOWEL = re.compile(
    r"\ba (?:Alameda|Alpine|Amador|El Dorado|Imperial|Inyo|Orange)\b"
)


def test_no_county_takes_the_wrong_article(built: Path) -> None:
    pages = _pages(built)
    assert "Planning a trip to an Inyo County water?" in pages["county/inyo/index.html"]
    assert [n for n, t in pages.items() if A_BEFORE_VOWEL.search(t)] == []


def test_negative_control_a_before_a_vowel_is_caught(built: Path) -> None:
    text = (built / "county" / "inyo" / "index.html").read_text(encoding="utf-8")
    sabotaged = text.replace("to an Inyo County", "to a Inyo County", 1)
    assert sabotaged != text  # the sabotage applied
    assert A_BEFORE_VOWEL.search(sabotaged)


def _stack_table_problems(text: str) -> list[str]:
    table = _search(r'<table class="stack-table".*?</table>', text, re.S).group(0)
    headers = re.findall(r'<th scope="col" role="columnheader">(.*?)</th>', table)
    problems = []
    rows = re.findall(r'<tr role="row">\s*(<td.*?)</tr>', table, re.S)
    if not rows:
        problems.append("no body rows")
    for row in rows:
        labels = re.findall(r'<td role="cell" data-label="([^"]*)">', row)
        if labels != headers:
            problems.append(f"labels {labels} are not the headers {headers}")
    return problems


def test_carried_states_table_stacks_with_labels_that_match_its_headers(
    built: Path,
) -> None:
    text = (built / "states" / "index.html").read_text(encoding="utf-8")
    assert _stack_table_problems(text) == []
    css = (site.TEMPLATES_DIR / "style.css").read_text(encoding="utf-8")
    assert (
        ".stack-table th, .stack-table td { overflow-wrap: normal; word-break: normal; }"
        in css
    )
    narrow = css.split("@media (max-width: 40rem) {", 1)[1]
    assert (
        ".stack-table, .stack-table tbody, .stack-table tr, .stack-table td { display: block; }"
        in narrow
    )


def test_negative_control_a_label_out_of_step_with_its_header_is_caught(
    built: Path,
) -> None:
    text = (built / "states" / "index.html").read_text(encoding="utf-8")
    sabotaged = text.replace('data-label="Agency"', 'data-label="Waters"', 1)
    assert sabotaged != text  # the sabotage applied
    assert _stack_table_problems(sabotaged)


def test_states_description_leads_with_the_search_phrase_when_it_fits() -> None:
    live = ["California", "Massachusetts", "Michigan", "New York", "Tennessee"]
    got = site_states._index_description(live, [])
    assert got.startswith("Trout stocking schedule by state: California, ")
    assert len(got) <= 160
    # Too long with the phrase: the old wording, still within the limit.
    soon = ["Massachusetts", "Michigan", "New York"]
    longer = site_states._index_description(["California", "Tennessee"], soon)
    assert longer.startswith("California and Tennessee trout stocking schedules; ")
    assert len(longer) <= 160
