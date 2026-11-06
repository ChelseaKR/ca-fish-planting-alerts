"""Virginia: DWR's monthly trout stocking schedule (a forward schedule).

**Off by default.** ``cfpa.states`` registers Virginia only when
``CFPA_ENABLE_VIRGINIA=1`` is set. Nothing in the daily run, the publish
workflow, the sitemap or the site changes while it is off. It stays off
until DWR says yes in writing (DECISIONS 0055): DWR's pages carry only a
copyright line, its web policy (2003) is a privacy statement, and under
DECISIONS 0004 the licence is ``unknown``.

The source is https://dwr.virginia.gov/fishing/trout/monthly-trout-stocking-schedule/,
read on 2026-11-05: one HTML table per month (a caption "Trout stocking
schedule for November 2026"), newest month first, with three columns:

    Date of stocking | Stocked water | County

What this reader does with it (the owner chose "monthly plan only" on
2026-11-05, expansion plan decision 6A):

- **Only the monthly plan is read.** DWR's daily page is a report of what
  was stocked; a state has one meaning here, and the plan is the one that
  looks ahead. DWR says to check the daily page before heading out, and the
  disclaimer says so too.
- A date is a day (MM/DD/YYYY). Some rows carry a note ("postponed",
  "Rescheduled to 11/9"). A row whose date cell is empty (a postponement
  with no new date) has no usable date and is skipped; a day it used to show
  then drops out and is marked removed, which is what DWR's page now says.
- There is no species and no count. Each row is one record, "Trout".
- Places are a county ("Floyd County") or an independent city ("City of
  Lynchburg"). A county is stored without the word "County"; a city is kept
  in DWR's words as the place. Anything else is a changed page and refused.
- A water is a name plus its place: DWR tells two Wolf Creeks apart only by
  a bracket ("Wolf Creek [Bland]"), which is kept in the name.

Copy rules (``COPY_RULES``): "scheduled", never "stocked on" or "planted";
a day, as DWR gives it; no species and no count, because DWR gives none.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import re
from collections.abc import Callable
from html.parser import HTMLParser

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
    get_text,
    slugify,
)

PAGE_URL = "https://dwr.virginia.gov/fishing/trout/monthly-trout-stocking-schedule/"
DAILY_URL = "https://dwr.virginia.gov/fishing/trout-stocking-schedule/"
DATA_URL = PAGE_URL
TERMS_URL = "https://dwr.virginia.gov/about/web-policy/"
ENV_FLAG = "CFPA_ENABLE_VIRGINIA"
TIME_ZONE = "America/New_York"
TABLE_CLASS = "trout-stockings__table"
NOTE_CLASS = "trout-stockings__notes"
HEADERS = ("Date of stocking", "Stocked water", "County")
SPECIES = "Trout"

_CAPTION = re.compile(r"^Trout stocking schedule for ([A-Z][a-z]+) (\d{4})$")
_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")

COPY_RULES = (
    "Say 'scheduled', never 'stocked on' a date and never 'planted'.",
    "DWR gives a day; show the day, and say DWR may move it.",
    "No species and no count: DWR's monthly plan gives neither.",
)

FORBIDDEN = re.compile(
    r"\b(only|first|best|top|unique|planted|stocked on)\b", re.IGNORECASE
)

LICENSE = LicenseSource(
    name="Virginia DWR Web Policy; DWR page footer",
    url=PAGE_URL,
    terms_url=TERMS_URL,
    terms_read_on="2026-11-05",
    commercial_reuse="unknown",
    attribution_required=False,
    terms_quote=(
        'The page footer says "© 2026 Virginia Department of Wildlife '
        'Resources". The Web Policy, "Last updated on May 6, 2003", is a '
        "privacy statement and disclaimer. Neither grants or denies reuse."
    ),
)


@dataclasses.dataclass
class _Cell:
    text: str = ""
    note: str = ""


class _Tables(HTMLParser):
    """Each month's table: its caption, header cells and rows."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[tuple[list[str], list[str], list[list[_Cell]]]] = []
        self._in_table = False
        self._in_caption = False
        self._caption: list[str] = []
        self._cell: _Cell | None = None
        self._in_note = False
        self._is_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "table" and TABLE_CLASS in classes:
            self._in_table = True
            self.tables.append(([], [], []))
        elif not self._in_table:
            return
        elif tag == "caption":
            self._in_caption = True
            self._caption = []
        elif tag == "tr":
            self.tables[-1][2].append([])
        elif tag in ("td", "th"):
            self._cell = _Cell()
            self._is_header = tag == "th"
        elif tag == "p" and NOTE_CLASS in classes:
            self._in_note = True

    def handle_endtag(self, tag: str) -> None:
        if not self._in_table:
            return
        if tag == "table":
            self._in_table = False
        elif tag == "caption":
            self._in_caption = False
            self.tables[-1][0].append(_clean("".join(self._caption)))
        elif tag in ("td", "th") and self._cell is not None:
            if self._is_header:
                self.tables[-1][1].append(_clean(self._cell.text))
            else:
                self.tables[-1][2][-1].append(self._cell)
            self._cell = None
        elif tag == "p":
            self._in_note = False

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self._caption.append(data)
        elif self._cell is not None:
            if self._in_note:
                self._cell.note += data
            else:
                self._cell.text += data


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


