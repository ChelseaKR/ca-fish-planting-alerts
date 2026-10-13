"""Michigan: the DNR Fish Stocking Database (stockings already done).

The ArcGIS layer ``DNR/FishStockingReportGISAGO/MapServer/0`` sits behind
the DNR's dashboard. RESEARCH.md (2026-10-11) counted 70,453 rows from
1979-01-23, each with the DNR's ``waters_id`` (a stable key), the water,
county, species, the day, the number of fish and their average length. The
DNR says there is "a delay between a stocking event and a corresponding
record": the newest trout record on 2026-10-11 was 2026-07-29. So the app
and site say "stocked on <day>" and always show how recent the newest
record is (``recency_note``), never "this week's stockings".

**Not fetched by the daily run** (``cfpa.states.ENABLED_STATES``). On
2026-10-12 the layer's host, utility.arcgis.com, answered its robots.txt
with a 301 to the arcgis.com home page, which is not a robots file, and an
unreadable robots.txt puts a host off-limits (the owner's rule). The field
names below are RESEARCH.md's description, not read from the layer today;
``arcgis.features`` refuses a response that lacks any of them.

The license is the dataset's own (quoted in ``LICENSE``): "no restrictions
on the use, reproduction, or distribution", with an indemnity clause the
owner has been asked about (RESEARCH.md §7, question 2).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import httpx

from . import arcgis
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
    slugify,
)

DASHBOARD_URL = (
    "https://midnr.maps.arcgis.com/apps/dashboards/77581b13c6984b919ab8ed927496a31f"
)
ITEM_URL = "https://www.arcgis.com/home/item.html?id=77581b13c6984b919ab8ed927496a31f"
LAYER_URL = (
    "https://utility.arcgis.com/usrsvcs/servers/fc7739be5f5247e7bf7f2c6bc9471140/"
    "rest/services/DNR/FishStockingReportGISAGO/MapServer/0"
)

# Unverified field names (see the module docstring).
F_KEY = "waters_id"
F_WATER = "water_name"
F_COUNTY = "county"
F_SPECIES = "species"
F_DATE = "stocking_date"
F_COUNT = "number_fish"
FIELDS = (F_KEY, F_WATER, F_COUNTY, F_SPECIES, F_DATE, F_COUNT)

# Re-read this many days before the newest record on file, because records
# arrive late and out of order.
LOOKBACK_DAYS = 120
# Kept in history from the first fetch, and the earliest record the snapshot
# and the site publish: five seasons, not 47 years, so the app's download
# stays small.
PUBLISH_SINCE = dt.date(2021, 1, 1)

LICENSE = LicenseSource(
    name="Michigan DNR Fish Stocking Database (dataset license)",
    url=DASHBOARD_URL,
    terms_url=ITEM_URL,
    terms_read_on="2026-10-12",
    commercial_reuse="permitted",
    attribution_required=False,
    terms_quote=(
        "This dataset is a public record and, as more fully described below, "
        "there are no restrictions on the use, reproduction, or distribution of "
        "this dataset. ... You must defend, indemnify and hold the State, its "
        "departments, subdivisions, officers, and employees harmless, without "
        "limitation, from and against all actions, claims, losses, liabilities, "
        "damages, costs, attorney fees, and expenses (including those required "
        "to establish the right to indemnification) arising out of or relating "
        "to your access or use of this dataset."
    ),
)


def _count(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise StateFormatError(f"{F_COUNT} is not a number: {value!r}")
    if value < 0 or value != int(value):
        raise StateFormatError(f"{F_COUNT} is not a whole count: {value!r}")
    return int(value)


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    if not bodies:
        raise StateFormatError("no Michigan DNR response to read")
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for attrs in arcgis.features(bodies, FIELDS):
        key = str(attrs.get(F_KEY) or "").strip()
        name = str(attrs.get(F_WATER) or "").strip()
        county = str(attrs.get(F_COUNTY) or "").strip()
        species = str(attrs.get(F_SPECIES) or "").strip()
        day = arcgis.epoch_ms_date(attrs.get(F_DATE), F_DATE)
        if not (key and name and species and day):
            skipped += 1
            continue
        wid = "mi-" + slugify(key)
        waters[wid] = WaterMeta(
            id=wid,
            slug=slugify(name, county, "county") if county else slugify(name, key),
            name=name,
            counties=(county,) if county else (),
            region=None,
            source_id=key,
            source_url=DASHBOARD_URL,
        )
        rec = ParsedRecord(
            water_id=wid,
            period=Period.day(day),
            species=species,
            count=_count(attrs.get(F_COUNT)),
        )
        prior = records.get(rec.key())
        if prior is not None and prior.count is not None and rec.count is not None:
            # Two lots of the same species on the same day: one stocking.
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


def since_date(known_newest: dt.date | None) -> dt.date:
    if known_newest is None:
        return PUBLISH_SINCE
    return max(PUBLISH_SINCE, known_newest - dt.timedelta(days=LOOKBACK_DAYS))


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    known_newest: dt.date | None = None,
) -> list[FetchedBody]:
    check_robots_strict(client, LAYER_URL, user_agent)
    since = since_date(known_newest).isoformat()
    return arcgis.query_all(
        client,
        LAYER_URL,
        user_agent,
        sleep,
        where=f"{F_DATE} >= DATE '{since}'",
        order_by=f"{F_DATE} ASC",
    )


SOURCE = StateSource(
    code="MI",
    name="Michigan",
    time_zone="America/Detroit",
    agency_name="Michigan Department of Natural Resources",
    agency_short_name="Michigan DNR",
    agency_url="https://www.michigan.gov/dnr",
    source_name="Michigan DNR Fish Stocking Database",
    source_url=DASHBOARD_URL,
    data_urls=(LAYER_URL,),
    semantics="report",
    date_precisions=("day",),
    attribution_text=(
        "Data: Michigan Department of Natural Resources, Fish Stocking Database "
        f"({DASHBOARD_URL})."
    ),
    attribution_url=DASHBOARD_URL,
    disclaimer=(
        "Trout Truck is independent and is not affiliated with or endorsed by the "
        "Michigan DNR or the State of Michigan. The State provides this dataset "
        '"AS IS" and makes no warranty of its accuracy, timeliness or '
        "completeness."
    ),
    license_summary=(
        "The Michigan DNR's stocking dataset is a public record with no "
        "restrictions on use, reproduction or distribution, under terms that "
        "also ask users to indemnify the State."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=(
        "Michigan DNR records often appear weeks after the stocking itself (the "
        'DNR notes "a delay between a stocking event and a corresponding '
        'record"), so a recent stocking may not be listed yet.'
    ),
    min_rows=1,
    publish_since=PUBLISH_SINCE,
    fetch=fetch,
    parse=parse,
)
