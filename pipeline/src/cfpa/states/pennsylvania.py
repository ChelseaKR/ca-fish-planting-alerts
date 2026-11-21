"""Pennsylvania: PFBC's adult trout stocking schedule (a forward schedule).

**Off by default.** ``cfpa.states`` registers Pennsylvania only when
``CFPA_ENABLE_PENNSYLVANIA=1`` is set. Nothing in the daily run, the publish
workflow, the sitemap or the site changes while it is off. It stays off
until PFBC says yes in writing (DECISIONS 0055): the schedule page says
"All Rights Reserved", and under DECISIONS 0004 the licence is ``unknown``.

The source is PFBC's "Adult Trout Stocking By County" search,
https://fbweb.pa.gov/TroutStocking/, read on 2026-11-05. There is no
download and no open-data copy (data.pa.gov has none, checked 2026-11-04).
The page's own script sends one JSON POST per county to
``/TroutStocking/Home/Secondpage`` and gets back an HTML fragment; every
stocking in it is one ``div.stocksDiv`` whose ``data-mapatt`` attribute holds
17 fields separated by ``|``, in the order the page's script names them:

    Water | County | Sec | Upper_Limit | Lower_Limit | StkgingDate | WeekOf |
    Brook | Brown | Rainbow | Golden | MtgPlc | MtgTime | Hatchery |
    TroutRegulation1 | Reg_Link | Season

What this reader does with it:

- **A day or a week, never finer than PFBC gives.** ``StkgingDate``
  (YYYY-MM-DD) is a day. Some in-season rows give only ``WeekOf``
  (MM-DD-YYYY), always a Monday on 2026-11-05; that is shown as the week
  starting on that Monday, never as the Monday itself. PFBC does not say how
  long its week is, so the week is the full seven days. A row with neither
  is skipped.
- **The meeting time and place are not read.** They are where volunteers
  meet the truck, not a promise of when fish are in a given spot.
- **Species are marks, not counts.** Brook, Brown, Rainbow and Golden carry
  an "X". Each mark is one record in PFBC's word plus "trout"; there is no
  number of fish.
- **A water is a name, a county and a section.** PFBC stocks a creek in
  numbered sections (0 for a lake), and the section is part of the name
  shown ("Bald Eagle Creek, section 4").
- **An empty county must say so.** A county with nothing in the window
  answers "No Stockings in this Date Range"; a fragment with neither rows
  nor that sentence is refused. Every row's county must be the county asked.
- **One POST per county, ``POLITE_DELAY_SECONDS`` apart.** 67 counties is
  about six minutes a run. The window starts 14 days back, so a week that
  began before today is still read (an unseen current record would
  otherwise be marked removed), and runs to the end of what PFBC lists.

Copy rules (``COPY_RULES``): "scheduled", never "stocked on" or "planted";
a day or a week as PFBC gives it; no counts; PFBC says every event is
"subject to change without notice".
"""

from __future__ import annotations

import datetime as dt
import html
import re
from collections.abc import Callable
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import httpx

from .base import (
    FetchContext,
    FetchedBody,
    LicenseSource,
    ParsedFeed,
    ParsedRecord,
    Period,
    StateFormatError,
    StateSource,
    WaterMeta,
    check_robots_strict,
    combined_sha256,
    post_json_for_text,
    slugify,
)

PAGE_URL = "https://fbweb.pa.gov/TroutStocking/"
DATA_URL = "https://fbweb.pa.gov/TroutStocking/Home/Secondpage"
AGENCY_PAGE_URL = (
    "https://www.pa.gov/agencies/fishandboat/fishing/stocking/trout-stocking"
)
ENV_FLAG = "CFPA_ENABLE_PENNSYLVANIA"
TIME_ZONE = "America/New_York"
POLITE_DELAY_SECONDS = 5.0
LOOKBACK_DAYS = 14
EMPTY_SENTENCE = "No Stockings in this Date Range"
WEEK_DAYS = 7

FIELDS = (
    "Water",
    "County",
    "Sec",
    "Upper_Limit",
    "Lower_Limit",
    "StkgingDate",
    "WeekOf",
    "Brook",
    "Brown",
    "Rainbow",
    "Golden",
    "MtgPlc",
    "MtgTime",
    "Hatchery",
    "TroutRegulation1",
    "Reg_Link",
    "Season",
)
SPECIES = ("Brook", "Brown", "Rainbow", "Golden")
# PFBC's season codes, from the page's own filter: In & Pre Season (P, I),
# Fall (F), Winter (W). A new code is a changed page and is refused.
SEASONS = frozenset({"P", "I", "F", "W"})

