"""Calendar feeds on a schedule state's water pages (DECISIONS 0064).

Tennessee's water pages get California's calendar box (DECISIONS 0062) and a
``feed.ics`` next to each page, honest about the three shapes TWRA gives a
date: a day is a one-day event, a week-of Sunday is a seven-day event, and a
"TBD <month>" is never an event. Massachusetts and Michigan pages get
neither. Built from the pinned fixtures only; feeds are read with a strict
parser here, since the project has no iCalendar dependency.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from markupsafe import escape as html_escape

from cfpa import cli, ics, site

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "states"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
BASE = "https://example.invalid/ca-fish-planting-alerts"
PAGE = f"{BASE}/tn/water/doe-river-carter-county/"
# A calendar event is a calendar event, and a schedule is not a confirmation.
BANNED_IN_A_FEED = ("alert", "notification", "stocked", "planted")

STATE: dict[str, Any] = {
    "code": "TN",
    "name": "Tennessee",
    "semantics": "schedule",
    "agency": {
        "name": "Tennessee Wildlife Resources Agency",
        "short_name": "TWRA",
        "url": "https://www.tn.gov/twra.html",
    },
    "source": {"read_method": "manual"},
    "as_of": "2026-11-07",
}
AUTOMATED: dict[str, Any] = {
    **STATE,
    "source": {"read_method": "automated"},
    "as_of": "2026-10-15",
}


def _period(precision: str, start: str) -> dict[str, str]:
    d = dt.date.fromisoformat(start)
    if precision == "day":
        end = d
    elif precision == "week":
        end = d + dt.timedelta(days=6)
    else:
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        end = nxt - dt.timedelta(days=1)
    return {"precision": precision, "start": start, "end": end.isoformat()}


def _plant(
    precision: str, start: str, species: str = "Rainbow Trout", status: str = "listed"
) -> dict[str, Any]:
    return {
        "period": _period(precision, start),
        "species": species,
        "status": status,
        "count": None,
        "first_observed_at": "2026-10-12T19:18:13Z",
        "last_observed_at": "2026-11-07T19:23:44Z",
    }


def _water(
    plants: list[dict[str, Any]], months_note: str | None = None
) -> dict[str, Any]:
    return {
        "id": "tn-carter-doe-river",
        "name": "Doe River",
        "counties": ["Carter"],
        "towns": [],
        "months_note": months_note,
        "plants": plants,
    }


def _feed(water: dict[str, Any], state: dict[str, Any] = STATE) -> str:
    return ics.build_schedule_ics(
        water=water, state=state, page_url=PAGE, species="trout"
    )


# ---- a strict reader ---------------------------------------------------------

_DATE = re.compile(r"^\d{8}$")
_STAMP = re.compile(r"^\d{8}T\d{6}Z$")
_UNESCAPED = re.compile(r"(?<!\\)[,;]")


def _unfold(text: str) -> list[str]:
    """RFC 5545 §3.1: CRLF line endings, no content line over 75 octets, a
    continuation line starts with one space."""
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")
    raw = text.split("\r\n")[:-1]
    for line in raw:
        assert len(line.encode("utf-8")) <= 75, line
    assert not raw[0].startswith(" ")
    return text.replace("\r\n ", "").split("\r\n")[:-1]


def _parse(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    """(calendar properties, events), each property once per component,
    keyed by its name with parameters ("DTSTART;VALUE=DATE")."""
    lines = _unfold(text)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    cal: dict[str, str] = {}
    events: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for line in lines[1:-1]:
        if line == "BEGIN:VEVENT":
            assert cur is None
            cur = {}
            continue
        if line == "END:VEVENT":
            assert cur is not None
            events.append(cur)
            cur = None
            continue
        assert not line.startswith(("BEGIN:", "END:")), line
        name, value = line.split(":", 1)
        target = cal if cur is None else cur
        assert name not in target, name
        target[name] = value
    assert cur is None
    assert cal["VERSION"] == "2.0"
    assert cal["PRODID"] == ics.PRODID
    assert cal["CALSCALE"] == "GREGORIAN"
    for key in ("X-WR-CALNAME", "X-WR-CALDESC"):
        assert not _UNESCAPED.search(cal[key]), cal[key]
    uids = [e["UID"] for e in events]
    assert len(set(uids)) == len(uids)
    for e in events:
        assert _STAMP.match(e["DTSTAMP"])
        assert _DATE.match(e["DTSTART;VALUE=DATE"])
        assert _DATE.match(e["DTEND;VALUE=DATE"])
        assert _end(e) > _start(e)
        assert e["UID"].endswith("@" + ics.UID_DOMAIN)
        for key in ("SUMMARY", "DESCRIPTION"):
            assert not _UNESCAPED.search(e[key]), e[key]
        assert e["URL"] == PAGE or e["URL"].startswith(BASE)
    return cal, events


def _start(e: dict[str, str]) -> dt.date:
    return dt.datetime.strptime(e["DTSTART;VALUE=DATE"], "%Y%m%d").date()


def _end(e: dict[str, str]) -> dt.date:
    return dt.datetime.strptime(e["DTEND;VALUE=DATE"], "%Y%m%d").date()


def _span(e: dict[str, str]) -> int:
    return (_end(e) - _start(e)).days


def _month_long(events: list[dict[str, str]]) -> list[dict[str, str]]:
    """Events that render a month as a block of days: never allowed."""
    return [e for e in events if _span(e) >= 28]


def _text(ics_text: str) -> str:
    return ics_text.replace("\r\n ", "").replace("\\,", ",").replace("\\;", ";")


def _read_feed(path: Path) -> str:
    """Bytes, decoded: a text-mode read would turn the CRLF line endings
    the strict reader checks into LF."""
    return path.read_bytes().decode("utf-8")


def _no_banned_words(cal: dict[str, str], events: list[dict[str, str]]) -> None:
    """In every line a person reads. PRODID and UID carry the repository's
    name, "ca-fish-planting-alerts", pinned for calendar apps (DECISIONS
    0062's identity rule), and are not prose."""
    prose = [cal["X-WR-CALNAME"], cal["X-WR-CALDESC"]]
    prose += [e["SUMMARY"] + " " + e["DESCRIPTION"] for e in events]
    for line in prose:
        # The test site's base URL carries the repository's name too.
        words = line.replace(BASE, "").lower()
        for word in BANNED_IN_A_FEED:
            assert word not in words, (word, line)


# ---- the three date shapes --------------------------------------------------


def test_a_day_is_a_one_day_event_and_a_week_spans_the_agencys_week():
    cal, events = _parse(
        _feed(_water([_plant("day", "2026-12-09"), _plant("week", "2027-02-28")]))
    )
    assert cal["X-WR-CALNAME"] == "Doe River trout stocking schedule (TWRA)"
    day, week = events
    assert (day["DTSTART;VALUE=DATE"], day["DTEND;VALUE=DATE"]) == (
        "20261209",
        "20261210",
    )
    assert _span(day) == 1
    assert day["SUMMARY"] == "Doe River stocking scheduled (TWRA)"
    assert "for Wednesday\\, December 9\\, 2026." in day["DESCRIPTION"]
    assert (week["DTSTART;VALUE=DATE"], week["DTEND;VALUE=DATE"]) == (
        "20270228",
        "20270307",
    )
    assert _span(week) == 7
    assert _start(week).weekday() == 6  # TWRA's Sunday, never a day inside it
    assert week["SUMMARY"] == "Week of 2027-02-28: Doe River stocking scheduled (TWRA)"
    assert "the week of Sunday\\, February 28\\, 2027" in week["DESCRIPTION"]
    assert "within five days after that Sunday" in week["DESCRIPTION"]


def test_a_tbd_month_is_never_an_event_and_is_named_in_words():
    """TWRA's "TBD 12/2027" sets no day or week. A month-long block or a
    guessed day would render that absence as a date, so it is said in words:
    in the calendar's description and in the nearest dated event's."""
    text = _feed(_water([_plant("week", "2027-02-28"), _plant("month", "2027-12-01")]))
    cal, events = _parse(text)
    assert len(events) == 1
    assert _month_long(events) == []
    assert "TBD in December 2027 per TWRA: no day or week set yet" in _text(
        cal["X-WR-CALDESC"]
    )
    assert "Also TBD in December 2027 per TWRA" in _text(events[0]["DESCRIPTION"])
    assert "20271201" not in text and "December 1" not in text


def test_a_water_with_only_a_tbd_month_has_no_event_at_all():
    cal, events = _parse(_feed(_water([_plant("month", "2026-12-01")])))
    assert events == []
    assert "TBD in December 2026 per TWRA" in _text(cal["X-WR-CALDESC"])


def test_negative_control_the_month_check_catches_a_month_long_event():
    """The check behind the two tests above must be able to fail: a feed
    doctored to carry the TBD month as a December-long event is caught."""
    good = _feed(_water([_plant("week", "2027-02-28"), _plant("month", "2027-12-01")]))
    event = good[good.index("BEGIN:VEVENT") : good.index("END:VEVENT\r\n") + 12]
    fake = (
        event.replace("DTSTART;VALUE=DATE:20270228", "DTSTART;VALUE=DATE:20271201")
        .replace("DTEND;VALUE=DATE:20270307", "DTEND;VALUE=DATE:20280101")
        .replace("2027-02-28-week@", "2027-12-01-month@")
    )
    doctored = good.replace("END:VCALENDAR", fake + "END:VCALENDAR")
    assert doctored != good  # the sabotage landed
    _, events = _parse(doctored)
    assert len(events) == 2
    assert len(_month_long(events)) == 1
    assert _month_long(_parse(good)[1]) == []


def test_month_letters_are_never_events_and_are_explained():
    cal, events = _parse(_feed(_water([], months_note="M, A, M, J, J, A, S")))
    assert events == []
    assert (
        "TWRA also lists this water by month letters (M, A, M, J, J, A, S), "
        "which are not dates and are not events." in _text(cal["X-WR-CALDESC"])
    )


def test_a_date_twra_took_off_its_schedule_is_not_an_event():
    _, events = _parse(
        _feed(
            _water(
                [
                    _plant("week", "2027-02-28", status="removed"),
                    _plant("day", "2027-03-02"),
                ]
            )
        )
    )
    assert [e["DTSTART;VALUE=DATE"] for e in events] == ["20270302"]


def test_two_species_on_one_date_are_one_event_naming_both():
    _, events = _parse(
        _feed(
            _water(
                [
                    _plant("day", "2027-03-02", "Rainbow Trout"),
                    _plant("day", "2027-03-02", "Brook Trout"),
                ]
            )
        )
    )
    assert len(events) == 1
    assert (
        "lists Brook Trout and Rainbow Trout at Doe River" in events[0]["DESCRIPTION"]
    )
    assert events[0]["UID"] == "tn-carter-doe-river-2027-03-02-day@" + ics.UID_DOMAIN


# ---- what every event says ----------------------------------------------------


def test_every_event_credits_twra_links_the_page_and_gives_the_download_date():
    text = _feed(_water([_plant("day", "2026-12-09"), _plant("week", "2027-02-28")]))
    cal, events = _parse(text)
    assert "from TWRA's published schedule file, downloaded 2026-11-07" in _text(
        cal["X-WR-CALDESC"]
    )
    for e in events:
        d = _text(e["DESCRIPTION"])
        assert d.startswith("TWRA's published stocking schedule lists Rainbow Trout")
        assert "Scheduled, not confirmed: TWRA says any stocking could be" in d
        assert "Data: Tennessee Wildlife Resources Agency (TWRA), from TWRA's" in d
        assert "published schedule file, downloaded 2026-11-07" in d
        assert "Trout Truck is independent and is not endorsed by TWRA." in d
        assert d.endswith(PAGE)
        assert e["URL"] == PAGE
    _no_banned_words(cal, events)
    assert "CDFW" not in text


def test_an_automated_read_says_read_not_downloaded():
    cal, events = _parse(_feed(_water([_plant("day", "2026-12-09")]), AUTOMATED))
    assert "from TWRA's published schedule, read 2026-10-15" in _text(
        cal["X-WR-CALDESC"]
    )
    assert "read 2026-10-15" in _text(events[0]["DESCRIPTION"])
    assert "downloaded" not in _text(events[0]["DESCRIPTION"])


def test_uids_are_pinned_literals():
    """Calendar apps key events on UID; a change here would duplicate events
    in subscribers' calendars."""
    _, events = _parse(
        _feed(_water([_plant("day", "2026-12-09"), _plant("week", "2027-02-28")]))
    )
    assert [e["UID"] for e in events] == [
        "tn-carter-doe-river-2026-12-09-day@ca-fish-planting-alerts.invalid",
        "tn-carter-doe-river-2027-02-28-week@ca-fish-planting-alerts.invalid",
    ]
    assert [e["DTSTAMP"] for e in events] == ["20261107T192344Z"] * 2


# ---- the header California uses -----------------------------------------------


def test_the_header_is_californias_header():
    """Same PRODID, refresh interval, escaping and folding as
    site.build_water_ics. The copies in site.py stay until the open
    California pull requests land; this pins them equal meanwhile."""
    assert ics.REFRESH_INTERVAL == site.ICS_REFRESH == "PT12H"
    for sample in ("a,b;c\\d\ne", "plain", "Lake O'Neill, Pond #2; x"):
        assert ics.escape(sample) == site._ics_escape(sample)
    ca = site.build_water_ics(
        water={
            "id": "cdfw-1",
            "name": "Eagle Lake",
            "plants": [
                {
                    "week": {"start": "2026-09-13", "end": "2026-09-19"},
                    "species": "Trout",
                    "status": "listed",
                    "last_observed_at": "2026-09-13T12:00:00Z",
                }
            ],
        },
        base_url="https://example.invalid/water/x/",
        species="trout",
    )
    tn = _feed(_water([_plant("day", "2026-12-09")]))
    assert ca.split("\r\n")[:6] == tn.split("\r\n")[:6]
    header = tn.split("BEGIN:VEVENT", 1)[0]
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT12H" in header
    assert "X-PUBLISHED-TTL:PT12H" in header


def test_folding_keeps_every_line_within_75_octets_and_whole_characters():
    """RFC 5545 §3.1 counts a continuation line's leading space, and a
    multi-byte character must not be cut in two (site._ics_fold does both;
    the shared fold does neither, which the strict reader here enforces)."""
    for long in (
        "DESCRIPTION:" + "word " * 40,
        "X-WR-CALDESC:" + "é" * 80,
        "SUMMARY:" + "ab" * 37 + "é" + "x" * 20,
        "S:" + "x" * 73,  # exactly 75: untouched
    ):
        folded = ics.fold(long)
        lines = folded.split("\r\n")
        assert all(len(ln.encode("utf-8")) <= 75 for ln in lines), lines
        assert all(ln.startswith(" ") for ln in lines[1:])
        assert folded.replace("\r\n ", "") == long
    assert ics.fold("S:" + "x" * 73) == "S:" + "x" * 73
    assert "\r\n" in ics.fold("S:" + "x" * 74)


def test_which_states_get_a_feed():
    assert ics.has_feed({"code": "TN", "semantics": "schedule"})
    assert not ics.has_feed({"code": "CA", "semantics": "schedule"})  # site.py's
    assert not ics.has_feed({"code": "MA", "semantics": "report"})
    assert not ics.has_feed({"code": "MI", "semantics": "report"})
    assert not ics.has_feed({"code": "NY", "semantics": "plan"})


# ---- the built site, from fixtures --------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("tn-feeds")
    cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA,
        site_out=root / "site",
        base_url=BASE,
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        states_dir=root / "states",
        states_fetch=("TN", "MA", "MI"),
        states_fixtures=STATE_FIXTURES,
    )
    return root / "site"


