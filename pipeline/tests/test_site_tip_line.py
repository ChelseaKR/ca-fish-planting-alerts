"""The Ko-fi tip line (DECISIONS 0073).

One sentence at the end of every water page (California and every other
state) and one line at the end of every calendar event's description
(California's and Tennessee's feeds), both pointing at ``tip.KOFI_URL``. No
other page carries it, nothing goes into the snapshots the apps read, and the
app sources never name Ko-fi. The feeds are read with a strict RFC 5545
reader (line length in octets, CRLF, continuation lines, TEXT escaping).
``tip.KOFI_URL = ""`` turns every trace off. The negative controls assert
that each sabotage changed the text before they assert the checker noticed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, ics, site, tip

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
REPO = Path(__file__).resolve().parents[2]
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"

# The approved words, exactly (Chelsea, 2026-11-17; DECISIONS 0073). The
# address comes from tip.KOFI_URL, so swapping in the real page changes
# nothing here. The calendar line carries the full https address.
CALENDAR_LINE = (
    f"Free calendar from Trout Truck, made by one person. Tips: {tip.KOFI_URL}"
)
# The link is a plain one: it opens in the same tab, like every other link on
# the site (0073 addendum, 2026-11-17), so it carries no target and no rel.
PAGE_LINE = (
    '<p class="tip-line muted">Trout Truck is free and made by one person. '
    f'<a href="{tip.KOFI_URL}">'
    "You can leave a tip on Ko-fi.</a></p>"
)
# Never in the tip wording: no safety, catch or outcome claim, no "no
# tracking", nothing that ties a tip to what the data did for someone.
BANNED_WORDS = (
    "safe",
    "catch",
    "caught",
    "bite",
    "trip",
    "help",
    "save",
    "track",
    "guarantee",
    "alert",
    "notification",
    "stocked",
    "planted",
)


# ---- the constant and the wording ----------------------------------------------


def test_the_address_is_one_well_formed_ko_fi_page_and_not_the_placeholder():
    """KOFI_URL is a plain https Ko-fi page address, and never the
    placeholder the branch carried before Chelsea sent her page."""
    assert re.fullmatch(r"https://ko-fi\.com/[A-Za-z0-9_]+", tip.KOFI_URL)
    assert "placeholder" not in tip.KOFI_URL.lower()


def test_the_water_page_line_is_on_since_the_board_answered():
    """Chelsea, 2026-11-17: hold the water-page line while the appeal is
    open, add it once Apple answers. The Board answered on 2026-11-17, so it
    is on. Changing this is a deliberate edit with its DECISIONS note."""
    assert tip.TIP_ON_WATER_PAGES is True
    assert tip.page_context() is not None
    assert tip.calendar_line() == CALENDAR_LINE


def test_the_switch_off_leaves_the_calendar_line(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tip, "TIP_ON_WATER_PAGES", False)
    assert tip.page_context() is None
    assert tip.calendar_line() == CALENDAR_LINE


def test_the_wording_is_the_approved_wording_and_makes_no_claim():
    assert tip.calendar_line() == CALENDAR_LINE
    assert tip.PAGE_LEAD == "Trout Truck is free and made by one person."
    assert tip.PAGE_LINK_TEXT == "You can leave a tip on Ko-fi."
    for text in (tip.calendar_line(), tip.PAGE_LEAD, tip.PAGE_LINK_TEXT):
        low = text.lower()
        assert not [w for w in BANNED_WORDS if w in low], text


def test_the_water_page_context_when_switched_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tip, "TIP_ON_WATER_PAGES", True)
    assert tip.page_context() == {
        "url": tip.KOFI_URL,
        "lead": "Trout Truck is free and made by one person.",
        "link_text": "You can leave a tip on Ko-fi.",
    }


def test_empty_url_turns_the_line_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tip, "KOFI_URL", "")
    monkeypatch.setattr(tip, "TIP_ON_WATER_PAGES", True)
    assert tip.calendar_line() == ""
    assert tip.page_context() is None
    assert ics.with_tip("x") == "x"


# ---- a strict RFC 5545 reader --------------------------------------------------

_UNESCAPED = re.compile(r"(?<!\\)[,;]")


def _strict_lines(text: str) -> list[str]:
    """RFC 5545 §3.1: CRLF only, no physical line over 75 octets (a
    continuation's leading space counts), a continuation starts with one
    space; returns the unfolded content lines."""
    problems = _fold_problems(text)
    assert not problems, problems
    return text.replace("\r\n ", "").split("\r\n")[:-1]


def _fold_problems(text: str) -> list[str]:
    found = []
    if not text.endswith("\r\n"):
        found.append("does not end with CRLF")
    if "\n" in text.replace("\r\n", "") or "\r" in text.replace("\r\n", ""):
        found.append("a bare CR or LF")
    for line in text.split("\r\n")[:-1]:
        if len(line.encode("utf-8")) > 75:
            found.append(f"{len(line.encode('utf-8'))} octets: {line!r}")
    if "�" in text:
        found.append("a replacement character: a multi-byte character was cut")
    return found


def _unescape(value: str) -> str:
    """RFC 5545 §3.3.11 TEXT, read back."""
    out, i = [], 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _descriptions(text: str) -> list[str]:
    """Every event's DESCRIPTION value, still escaped, each checked for an
    unescaped comma or semicolon."""
    values = []
    for line in _strict_lines(text):
        if line.startswith("DESCRIPTION:"):
            value = line.split(":", 1)[1]
            assert not _UNESCAPED.search(value), value
            values.append(value)
    return values


def _ca_feed(name: str = "Shadow Cliff Lake") -> str:
    return site.build_water_ics(
        water={
            "id": "cdfw-1",
            "name": name,
            "plants": [
                {
                    "week": {"start": "2026-09-13", "end": "2026-09-19"},
                    "species": "Rainbow Trout",
                    "status": "listed",
                    "last_observed_at": "2026-09-13T12:00:00Z",
                },
                {
                    "week": {"start": "2026-09-20", "end": "2026-09-26"},
                    "species": "Rainbow Trout",
                    "status": "listed",
                    "last_observed_at": "2026-09-20T12:00:00Z",
                },
            ],
        },
        base_url="https://trouttruck.com/water/shadow-cliff-lake/",
        species="trout",
    )


def _tn_feed() -> str:
    state = {
        "code": "TN",
        "name": "Tennessee",
        "semantics": "schedule",
        "agency": {
            "name": "Tennessee Wildlife Resources Agency",
            "short_name": "TWRA",
        },
        "source": {"read_method": "manual"},
        "as_of": "2026-11-07",
    }
    plant = {
        "period": {"precision": "day", "start": "2026-12-09", "end": "2026-12-09"},
        "species": "Rainbow Trout",
        "status": "listed",
        "count": None,
        "first_observed_at": "2026-10-12T19:18:13Z",
        "last_observed_at": "2026-11-07T19:23:44Z",
    }
    water = {
        "id": "tn-carter-doe-river",
        "name": "Doe River",
        "counties": ["Carter"],
        "towns": [],
        "months_note": None,
        "plants": [plant],
    }
    return ics.build_schedule_ics(
        water=water,
        state=state,
        page_url="https://trouttruck.com/tn/water/doe-river-carter-county/",
        species="trout",
    )


# ---- the feeds -----------------------------------------------------------------


def test_every_california_event_ends_with_the_line_escaped_and_folded():
    text = _ca_feed()
    descriptions = _descriptions(text)
    assert len(descriptions) == 2
    want = (
        "CDFW plants are subject to change. "
        "https://trouttruck.com/water/shadow-cliff-lake/\n" + CALENDAR_LINE
    )
    for d in descriptions:
        # The newline is the two characters \n and the comma is \, on the wire.
        assert d.endswith(
            "\\nFree calendar from Trout Truck\\, made by one person. "
            f"Tips: {tip.KOFI_URL}"
        )
        assert _unescape(d) == want
    # The description is long enough to need folding, so the fold is tested.
    assert any(ln.startswith(" ") for ln in text.split("\r\n"))


def test_every_tennessee_event_ends_with_the_line_escaped_and_folded():
    text = _tn_feed()
    descriptions = _descriptions(text)
    assert len(descriptions) == 1
    read = _unescape(descriptions[0])
    assert read.endswith(
        "https://trouttruck.com/tn/water/doe-river-carter-county/\n" + CALENDAR_LINE
    )
    assert read.count(CALENDAR_LINE) == 1


def test_the_line_is_never_the_calendars_own_description_or_an_event():
    """Each event's description only: not the calendar's name or
    description, not a summary, and never an event of its own."""
    for text in (_ca_feed(), _tn_feed()):
        lines = _strict_lines(text)
        events = sum(1 for ln in lines if ln == "BEGIN:VEVENT")
        for line in lines:
            if "ko-fi" in line.lower():
                assert line.startswith("DESCRIPTION:"), line
        assert sum("ko-fi" in ln.lower() for ln in lines) == events


def test_a_multibyte_water_name_is_folded_without_cutting_a_character():
    name = "Lago Élan Ñandú " * 4
    text = _ca_feed(name.strip())
    _strict_lines(text)
    assert name.strip() in text.replace("\r\n ", "")


def test_a_comma_or_semicolon_in_the_address_is_escaped(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tip, "KOFI_URL", "https://ko-fi.com/a,b;c\\d")
    for d in _descriptions(_ca_feed()) + _descriptions(_tn_feed()):
        assert d.endswith("Tips: https://ko-fi.com/a\\,b\\;c\\\\d")
        assert _unescape(d).endswith("Tips: https://ko-fi.com/a,b;c\\d")


def test_off_the_feeds_are_as_before(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tip, "KOFI_URL", "")
    ca, tn = _ca_feed(), _tn_feed()
    assert "ko-fi" not in ca.lower() and "ko-fi" not in tn.lower()
    for d in _descriptions(ca):
        assert _unescape(d) == (
            "CDFW plants are subject to change. "
            "https://trouttruck.com/water/shadow-cliff-lake/"
        )
    for d in _descriptions(tn):
        assert _unescape(d).endswith(
            "https://trouttruck.com/tn/water/doe-river-carter-county/"
        )


def test_negative_controls_the_reader_catches_a_bad_fold_and_a_bare_comma():
    text = _ca_feed()
    # California's old local fold: 75 octets, then a space plus 75 more.
    raw = "DESCRIPTION:" + "x" * 160
    old = "\r\n ".join([raw[:75], raw[75:150], raw[150:]])
    bad = text.replace("END:VCALENDAR\r\n", old + "\r\nEND:VCALENDAR\r\n")
    assert bad != text
    assert any("76 octets" in p for p in _fold_problems(bad))
    cut = text.replace("Shadow", "Sh�dow", 1)
    assert cut != text
    assert any("replacement" in p for p in _fold_problems(cut))
    unescaped = text.replace("Trout Truck\\, made", "Trout Truck, made")
    assert unescaped != text
    with pytest.raises(AssertionError):
        _descriptions(unescaped)


# ---- the built site ------------------------------------------------------------


@pytest.fixture(scope="module")
def snapshots(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any]:
    """The v1 and v2 snapshots of a fixture run with three other states on."""
    root = tmp_path_factory.mktemp("tip-snap")
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
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=FIXTURES / "states",
    )
    v1 = json.loads((out / "snapshot" / "v1.json").read_text(encoding="utf-8"))
    v2 = json.loads((out / "snapshot" / "v2.json").read_text(encoding="utf-8"))
    return v1, v2


def _build(root: Path, snaps: tuple[Any, Any], *, water_pages: bool) -> Path:
    """Build the site with ``tip.TIP_ON_WATER_PAGES`` set to ``water_pages``
    (restored afterwards; module fixtures cannot use monkeypatch)."""
    out = root / "site"
    v1, v2 = snaps
    original = tip.TIP_ON_WATER_PAGES
    tip.TIP_ON_WATER_PAGES = water_pages
    try:
        site.build_site(
            v1,
            out,
            base_url=BASE_URL,
            snapshot_v2=v2,
            build_date=dt.date(2026, 12, 1),
        )
    finally:
        tip.TIP_ON_WATER_PAGES = original
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory, snapshots: Any) -> Path:
    """The switch off: the calendar line on, the water-page line off."""
    return _build(tmp_path_factory.mktemp("tip-default"), snapshots, water_pages=False)


@pytest.fixture(scope="module")
def built_on(tmp_path_factory: pytest.TempPathFactory, snapshots: Any) -> Path:
    """As shipped since the Board answered (2026-11-17): both on."""
    return _build(tmp_path_factory.mktemp("tip-on"), snapshots, water_pages=True)


def _water_pages(out: Path) -> set[Path]:
    """California's /water/<slug>/ and every state's /<st>/water/<slug>/."""
    pages = set(out.glob("water/*/index.html"))
    pages |= set(out.glob("*/water/*/index.html"))
    return pages


def _page_problems(out: Path, *, water_pages: bool = True) -> list[str]:
    """On: the exact line once, last in <main>, on every water page, and
    nowhere else. No Ko-fi script, image, frame or analytics label anywhere,
    and nothing in a snapshot."""
    want = _water_pages(out) if water_pages else set()
    found: list[str] = []
    states_seen = {p.relative_to(out).parts[0] for p in _water_pages(out)}
    if "water" not in states_seen or len(states_seen) < 2:
        found.append(f"water pages of too few states were built: {states_seen}")
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.suffix not in {
            ".html",
            ".xml",
            ".txt",
            ".json",
            ".js",
            ".webmanifest",
        }:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(out)
        count = text.lower().count("ko-fi.com")
        if path in want:
            if text.count(PAGE_LINE) != 1 or count != 1:
                found.append(f"{rel}: the line is not there exactly once")
                continue
            main = text.split('<main id="main"', 1)[1].split("</main>", 1)[0]
            if not main.rstrip().endswith(PAGE_LINE):
                found.append(f"{rel}: the line is not the end of <main>")
        elif count:
            found.append(f"{rel}: Ko-fi on a page that should not have it")
        for pattern in (
            r"<script[^>]*ko-fi",
            r"<(img|iframe)[^>]*ko-fi",
            r"ko-fi[^>]*data-ga",
            r"data-ga[^>]*ko-fi",
            r"storage\.ko-fi|ko-fi[^\"']*widget",
        ):
            if re.search(pattern, text, re.I):
                found.append(f"{rel}: {pattern}")
    return found


_KOFI_LINK = re.compile(r"<a\b[^>]*\bhref=\"https://ko-fi\.com/[^\"]*\"[^>]*>", re.I)


def _new_tab_problems(out: Path) -> list[str]:
    """Every Ko-fi link on every built page that would open a new tab, or
    that carries a rel left over from when it did."""
    found: list[str] = []
    seen = 0
    for path in sorted(out.rglob("*.html")):
        for tag in _KOFI_LINK.findall(path.read_text(encoding="utf-8")):
            seen += 1
            for attribute in ("target", "rel"):
                if re.search(rf"\b{attribute}\s*=", tag):
                    found.append(f"{path.relative_to(out)}: {attribute} on {tag}")
    if not seen:
        found.append("no Ko-fi link on any built page, so this checked nothing")
    return found


def test_the_tip_link_opens_in_the_same_tab(built_on: Path):
    """The 2026-11-17 accessibility sweep's T5: the tip link was the only link
    on the site that opened a new tab, and it did not say so. A screen
    reader or magnifier user found the Back button dead with no word of
    why. The owner chose the same tab over adding words (0073 addendum), so
    the link carries no `target`, and no `rel="noopener"`, which was there
    only for the new tab. The words do not change."""
    assert _new_tab_problems(built_on) == []
    assert set(tip.page_context() or {}) == {"url", "lead", "link_text"}
    assert not hasattr(tip, "LINK_TARGET")
    assert not hasattr(tip, "LINK_REL")
    template = (Path(site.TEMPLATES_DIR) / "_tip_line.html.jinja").read_text("utf-8")
    assert "target=" not in template
    assert "rel=" not in template


def test_negative_control_a_new_tab_link_is_caught(tmp_path: Path, snapshots: Any):
    out = _build(tmp_path, snapshots, water_pages=True)
    assert _new_tab_problems(out) == []
    page = sorted(out.glob("water/*/index.html"))[0]
    text = page.read_text(encoding="utf-8")
    old = text.replace(
        f'<a href="{tip.KOFI_URL}">',
        f'<a href="{tip.KOFI_URL}" target="_blank" rel="noopener">',
        1,
    )
    assert old != text
    page.write_text(old, encoding="utf-8")
    problems = _new_tab_problems(out)
    assert len(problems) == 2
    assert all(str(page.relative_to(out)) in problem for problem in problems)


def test_switched_off_no_page_has_the_line(built: Path):
    """TIP_ON_WATER_PAGES False: no page, feeds unchanged (0073)."""
    assert _page_problems(built, water_pages=False) == []
    for page in built.rglob("*.html"):
        assert "tip-line" not in page.read_text(encoding="utf-8"), page


def test_as_shipped_every_water_page_and_no_other_page_has_the_line(
    built_on: Path,
):
    assert _page_problems(built_on) == []


@pytest.mark.parametrize("which", ["built", "built_on"])
def test_every_built_feed_event_ends_with_the_line(
    which: str, request: pytest.FixtureRequest
):
    """The calendar line does not depend on the switch: on in both builds."""
    out: Path = request.getfixturevalue(which)
    feeds = sorted(out.rglob("feed.ics"))
    assert any(p.parts[-3] == "water" and p.parts[-4] == "site" for p in feeds)
    assert any(p.relative_to(out).parts[0] == "tn" for p in feeds)
    for feed in feeds:
        text = feed.read_bytes().decode("utf-8")
        for d in _descriptions(text):
            assert _unescape(d).endswith("\n" + CALENDAR_LINE), feed


def test_the_snapshots_the_apps_read_never_carry_it(snapshots: Any, built_on: Path):
    """The apps read snapshot/v1.json and v2.json (written by the pipeline
    run, not the page build); the page build writes no other JSON with it."""
    for snap in snapshots:
        text = json.dumps(snap).lower()
        assert "ko-fi" not in text and "kofi" not in text
    for path in built_on.rglob("*.json"):
        assert "ko-fi" not in path.read_text(encoding="utf-8").lower(), path


@pytest.mark.parametrize("water_pages", [False, True])
def test_no_address_no_page_and_no_feed_has_it(
    water_pages: bool,
    tmp_path: Path,
    snapshots: Any,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(tip, "KOFI_URL", "")
    out = _build(tmp_path, snapshots, water_pages=water_pages)
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".ics", ".json", ".xml"}:
            text = path.read_bytes().decode("utf-8", errors="ignore").lower()
            assert "ko-fi" not in text, path
            assert "tip-line" not in text, path


def test_negative_controls_the_page_check_notices(tmp_path: Path, snapshots: Any):
    out = _build(tmp_path, snapshots, water_pages=True)
    assert _page_problems(out) == []
    ca = sorted(out.glob("water/*/index.html"))[0]
    tn = sorted(out.glob("tn/water/*/index.html"))[0]
    home = out / "index.html"

    def sabotage(path: Path, old: str, new: str) -> None:
        text = path.read_text(encoding="utf-8")
        changed = text.replace(old, new, 1)
        assert changed != text
        path.write_text(changed, encoding="utf-8")

    sabotage(ca, PAGE_LINE, "")
    sabotage(
        tn,
        f'<a href="{tip.KOFI_URL}">',
        f'<a href="{tip.KOFI_URL}" data-ga-event="tip">',
    )
    sabotage(home, "</main>", PAGE_LINE + "</main>")
    problems = "\n".join(_page_problems(out))
    assert str(ca.relative_to(out)) in problems
    assert str(tn.relative_to(out)) in problems
    assert "index.html: Ko-fi on a page that should not have it" in problems
    # With the switch off, a water page carrying the line is caught too.
    off = _build(tmp_path / "off", snapshots, water_pages=False)
    assert _page_problems(off, water_pages=False) == []
    ca_off = sorted(off.glob("water/*/index.html"))[0]
    sabotage(ca_off, "</main>", PAGE_LINE + "</main>")
    assert str(ca_off.relative_to(off)) in "\n".join(
        _page_problems(off, water_pages=False)
    )


# ---- the apps ------------------------------------------------------------------


def test_the_app_sources_never_name_ko_fi():
    """The iOS app (and the Android one) show no tip: they read the
    snapshot only, open the site in the system browser, and have no web view
    and no calendar feed (DECISIONS 0011, 0073). Any Ko-fi string in their
    sources would be a tip inside an app."""
    hits = []
    for tree in ("ios", "android"):
        for path in (REPO / tree).rglob("*"):
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            if path.suffix in {".png", ".jpg", ".jar", ".keystore", ".car"}:
                continue
            text = path.read_bytes().decode("utf-8", errors="ignore").lower()
            if "ko-fi" in text or "kofi" in text:
                hits.append(str(path.relative_to(REPO)))
    assert hits == []