@dataclasses.dataclass(frozen=True)
class Row:
    day: dt.date | None
    name: str
    place: str
    note: str


def place(raw: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(counties, towns): 'Floyd County' -> (('Floyd',), ()); 'City of
    Lynchburg' -> ((), ('City of Lynchburg',)). Anything else is refused."""
    if raw.endswith(" County") and len(raw) > len(" County"):
        return (raw[: -len(" County")],), ()
    if raw.startswith("City of ") and len(raw) > len("City of "):
        return (), (raw,)
    raise StateFormatError(f"DWR place {raw!r} is neither a county nor a city")


def _month_number(name: str) -> int:
    try:
        return dt.datetime.strptime(name, "%B").month
    except ValueError as exc:
        raise StateFormatError(f"DWR caption month {name!r} is not a month") from exc


def _row(cells: list[_Cell]) -> Row:
    if len(cells) != len(HEADERS):
        raise StateFormatError(f"DWR row has {len(cells)} cells")
    date_text = _clean(cells[0].text)
    day: dt.date | None = None
    if date_text:
        dm = _DATE.match(date_text)
        if not dm:
            raise StateFormatError(f"DWR date {date_text!r} is not MM/DD/YYYY")
        try:
            day = dt.date(int(dm.group(3)), int(dm.group(1)), int(dm.group(2)))
        except ValueError as exc:
            raise StateFormatError(f"DWR date {date_text!r}: {exc}") from exc
    name = _clean(cells[1].text)
    where = _clean(cells[2].text)
    if not name or not where:
        raise StateFormatError(f"DWR row without a water or place: {name!r}")
    note = re.sub(r"^Note:\s*", "", _clean(cells[1].note))
    return Row(day, name, where, note)


def parse_body(text: str) -> list[Row]:
    p = _Tables()
    p.feed(text)
    if not p.tables:
        raise StateFormatError("DWR's page has no monthly schedule table")
    out: list[Row] = []
    for captions, headers, rows in p.tables:
        if len(captions) != 1 or not (m := _CAPTION.match(captions[0])):
            raise StateFormatError(f"DWR's table caption changed: {captions!r}")
        _month_number(m.group(1))
        if tuple(headers) != HEADERS:
            raise StateFormatError(f"DWR's table headers changed: {headers!r}")
        # An empty list is the header row, whose cells went to ``headers``.
        out.extend(_row(cells) for cells in rows if cells)
    return out


def water_id(name: str, where: str) -> str:
    return "va-" + slugify(name, where)


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    if len(bodies) != 1:
        raise StateFormatError(f"expected one DWR page, got {len(bodies)}")
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    notes: list[str] = []
    for row in parse_body(bodies[0].text):
        counties, towns = place(row.place)
        wid = water_id(row.name, row.place)
        waters[wid] = WaterMeta(
            id=wid,
            slug=slugify(
                row.name, *(counties or towns), *(("county",) if counties else ())
            ),
            name=row.name,
            counties=counties,
            towns=towns,
            source_url=PAGE_URL,
        )
        if row.day is None:
            skipped += 1
            notes.append(
                f"{row.name} ({row.place}) has no date"
                + (f' (DWR: "{row.note}")' if row.note else "")
            )
            continue
        rec = ParsedRecord(wid, Period.day(row.day), SPECIES)
        records[rec.key()] = rec
    first = bodies[0]
    return ParsedFeed(
        waters=waters,
        records=sorted(records.values(), key=lambda r: r.key()),
        fetched_at=first.fetched_at,
        content_sha256=combined_sha256(bodies),
        last_modified=first.last_modified,
        skipped=skipped,
        etag=first.etag,
        skipped_notes=tuple(f"skipped {n}" for n in notes),
    )


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
) -> list[FetchedBody]:
    # One page (about 116 KB on 2026-11-05) holding every month DWR lists.
    check_robots_strict(client, DATA_URL, user_agent)
    return [get_text(client, DATA_URL, user_agent, accept="text/html")]


SOURCE = StateSource(
    code="VA",
    name="Virginia",
    time_zone=TIME_ZONE,
    agency_name="Virginia Department of Wildlife Resources",
    agency_short_name="DWR",
    agency_url="https://dwr.virginia.gov/",
    source_name="DWR monthly trout stocking schedule",
    source_url=PAGE_URL,
    data_urls=(DATA_URL,),
    semantics="schedule",
    date_precisions=("day",),
    attribution_text=(
        "Data: Virginia Department of Wildlife Resources (DWR), monthly trout "
        f"stocking schedule ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not endorsed by DWR or the "
        "Commonwealth of Virginia. These are DWR's scheduled dates, not "
        'confirmed stockings. DWR: stocking dates and locations "may be '
        "adjusted due to weather, drought conditions, or other unforeseen "
        'circumstances." DWR asks anglers to check its daily trout stocking '
        f"schedule ({DAILY_URL}) before heading out. DWR's monthly schedule "
        "names no species and no number of fish."
    ),
    license_summary=(
        "DWR's pages carry a copyright line and no reuse terms, and DWR's web "
        "policy is a privacy statement. Whether reuse is allowed is unknown."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=None,
    min_rows=1,
    publish_since=None,
    fetch=fetch,
    parse=parse,
)
