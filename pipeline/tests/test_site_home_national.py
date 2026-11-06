"""The national home page (DECISIONS 0052, plan N5).

A build whose v2 carries more than one state leads its home page with
"Trout stocking schedules by state" and one card per v2 state. California's
this-week list stays on the same URL under its own H2, which keeps the
sentence that was the H1. Every card, and every state the title and
description name, comes from v2, so these tests build with different states
and doctor v2 to check that the page follows the data:

- no card for a state v2 does not carry, and none missing for one it does;
- a state whose checks have failed for more than a week says "Updates
  paused since <last good read>" (the /states/ rule, DECISIONS 0051);
- a state with no waters on record shows no count, never a zero.

A California-only build keeps the California home page byte for byte; that
is test_snapshot_v2's
test_a_california_only_v2_leaves_every_california_page_unchanged.

Each negative control asserts that its sabotage applied before it asserts
that the check caught it.
"""

from __future__ import annotations

import copy
import datetime as dt
import html as htmllib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, share_cards, site, state_coverage

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"

CARD_RE = re.compile(
    r'<li class="tt-state tt-state--live" id="home-state-(\w\w)">(.*?)</li>', re.S
)


def _build(root: Path, states: tuple[str, ...]) -> Path:
    out = root / "site"
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states" if states else None,
        states_fetch=states,
        states_fixtures=FIXTURES / "states" if states else None,
    )
    return out


@pytest.fixture(scope="module")
def five(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("five"), ("TN", "MA", "MI", "NY"))


@pytest.fixture(scope="module")
def two(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("two"), ("TN",))


@pytest.fixture(scope="module")
def plain(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("plain"), ())


def _home(out: Path) -> str:
    return (out / "index.html").read_text("utf-8")


def _v2(out: Path) -> dict[str, Any]:
    v2: dict[str, Any] = json.loads((out / "snapshot" / "v2.json").read_text("utf-8"))
    return v2


def _rebuild(built: Path, out: Path, v2: dict[str, Any]) -> str:
    """The home page rebuilt from ``built``'s v1 and a (doctored) v2."""
    v1 = json.loads((built / "snapshot" / "v1.json").read_text("utf-8"))
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    return _home(out)


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _cards(page: str) -> dict[str, str]:
    """Each state card's visible text, by its state code (upper case)."""
    return {code.upper(): _text(body) for code, body in CARD_RE.findall(page)}


def _one(pattern: str, page: str) -> str:
    m = re.search(pattern, page, re.S)
    assert m, pattern
    return htmllib.unescape(m.group(1))


def _title(page: str) -> str:
    return _one(r"<title>(.*?)</title>", page)


def _description(page: str) -> str:
    return _one(r'<meta name="description" content="([^"]*)"', page)


def _card_problems(page: str, v2: dict[str, Any]) -> list[str]:
    """Every way the state cards can disagree with v2."""
    cards = _cards(page)
    want = [s["code"] for s in v2["states"]]
    out = []
    if list(cards) != want:
        out.append(f"cards {list(cards)} are not v2's states {want}")
    for s in v2["states"]:
        text = cards.get(s["code"], "")
        if s["agency"]["short_name"] not in text:
            out.append(f"{s['code']}: agency missing")
        count = s["waters_count"]
        if count and f"{count} waters" not in text:
            out.append(f"{s['code']}: waters count missing")
    return out


# ---- title, H1, description and California's section


def test_a_multi_state_home_is_national(five: Path) -> None:
    page = _home(five)
    assert _title(page) == "Trout stocking schedules by state | Trout Truck"
    assert re.findall(r"<h1[^>]*>(.*?)</h1>", page) == [
        "Trout stocking schedules by state"
    ]
    # California's sentence, which was the H1, is the California section's H2.
    label = _v2(five)["states"][0]["current_week"]["label"]
    h2 = _one(r'<h2 id="california">(.*?)</h2>', page)
    assert h2.startswith(
        ("California trout planting schedule", "This week's California")
    )
    assert h2.endswith(label)
    assert "Each state's wildlife agency publishes trout stocking differently." in (
        _text(page)
    )
    # The picker comes before California's section.
    assert page.index('id="pick-state"') < page.index('id="california"')


