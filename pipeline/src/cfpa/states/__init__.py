"""Stocking data from states other than California (docs/adr/0015).

California keeps its own pipeline (``cfpa.fetch``, ``cfpa.history``,
``cfpa.snapshot``), and ``snapshot/v1.json`` is built from it exactly as
before. Every other state is a ``StateSource`` here: one agency feed, its
license quoted, its own append-only history file, and its own idea of what a
record means (a schedule that says when fish *will* come, a report of
stockings that already happened, or a once-a-year plan in the agency's own
words). ``cfpa.snapshot_v2`` joins them with California into
``snapshot/v2.json``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from .base import StateSource
from .ma import SOURCE as MA
from .mi import SOURCE as MI
from .ny import SOURCE as NY
from .oregon import ENV_FLAG as OREGON_FLAG
from .oregon import SOURCE as OR
from .tn import SOURCE as TN


def oregon_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Oregon is off unless ``CFPA_ENABLE_OREGON`` is exactly ``1``. Unset,
    empty and ``0`` are off; any other value refuses the run rather than being
    guessed at (a typo must not silently turn a state on or leave it off)."""
    value = (os.environ if env is None else env).get(OREGON_FLAG, "").strip()
    if value in ("", "0"):
        return False
    if value == "1":
        return True
    raise ValueError(f"{OREGON_FLAG} must be 1 or 0 (or unset), not {value!r}")


def registered_sources(
    env: Mapping[str, str] | None = None,
) -> dict[str, StateSource]:
    """Every state this code knows how to read, by postal code. Oregon joins
    only behind its flag (docs/DECISIONS.md 0032), so a default run has the
    same registry, pages, sitemap and snapshot as before Oregon existed."""
    found = [TN, MA, MI, NY]
    if oregon_enabled(env):
        found.append(OR)
    return {s.code: s for s in found}


# The states the daily run fetches. A state is added here only after its
# fetch has worked on live data (DECISIONS 0034): Tennessee on 2026-10-12;
# Michigan (DNR's CSV, robots 404), Massachusetts (ArcGIS Hub, robots 200,
# Crawl-delay 60) and New York (OPEN-NY's API) on 2026-10-13. Massachusetts'
# own layer host, services1.arcgis.com, answers robots.txt with 403 and is
# never touched. Oregon is added by its flag (DECISIONS 0032).
FETCHED_STATES: tuple[str, ...] = ("TN", "MI", "MA", "NY")


def enabled_states(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The states the daily run fetches. Oregon is added by its flag."""
    return FETCHED_STATES + (("OR",) if oregon_enabled(env) else ())


# Every state this code knows how to read, by postal code.
SOURCES: dict[str, StateSource] = registered_sources()

# The states the daily run fetches (see ``FETCHED_STATES``).
ENABLED_STATES: tuple[str, ...] = enabled_states()

__all__ = [
    "ENABLED_STATES",
    "FETCHED_STATES",
    "SOURCES",
    "StateSource",
    "enabled_states",
    "oregon_enabled",
    "registered_sources",
]
