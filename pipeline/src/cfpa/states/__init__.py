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

import os
from collections.abc import Mapping

from .base import StateSource
from .ma import SOURCE as MA
from .mi import SOURCE as MI
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
    found = [TN, MA, MI]
    if oregon_enabled(env):
        found.append(OR)
    return {s.code: s for s in found}


def enabled_states(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The states the daily run fetches. Oregon is added by its flag."""
    return ("TN", "OR") if oregon_enabled(env) else ("TN",)


# Every state this code knows how to read, by postal code.
SOURCES: dict[str, StateSource] = registered_sources()

# The states the daily run fetches. Massachusetts and Michigan are built and
# tested but not fetched: on 2026-10-12 neither data host serves a readable
# robots.txt (services1.arcgis.com answers 403; utility.arcgis.com redirects
# to the arcgis.com home page), and the owner's rule is that an unreadable
# robots.txt puts a host off-limits. ``base.check_robots_strict`` enforces
# the same rule if one is ever fetched by hand with ``--states MA``.
ENABLED_STATES: tuple[str, ...] = enabled_states()

__all__ = [
    "ENABLED_STATES",
    "SOURCES",
    "StateSource",
    "enabled_states",
    "oregon_enabled",
    "registered_sources",
]
