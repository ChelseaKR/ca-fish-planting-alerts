"""Tennessee: TWRA's trout stocking schedule (a forward schedule).

The page https://www.tn.gov/twra/fishing/trout-information-stockings.html
loads its schedule table from one JSON file, which this reads. Each row is a
water (county + location, no agency id), a species, and a date in one of
three columns, which is also its precision:

- ``STOCKING DAY``: an exact day, ``10/14/2026``. Or ``TBD 12/2026``: the
  month is set and the day is not, so the record is a month.
- ``STOCKING WEEK``: a Sunday. TWRA: '"Week of" dates listed are all
  Sundays; the stocking event will occur within five days after the date
  listed.' A week, never shown as a day. The 2027 file also puts
  ``TBD 12/2027`` here; that is a month, read exactly as the DAY column's
  TBD, and never shown as a week.
- ``STOCKING MONTHS``: one letter per month (``M, A, M, J, J, A, S``). TWRA:
  "Tailwater and Reservoir stocking dates are variable throughout the months
  indicated." The letters are ambiguous on their own ("M" is March or May),
  so they are kept verbatim as the water's ``months_note`` and never turned
  into dates.

Read 2026-10-12: 616 rows, 136 waters, every week date a Sunday, dates from
2026-01-01 to 2026-12-24. Read 2026-11-05 (from Chelsea's Mac, not a
runner): TWRA's 2027 schedule, 713 rows, 582 of them in 2027, out to
2027-12-30. Four of its "week of" dates are not Sundays (3/21/2026, a
Saturday; 7/12, 7/19 and 7/26/2027, Mondays). A row like that is skipped,
never moved to a guessed Sunday, and named in the run log; the file is
refused only when more than ``MAX_BAD_ROWS`` rows (or more than
``MAX_BAD_SHARE`` of all rows) are like that, so a reshaped feed still fails.
License: the TN.gov Linking Policy (quoted in
``LICENSE``) lets the information be copied when it identifies the agency
and its web address and implies no endorsement.
"""

from __future__ import annotations

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

PAGE_URL = "https://www.tn.gov/twra/fishing/trout-information-stockings.html"
DATA_URL = (
    "https://www.tn.gov/twra/fishing/trout-information-stockings/_jcr_content/"
    "contentFullWidth/tn_complex_datatable_1990410459.exceldriven.json"
)

COLUMNS = (
    "REGION",
    "COUNTY",
    "LOCATION",
    "TYPE",
    "STOCKING DAY",
    "STOCKING WEEK",
    "STOCKING MONTHS",
    "SPECIES",
)
REGION_CODES = ("1", "2", "3", "4")
# A few non-Sunday "week of" rows are TWRA typos and are skipped; more than
# this many (or more than this share of rows) means the feed changed shape.
MAX_BAD_ROWS = 10
MAX_BAD_SHARE = 0.02

_DAY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_TBD_MONTH_RE = re.compile(r"^TBD\s+(\d{1,2})/(\d{4})$")

LICENSE = LicenseSource(
    name="TN.gov Linking Policy (covers information posted on TN.gov)",
    url=PAGE_URL,
    terms_url="https://www.tn.gov/web-policies/linking-policy.html",
    terms_read_on="2026-10-12",
    commercial_reuse="permitted",
    attribution_required=True,
    terms_quote=(
        "The information posted on a TN.gov Web site may be copied so long as "
        "it is presented in a non-misleading way and does not imply that either "
        "the site owner or the information, as it is presented on the site "
        "owner's Web site, is endorsed by the State. Use of the information "
        "must identify the state agency that is the source of the information, "
        "and the agency's Web address."
    ),
)


def _date(text: str) -> dt.date | None:
    m = _DAY_RE.match(text)
    if not m:
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        return dt.date(year, month, day)
    except ValueError as exc:
        raise StateFormatError(f"TWRA date {text!r} is not a real date") from exc


def _day_column(text: str) -> Period | None:
    if not text:
        return None
    d = _date(text)
    if d is not None:
        return Period.day(d)
    m = _TBD_MONTH_RE.match(text)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if not 1 <= month <= 12:
            raise StateFormatError(f"TWRA month {text!r} is not a month")
        return Period.month(year, month)
    raise StateFormatError(
        f"TWRA's STOCKING DAY column holds {text!r}, which is neither a date nor "
        "'TBD <month>/<year>'"
    )


class _NotASunday(ValueError):
    """A "week of" date that is not a Sunday: TWRA says they all are, so the
    row's week cannot be known and the row is skipped (never guessed)."""


def _week_column(text: str) -> Period | None:
    if not text:
        return None
    m = _TBD_MONTH_RE.match(text)
    if m:
        # The 2027 file's "TBD 12/2027": a month, exactly like the DAY
        # column's TBD. Never turned into a week.
        month, year = int(m.group(1)), int(m.group(2))
        if not 1 <= month <= 12:
            raise StateFormatError(f"TWRA month {text!r} is not a month")
        return Period.month(year, month)
    d = _date(text)
    if d is None:
        raise StateFormatError(f"TWRA's STOCKING WEEK column holds {text!r}")
    if d.weekday() != 6:
        raise _NotASunday(f"week of {text} is a {d.strftime('%A')}, not a Sunday")
    return Period.week(d)


