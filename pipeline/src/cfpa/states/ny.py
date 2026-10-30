"""New York: NYS DEC's spring trout stocking plan (a once-a-year plan).

Read from OPEN-NY's SODA API, the authorized way to read the portal (its
terms bar scraping the site by bot): https://data.ny.gov/resource/d9y2-n436.json,
"Current Season Spring Trout Stocking". ``data.ny.gov/robots.txt`` is
readable (200, ``Crawl-delay: 1``) and does not disallow ``/resource/``.

Measured 2026-10-12: 1,310 rows for 2026 (updated 2026-03-19), 582 waters,
columns ``year, dec_region, county, town, waterbody, date, number,
species_name, size_inches``. ``date`` is free text in 25 forms: "April -
first week", "Spring", "March - fourth week", "April", "Mid April", "Early
May", "March - April" and so on.

Those words are DEC's, and they are never turned into a date (DECISIONS
0034). Each is an "approximate" period: its label is DEC's text and the
year, verbatim ("April - third week, 2026"), and its start and end only bound
it, for ordering and for the app's reminders. A form this code does not know
refuses the feed rather than being guessed at.

Semantics: a ``plan``. It looks forward like a schedule, but it is one
publication a year, so nothing is ever inferred as removed from it, and the
words are "planned for", not "scheduled" or "stocked". The plans pile up in
Trout Truck's history year by year, which DEC's current-season file does not
keep.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re
from collections.abc import Callable

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

PAGE_URL = (
    "https://data.ny.gov/Recreation/Current-Season-Spring-Trout-Stocking/d9y2-n436"
)
DATA_URL = "https://data.ny.gov/resource/d9y2-n436.json"
TERMS_URL = "https://data.ny.gov/download/77gx-ii52/application%2Fpdf"

COLUMNS = ("year", "dec_region", "county", "town", "waterbody", "date", "species_name")
REGION_CODES = tuple(str(n) for n in range(1, 10))

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_PARTS = {"early": (1, 10), "mid": (11, 20), "late": (21, 31)}
_MONTH = "(" + "|".join(name for name in calendar.month_name if name) + ")"
_WEEK_RE = re.compile(rf"^{_MONTH} - (first|second|third|fourth|fifth) week$", re.I)
_MONTH_RE = re.compile(rf"^{_MONTH}$", re.I)
_PART_RE = re.compile(rf"^(Early|Mid|Late) {_MONTH}$", re.I)
_RANGE_RE = re.compile(rf"^{_MONTH} - {_MONTH}$", re.I)

LICENSE = LicenseSource(
    name="OPEN-NY Terms of Use",
    url=PAGE_URL,
    terms_url=TERMS_URL,
    terms_read_on="2026-10-12",
    commercial_reuse="permitted",
    attribution_required=False,
    terms_quote=(
        "So long as you are not doing anything malicious with NYS data, you may "
        "use it as you wish, subject to no other requirements."
    ),
)


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def bounds(text: str, year: int) -> tuple[dt.date, dt.date]:
    """The span DEC's words cover, for ordering and reminders only. Raises
    StateFormatError for a form not seen in DEC's file."""
    t = " ".join(text.split())
    if m := _WEEK_RE.match(t):
        month = _MONTHS[m.group(1).lower()]
        n = _ORDINALS[m.group(2).lower()]
        first = 1 + 7 * (n - 1)
        last_day = _last_day(year, month)
        if first > last_day:
            raise StateFormatError(f"{t!r} names a week {year} does not have")
        end = last_day if n >= 4 else first + 6
        return dt.date(year, month, first), dt.date(year, month, min(end, last_day))
    if m := _MONTH_RE.match(t):
        month = _MONTHS[m.group(1).lower()]
        return dt.date(year, month, 1), dt.date(year, month, _last_day(year, month))
    if m := _PART_RE.match(t):
        lo, hi = _PARTS[m.group(1).lower()]
        month = _MONTHS[m.group(2).lower()]
        return dt.date(year, month, lo), dt.date(
            year, month, min(hi, _last_day(year, month))
        )
    if m := _RANGE_RE.match(t):
        a, b = _MONTHS[m.group(1).lower()], _MONTHS[m.group(2).lower()]
        if b < a:
            raise StateFormatError(f"{t!r} runs backward")
        return dt.date(year, a, 1), dt.date(year, b, _last_day(year, b))
    if t.lower() == "spring":
        # DEC's spring stocking runs March to June in its own file.
        return dt.date(year, 3, 1), dt.date(year, 6, 30)
    raise StateFormatError(f"DEC's date {t!r} is a form this code does not know")


