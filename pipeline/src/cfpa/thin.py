"""Which water pages are thin (DECISIONS 0041).

A water page with fewer than ``WATER_INDEX_MIN_DATED_ROWS`` dated stocking
rows keeps its page, its calendar feed and every link to it, but carries a
robots ``noindex,follow`` tag, is left out of the sitemap, and carries no
Amazon gear block. One function decides both, so the sitemap, the robots tag
and the gear block always agree about a page.

A **dated row** is one row of the page's stocking table that is a stocking
with a date (the site's own data model, ``schema/snapshot.v1.json`` and
``snapshot.v2.json``):

- its status is not ``removed`` (a plant the agency dropped is shown as
  "Schedule changed", not as a stocking), and
- its period is a day, a week, or an agency's own words for a part of a month
  (v2 ``approximate``, New York's "April - third week"), never a bare month
  (Tennessee's "TBD 12/2026"), which is the precision the hub's date span
  (``site_states._date_range_label``) already leaves out as undated.

California's v1 plants always carry a CDFW week, so for them only the status
matters. Kept in its own module because ``site.py`` imports ``site_states``,
and both need it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Owner decision 2026-10-30, after the 2026-10-23 site-wide re-rank: the
# same threshold as the audit's fix 2 and 3 (tt-indexing-audit-2026-10-30).
WATER_INDEX_MIN_DATED_ROWS = 2

# Water pages that stay indexed, with their gear block, even though they are
# thin: pages Search Console shows people already find. Checked 2026-10-30
# against the top pages by impressions, 2026-08-01 to 2026-10-30
# (sc-domain:trouttruck.com). Only this one, the 10th page of the site by
# impressions (18, 1 click) with 1 dated row, was in the top 25 or had 10 or
# more impressions; the next thin page had 7. Paths, as in sitemap.xml.
KEEP_INDEXED_PATHS: frozenset[str] = frozenset(
    {
        "/tn/water/fountain-city-lake-knox-county/",
    }
)


def _is_dated(p: dict[str, Any]) -> bool:
    if p.get("status") == "removed":
        return False
    period = p.get("period")
    if period is None:
        # v1 (California): every plant is a CDFW week.
        return "week" in p
    return bool(period.get("precision") != "month")


def dated_rows(plants: Iterable[dict[str, Any]]) -> int:
    """How many of ``plants`` are dated stocking rows (see the module doc)."""
    return sum(1 for p in plants if _is_dated(p))


def is_thin(plants: Iterable[dict[str, Any]], path: str = "") -> bool:
    """Whether a water page is thin: noindex, out of the sitemap, and no gear
    block. ``path`` is the page's site path (``/water/<slug>/`` or
    ``/<code>/water/<slug>/``), checked against ``KEEP_INDEXED_PATHS``."""
    if path in KEEP_INDEXED_PATHS:
        return False
    return dated_rows(plants) < WATER_INDEX_MIN_DATED_ROWS