def _waters(out: Path, code: str) -> list[dict[str, Any]]:
    v2 = json.loads((out / "snapshot" / "v2.json").read_text("utf-8"))
    return [w for w in v2["waters"] if w["state"] == code]


def _state(out: Path, code: str) -> dict[str, Any]:
    v2 = json.loads((out / "snapshot" / "v2.json").read_text("utf-8"))
    return next(s for s in v2["states"] if s["code"] == code)


def _page(out: Path, w: dict[str, Any]) -> str:
    return (out / w["site_path"].strip("/") / "index.html").read_text("utf-8")


_ANCHOR = re.compile(r'<a\b[^>]*data-ga-event="calendar_subscribe_click"[^>]*>')
_ATTR = re.compile(r'([a-z-]+)="([^"]*)"')


def _calendar_anchors(html: str) -> list[dict[str, str]]:
    return [dict(_ATTR.findall(m.group(0))) for m in _ANCHOR.finditer(html)]


def test_every_tennessee_water_page_shows_the_box_and_has_a_feed(built: Path):
    """The same partial as California's (DECISIONS 0062): the same three
    links in the same order, each with calendar_subscribe_click and its
    link_type, to this page's own feed; the words name TWRA, a day or a
    week, never CDFW, and never Android."""
    waters = _waters(built, "TN")
    assert len(waters) == 136
    for w in waters:
        html = _page(built, w)
        page_url = f"{BASE}{w['site_path']}"
        assert html.count('class="calendar-subscribe"') == 1, w["slug"]
        anchors = _calendar_anchors(html)
        assert [a["data-ga-type"] for a in anchors] == ["webcal", "google", "ics"]
        assert {a["data-ga-placement"] for a in anchors} == {"state_water"}
        webcal = "webcal://" + page_url.split("://", 1)[1] + "feed.ics"
        assert anchors[0]["href"] == webcal
        g = urlsplit(anchors[1]["href"])
        assert (g.scheme, g.hostname, g.path) == (
            "https",
            "calendar.google.com",
            "/calendar/r",
        )
        assert parse_qs(g.query) == {"cid": [webcal]}
        assert anchors[1]["href"].endswith(quote(webcal, safe=""))
        assert anchors[2]["href"] == "feed.ics"
        assert page_url + "feed.ics" in html
        assert (built / w["site_path"].strip("/") / "feed.ics").is_file()
        box = html[html.index('class="calendar-subscribe"') :]
        box = box[: box.index("</div>")]
        assert f"Get {html_escape(w['name'])}'s new dates in your calendar" in box
        assert "each day or week TWRA schedules" in box
        assert "Apple Calendar (iPhone, iPad, Mac): subscribe" in box
        assert "Google Calendar (any phone or computer): add it" in box
        assert "download a one-time copy (.ics)" in box
        assert "appears on a new date" in box
        assert "CDFW" not in box
        assert "android" not in html.lower()
        # After the lede, before the history table.
        assert (
            html.index('class="lede"')
            < html.index('class="calendar-subscribe"')
            < html.index("<h2>Stocking schedule and history</h2>")
        )


