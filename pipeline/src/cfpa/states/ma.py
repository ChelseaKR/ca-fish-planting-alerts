"""Massachusetts: MassWildlife's trout stocking report (stockings already done).

The data is MassWildlife's ArcGIS item "Stocked Fish (View)"
(``e27aa5ec1ef74659aac1ef12b39510f1``), the layer behind
https://www.mass.gov/info-details/trout-stocking-report. Its item text:
"This view only excludes planned stocking activities and only shows stocking
activities that have been fulfilled."

**The route** (the owner's decision of 2026-10-13, DECISIONS 0034): the
ArcGIS Hub download API on ``hub.arcgis.com``, whose robots.txt is readable
(200, ``Crawl-delay: 60``, ``/api/`` allowed). The layer's own host,
``services1.arcgis.com``, answers its robots.txt with 403 and is never
touched; neither is ``www.mass.gov`` (403, and "fair use" terms).

1. ``GET /api/download/v1/items/<id>/csv?redirect=false&layers=0``. Hub
   answers 202 ``{"status": "Pending"}`` while it builds the file, or 200
   ``{"status": "Completed", "resultUrl": ...}``. A Completed answer with
   ``"cacheStatus": "stale"`` means Hub's file is older than the layer; that
   is a failed check and the file is not read (DECISIONS 0063). Only then,
   after the Crawl-delay, one ``GET /api/v3/datasets/<id>_0``: Hub's own
   metadata for the layer, for MassWildlife's last edit and record count,
   which the failed check records (DECISIONS 0071). A failure there leaves
   both unknown and changes nothing else.
2. On 202, wait the host's Crawl-delay (61 s) and ask again, at most
   ``MAX_POLLS`` times in all.
3. ``GET`` the ``resultUrl`` exactly as returned, after checking that its host
   is ``hub.arcgis.com`` and that robots.txt allows its path. Redirects are
   never followed.

So a run makes two to three requests, 61 s apart (three when Hub's file is
stale: the status, the metadata, and no CSV).

The CSV (measured 2026-10-12, 150 rows, 2026-09-24 to 2026-10-09):
``OBJECTID, Waterbody ("Lake Wyola - Shutesbury"), Town, Species (a code),
Water_Town_Code ("34103-272", a stable key), GlobalID, Stocked_Date
("2026/09/25 22:00:00+00")``. Every time seen is 22:00 UTC, so the date as
written is the local date. A report: nothing is ever inferred as removed
(DECISIONS 0016); rows age off at the end of the season, and Trout Truck's
history becomes the long record.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from .base import (
    FetchContext,
    FetchedBody,
    LicenseSource,
    ParsedFeed,
    ParsedRecord,
    Period,
    StaleCopyError,
    StateFetchError,
    StateFormatError,
    StateSource,
    WaterMeta,
    check_robots_strict,
    combined_sha256,
    get_text,
    polite_delay,
    slugify,
)

PAGE_URL = "https://www.mass.gov/info-details/trout-stocking-report"
ITEM_ID = "e27aa5ec1ef74659aac1ef12b39510f1"
HUB_HOST = "hub.arcgis.com"
DOWNLOAD_URL = f"https://{HUB_HOST}/api/download/v1/items/{ITEM_ID}/csv"
ITEM_URL = f"https://www.arcgis.com/home/item.html?id={ITEM_ID}"
# Hub's metadata for the layer (layer 0 of the item): its record count and
# the layer's last edit, which Hub reads from the service itself.
METADATA_URL = f"https://{HUB_HOST}/api/v3/datasets/{ITEM_ID}_0"
# Hub says where ``modified`` came from; only the layer's own edit date is
# MassWildlife's last change (the item's ``modified`` is not).
LAYER_EDIT_PROVENANCE = "layer.editingInfo.lastEditDate"

# At most this many download-status requests per run, then the CSV itself.
MAX_POLLS = 2

COLUMNS = ("Waterbody", "Town", "Species", "Water_Town_Code", "Stocked_Date")

# MassWildlife's own legend: the layer's coded-value domain
# ``cvd_FishSpecies``, read 2026-10-12 from the Hub's metadata for the item
# (``/api/v3/datasets/<id>_0``). "BT" is verified there as Brown Trout. A
# code not in it refuses the feed, so a new code is never shown as a guess.
SPECIES_NAMES: dict[str, str] = {
    "BT": "Brown Trout",
    "EBT": "Eastern Brook Trout",
    "RT": "Rainbow Trout",
    "S": "Broodstock Salmon",
    "TT": "Tiger Trout",
}

_DATE_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2}) \d{2}:\d{2}:\d{2}\+00$")

LICENSE = LicenseSource(
    name="MassWildlife Stocked Fish (View), ArcGIS item license",
    url=ITEM_URL,
    terms_url=ITEM_URL,
    terms_read_on="2026-10-12",
    commercial_reuse="permitted",
    attribution_required=False,
    terms_quote=(
        "All maps and other material provided herein are protected by copyright. "
        "Permission is granted to copy and use the materials herein."
    ),
)


def _day(text: str) -> dt.date:
    m = _DATE_RE.match(text.strip())
    if not m:
        raise StateFormatError(
            f"Stocked_Date is not 'YYYY/MM/DD hh:mm:ss+00': {text!r}"
        )
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _water_name(waterbody: str, town: str) -> str:
    """ "Lake Wyola - Shutesbury" -> "Lake Wyola" when the suffix is the town."""
    suffix = f" - {town}"
    return (
        waterbody[: -len(suffix)] if town and waterbody.endswith(suffix) else waterbody
    )


def parse(bodies: list[FetchedBody]) -> ParsedFeed:
    if len(bodies) != 1:
        raise StateFormatError(f"expected one MassWildlife file, got {len(bodies)}")
    reader = csv.DictReader(io.StringIO(bodies[0].text.lstrip("﻿")))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise StateFormatError(f"MassWildlife's file is missing columns {missing}")
    waters: dict[str, WaterMeta] = {}
    records: dict[tuple[str, str, str, str], ParsedRecord] = {}
    skipped = 0
    for row in reader:
        waterbody = (row["Waterbody"] or "").strip()
        town = (row["Town"] or "").strip()
        key = (row["Water_Town_Code"] or "").strip()
        code = (row["Species"] or "").strip()
        when = (row["Stocked_Date"] or "").strip()
        if not (waterbody and key and code and when):
            skipped += 1
            continue
        if code not in SPECIES_NAMES:
            raise StateFormatError(
                f"species code {code!r} is not in MassWildlife's legend "
                f"{sorted(SPECIES_NAMES)}; refusing rather than guessing"
            )
        name = _water_name(waterbody, town)
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
            water_id=wid, period=Period.day(_day(when)), species=SPECIES_NAMES[code]
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


def _status(body: FetchedBody) -> dict[str, object]:
    try:
        doc = json.loads(body.text)
    except json.JSONDecodeError as exc:
        raise StateFormatError(f"Hub's download status is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise StateFormatError("Hub's download status is not an object")
    return doc


class _HubCacheStale(Exception):
    """Hub answered Completed with ``cacheStatus`` "stale"."""


def _result_url(status: dict[str, object]) -> str | None:
    if status.get("status") != "Completed":
        return None
    # Hub's own flag that its file is older than the layer (DECISIONS 0063).
    # On 2026-11-07 Hub answered "stale" for a file built 2026-10-13 02:35 UTC
    # (150 rows) while the layer said 155 records, last edited 2026-10-13
    # 17:06 UTC. Reading that file would show old data as current, so it is
    # a failed check: the last good data is kept and the pages say so.
    if status.get("cacheStatus") == "stale":
        raise _HubCacheStale
    url = status.get("resultUrl")
    if not isinstance(url, str):
        raise StateFormatError("Hub said Completed but gave no resultUrl")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != HUB_HOST:
        raise StateFetchError(
            f"Hub's resultUrl is on {parts.netloc!r}, not {HUB_HOST}; not followed"
        )
    return url


def layer_facts(text: str) -> tuple[dt.datetime | None, int | None]:
    """MassWildlife's last edit to the layer and its record count, from Hub's
    metadata (``/api/v3/datasets/<id>_0``, measured 2026-11-14:
    ``data.attributes.modified`` 1791911199165, ``modifiedProvenance``
    "layer.editingInfo.lastEditDate", ``recordCount`` 155), the edit to the
    whole second. Each is None
    when it is missing or not what it should be; never a guess."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    data = doc.get("data") if isinstance(doc, dict) else None
    attrs = data.get("attributes") if isinstance(data, dict) else None
    if not isinstance(attrs, dict):
        return None, None
    edited: dt.datetime | None = None
    millis = attrs.get("modified")
    if (
        attrs.get("modifiedProvenance") == LAYER_EDIT_PROVENANCE
        and isinstance(millis, int)
        and not isinstance(millis, bool)
        and millis > 0
    ):
        # Whole seconds: what the history file keeps.
        edited = dt.datetime.fromtimestamp(millis // 1000, dt.UTC)
    count = attrs.get("recordCount")
    records = (
        count
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0
        else None
    )
    return edited, records


def _stale_copy_error(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    delay: float,
) -> StaleCopyError:
    """The failed check for a stale Hub file, with what Hub's metadata says
    about MassWildlife's layer: one more request, after the Crawl-delay. If
    it cannot be read, both facts are unknown (DECISIONS 0071), which the
    freshness watchdog counts as stuck."""
    edited: dt.datetime | None = None
    records: int | None = None
    try:
        check_robots_strict(client, METADATA_URL, user_agent)
        sleep(delay)
        edited, records = layer_facts(get_text(client, METADATA_URL, user_agent).text)
    except StateFetchError:
        pass
    facts = (
        "MassWildlife's layer was last edited "
        + (edited.strftime("%Y-%m-%d %H:%M UTC") if edited else "(unknown)")
        + ", with "
        + (str(records) if records is not None else "an unknown number of")
        + " records, per Hub's metadata"
    )
    return StaleCopyError(
        "Hub marked its copy of MassWildlife's layer stale (cacheStatus "
        "'stale'): MassWildlife changed the layer after Hub built the file, "
        f"so the file is not current; not read. {facts}",
        source_last_edit_at=edited,
        source_record_count=records,
    )


def fetch(
    client: httpx.Client,
    user_agent: str,
    sleep: Callable[[float], None],
    context: FetchContext | None = None,
) -> list[FetchedBody]:
    """robots.txt, the download status (polled at the Crawl-delay), the CSV."""
    delay = polite_delay(check_robots_strict(client, DOWNLOAD_URL, user_agent))
    url: str | None = None
    for attempt in range(MAX_POLLS):
        if attempt:
            sleep(delay)
        status = _status(
            get_text(
                client,
                DOWNLOAD_URL,
                user_agent,
                params={"redirect": "false", "layers": "0"},
            )
        )
        try:
            url = _result_url(status)
        except _HubCacheStale:
            raise _stale_copy_error(client, user_agent, sleep, delay) from None
        if url is not None:
            break
        if status.get("status") not in ("Pending", "Processing", "InProgress"):
            raise StateFetchError(f"Hub's download is {status.get('status')!r}")
    if url is None:
        raise StateFetchError(
            f"Hub had not built the file after {MAX_POLLS} requests; trying next run"
        )
    check_robots_strict(client, url, user_agent)
    sleep(delay)
    return [get_text(client, url, user_agent, accept="text/csv")]


SOURCE = StateSource(
    code="MA",
    name="Massachusetts",
    time_zone="America/New_York",
    agency_name="Massachusetts Division of Fisheries and Wildlife",
    agency_short_name="MassWildlife",
    agency_url="https://www.mass.gov/orgs/masswildlife",
    source_name="MassWildlife trout stocking report",
    source_url=PAGE_URL,
    data_urls=(DOWNLOAD_URL,),
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
        "MassWildlife has reported as done, by the day."
    ),
    license_summary=(
        "The stocking layer's own license grants permission to copy and use it. "
        "It is read through ArcGIS Hub's public download API; the mass.gov page, "
        "whose terms allow fair use and nothing more, is never read."
    ),
    license_sources=(LICENSE,),
    regions=(),
    recency_note=None,
    # A report never infers a removal, so an empty file (the season is over)
    # changes nothing on file; there is no "nothing stocked" to misread.
    min_rows=0,
    publish_since=None,
    fetch=fetch,
    parse=parse,
)
