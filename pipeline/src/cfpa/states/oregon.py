"""Oregon: ODFW's weekly trout stocking schedule (a forward schedule).

**Off by default.** This module is importable, but ``cfpa.states`` only
registers Oregon when the environment variable ``CFPA_ENABLE_OREGON=1`` is
set (see ``cfpa.states.registered_sources``). Nothing in the daily run, the
publish workflow, the sitemap or the site changes while it is off. Oregon
stays off until the owner decides: ODFW's page and the State's website terms
are silent on reuse, so under DECISIONS 0004 ("Unknown = not used") the
licence below is recorded as ``unknown``.

The source, https://myodfw.com/fishing/species/trout/stocking-schedule, is
one HTML table (a Drupal view), one row per waterbody per week:

    Week of | Waterbody | Zone/Office | Legals | Trophy | Brood | Fingerling | Total

What is different from California and Tennessee, all read on 2026-10-20/21:

- **Weeks run Monday to Friday.** ODFW: "The Monday dates listed indicate
  the START of the week." CDFW and TWRA weeks start on a Sunday.
- **The view is capped at 50 rows** per request with no pager, and the
  ``stocking-schedule-print`` view is capped at 500 rows (it stopped at
  2027-05-07 while the schedule runs past 2028-02). A silently cut-off page
  would drop waters, so the fetch asks for one Monday-to-Friday window at a
  time, splits a window that fills the cap into the six zones, and refuses a
  page that is still at the cap.
- **There is no species column and no county.** The four count columns are
  size classes of trout; each non-zero count is one record, labeled with
  ODFW's own words (no inch sizes: the page gives none). Zone (six) is the
  place; the office after the slash is unstable and is never used.
- **An empty week renders no table and no "no results" sentence**, the same
  as a broken page, so the filter form must be present for an empty week to
  be believed.
- **Names are upper-case and abbreviated, with no id.** A water is a name
  plus a zone: LOST LK is four lakes, FISH LK three, CLEAR LK two.
- **The far weeks look carried forward** (November 2027 matches November
  2026 row for row). Only a fixed, near window is fetched: ``HORIZON_WEEKS``.

Copy rules for anything shown to people about Oregon (``COPY_RULES``,
pinned by ``tests/test_oregon.py``):

1. ODFW says "stocking" and "stocked"; California says "planting". The site
   says "scheduled" for what ODFW lists, as it does for every state, and
   never gives a stocking as having happened ("scheduled", never "stocked
   on" a date, never "planted").
2. ODFW lists the WEEK, not a day, and says stocking "may happen a week
   before/after the scheduled date". Show a week, never a day.
3. Size classes keep ODFW's words: Legals, Trophy, Brood, Fingerling. No
   inch sizes, because the current page gives none.
4. ODFW lists a water once for each week it plans to stock it, with a count
   per class, and often more than once a season. How often a water appears
   is ODFW's plan for the weeks fetched, not a promise or a rate: never
   "every other week", never a total for the season, and "nothing later
   listed" means nothing later within the weeks fetched.
5. Counts are ODFW's planned fish for that week. Two offices listing the
   same water and week are added together.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from collections.abc import Callable
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import httpx

from .base import (
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
    get_text,
    slugify,
)

PAGE_URL = "https://myodfw.com/fishing/species/trout/stocking-schedule"
DATA_URL = PAGE_URL  # the same URL with date (and zone) filters
TERMS_URL = "https://www.oregon.gov/pages/terms-and-conditions.aspx"
ROW_CAP = 50
# How many Monday-to-Friday weeks, counting the current one, one run reads.
# Fixed, never "until empty": the merge flags an unseen future record as
# removed, so a window that changed length would flip records wrongly.
HORIZON_WEEKS = 8
POLITE_DELAY_SECONDS = 5.0
TIME_ZONE = "America/Los_Angeles"
FORM_ID = "views-exposed-form-stocking-schedule-block-1"
ENV_FLAG = "CFPA_ENABLE_OREGON"

# ODFW's zone filter, in the order the page's own select lists them.
ZONES = ("Central", "Northeast", "Northwest", "Southeast", "Southwest", "Willamette")
ZONE_FILTER = {name: str(i) for i, name in enumerate(ZONES, start=1)}

# Column header -> the label shown to people (ODFW's own word, plus "trout").
COLUMNS = {
    "Legals": "Legal-size trout",
    "Trophy": "Trophy trout",
    "Brood": "Brood trout",
    "Fingerling": "Fingerling trout",
}
HEADERS = ("Week of", "Waterbody", "Zone/Office", *COLUMNS, "Total")

# Words the brief's copy rules keep out of site copy. "stocked on <date>" and
# "planted" would claim a day or a happened-stocking; the rest are claims
# nobody can back up. The disclaimer's word is "scheduled".
FORBIDDEN = re.compile(
    r"\b(only|first|best|top|unique|planted|stocked on)\b", re.IGNORECASE
)

# The two phrases that would say a stocking already happened, which a
# schedule never says; checked across every rendered Oregon page.
FORBIDDEN_CLAIMS = re.compile(r"\b(planted|stocked on)\b", re.IGNORECASE)

COPY_RULES = (
    "Say 'scheduled', never 'planted' and never 'stocked on' a date.",
    "ODFW lists a week (Monday to Friday), never a day; show the week.",
    "Size classes keep ODFW's words and carry no inch sizes.",
    "How often a water appears is ODFW's plan for the weeks fetched, not a rate.",
    "Counts are planned fish for that week; two offices' rows are added.",
)

LICENSE = LicenseSource(
    name="Oregon.gov Terms and Conditions (the State's websites); ODFW page footer",
    url=PAGE_URL,
    terms_url=TERMS_URL,
    terms_read_on="2026-10-20",
    commercial_reuse="unknown",
    attribution_required=False,
    terms_quote=(
        "ODFW's schedule page footer says: \"Copyright 2026 Oregon Department of "
        'Fish & Wildlife". The State\'s terms say: "The content and services '
        'provided by the Sites are provided \\"as is\\" and without warranties '
        'of any kind" and that "some Sites have additional terms and '
        'conditions". Neither grants or denies reuse.'
    ),
)

_ABBREV = {
    "LK": "Lake",
    "PD": "Pond",
    "RES": "Reservoir",
    "CR": "Creek",
    "R": "River",
    "PK": "Park",
    "FMR": "Former",
    "MT": "Mount",
    "RD": "Road",
    "CO": "County",
}  # a reviewed alias file, like California's, is the production answer


@dataclasses.dataclass
class _Cell:
    text: str = ""
    times: list[str] = dataclasses.field(default_factory=list)


class _Table(HTMLParser):
    """The results table and the filter form's id, with no regex over tags."""

    def __init__(self) -> None:
        super().__init__()
        self.has_form = False
        self.has_table = False
        self.rows: list[list[_Cell]] = []
        self._cell: _Cell | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "form" and a.get("id") == FORM_ID:
            self.has_form = True
        elif tag == "table":
            self.has_table = True
        elif tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th") and self.rows:
            self._cell = _Cell()
            self.rows[-1].append(self._cell)
        elif tag == "time" and self._cell is not None and a.get("datetime"):
            self._cell.times.append(a["datetime"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.text += data


@dataclasses.dataclass(frozen=True)
class _Row:
    start: dt.date
    end: dt.date
    name: str
    zone: str
    counts: dict[str, int]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def display_name(raw: str) -> str:
    """'HENRY HAGG LK' -> 'Henry Hagg Lake'. Unreviewed: a name with a
    leftover abbreviation is shown as ODFW wrote it, never guessed at."""
    words = []
    for w in re.split(r"(\s+|-)", raw):
        core = w.strip(",.")
        if core.isupper() and core in _ABBREV:
            words.append(_ABBREV[core])
        elif w.isupper() and len(w) > 1:
            words.append(w.capitalize())
        else:
            words.append(w)
    return "".join(words)


def water_id(name: str, zone: str) -> str:
    # The zone is part of the identity (see the module docstring). The office
    # is not: one lake appears under several offices from week to week.
    return "or-" + slugify(name, zone)


def _count(text: str) -> int:
    t = text.replace(",", "")
    if not t.isdigit():
        raise StateFormatError(f"ODFW count {text!r} is not a number")
    return int(t)


def parse_body(text: str) -> list[_Row]:
    p = _Table()
    p.feed(text)
    if not p.has_table:
        # An empty week renders the filter form and nothing else. A broken
        # page looks the same, so without the form it is refused.
        if not p.has_form:
            raise StateFormatError(
                "ODFW page has neither the table nor the filter form"
            )
        return []
    rows = [r for r in p.rows if r]
    if not rows or [_clean(c.text) for c in rows[0]] != list(HEADERS):
        raise StateFormatError("ODFW's table headers changed: refused")
    out: list[_Row] = []
    for r in rows[1:]:
        if len(r) != len(HEADERS):
            raise StateFormatError(f"ODFW row has {len(r)} cells")
        if len(r[0].times) != 2:
            raise StateFormatError("ODFW row without a start and end date")
        try:
            start, end = (dt.date.fromisoformat(t[:10]) for t in r[0].times)
        except ValueError as exc:
            raise StateFormatError(
                f"ODFW week date {r[0].times!r} is not a date"
            ) from exc
        zone = _clean(r[2].text).partition("/")[0].strip()
        counts = {k: _count(_clean(r[3 + i].text)) for i, k in enumerate(COLUMNS)}
        total = _count(_clean(r[7].text))
        name = _clean(r[1].text)
        if sum(counts.values()) != total:
            raise StateFormatError(
                f"ODFW total {total} is not the sum of its columns {counts} for {name}"
            )
        out.append(_Row(start, end, name, zone, counts))
    return out


def _check_row(row: _Row) -> bool:
    """False for a row with no zone (skipped); raises for a changed shape."""
    if row.start.weekday() != 0 or row.end != row.start + dt.timedelta(days=4):
        raise StateFormatError(
            f"ODFW week {row.start}..{row.end} is not Monday..Friday"
        )
    if row.zone == "":
        return False  # seen on 2026-10-20: a row with no zone or office
    if row.zone not in ZONES:
        raise StateFormatError(f"ODFW zone {row.zone!r} is new")
    return True


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for body in bodies:
        rows = parse_body(body.text)
        if len(rows) >= ROW_CAP:
            raise StateFormatError(
                f"{body.url} returned {len(rows)} rows, the view's cap; it may be "
                "cut off, so it is refused"
            )
        for row in rows:
            if not _check_row(row):
                skipped += 1
                continue
            wid = water_id(row.name, row.zone)
            shown = display_name(row.name)
            waters[wid] = WaterMeta(
                id=wid,
                slug=slugify(shown, row.zone),
                name=shown,
                counties=(),
                region=row.zone,
                source_id=None,
                source_url=PAGE_URL,
            )
            if not any(row.counts.values()):
                skipped += 1
                continue
            for col, label in COLUMNS.items():
                n = row.counts[col]
                if not n:
                    continue
                rec = ParsedRecord(wid, Period(row.start, row.end, "week"), label, n)
                k = rec.key()
                if k in records:  # the same water, week and class twice: add up
                    rec = ParsedRecord(
                        wid, rec.period, label, n + (records[k].count or 0)
                    )
                records[k] = rec
    first = bodies[0]
    return ParsedFeed(
        waters=waters,
        records=sorted(records.values(), key=lambda r: r.key()),
        fetched_at=first.fetched_at,
        content_sha256=combined_sha256(bodies),
        last_modified=first.last_modified,
        skipped=skipped,
    )


def monday_of(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def window_params(monday: dt.date, zone: str | None = None) -> dict[str, str]:
    params = {
        "field_planned_stocking_date_value": monday.isoformat(),
        "field_planned_stocking_date_end_value": (
            monday + dt.timedelta(days=4)
        ).isoformat(),
    }
    if zone is not None:
        params["field_zone_value"] = ZONE_FILTER[zone]
    return params


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    known_newest: dt.date | None = None,
    today: dt.date | None = None,
) -> list[FetchedBody]:
    """HORIZON_WEEKS windows from this week's Monday. A window that fills the
    row cap is read again one zone at a time; a zone that still fills it is
    refused. One request per URL, ``POLITE_DELAY_SECONDS`` apart."""
    check_robots_strict(client, DATA_URL, user_agent)
    first_monday = monday_of(today or dt.datetime.now(ZoneInfo(TIME_ZONE)).date())
    bodies: list[FetchedBody] = []
    for i in range(HORIZON_WEEKS):
        monday = first_monday + dt.timedelta(weeks=i)
        sleep(POLITE_DELAY_SECONDS)
        body = get_text(
            client,
            DATA_URL,
            user_agent,
            params=window_params(monday),
            accept="text/html",
        )
        if len(parse_body(body.text)) < ROW_CAP:
            bodies.append(body)
            continue
        for zone in ZONES:
            sleep(POLITE_DELAY_SECONDS)
            part = get_text(
                client,
                DATA_URL,
                user_agent,
                params=window_params(monday, zone),
                accept="text/html",
            )
            if len(parse_body(part.text)) >= ROW_CAP:
                raise StateFormatError(
                    f"ODFW's {zone} zone for the week of {monday} still fills the "
                    f"{ROW_CAP}-row cap, so it may be cut off"
                )
            bodies.append(part)
    return bodies


SOURCE = StateSource(
    code="OR",
    name="Oregon",
    time_zone=TIME_ZONE,
    agency_name="Oregon Department of Fish and Wildlife",
    agency_short_name="ODFW",
    agency_url="https://myodfw.com/",
    source_name="ODFW weekly trout stocking schedule",
    source_url=PAGE_URL,
    data_urls=(DATA_URL,),
    semantics="schedule",
    date_precisions=("week",),
    attribution_text=(
        "Data: Oregon Department of Fish and Wildlife (ODFW), weekly trout "
        f"stocking schedule ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not endorsed by ODFW or the State of "
        "Oregon. These are ODFW's scheduled weeks, not confirmed stockings. ODFW: "
        '"The schedule is subject to change without notice." ODFW also says some '
        "waterbodies may not be stocked as scheduled, and that stocking may "
        "happen a week before or after the scheduled date. A week-of date is the "
        "Monday that starts the week; ODFW lists the week, not the day. A water "
        "appears once for each week ODFW plans to stock it, as far ahead as this "
        f"site reads ({HORIZON_WEEKS} weeks). That is ODFW's plan, not a rate."
    ),
    license_summary=(
        "ODFW's page carries a copyright line and no reuse terms, and the "
        "State of Oregon's website terms neither grant nor deny reuse. Whether "
        "reuse is allowed is unknown."
    ),
    license_sources=(LICENSE,),
    regions=tuple((z, f"{z} Zone") for z in ZONES),
    recency_note=None,
    min_rows=1,
    publish_since=None,
    fetch=fetch,
    parse=parse,
    week_starts_on=0,
    week_days=5,
    week_phrase="the week starting on a Monday",
)