# PFBC's 67 counties, as its county list spells them (read 2026-11-05).
COUNTIES = (
    "Adams",
    "Allegheny",
    "Armstrong",
    "Beaver",
    "Bedford",
    "Berks",
    "Blair",
    "Bradford",
    "Bucks",
    "Butler",
    "Cambria",
    "Cameron",
    "Carbon",
    "Centre",
    "Chester",
    "Clarion",
    "Clearfield",
    "Clinton",
    "Columbia",
    "Crawford",
    "Cumberland",
    "Dauphin",
    "Delaware",
    "Elk",
    "Erie",
    "Fayette",
    "Forest",
    "Franklin",
    "Fulton",
    "Greene",
    "Huntingdon",
    "Indiana",
    "Jefferson",
    "Juniata",
    "Lackawanna",
    "Lancaster",
    "Lawrence",
    "Lebanon",
    "Lehigh",
    "Luzerne",
    "Lycoming",
    "McKean",
    "Mercer",
    "Mifflin",
    "Monroe",
    "Montgomery",
    "Montour",
    "Northampton",
    "Northumberland",
    "Perry",
    "Philadelphia",
    "Pike",
    "Potter",
    "Schuylkill",
    "Snyder",
    "Somerset",
    "Sullivan",
    "Susquehanna",
    "Tioga",
    "Union",
    "Venango",
    "Warren",
    "Washington",
    "Wayne",
    "Westmoreland",
    "Wyoming",
    "York",
)

COPY_RULES = (
    "Say 'scheduled', never 'stocked on' a date and never 'planted'.",
    "A day or a week starting on a Monday, as PFBC gives it; never finer.",
    "Species are PFBC's marks; there is no number of fish.",
    "PFBC: every stocking event is subject to change without notice.",
)

FORBIDDEN = re.compile(
    r"\b(only|first|best|top|unique|planted|stocked on)\b", re.IGNORECASE
)

LICENSE = LicenseSource(
    name="PFBC Adult Trout Stocking By County page footer",
    url=PAGE_URL,
    terms_url=PAGE_URL,
    terms_read_on="2026-11-05",
    commercial_reuse="unknown",
    attribution_required=False,
    terms_quote=(
        'The schedule page footer says "Copyright © 2023 Commonwealth of '
        'Pennsylvania. All Rights Reserved". No reuse terms were found.'
    ),
)


class _Fragment(HTMLParser):
    """The county the server echoes, each stocking's ``data-mapatt``, and
    whether the "no stockings" sentence is there."""

    def __init__(self) -> None:
        super().__init__()
        self.county: str | None = None
        self.mapatts: list[str] = []
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if a.get("id") == "countyName":
            label = a.get("aria-label") or ""
            prefix = "Selected County is"
            if label.startswith(prefix):
                self.county = label[len(prefix) :].strip()
        classes = (a.get("class") or "").split()
        if tag == "div" and "stocksDiv" in classes:
            self.mapatts.append(a.get("data-mapatt") or "")

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    @property
    def says_empty(self) -> bool:
        return EMPTY_SENTENCE in " ".join(" ".join(self._text).split())


def _fields(mapatt: str) -> dict[str, str]:
    parts = html.unescape(mapatt).split("|")
    if len(parts) != len(FIELDS):
        raise StateFormatError(
            f"PFBC stocking has {len(parts)} fields, not {len(FIELDS)}: {mapatt[:80]!r}"
        )
    return {k: v.strip() for k, v in zip(FIELDS, parts, strict=True)}


def parse_body(text: str, county: str | None = None) -> list[dict[str, str]]:
    """Every stocking in one county's fragment. ``county`` is the county
    asked for, when known; the server's echo must match it."""
    p = _Fragment()
    p.feed(text)
    if p.county is None:
        raise StateFormatError("PFBC's answer does not name a county")
    if county is not None and p.county != county:
        raise StateFormatError(f"asked PFBC for {county}, got {p.county!r}")
    rows = [_fields(m) for m in p.mapatts]
    if not rows and not p.says_empty:
        raise StateFormatError(
            f"PFBC's answer for {p.county} has no stockings and no "
            f"{EMPTY_SENTENCE!r} sentence"
        )
    for r in rows:
        if r["County"] != p.county:
            raise StateFormatError(
                f"a {r['County']!r} stocking is in PFBC's answer for {p.county}"
            )
        if r["Season"] not in SEASONS:
            raise StateFormatError(f"PFBC season code {r['Season']!r} is new")
        for sp in SPECIES:
            if r[sp] not in ("", "X"):
                raise StateFormatError(f"PFBC {sp} mark {r[sp]!r} is not X or blank")
    return rows