def test_the_description_names_each_v2_state(five: Path) -> None:
    v2 = _v2(five)
    description = _description(_home(five))
    assert len(description) <= site.HOME_DESCRIPTION_MAX
    assert description.startswith("Trout stocking by state: ")
    for s in v2["states"]:
        assert s["name"] in description


def test_a_long_state_list_falls_back_to_a_count() -> None:
    names = [f"State number {i}" for i in range(12)]
    text = site._home_description_national(
        names, "week of 2026-09-13", week_is_empty=False
    )
    assert text == (
        "Trout stocking by state, from 12 state agencies. California's "
        "schedule for the week of 2026-09-13 and each water's history."
    )
    short = site._home_description_national(
        ["California", "Tennessee"], "week of 2026-09-13", week_is_empty=True
    )
    assert short == (
        "Trout stocking by state: California and Tennessee. California's next "
        "and latest scheduled waters and each water's history."
    )


def test_a_california_only_build_keeps_the_california_home(plain: Path) -> None:
    page = _home(plain)
    assert 'id="pick-state"' not in page
    assert "state_card_click" not in page
    assert _title(page) == "California trout planting schedule this week | Trout Truck"
    assert re.search(r"<h1>(This week's )?California trout planting schedule", page)
    assert "share/national.png" not in page
    assert not (plain / "assets" / "share" / "national.png").exists()


# ---- the state cards


def test_one_card_per_v2_state_in_v2_order(five: Path, two: Path) -> None:
    for out in (five, two):
        assert _card_problems(_home(out), _v2(out)) == []
    assert list(_cards(_home(two))) == ["CA", "TN"]


def test_no_card_for_a_state_outside_v2(five: Path, tmp_path: Path) -> None:
    v2 = copy.deepcopy(_v2(five))
    v2["states"] = [s for s in v2["states"] if s["code"] != "MI"]
    page = _rebuild(five, tmp_path / "out", v2)
    assert "MI" not in _cards(page)
    assert "Michigan" not in _text(page.split('id="california"')[0])
    assert "Michigan" not in _description(page)
    assert _card_problems(page, v2) == []


def test_control_a_card_v2_does_not_carry_is_caught(five: Path) -> None:
    page = _home(five)
    v2 = copy.deepcopy(_v2(five))
    v2["states"] = [s for s in v2["states"] if s["code"] != "NY"]
    assert "NY" in _cards(page)  # the page has the card v2 no longer carries
    assert _card_problems(page, v2) != []


def test_each_card_links_a_page_this_build_wrote(five: Path) -> None:
    page = _home(five)
    hrefs = dict(
        re.findall(
            r'<a href="([^"]+)" data-ga-event="state_card_click"[^>]*'
            r'data-ga-state="(\w\w)"',
            page,
        )
    )
    by_code = {code: href for href, code in hrefs.items()}
    assert by_code["CA"] == "#california"
    for code, href in by_code.items():
        if code != "CA":
            assert href == f"{code.lower()}/"
            assert (five / href / "index.html").exists(), href
    assert 'href="./states/#every-state"' in page
    assert 'id="every-state"' in (five / "states" / "index.html").read_text("utf-8")


def test_card_words_follow_each_agency(five: Path) -> None:
    cards = _cards(_home(five))
    assert cards["CA"].startswith("California Weekly schedule from CDFW")
    assert "Open the California weekly schedule" in cards["CA"]
    assert "Open the New York spring plan" in cards["NY"]
    assert "Open the Michigan stocking report" in cards["MI"]