def test_massachusetts_and_michigan_pages_have_neither_box_nor_feed(built: Path):
    """A report of past stockings has nothing to subscribe to yet
    (DECISIONS 0064 says what each state would need)."""
    seen = 0
    for code in ("MA", "MI"):
        for w in _waters(built, code):
            html = _page(built, w)
            assert "calendar-subscribe" not in html, w["slug"]
            assert "calendar_subscribe_click" not in html, w["slug"]
            assert not (built / w["site_path"].strip("/") / "feed.ics").exists()
            seen += 1
    assert seen > 100
    assert not list((built / "ma").rglob("*.ics"))
    assert not list((built / "mi").rglob("*.ics"))


def test_every_built_tennessee_feed_is_valid_and_matches_its_data(built: Path):
    """Strictly parsed: one event per listed day or week, none for a TBD
    month, none for month letters, every event a one-day or seven-day
    all-day span, and the words the pages use for the data's age."""
    state = _state(built, "TN")
    counts = {"day": 0, "week": 0}
    tbd_feeds = 0
    letter_feeds = 0
    for w in _waters(built, "TN"):
        text = _read_feed(built / w["site_path"].strip("/") / "feed.ics")
        cal, events = _parse(text)
        listed = [p for p in w["plants"] if p["status"] == "listed"]
        dated = {
            (p["period"]["start"], p["period"]["precision"])
            for p in listed
            if p["period"]["precision"] in ("day", "week")
        }
        assert len(events) == len(dated), w["slug"]
        assert _month_long(events) == [], w["slug"]
        for e in events:
            assert _span(e) in (1, 7), (w["slug"], e["UID"])
            counts["day" if _span(e) == 1 else "week"] += 1
            assert "stocking scheduled (TWRA)" in e["SUMMARY"]
            assert (e["SUMMARY"].startswith("Week of ")) == (_span(e) == 7)
            assert _text(e["DESCRIPTION"]).endswith(f"{BASE}{w['site_path']}")
        months = [p for p in listed if p["period"]["precision"] == "month"]
        if months:
            tbd_feeds += 1
            assert "TBD in" in _text(cal["X-WR-CALDESC"]), w["slug"]
            for p in months:
                first = p["period"]["start"].replace("-", "")
                assert f"DTSTART;VALUE=DATE:{first}" not in text, w["slug"]
        else:
            assert "TBD in" not in text
        if w["months_note"]:
            letter_feeds += 1
            assert w["months_note"] in _text(cal["X-WR-CALDESC"])
        assert cal["X-WR-CALNAME"].startswith(ics.escape(w["name"]))
        _no_banned_words(cal, events)
        # The fixture is the automated read of 2026-09-13, so "read", not
        # "downloaded" (DECISIONS 0061).
        assert state["source"]["read_method"] == "automated"
        assert "read 2026-09-13" in _text(cal["X-WR-CALDESC"])
    # The 2026 fixture (616 rows, 136 waters): 452 week rows and 109 day rows,
    # each a distinct (water, date, species); 38 "TBD 12/2026" rows over 34
    # waters; 16 waters listed by month letters.
    assert counts == {"day": 109, "week": 452}
    assert tbd_feeds == 34
    assert letter_feeds == 16


