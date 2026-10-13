"""Reading an ArcGIS REST ``query`` endpoint, for the states that publish
their stocking records as an ArcGIS layer (Massachusetts, Michigan).

Field names are passed in, never discovered: a response whose ``fields``
list lacks any of them is refused whole (``StateFormatError``), so a renamed
column can only stop a state's update, never publish a wrong value.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable, Iterable
from typing import Any

import httpx

from .base import (
    POLITE_DELAY_SECONDS,
    FetchedBody,
    StateFetchError,
    StateFormatError,
    get_text,
)

PAGE_SIZE = 1000
# A run that needs more pages than this is not reading a stocking report.
MAX_PAGES = 120


def query_all(
    client: httpx.Client,
    layer_url: str,
    user_agent: str,
    sleep: Callable[[float], None],
    *,
    where: str,
    order_by: str,
) -> list[FetchedBody]:
    """Every page of ``where``, oldest request first, ``POLITE_DELAY_SECONDS``
    apart. The robots check is the caller's, before the first page."""
    bodies: list[FetchedBody] = []
    for page in range(MAX_PAGES):
        if page:
            sleep(POLITE_DELAY_SECONDS)
        body = get_text(
            client,
            f"{layer_url}/query",
            user_agent,
            params={
                "where": where,
                "outFields": "*",
                "orderByFields": order_by,
                "resultOffset": str(page * PAGE_SIZE),
                "resultRecordCount": str(PAGE_SIZE),
                "returnGeometry": "false",
                "f": "json",
            },
        )
        bodies.append(body)
        if not _decode(body).get("exceededTransferLimit"):
            return bodies
    raise StateFetchError(
        f"{layer_url} still had more rows after {MAX_PAGES} pages; refusing"
    )


def _decode(body: FetchedBody) -> dict[str, Any]:
    try:
        doc = json.loads(body.text)
    except json.JSONDecodeError as exc:
        raise StateFormatError(f"ArcGIS response is not JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise StateFormatError("ArcGIS response is not an object")
    if "error" in doc:
        raise StateFormatError(f"ArcGIS answered with an error: {doc['error']}")
    return doc


def features(
    bodies: Iterable[FetchedBody], required_fields: Iterable[str]
) -> list[dict[str, Any]]:
    """Every feature's attributes, after checking each page names every
    required field."""
    need = set(required_fields)
    out: list[dict[str, Any]] = []
    for body in bodies:
        doc = _decode(body)
        names = {f.get("name") for f in doc.get("fields", []) if isinstance(f, dict)}
        missing = sorted(need - names)
        if missing:
            raise StateFormatError(
                f"ArcGIS layer is missing fields {missing} (it has {sorted(n for n in names if n)}); "
                "the layer may have changed, so nothing from it is used"
            )
        feats = doc.get("features")
        if not isinstance(feats, list):
            raise StateFormatError("ArcGIS response has no 'features' list")
        for feat in feats:
            attrs = feat.get("attributes") if isinstance(feat, dict) else None
            if not isinstance(attrs, dict):
                raise StateFormatError("ArcGIS feature has no attributes")
            out.append(attrs)
    return out


def epoch_ms_date(value: Any, field: str) -> dt.date | None:
    """An ArcGIS date field (milliseconds since 1970, UTC) as a calendar date.

    The UTC date is used: a layer that stores a local midnight (04:00 or
    05:00 UTC in the East) and one that stores a UTC midnight both land on
    the right day that way, where converting to Eastern time would move the
    second kind back a day.
    """
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise StateFormatError(f"{field} is not an ArcGIS date: {value!r}")
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC).date()
