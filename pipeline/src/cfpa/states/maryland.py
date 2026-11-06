"""Maryland: DNR's recently stocked trout locations (a report, by the day).

**Off by default.** ``cfpa.states`` registers Maryland only when
``CFPA_ENABLE_MARYLAND=1`` is set. Nothing in the daily run, the publish
workflow, the sitemap or the site changes while it is off. It stays off
until DNR says yes in writing (DECISIONS 0055): DNR's pages carry no reuse
terms either way, and under DECISIONS 0004 the licence is ``unknown``.

The source is the JSON feed behind the "Recently Stocked Locations" table on
https://dnr.maryland.gov/fisheries/Pages/trout/stocking.aspx :
https://webapps02.dnr.state.md.us/DNRTroutStockingAPI/api/RecentStockings,
one list of objects, read on 2026-11-05 (357 rows, 130 locations, dated
2026-02-09 to 2026-10-29). Each row:

    FKintLocationID  LOCATION  County  NumOfFish  Species
    RegulationDetails  ActivityDate  ClosureCode

What this reader does with it:

- ``FKintLocationID`` is DNR's own id, stable for a name, so it is the
  water's identity (``source_id``).
- It is a **report**: ``ActivityDate`` is a day DNR stocked. Rows age off
  the feed, so a missing row means nothing (no removal is inferred, and the
  feed is not a whole file).
- ``NumOfFish`` is one number for the row, and ``Species`` can name more
  than one kind ("Rainbow/Golden"). The count is never split between them:
  the record keeps DNR's combined words.
- ``County`` can name two counties ("Montgomery - Howard"), can be the bare
  word "County" (no county given), or a misspelling ("Cecill"). A county
  that is not one of Maryland's is left out, never guessed, and said in the
  run log.
- ``ClosureCode`` and ``RegulationDetails`` are not read: DNR's page does
  not say what the codes mean, and a regulation is not a stocking.
- Two rows for one location, day and species are added together.

Copy rules (``COPY_RULES``, pinned by ``tests/test_states_pa_va_md.py``):
"stocked on" a day DNR reported, never "scheduled"; a count belongs to DNR's
whole species phrase; no county when DNR gives none; never a season total.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable
from typing import Any

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

PAGE_URL = "https://dnr.maryland.gov/fisheries/Pages/trout/stocking.aspx"
DATA_URL = "https://webapps02.dnr.state.md.us/DNRTroutStockingAPI/api/RecentStockings"
TERMS_URL = "https://dnr.maryland.gov/Pages/privacyPolicy.aspx"
ENV_FLAG = "CFPA_ENABLE_MARYLAND"
TIME_ZONE = "America/New_York"

COLUMNS = (
    "FKintLocationID",
    "LOCATION",
    "County",
    "NumOfFish",
    "Species",
    "ActivityDate",
)

# Maryland's 23 counties and Baltimore City, as DNR spells them.
COUNTIES = frozenset(
    {
        "Allegany",
        "Anne Arundel",
        "Baltimore",
        "Baltimore City",
        "Calvert",
        "Caroline",
        "Carroll",
        "Cecil",
        "Charles",
        "Dorchester",
        "Frederick",
        "Garrett",
        "Harford",
        "Howard",
        "Kent",
        "Montgomery",
        "Prince George's",
        "Queen Anne's",
        "St. Mary's",
        "Somerset",
        "Talbot",
        "Washington",
        "Wicomico",
        "Worcester",
    }
)
# Spellings seen in DNR's feed for a county above. Reviewed one by one; a
# spelling not here and not above is left out, never guessed.
COUNTY_SPELLINGS = {
    "Cecill": "Cecil",
    "Prince Georges": "Prince George's",
}

COPY_RULES = (
    "Say 'stocked on' a day DNR reported; never 'scheduled' or 'planned'.",
    "A count belongs to DNR's whole species phrase; never split it by kind.",
    "No county is shown when DNR gives none; never a guessed county.",
    "DNR's feed keeps only recent rows; never a total or a season count.",
)

FORBIDDEN = re.compile(
    r"\b(only|first|best|top|unique|planted|scheduled|planned)\b", re.IGNORECASE
)

LICENSE = LicenseSource(
    name="Maryland DNR stocking page and Online Privacy Policy",
    url=PAGE_URL,
    terms_url=TERMS_URL,
    terms_read_on="2026-11-05",
    commercial_reuse="unknown",
    attribution_required=False,
    terms_quote=(
        "The stocking page carries no copyright line or reuse terms. DNR's "
        "privacy policy covers personal data only: it will not disclose "
        '"any part of a public record the contains your personal information".'
    ),
)


def water_id(location_id: int) -> str:
    return f"md-{location_id}"


def _rows(bodies: list[FetchedBody]) -> list[dict[str, Any]]:
    if len(bodies) != 1:
        raise StateFormatError(f"expected one DNR feed, got {len(bodies)}")
    try:
        doc = json.loads(bodies[0].text)
    except json.JSONDecodeError as exc:
        raise StateFormatError(f"DNR's feed is not JSON: {exc}") from exc
    if not isinstance(doc, list):
        raise StateFormatError("DNR's feed is not a list")
    for i, row in enumerate(doc):
        if not isinstance(row, dict):
            raise StateFormatError(f"DNR row {i} is not an object")
        missing = [c for c in COLUMNS if c not in row]
        if missing:
            raise StateFormatError(f"DNR row {i} is missing {missing}")
    return doc


def counties(raw: str) -> tuple[tuple[str, ...], list[str]]:
    """('Montgomery', 'Howard') from 'Montgomery - Howard'; a part that is not
    a Maryland county is dropped and returned in the second list."""
    found: list[str] = []
    unknown: list[str] = []
    for part in (p.strip() for p in raw.split(" - ")):
        name = COUNTY_SPELLINGS.get(part, part)
        if name in COUNTIES:
            if name not in found:
                found.append(name)
        elif part:
            unknown.append(part)
    return tuple(found), unknown


def species_label(raw: str) -> str:
    """'Rainbow/Golden' -> 'Rainbow/Golden trout': DNR's words, one phrase."""
    parts = [p.strip() for p in raw.split("/")]
    if not parts or not all(p.isalpha() for p in parts):
        raise StateFormatError(f"DNR species {raw!r} is not a list of names")
    return "/".join(parts) + " trout"