def water_id(county: str, location: str) -> str:
    return "tn-" + slugify(county, location)


def _rows(bodies: list[FetchedBody]) -> list[dict[str, str]]:
    if len(bodies) != 1:
        raise StateFormatError(f"expected one TWRA file, got {len(bodies)}")
    try:
        doc = json.loads(bodies[0].text)
    except json.JSONDecodeError as exc:
        raise StateFormatError(f"TWRA's schedule is not JSON: {exc}") from exc
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise StateFormatError("TWRA's schedule has no 'data' list")
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise StateFormatError(f"TWRA row {i} is not an object")
        missing = [c for c in COLUMNS if c not in row]
        if missing:
            raise StateFormatError(f"TWRA row {i} is missing columns {missing}")
        out.append({c: str(row[c] or "").strip() for c in COLUMNS})
    return out


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    bad: list[str] = []
    rows = _rows(bodies)
    for row in rows:
        county, location, species = row["COUNTY"], row["LOCATION"], row["SPECIES"]
        if not county or not location or not species:
            skipped += 1
            continue
        region = row["REGION"]
        if region not in REGION_CODES:
            raise StateFormatError(f"TWRA region {region!r} is not one of 1-4")
        try:
            week = _week_column(row["STOCKING WEEK"])
        except _NotASunday as exc:
            # Skip the whole row: its week is unknowable, and a guessed
            # Sunday would be a date TWRA never gave.
            bad.append(f"{location} ({county} County), {species}: {exc}")
            skipped += 1
            continue
        periods = [p for p in (_day_column(row["STOCKING DAY"]), week) if p is not None]
        months = row["STOCKING MONTHS"]
        if not periods and not months:
            skipped += 1
            continue
        wid = water_id(county, location)
        prior = waters.get(wid)
        waters[wid] = WaterMeta(
            id=wid,
            slug=slugify(location, county, "county"),
            name=location,
            counties=(county,),
            region=region,
            source_id=None,
            source_url=PAGE_URL,
            months_note=months or (prior.months_note if prior else None),
        )
        for period in periods:
            rec = ParsedRecord(water_id=wid, period=period, species=species)
            records[rec.key()] = rec
    cap = min(MAX_BAD_ROWS, int(len(rows) * MAX_BAD_SHARE))
    if len(bad) > cap:
        raise StateFormatError(
            f"{len(bad)} of TWRA's {len(rows)} rows have a 'week of' date that is "
            f"not a Sunday (more than {cap}); TWRA says they are all Sundays, so "
            f"the feed may have changed. First: {bad[0]}"
        )
    first = bodies[0]
    return ParsedFeed(
        waters=waters,
        records=sorted(records.values(), key=lambda r: r.key()),
        fetched_at=first.fetched_at,
        content_sha256=combined_sha256(bodies),
        last_modified=first.last_modified,
        skipped=skipped,
        skipped_notes=tuple(f"skipped {b}" for b in bad),
    )


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
) -> list[FetchedBody]:
    # One whole-year file, about 100 KB: read whole each run.
    check_robots_strict(client, DATA_URL, user_agent)
    return [get_text(client, DATA_URL, user_agent)]


SOURCE = StateSource(
    code="TN",
    name="Tennessee",
    time_zone="America/Chicago",
    agency_name="Tennessee Wildlife Resources Agency",
    agency_short_name="TWRA",
    agency_url="https://www.tn.gov/twra.html",
    source_name="TWRA trout stocking schedule",
    source_url=PAGE_URL,
    data_urls=(DATA_URL,),
    semantics="schedule",
    date_precisions=("day", "week", "month"),
    attribution_text=(
        "Data: Tennessee Wildlife Resources Agency (TWRA), trout stocking "
        f"schedule ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not endorsed by TWRA or the State of "
        "Tennessee. These are TWRA's scheduled dates, not confirmed stockings. "
        'TWRA: "Any stocking event could be postponed or cancelled due to '
        'unforeseen problems such as adverse weather or warm water temperatures." '
        "A week-of date is a Sunday, and TWRA says the stocking falls within five "
        "days after it."
    ),
    license_summary=(
        "TWRA's schedule is information posted on TN.gov. The TN.gov Linking "
        "Policy lets it be copied when it is presented in a non-misleading way, "
        "implies no endorsement by the State, and identifies the agency and its "
        "web address, which every page and screen that shows it does."
    ),
    license_sources=(LICENSE,),
    regions=tuple((code, f"TWRA Region {code}") for code in REGION_CODES),
    recency_note=None,
    min_rows=100,
    publish_since=None,
    fetch=fetch,
    parse=parse,
)