def test_the_tbd_month_feed_from_the_fixture(built: Path):
    """McKenzie City Park: one day (1/14/2026) and "TBD 12/2026" in TWRA's
    2026 file. One event, and December is words, not a block."""
    w = next(x for x in _waters(built, "TN") if x["name"] == "McKenzie City Park")
    text = _read_feed(built / w["site_path"].strip("/") / "feed.ics")
    cal, events = _parse(text)
    assert [e["DTSTART;VALUE=DATE"] for e in events] == ["20260114"]
    assert "TBD in December 2026 per TWRA" in _text(cal["X-WR-CALDESC"])
    assert "Also TBD in December 2026 per TWRA" in _text(events[0]["DESCRIPTION"])
    # The page still offers the box: a subscriber hears when a day is set.
    assert 'class="calendar-subscribe"' in _page(built, w)


def test_a_month_letters_only_feed_has_no_event_and_says_why(built: Path):
    w = next(
        x for x in _waters(built, "TN") if x["name"].startswith("Norris Tailwater")
    )
    assert w["months_note"] and not w["plants"]
    cal, events = _parse(_read_feed(built / w["site_path"].strip("/") / "feed.ics"))
    assert events == []
    assert w["months_note"] in _text(cal["X-WR-CALDESC"])
    assert "not dates and are not events" in _text(cal["X-WR-CALDESC"])