def _day(raw: str) -> dt.date:
    try:
        return dt.datetime.fromisoformat(raw).date()
    except ValueError as exc:
        raise StateFormatError(f"DNR date {raw!r} is not a date") from exc


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    rows = _rows(bodies)
    # First pass: each location's name and the counties any of its rows give,
    # so a water's counties and slug never depend on row order.
    names: dict[int, str] = {}
    places: dict[int, list[str]] = {}
    notes: list[str] = []
    for row in rows:
        loc_id = row["FKintLocationID"]
        name = str(row["LOCATION"] or "").strip()
        if not isinstance(loc_id, int) or not name:
            continue
        if names.setdefault(loc_id, name) != name:
            raise StateFormatError(
                f"DNR location {loc_id} has two names: {names[loc_id]!r}, {name!r}"
            )
        found, unknown = counties(str(row["County"] or ""))
        have = places.setdefault(loc_id, [])
        have.extend(c for c in found if c not in have)
        if unknown:
            note = f"{name}: county {', '.join(unknown)!r} is not a Maryland county"
            if note not in notes:
                notes.append(note)
    waters: dict[str, WaterMeta] = {}
    for loc_id, name in names.items():
        found_all = tuple(sorted(places[loc_id]))
        wid = water_id(loc_id)
        waters[wid] = WaterMeta(
            id=wid,
            slug=slugify(name, *found_all, "county") if found_all else slugify(name),
            name=name,
            counties=found_all,
            source_id=str(loc_id),
            source_url=PAGE_URL,
        )
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for row in rows:
        loc_id = row["FKintLocationID"]
        if loc_id not in names or not row["ActivityDate"]:
            skipped += 1
            continue
        wid = water_id(loc_id)
        period = Period.day(_day(str(row["ActivityDate"])))
        species = species_label(str(row["Species"]))
        count_text = str(row["NumOfFish"] or "").replace(",", "").strip()
        count = int(count_text) if count_text.isdigit() else None
        rec = ParsedRecord(wid, period, species, count)
        earlier = records.get(rec.key())
        if earlier is not None:
            # Two rows for one location, day and species: add them up. A row
            # with no number makes the day's total unknown, never a partial.
            total = (
                None
                if count is None or earlier.count is None
                else count + earlier.count
            )
            rec = ParsedRecord(wid, period, species, total)
        records[rec.key()] = rec
    first = bodies[0]
    return ParsedFeed(
        waters=waters,
        records=sorted(records.values(), key=lambda r: r.key()),
        fetched_at=first.fetched_at,
        content_sha256=combined_sha256(bodies),
        last_modified=first.last_modified,
        skipped=skipped,
        skipped_notes=tuple(f"left out {n}" for n in notes),
    )


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
) -> list[FetchedBody]:
    # One small file (about 76 KB on 2026-11-05): read whole each run.
    check_robots_strict(client, DATA_URL, user_agent)
    return [get_text(client, DATA_URL, user_agent)]


SOURCE = StateSource(
    code="MD",
    name="Maryland",
    time_zone=TIME_ZONE,
    agency_name="Maryland Department of Natural Resources",
    agency_short_name="DNR",
    agency_url="https://dnr.maryland.gov/fisheries/",
    source_name="Maryland DNR recently stocked trout locations",
    source_url=PAGE_URL,
    data_urls=(DATA_URL,),
    semantics="report",
    date_precisions=("day",),
    attribution_text=(
        "Data: Maryland Department of Natural Resources (DNR), recently "
        f"stocked trout locations ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not endorsed by DNR or the State of "
        "Maryland. These are stockings DNR has reported as done, by the day. "
        "DNR's feed keeps recent stockings, and older ones drop off it. A "
        "count is for every kind of trout DNR names in that row together."
    ),
    license_summary=(
        "DNR's stocking page carries no reuse terms, and DNR's privacy policy "
        "covers personal data, not reuse. Whether reuse is allowed is unknown."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=None,
    # A report never infers a removal, but an empty feed in a year-round
    # program is more likely broken than true, so it is refused.
    min_rows=1,
    publish_since=None,
    fetch=fetch,
    parse=parse,
)