def period(text: str, year: int) -> Period:
    start, end = bounds(text, year)
    return Period.approximate(start, end, f"{' '.join(text.split())}, {year}")


def _count(text: object) -> int | None:
    if text in (None, ""):
        return None
    try:
        n = int(str(text).strip())
    except ValueError as exc:
        raise StateFormatError(f"DEC's number is not a count: {text!r}") from exc
    if n < 0:
        raise StateFormatError(f"DEC's number is negative: {text!r}")
    return n


def _row(i: int, row: object) -> tuple[WaterMeta, ParsedRecord] | None:
    """One DEC row as a water and a planned record, or None when it has no
    water, species or date. Raises StateFormatError on a changed shape."""
    if not isinstance(row, dict):
        raise StateFormatError(f"DEC row {i} is not an object")
    missing = [c for c in COLUMNS if c not in row]
    if missing:
        raise StateFormatError(f"DEC row {i} is missing {missing}")
    county, town, water, species, when = (
        str(row[k]).strip()
        for k in ("county", "town", "waterbody", "species_name", "date")
    )
    if not (county and water and species and when):
        return None
    try:
        year = int(str(row["year"]).strip())
    except ValueError as exc:
        raise StateFormatError(f"DEC row {i} has year {row['year']!r}") from exc
    region = str(row["dec_region"]).strip()
    if region not in REGION_CODES:
        raise StateFormatError(f"DEC region {region!r} is not 1-9")
    wid = "ny-" + slugify(county, town, water)
    meta = WaterMeta(
        id=wid,
        slug=slugify(water, town, county, "county"),
        name=water,
        counties=(county,),
        towns=(town,) if town else (),
        region=region,
        source_id=None,
        source_url=PAGE_URL,
    )
    rec = ParsedRecord(
        water_id=wid,
        period=period(when, year),
        species=species,
        count=_count(row.get("number")),
    )
    return meta, rec


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    if len(bodies) != 1:
        raise StateFormatError(f"expected one DEC response, got {len(bodies)}")
    try:
        rows = json.loads(bodies[0].text)
    except json.JSONDecodeError as exc:
        raise StateFormatError(f"DEC's plan is not JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise StateFormatError("DEC's plan is not a list of rows")
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for i, row in enumerate(rows):
        parsed = _row(i, row)
        if parsed is None:
            skipped += 1
            continue
        meta, rec = parsed
        waters[meta.id] = meta
        prior = records.get(rec.key())
        if prior is not None and prior.count is not None and rec.count is not None:
            # Several sizes of one species in one period: one planned stocking.
            rec = ParsedRecord(
                rec.water_id, rec.period, rec.species, prior.count + rec.count
            )
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


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
) -> list[FetchedBody]:
    """robots.txt, then one SODA request for the whole current season."""
    check_robots_strict(client, DATA_URL, user_agent)
    return [get_text(client, DATA_URL, user_agent, params={"$limit": "50000"})]


SOURCE = StateSource(
    code="NY",
    name="New York",
    time_zone="America/New_York",
    agency_name="New York State Department of Environmental Conservation",
    agency_short_name="NYS DEC",
    agency_url="https://dec.ny.gov/",
    source_name="NYS DEC spring trout stocking plan (OPEN-NY)",
    source_url=PAGE_URL,
    data_urls=(DATA_URL,),
    semantics="plan",
    date_precisions=("approximate",),
    attribution_text=(
        "Data: New York State Department of Environmental Conservation, Current "
        f"Season Spring Trout Stocking, via OPEN-NY ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not affiliated with or endorsed by NYS "
        "DEC or the State of New York. These are DEC's planned stockings for the "
        'spring, in DEC\'s own words for when, such as "April - third week". '
        "They are plans, not dates, and not confirmed stockings."
    ),
    license_summary=(
        "OPEN-NY's terms let the data be used as anyone wishes, with no other "
        "requirement. It is read through the portal's API, the authorized route."
    ),
    license_sources=(LICENSE,),
    regions=tuple((code, f"DEC Region {code}") for code in REGION_CODES),
    recency_note=None,
    # DEC publishes about 1,300 rows each spring: fewer than this looks like a
    # truncated or reshaped response.
    min_rows=300,
    publish_since=None,
    fetch=fetch,
    parse=parse,
)