def test_doe_river_reads_as_weeks(built: Path):
    w = next(x for x in _waters(built, "TN") if x["name"] == "Doe River")
    cal, events = _parse(_read_feed(built / w["site_path"].strip("/") / "feed.ics"))
    assert cal["X-WR-CALNAME"] == "Doe River trout stocking schedule (TWRA)"
    assert "for Doe River (Carter County, Tennessee)" in _text(cal["X-WR-CALDESC"])
    assert len(events) == 9 and all(_span(e) == 7 for e in events)
    assert (
        events[0]["SUMMARY"]
        == "Week of 2026-03-01: Doe River stocking scheduled (TWRA)"
    )
    assert (
        events[-1]["SUMMARY"]
        == "Week of 2026-10-04: Doe River stocking scheduled (TWRA)"
    )


def test_the_california_box_is_unchanged(built: Path):
    """The partial's new variables default to California's words, so a
    California page reads exactly as DECISIONS 0062 wrote it."""
    snap = json.loads((built / "snapshot" / "v1.json").read_text("utf-8"))
    html = (built / "water" / snap["waters"][0]["slug"] / "index.html").read_text(
        "utf-8"
    )
    anchors = _calendar_anchors(html)
    assert [a["data-ga-type"] for a in anchors] == ["webcal", "google", "ics"]
    assert {a["data-ga-placement"] for a in anchors} == {"water"}
    assert "new weeks in your calendar" in html
    assert "Subscribe once: each week CDFW schedules" in html
    assert "appears in a new week" in html
    assert "TWRA" not in html
