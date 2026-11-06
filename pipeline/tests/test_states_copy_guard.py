"""/states/ as the honest coverage page (DECISIONS 0051, plan N4).

- No title or heading anywhere on the site claims coverage: "all 50 states",
  "every state", "all states" or "nationwide" (``_claim_problems``).
- "Live on Trout Truck" only for a state in v2; a v2 state whose checks have
  failed for more than a week says "Updates paused since <last good read>".
- "Asking the agency" only for a state with a send date recorded in
  ``data/states_asked.json``; a malformed entry stops the build.
- The do-not-do states say "the agency's terms don't allow reuse".
- No per-state stub page and no signup.

Each negative control sabotages a page or the data, asserts the sabotage
applied, and asserts the guard notices.
"""

from __future__ import annotations

import copy
import datetime as dt
import html as html_mod
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, site, site_states, state_coverage

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

CLAIM = re.compile(
    r"\b(all 50 states|all fifty states|every state|all states|nationwide)\b", re.I
)
CARD_RE = re.compile(r'<li class="tt-state[^"]*" id="state-(\w\w)">(.*?)</li>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return " ".join(html_mod.unescape(TAG_RE.sub("", fragment)).split())


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
    return _build(tmp_path_factory.mktemp("guard"), ("TN", "MA", "MI", "NY"))


def _snapshots(out: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    v1 = json.loads((out / "snapshot" / "v1.json").read_text("utf-8"))
    v2 = json.loads((out / "snapshot" / "v2.json").read_text("utf-8"))
    return v1, v2


def _rebuild(built: Path, out: Path, v2: dict[str, Any]) -> str:
    """The site rebuilt from ``built``'s v1 and a (doctored) v2; /states/."""
    v1, _ = _snapshots(built)
    site.build_site(v1, out, base_url=BASE_URL, snapshot_v2=v2)
    return (out / "states" / "index.html").read_text("utf-8")


def _cards(text: str) -> dict[str, str]:
    return {code.upper(): _text(body) for code, body in CARD_RE.findall(text)}


# ---- titles and headings


def _claim_problems(name: str, html: str) -> list[str]:
    lines = re.findall(r"<title>(.*?)</title>", html, re.S)
    lines += re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.S)
    lines += re.findall(
        r'<meta (?:property="og:title"|name="twitter:title") content="([^"]*)"', html
    )
    return [f"{name}: {_text(x)!r}" for x in lines if CLAIM.search(_text(x))]


def test_no_title_or_heading_on_the_site_claims_coverage(built: Path) -> None:
    pages = sorted(built.rglob("*.html"))
    assert len(pages) > 100
    problems = [p for f in pages for p in _claim_problems(str(f), f.read_text("utf-8"))]
    assert problems == []


def test_the_states_title_and_h1_are_the_approved_ones(built: Path) -> None:
    text = (built / "states" / "index.html").read_text("utf-8")
    assert "<title>Trout stocking schedule by state | Trout Truck</title>" in text
    assert "<h1>Trout stocking schedule by state</h1>" in text
    assert site_states.STATES_INDEX_HEADING == "Trout stocking schedule by state"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "<h1>Trout stocking schedule by state</h1>",
            "<h1>Trout stocking schedule for every state</h1>",
        ),
        (
            "schedule by state | Trout Truck</title>",
            "schedule for all 50 states | Trout Truck</title>",
        ),
        (
            '<h2 id="every-state">Where each state stands</h2>',
            '<h2 id="every-state">Every state</h2>',
        ),
        (
            "<h1>Trout stocking schedule by state</h1>",
            "<h1>Trout stocking, nationwide</h1>",
        ),
    ],
)
def test_control_a_coverage_claim_in_a_title_or_heading_is_caught(
    built: Path, old: str, new: str
) -> None:
    text = (built / "states" / "index.html").read_text("utf-8")
    sabotaged = text.replace(old, new, 1)
    assert sabotaged != text  # the sabotage applied
    assert _claim_problems("states", sabotaged)
    assert not _claim_problems("states", text)


# ---- live and paused come from v2


def test_live_cards_are_exactly_the_v2_states(built: Path) -> None:
    _, v2 = _snapshots(built)
    cards = _cards((built / "states" / "index.html").read_text("utf-8"))
    assert len(cards) == 51
    live = {c for c, t in cards.items() if " Live on Trout Truck " in f" {t} "}
    assert live == {s["code"] for s in v2["states"]}
    assert not any("Updates paused" in t for t in cards.values())


def _stale(v2: dict[str, Any], code: str, days: float) -> dict[str, Any]:
    doctored = copy.deepcopy(v2)
    now = dt.datetime.fromisoformat(doctored["generated_at"].replace("Z", "+00:00"))
    last = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for s in doctored["states"]:
        if s["code"] == code:
            s["checks"].update(last_attempt_ok=False, last_success_at=last)
    return doctored


