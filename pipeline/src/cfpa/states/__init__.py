"""Stocking data from states other than California (docs/adr/0015).

California keeps its own pipeline (``cfpa.fetch``, ``cfpa.history``,
``cfpa.snapshot``), and ``snapshot/v1.json`` is built from it exactly as
before. Every other state is a ``StateSource`` here: one agency feed, its
license quoted, its own append-only history file, and its own idea of what a
record means (a schedule that says when fish *will* come, or a report of
stockings that already happened). ``cfpa.snapshot_v2`` joins them with
California into ``snapshot/v2.json``.
"""

from __future__ import annotations

from .base import StateSource
from .ma import SOURCE as MA
from .mi import SOURCE as MI
from .ny import SOURCE as NY
from .tn import SOURCE as TN

# Every state this code knows how to read, by postal code.
SOURCES: dict[str, StateSource] = {s.code: s for s in (TN, MA, MI, NY)}

# The states the daily run fetches. A state is added here only after its
# fetch has worked on live data (DECISIONS 0028): Tennessee on 2026-10-12;
# Michigan (DNR's CSV, robots 404), Massachusetts (ArcGIS Hub, robots 200,
# Crawl-delay 60) and New York (OPEN-NY's API) on 2026-10-13. Massachusetts'
# own layer host, services1.arcgis.com, answers robots.txt with 403 and is
# never touched.
ENABLED_STATES: tuple[str, ...] = ("TN", "MI", "MA", "NY")

__all__ = ["ENABLED_STATES", "SOURCES", "StateSource"]
