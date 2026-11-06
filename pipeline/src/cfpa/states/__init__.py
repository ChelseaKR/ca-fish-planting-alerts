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
from .maryland import ENV_FLAG as MARYLAND_FLAG
from .maryland import SOURCE as MD
from .mi import SOURCE as MI
from .ny import SOURCE as NY
from .oregon import ENV_FLAG as OREGON_FLAG
from .oregon import SOURCE as OR
from .pennsylvania import ENV_FLAG as PENNSYLVANIA_FLAG
from .pennsylvania import SOURCE as PA
from .tn import SOURCE as TN
from .virginia import ENV_FLAG as VIRGINIA_FLAG
from .virginia import SOURCE as VA

# States that are built and tested but off by default, each behind its own
# environment flag, in the order they join the registry when on. None of them
# has the agency's written permission yet (DECISIONS 0032, 0055).
FLAGGED: tuple[tuple[str, StateSource], ...] = (
    (OREGON_FLAG, OR),
    (PENNSYLVANIA_FLAG, PA),
    (VIRGINIA_FLAG, VA),
    (MARYLAND_FLAG, MD),
)


def flag_enabled(flag: str, env: Mapping[str, str] | None = None) -> bool:
    """A flagged state is off unless its flag is exactly ``1``. Unset, empty
    and ``0`` are off; any other value refuses the run rather than being
    guessed at (a typo must not silently turn a state on or leave it off)."""
    value = (os.environ if env is None else env).get(flag, "").strip()
    if value in ("", "0"):
        return False
    if value == "1":
        return True
    raise ValueError(f"{flag} must be 1 or 0 (or unset), not {value!r}")


def oregon_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Oregon is off unless ``CFPA_ENABLE_OREGON`` is exactly ``1``."""
    return flag_enabled(OREGON_FLAG, env)


def _flagged_on(env: Mapping[str, str] | None) -> list[StateSource]:
    return [source for flag, source in FLAGGED if flag_enabled(flag, env)]


def registered_sources(
    env: Mapping[str, str] | None = None,
) -> dict[str, StateSource]:
    """Every state this code knows how to read, by postal code. Oregon,
    Pennsylvania, Virginia and Maryland join only behind their flags
    (docs/DECISIONS.md 0032 and 0055), so a default run has the same registry,
    pages, sitemap and snapshot as before any of them existed."""
    found = [TN, MA, MI, NY, *_flagged_on(env)]
    return {s.code: s for s in found}


# The states the daily run fetches. A state is added here only after its
# fetch has worked on live data (DECISIONS 0034): Tennessee on 2026-10-12;
# Michigan (DNR's CSV, robots 404), Massachusetts (ArcGIS Hub, robots 200,
# Crawl-delay 60) and New York (OPEN-NY's API) on 2026-10-13. Massachusetts'
# own layer host, services1.arcgis.com, answers robots.txt with 403 and is
# never touched. Oregon (DECISIONS 0032) and Pennsylvania, Virginia and
# Maryland (0055) are added only by their flags.
FETCHED_STATES: tuple[str, ...] = ("TN", "MI", "MA", "NY")


def enabled_states(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The states the daily run fetches. A flagged state is added by its flag."""
    return FETCHED_STATES + tuple(s.code for s in _flagged_on(env))


# Every state this code knows how to read, by postal code.
SOURCES: dict[str, StateSource] = registered_sources()

# The states the daily run fetches (see ``FETCHED_STATES``).
ENABLED_STATES: tuple[str, ...] = enabled_states()

__all__ = [
    "ENABLED_STATES",
    "FETCHED_STATES",
    "FLAGGED",
    "SOURCES",
    "StateSource",
    "enabled_states",
    "flag_enabled",
    "oregon_enabled",
    "registered_sources",
]