def test_a_state_failing_for_over_a_week_reads_paused_with_its_date(
    built: Path, tmp_path: Path
) -> None:
    _, v2 = _snapshots(built)
    doctored = _stale(v2, "TN", 10)
    assert doctored != v2  # the sabotage applied
    text = _rebuild(built, tmp_path / "paused", doctored)
    tn = next(s for s in doctored["states"] if s["code"] == "TN")
    day = dt.date.fromisoformat(tn["checks"]["last_success_at"][:10])
    label = f"{day.strftime('%b')} {day.day}, {day.year}"
    cards = _cards(text)
    assert cards["TN"] == (
        f"Tennessee Updates paused since {label} Open Tennessee's schedule"
    )
    # The live table says it too, instead of a bare "last checked" date.
    assert f"Updates paused since {label}</td>" in text
    assert "Live on Trout Truck" not in cards["TN"]
    # Still carried: the pages stay up and the lede still names Tennessee.
    assert 'href="../tn/">Open Tennessee' in text


def test_control_a_short_failure_is_not_called_paused(
    built: Path, tmp_path: Path
) -> None:
    _, v2 = _snapshots(built)
    text = _rebuild(built, tmp_path / "short", _stale(v2, "TN", 3))
    assert "Live on Trout Truck" in _cards(text)["TN"]
    assert not any("Updates paused" in t for t in _cards(text).values())
    assert "Updates paused since" not in text


# ---- asking only with a recorded send date


def test_the_committed_asked_file_is_valid() -> None:
    raw = json.loads(state_coverage.ASKED_PATH.read_text("utf-8"))
    assert set(raw) == {"about", "asked"}
    state_coverage.load_asked()  # raises on any malformed entry


def test_no_card_says_asking_without_a_recorded_date(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "asked.json"
    empty.write_text('{"asked": {}}', "utf-8")
    monkeypatch.setattr(state_coverage, "ASKED_PATH", empty)
    _, v2 = _snapshots(built)
    text = _rebuild(built, tmp_path / "none", v2)
    assert "Asking" not in text.split('id="every-state"', 1)[1].split("</p>", 1)[1]


def test_a_recorded_send_date_shows_asking_since_that_date(
    built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = tmp_path / "asked.json"
    asked.write_text('{"asked": {"OR": "2026-11-02", "TN": "2026-11-02"}}', "utf-8")
    monkeypatch.setattr(state_coverage, "ASKED_PATH", asked)
    _, v2 = _snapshots(built)
    cards = _cards(_rebuild(built, tmp_path / "asked", v2))
    assert cards["OR"].startswith("Oregon Asking the agency, since Nov 2, 2026 ")
    # A live state stays live: being asked never outranks having pages.
    assert "Live on Trout Truck" in cards["TN"]
    assert "Asking" not in cards["TN"]
    assert "Asking" not in cards["PA"]


@pytest.mark.parametrize(
    "body",
    [
        '{"asked": {"OR": ""}}',
        '{"asked": {"OR": null}}',
        '{"asked": {"OR": "soon"}}',
        '{"asked": {"OR": "2099-01-01"}}',
        '{"asked": {"XX": "2026-11-02"}}',
        '{"asked": ["OR"]}',
    ],
)
def test_control_an_undated_or_malformed_entry_stops_the_build(
    tmp_path: Path, body: str
) -> None:
    path = tmp_path / "asked.json"
    path.write_text(body, "utf-8")
    with pytest.raises(state_coverage.AskedFileError):
        state_coverage.load_asked(path)


# ---- the other statuses


def test_do_not_do_states_say_the_terms_dont_allow_reuse(built: Path) -> None:
    cards = _cards((built / "states" / "index.html").read_text("utf-8"))
    for code in state_coverage.TERMS_DONT_ALLOW:
        assert (
            "Not planned The agency\u2019s terms don\u2019t allow reuse." in cards[code]
        )
    others = set(cards) - state_coverage.TERMS_DONT_ALLOW
    assert not any("terms don" in cards[c] for c in others)
    assert {
        "AK",
        "ID",
        "IN",
        "MN",
        "MO",
        "NC",
        "TX",
        "WA",
    } == state_coverage.TERMS_DONT_ALLOW


def test_every_card_has_its_anchor(built: Path) -> None:
    text = (built / "states" / "index.html").read_text("utf-8")
    ids = re.findall(r'<li class="tt-state[^"]*" id="(state-\w\w)">', text)
    assert len(ids) == len(set(ids)) == 51
    assert 'id="every-state"' in text


def test_no_stub_pages_and_no_signup(built: Path) -> None:
    states_dir = built / "states"
    assert [p.name for p in states_dir.iterdir()] == ["index.html"]
    text = (states_dir / "index.html").read_text("utf-8")
    for marker in ("<form", "<input", "mailto:", "sign up", "signup", "notify me"):
        assert marker not in text.lower(), marker
    assert "Coming soon" not in text


def test_control_the_card_parser_reads_a_status(built: Path) -> None:
    text = (built / "states" / "index.html").read_text("utf-8")
    sabotaged = text.replace(
        "Trout Truck doesn&rsquo;t carry Oregon.", "Asking the agency, since soon.", 1
    )
    assert sabotaged != text
    assert "Asking" in _cards(sabotaged)["OR"]
