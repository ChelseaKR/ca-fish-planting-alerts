"""Massachusetts: MassWildlife's trout stocking report (stockings already done).

The ArcGIS layer ``StockedFish_View/FeatureServer/0`` feeds
https://www.mass.gov/info-details/trout-stocking-report ("stocking locations
are updated daily"). Each feature is one completed stocking: a waterbody, its
town, a species code, MassWildlife's ``Water_Town_Code`` (a stable key), and
the day. It is a report, not a schedule, so nothing is ever inferred as
removed: rows age off at the end of the season (docs/DECISIONS.md 0016).

**Not fetched by the daily run** (``cfpa.states.ENABLED_STATES``). On
2026-10-12 the layer's host, services1.arcgis.com, answered its robots.txt
with HTTP 403, and an unreadable robots.txt puts a host off-limits (the
owner's rule). So no live response was taken for this lane, and the field
names below are the ones RESEARCH.md (2026-10-11) describes, not ones read
from the layer today. ``arcgis.features`` refuses a response that lacks any
of them, so a wrong name stops the state's update instead of publishing a
wrong value. The test fixture is built to these names and says so.

The mass.gov page itself is "fair use" only (its terms), so it is never
read; the layer's own item license grants copying and use.
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

PAGE_URL = "https://www.mass.gov/info-details/trout-stocking-report"
LAYER_URL = (
    "https://services1.arcgis.com/7iJyYTjCtKsZS1LR/arcgis/rest/services/"
    "StockedFish_View/FeatureServer/0"
)

# Unverified field names (see the module docstring).
F_WATER = "Waterbody"
F_TOWN = "Town"
F_SPECIES = "Species"
F_KEY = "Water_Town_Code"
F_DATE = "Date"
FIELDS = (F_WATER, F_TOWN, F_SPECIES, F_KEY, F_DATE)

# MassWildlife publishes a species code. Codes are shown as published until
# a mapping is confirmed against the live layer; none is guessed here.
SPECIES_NAMES: dict[str, str] = {}

LICENSE = LicenseSource(
    name="MassWildlife StockedFish_View (ArcGIS item license)",
    url=LAYER_URL,
    terms_url="https://www.mass.gov/info-details/trout-stocking-report",
    terms_read_on="2026-10-11",
    commercial_reuse="permitted",
    attribution_required=False,
    terms_quote=(
        "All maps and other material provided herein are protected by copyright. "
        "Permission is granted to copy and use the materials herein."
    ),
)


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    if not bodies:
        raise StateFormatError("no MassWildlife response to read")
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for attrs in arcgis.features(bodies, FIELDS):
        name = str(attrs.get(F_WATER) or "").strip()
        town = str(attrs.get(F_TOWN) or "").strip()
        key = str(attrs.get(F_KEY) or "").strip()
        code = str(attrs.get(F_SPECIES) or "").strip()
        day = arcgis.epoch_ms_date(attrs.get(F_DATE), F_DATE)
        if not (name and key and code and day):
            skipped += 1
            continue
        wid = "ma-" + slugify(key)
        waters[wid] = WaterMeta(
            id=wid,
            slug=slugify(name, town),
            name=name,
            towns=(town,) if town else (),
            region=None,
            source_id=key,
            source_url=PAGE_URL,
        )
        rec = ParsedRecord(
            water_id=wid, period=Period.day(day), species=SPECIES_NAMES.get(code, code)
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
    known_newest: dt.date | None = None,
) -> list[FetchedBody]:
    check_robots_strict(client, LAYER_URL, user_agent)
    return arcgis.query_all(
        client, LAYER_URL, user_agent, sleep, where="1=1", order_by=f"{F_DATE} ASC"
    )


SOURCE = StateSource(
    code="MA",
    name="Massachusetts",
    time_zone="America/New_York",
    agency_name="Massachusetts Division of Fisheries and Wildlife",
    agency_short_name="MassWildlife",
    agency_url="https://www.mass.gov/orgs/masswildlife",
    source_name="MassWildlife trout stocking report",
    source_url=PAGE_URL,
    data_urls=(LAYER_URL,),
    semantics="report",
    date_precisions=("day",),
    attribution_text=(
        "Data: Massachusetts Division of Fisheries and Wildlife (MassWildlife), "
        f"trout stocking report ({PAGE_URL})."
    ),
    attribution_url=PAGE_URL,
    disclaimer=(
        "Trout Truck is independent and is not affiliated with or endorsed by "
        "MassWildlife or the Commonwealth of Massachusetts. These are stockings "
        "MassWildlife has reported, by the day it reported them."
    ),
    license_summary=(
        "The stocking layer's own license grants permission to copy and use it. "
        "The mass.gov page that shows it allows fair use only, so the data is "
        "read from the layer, never from the page."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=None,
    min_rows=1,
    publish_since=None,
    fetch=fetch,
    parse=parse,
)