def _stale(v2: dict[str, Any], code: str, days: int) -> dict[str, Any]:
    """``v2`` with ``code``'s latest check failed and its last good read
    ``days`` before v2 was generated."""
    v2 = copy.deepcopy(v2)
    now = dt.datetime.fromisoformat(v2["generated_at"].replace("Z", "+00:00"))
    state = next(s for s in v2["states"] if s["code"] == code)
    state["checks"]["last_attempt_ok"] = False
    state["checks"]["last_success_at"] = (now - dt.timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return v2


def test_a_stale_state_says_updates_paused_since_its_last_good_read(
    five: Path, tmp_path: Path
) -> None:
    v2 = _stale(_v2(five), "TN", 10)
    last = dt.date.fromisoformat(
        next(s for s in v2["states"] if s["code"] == "TN")["checks"]["last_success_at"][
            :10
        ]
    )
    page = _rebuild(five, tmp_path / "out", v2)
    tn = _cards(page)["TN"]
    assert f"Updates paused since {last.strftime('%B')} {last.day}, {last.year}" in tn
    assert "Last checked" not in tn
    # The other states are untouched, and the pages stay linked.
    assert all("Updates paused" not in t for c, t in _cards(page).items() if c != "TN")
    assert "Open the Tennessee schedule" in tn
    # /states/ and the home page use the one rule.
    tn_v2 = next(s for s in v2["states"] if s["code"] == "TN")
    now = dt.datetime.fromisoformat(v2["generated_at"].replace("Z", "+00:00"))
    assert state_coverage._paused_since(tn_v2, now) == last


def test_control_a_failed_check_inside_the_week_is_not_paused(
    five: Path, tmp_path: Path
) -> None:
    v2 = _stale(_v2(five), "TN", 3)
    tn_v2 = next(s for s in v2["states"] if s["code"] == "TN")
    assert tn_v2["checks"]["last_attempt_ok"] is False  # the sabotage applied
    tn = _cards(_rebuild(five, tmp_path / "out", v2))["TN"]
    assert "Updates paused" not in tn
    assert "Last checked" in tn


def test_a_state_with_no_waters_shows_no_count(five: Path, tmp_path: Path) -> None:
    v2 = copy.deepcopy(_v2(five))
    next(s for s in v2["states"] if s["code"] == "MA")["waters_count"] = 0
    ma = _cards(_rebuild(five, tmp_path / "out", v2))["MA"]
    assert "0 waters" not in ma and "waters" not in ma
    assert ma.startswith("Massachusetts Stocking report from MassWildlife Last checked")


# ---- the share card, llms.txt and the analytics markup


def test_the_home_page_uses_the_national_share_card(five: Path) -> None:
    page = _home(five)
    assert f"{BASE}/assets/share/national.png" in page
    assert (five / "assets" / "share" / "national.png").exists()
    card = share_cards.CARD_KINDS["national"]
    assert "stock" not in f"{card.title} {card.subtitle}".lower()
    # The other pages keep their own cards.
    assert "share/county.png" in (five / "county" / "index.html").read_text("utf-8")


def test_llms_txt_describes_the_national_home(five: Path, plain: Path) -> None:
    text = (five / "llms.txt").read_text("utf-8")
    assert (
        f"- [Home]({BASE}/): each state on this site at a glance, and "
        "California's schedule for the current week"
    ) in text
    assert f"- [States]({BASE}/states/): each state's status" in text
    assert "Each agency publishes on its own rhythm" in text
    old = (plain / "llms.txt").read_text("utf-8")
    assert f"- [Home]({BASE}/): this week's California schedule" in old
    assert "[States]" not in old and "own rhythm" not in old


def test_every_card_link_carries_the_click_event_and_its_state(five: Path) -> None:
    page = _home(five)
    anchors = re.findall(r"<a\b[^>]*data-ga-event=\"state_card_click\"[^>]*>", page)
    assert len(anchors) == len(_v2(five)["states"])
    for a in anchors:
        assert 'data-ga-placement="home"' in a
        assert 'data-ga-type="state_card"' in a
        assert re.search(r'data-ga-state="[A-Z]{2}"', a)
