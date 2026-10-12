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
from .tn import SOURCE as TN

# Every state this code knows how to read, by postal code.
SOURCES: dict[str, StateSource] = {s.code: s for s in (TN, MA, MI)}

# The states the daily run fetches. Massachusetts and Michigan are built and
# tested but not fetched: on 2026-10-12 neither data host serves a readable
# robots.txt (services1.arcgis.com answers 403; utility.arcgis.com redirects
# to the arcgis.com home page), and the owner's rule is that an unreadable
# robots.txt puts a host off-limits. ``base.check_robots_strict`` enforces
# the same rule if one is ever fetched by hand with ``--states MA``.
ENABLED_STATES: tuple[str, ...] = ("TN",)

__all__ = ["ENABLED_STATES", "SOURCES", "StateSource"]
