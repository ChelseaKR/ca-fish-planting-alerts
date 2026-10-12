"""Read the geocoder's committed output for the snapshot builder.

``pipeline/data/water_locations.json`` is written by ``cfpa-geocode`` (run by
hand, offline; see ``cfpa.geocode``) and committed. The daily run only reads
it. Only ``exact`` and ``owner_resolved`` waters carry a point; every other
water gets ``None``, so an ambiguous or unmatched water is never placed.

Snapshot v1 never reads this file: its ``location`` stays ``null`` byte for
byte for installed 1.0 builds. Snapshot v2 calls :func:`location_for` for each
California water.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .geocode import LOCATIONS_SCHEMA

PLACED = frozenset({"exact", "owner_resolved"})
KINDS = frozenset({"waterbody", "named_point", "stream_point"})
LOCATION_KEYS = ("lat", "lon", "source", "kind", "source_feature_id")


def load_locations(path: Path) -> dict[int, dict[str, Any]]:
    """CDFW stock id -> location, for placed waters only."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != LOCATIONS_SCHEMA:
        raise ValueError(f"{path}: schema is not {LOCATIONS_SCHEMA}")
    out: dict[int, dict[str, Any]] = {}
    for w in doc["waters"]:
        loc = w.get("location")
        if w["status"] not in PLACED:
            if loc is not None:
                raise ValueError(
                    f"cdfw-{w['cdfw_stock_id']}: {w['status']} with a point"
                )
            continue
        out[int(w["cdfw_stock_id"])] = _checked(w["cdfw_stock_id"], loc)
    return out


def _checked(stock_id: object, loc: Any) -> dict[str, Any]:
    if not isinstance(loc, dict) or set(loc) != set(LOCATION_KEYS):
        raise ValueError(f"cdfw-{stock_id}: location must have {LOCATION_KEYS}")
    lat, lon = loc["lat"], loc["lon"]
    # California's bounding box, generously: a point outside it is a bug.
    if not (32.0 <= lat <= 42.5 and -125.0 <= lon <= -114.0):
        raise ValueError(f"cdfw-{stock_id}: {lat}, {lon} is not in California")
    if loc["kind"] not in KINDS:
        raise ValueError(f"cdfw-{stock_id}: unknown kind {loc['kind']!r}")
    return {k: loc[k] for k in LOCATION_KEYS}


def location_for(
    locations: Mapping[int, dict[str, Any]], stock_id: int
) -> dict[str, Any] | None:
    """The v2 ``location`` value for one California water, or None."""
    loc = locations.get(stock_id)
    return None if loc is None else dict(loc)