def period(row: dict[str, str]) -> Period | None:
    """The stocking day, else the week starting on PFBC's Monday, else None."""
    if row["StkgingDate"]:
        try:
            return Period.day(dt.date.fromisoformat(row["StkgingDate"]))
        except ValueError as exc:
            raise StateFormatError(
                f"PFBC date {row['StkgingDate']!r} is not YYYY-MM-DD"
            ) from exc
    if row["WeekOf"]:
        try:
            monday = dt.datetime.strptime(row["WeekOf"], "%m-%d-%Y").date()
        except ValueError as exc:
            raise StateFormatError(
                f"PFBC week {row['WeekOf']!r} is not MM-DD-YYYY"
            ) from exc
        if monday.weekday() != 0:
            raise StateFormatError(f"PFBC week of {monday} is not a Monday")
        return Period(monday, monday + dt.timedelta(days=WEEK_DAYS - 1), "week")
    return None


def display_name(water: str, section: str) -> str:
    if section in ("", "0"):
        return water
    return f"{water}, section {section}"


def water_id(county: str, water: str, section: str) -> str:
    return "pa-" + slugify(county, water, "section", section or "0")


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for body in bodies:
        for row in parse_body(body.text):
            county, water, sec = row["County"], row["Water"], row["Sec"]
            if not water:
                skipped += 1
                continue
            wid = water_id(county, water, sec)
            shown = display_name(water, sec)
            waters[wid] = WaterMeta(
                id=wid,
                slug=slugify(shown, county, "county"),
                name=shown,
                counties=(county,),
                source_url=PAGE_URL,
            )
            when = period(row)
            marked = [sp for sp in SPECIES if row[sp] == "X"]
            if when is None or not marked:
                skipped += 1
                continue
            for sp in marked:
                rec = ParsedRecord(wid, when, f"{sp} trout")
                records[rec.key()] = rec
    first = bodies[0]
    return ParsedFeed(
        waters=waters,
        records=sorted(records.values(), key=lambda r: r.key()),
        fetched_at=first.fetched_at,
        content_sha256=combined_sha256(bodies),
        last_modified=first.last_modified,
        skipped=skipped,
    )


def search_payload(county: str, start: dt.date) -> dict[str, str]:
    """The search form exactly as PFBC's page sends it, all seasons."""
    return {
        "County": county,
        "StartDate": start.isoformat(),
        "EndDate": "",
        "PageNumber": "",
        "Water": "",
        "Season": "",
    }


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
    today: dt.date | None = None,
) -> list[FetchedBody]:
    check_robots_strict(client, DATA_URL, user_agent)
    start = (today or dt.datetime.now(ZoneInfo(TIME_ZONE)).date()) - dt.timedelta(
        days=LOOKBACK_DAYS
    )
    bodies: list[FetchedBody] = []
    for county in COUNTIES:
        sleep(POLITE_DELAY_SECONDS)
        body = post_json_for_text(
            client, DATA_URL, user_agent, search_payload(county, start)
        )
        parse_body(body.text, county)  # refuse a wrong or unreadable answer now
        bodies.append(body)
    return bodies


SOURCE = StateSource(
    code="PA",
    name="Pennsylvania",
    time_zone=TIME_ZONE,
    agency_name="Pennsylvania Fish and Boat Commission",
    agency_short_name="PFBC",
    agency_url=AGENCY_PAGE_URL,
    source_name="PFBC adult trout stocking schedule",
    source_url=PAGE_URL,
    data_urls=(DATA_URL,),
    semantics="schedule",
    date_precisions=("day", "week"),
    attribution_text=(
        "Data: Pennsylvania Fish and Boat Commission (PFBC), adult trout "
        f"stocking by county ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not endorsed by PFBC or the "
        "Commonwealth of Pennsylvania. These are PFBC's scheduled dates, not "
        'confirmed stockings. PFBC: "All stocking events are subject to change '
        'without notice." Where PFBC gives a week and no day, it is the week '
        "starting on that Monday. PFBC marks which trout species are planned "
        "and gives no number of fish."
    ),
    license_summary=(
        "PFBC's schedule page says All Rights Reserved and has no reuse terms. "
        "Whether reuse is allowed is unknown."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=None,
    min_rows=1,
    publish_since=None,
    fetch=fetch,
    parse=parse,
    week_starts_on=0,
    week_days=WEEK_DAYS,
    week_phrase="the week starting on a Monday",
)
