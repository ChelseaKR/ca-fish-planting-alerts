"""Michigan: the DNR's fish stocking data, a report of stockings done.

Read from the DNR's own CSV, linked from its Fish Stocking Database
dashboard as "Fish stocking data is available for download in CSV format":
https://michigandnr.com/publications/PDFS/Fishing/FishStocking/FishStockingData.csv.
That host's robots.txt answers 404, which counts as "no rules" (DECISIONS
0025). The ArcGIS layer behind the dashboard sits on a host whose robots.txt
redirects to a home page, so it is never read.

Measured 2026-10-12 (Last-Modified Fri, 09 Oct 2026 18:27:05 GMT): 70,453
rows from 1979-01-23, columns ``County_Name, Water_Body_Name, sitename, Town,
Range, Section, Species, Strain, Marking_Group, Stocking_Date (MM/DD/YYYY),
Number_Fish_Stocked, Average_Length_Inches, Operation``. Species values carry
padding spaces. There is no water id, so a water is county + water + site.

What is kept (DECISIONS 0034):

- **Trout only**: brown, rainbow, brook and lake trout (every species whose
  name contains "trout"). The product is Trout Truck.
- **Public stockings only**: the ``PUBLIC_OPERATIONS`` below. Private ponds
  stocked under permit, research, school and out-of-state rows are left out,
  because they are not water an angler can fish.
- **2021 onward** (``PUBLISH_SINCE``), in history and in the snapshot.

The DNR says "There may be a delay between a stocking event and a
corresponding record on this table", so records are "stocked on <day>" with
that lag said beside them (``recency_note``), never "this week".

The file is about 9.6 MB, so each run asks for it conditionally (ETag and
If-Modified-Since); an unchanged file costs a 304 and nothing more.

License: the dataset's own terms (quoted in ``LICENSE``), which the owner
accepted on 2026-10-13, indemnity and release clauses included.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
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

DASHBOARD_URL = (
    "https://midnr.maps.arcgis.com/apps/dashboards/77581b13c6984b919ab8ed927496a31f"
)
ITEM_URL = "https://www.arcgis.com/home/item.html?id=fc7739be5f5247e7bf7f2c6bc9471140"
CSV_URL = (
    "https://michigandnr.com/publications/PDFS/Fishing/FishStocking/"
    "FishStockingData.csv"
)

COLUMNS = (
    "County_Name",
    "Water_Body_Name",
    "sitename",
    "Species",
    "Stocking_Date",
    "Number_Fish_Stocked",
    "Operation",
)

ACCEPT = "text/csv, application/octet-stream;q=0.9, */*;q=0.1"

# Stockings into water the public can fish. Everything else in the file
# ("Private Plant (under permit)", "Private Water Private Operation",
# "Research", "Educational Institution", "Marsh & Rearing Pond Release",
# "Transplant of Wild Fish", "Indiana", "Wisconsin", ...) is left out.
PUBLIC_OPERATIONS = frozenset(
    {
        "State Plant",
        "Federal Plant",
        "Tribal Plant",
        "Tribal/DNR Coop Plant",
        "INDNR/DNR Coop Plant",
        "Public Plant",
        "Mitigation Plant",
    }
)

# Kept in history from the first fetch, and the earliest record the snapshot
# and the site publish: five seasons, not 47 years.
PUBLISH_SINCE = dt.date(2021, 1, 1)

LICENSE = LicenseSource(
    name="Michigan DNR Fish Stocking Database (dataset license)",
    url=CSV_URL,
    terms_url=ITEM_URL,
    terms_read_on="2026-10-12",
    commercial_reuse="permitted",
    attribution_required=False,
    terms_quote=(
        "This dataset is a public record and, as more fully described below, "
        "there are no restrictions on the use, reproduction, or distribution of "
        "this dataset. ... You forever release the State, its departments, "
        "subdivisions, officers, and employees from all claims, rights, actions, "
        "demands, damages, liabilities, expenses and fees, which arise out of or "
        "relate to your access or use of this dataset. You must defend, "
        "indemnify and hold the State, its departments, subdivisions, officers, "
        "and employees harmless, without limitation, from and against all "
        "actions, claims, losses, liabilities, damages, costs, attorney fees, "
        "and expenses (including those required to establish the right to "
        "indemnification) arising out of or relating to your access or use of "
        "this dataset."
    ),
)


def _count(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        n = int(text)
    except ValueError as exc:
        raise StateFormatError(
            f"Number_Fish_Stocked is not a whole number: {text!r}"
        ) from exc
    if n < 0:
        raise StateFormatError(f"Number_Fish_Stocked is negative: {text!r}")
    return n


def _day(text: str) -> dt.date:
    try:
        return dt.datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except ValueError as exc:
        raise StateFormatError(f"Stocking_Date is not MM/DD/YYYY: {text!r}") from exc


def water_id(county: str, water: str, site: str) -> str:
    return "mi-" + slugify(county, water, site)


def _rows(bodies: list[FetchedBody]) -> list[dict[str, str]]:
    if len(bodies) != 1:
        raise StateFormatError(f"expected one Michigan DNR file, got {len(bodies)}")
    reader = csv.DictReader(io.StringIO(bodies[0].text.lstrip("﻿")))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise StateFormatError(
            f"the Michigan DNR file is missing columns {missing}; it may have changed"
        )
    return [{k: (v or "") for k, v in row.items() if k} for row in reader]


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for row in _rows(bodies):
        species = " ".join(row["Species"].split())
        if "trout" not in species.lower():
            continue
        if row["Operation"].strip() not in PUBLIC_OPERATIONS:
            continue
        day = _day(row["Stocking_Date"])
        if day < PUBLISH_SINCE:
            continue
        county = row["County_Name"].strip()
        water = row["Water_Body_Name"].strip()
        site = row["sitename"].strip()
        if not (county and water):
            skipped += 1
            continue
        wid = water_id(county, water, site)
        name = water if not site or site == water else f"{water} ({site})"
        waters[wid] = WaterMeta(
            id=wid,
            slug=slugify(water, site, county, "county"),
            name=name,
            counties=(county,),
            region=None,
            source_id=None,
            source_url=DASHBOARD_URL,
        )
        rec = ParsedRecord(
            water_id=wid,
            period=Period.day(day),
            species=species,
            count=_count(row["Number_Fish_Stocked"]),
        )
        prior = records.get(rec.key())
        if prior is not None:
            # Two lots of one species on one day at one site: one stocking.
            total = (prior.count or 0) + (rec.count or 0)
            both_none = prior.count is None and rec.count is None
            rec = ParsedRecord(
                rec.water_id, rec.period, rec.species, None if both_none else total
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
        etag=first.etag,
    )


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
) -> list[FetchedBody]:
    """robots.txt, then one conditional GET (NotModified on a 304)."""
    check_robots_strict(client, CSV_URL, user_agent)
    # The server answers "Accept: text/csv" with 406 (measured 2026-10-13); it
    # serves the file as application/octet-stream.
    return [get_text(client, CSV_URL, user_agent, accept=ACCEPT, since=context)]


SOURCE = StateSource(
    code="MI",
    name="Michigan",
    time_zone="America/Detroit",
    agency_name="Michigan Department of Natural Resources",
    agency_short_name="Michigan DNR",
    agency_url="https://www.michigan.gov/dnr",
    source_name="Michigan DNR fish stocking data",
    source_url=DASHBOARD_URL,
    data_urls=(CSV_URL,),
    semantics="report",
    date_precisions=("day",),
    attribution_text=(
        "Data: Michigan Department of Natural Resources, fish stocking data "
        f"({DASHBOARD_URL})."
    ),
    attribution_url=DASHBOARD_URL,
    disclaimer=(
        "Trout Truck is independent and is not affiliated with or endorsed by the "
        "Michigan DNR or the State of Michigan. The State provides this dataset "
        '"AS IS" and makes no warranty of its accuracy, timeliness or '
        "completeness. Trout stockings into public waters, and no others."
    ),
    license_summary=(
        "The Michigan DNR's stocking dataset is a public record with no "
        "restrictions on use, reproduction or distribution. Its terms also ask "
        "users to release and indemnify the State, which the owner accepted on "
        "2026-10-13."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=(
        "Michigan DNR records often appear weeks after the stocking itself (the "
        'DNR notes "a delay between a stocking event and a corresponding '
        'record"), so a recent stocking may not be listed yet.'
    ),
    # About 700 public trout stockings a year since 2021: fewer than this
    # looks like a truncated file, not a quiet year.
    min_rows=1000,
    publish_since=PUBLISH_SINCE,
    fetch=fetch,
    parse=parse,
)
