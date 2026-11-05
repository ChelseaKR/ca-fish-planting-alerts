"""Answer-first openings for a named set of pages (DECISIONS 0046).

After the 2026-10-23 re-rank, the pages Search Console still tied to real
queries opened with background ("21 waters in Fresno County have been ...")
or with a bare "None scheduled". This module decides which pages lead with
the answer instead, and builds that answer from the snapshot alone:

- ``/county/fresno/``: this week's waters, the week before, the most recent
  other water, and the water in the city of Fresno by CDFW's own name;
- ``/water/ralphine-lake/``: the USGS name first, the last scheduled week, the
  weeks it was on the schedule in the same quarter last year, and the nearest
  waters on this week's schedule in place of the region list;
- ``/``: "CDFW (DFG)" in the h1 and this week's count of waters and counties;
- ``/county/``: the same count and a link to this week's list;
- three water pages that open with "None scheduled" (Collins, Skinner, Shadow
  Cliff): a water on this week's schedule near them, in the status block.

Only the pages in ``ANSWER_FIRST_PAGES`` change. Every other page, the
control pages in ``CONTROL_PATHS`` above all, builds byte for byte as before,
so the 2026-12-15 reading can tell a page fix from a site-wide re-score
(tt-fallback-plan-2026-11-04, section 4). Applying the same rules to every
page is Batch B, gated on that reading.

Nothing here estimates. "Nearest" is a straight line between two U.S.
Geological Survey points, and is said only between placed waters; a water
with no point is matched by county, then by CDFW region, and the page says
which. When this week's schedule has nothing to offer, the line is left out:
the page never shows an empty list or a zero.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# Page path -> the changes it gets. Paths as in sitemap.xml.
ANSWER_FIRST_PAGES: Mapping[str, frozenset[str]] = {
    "/": frozenset({"home_count"}),
    "/county/": frozenset({"counties_count"}),
    "/county/fresno/": frozenset({"county_answer", "winter_first"}),
    "/water/ralphine-lake/": frozenset(
        {"name_first", "answer_lede", "last_season", "nearest_list", "nearest_status"}
    ),
    "/water/collins-lake/": frozenset({"nearest_status"}),
    "/water/skinner-lake/": frozenset({"nearest_status"}),
    "/water/shadow-cliff-lake/": frozenset({"nearest_status"}),
}

# The plan's controls: pages that stay as they are, so that a rise shared by
# them and the treated pages reads as Google re-scoring the site.
CONTROL_PATHS: frozenset[str] = frozenset(
    {
        "/county/los-angeles/",
        "/county/sacramento/",
        "/water/mojave-narrows-regional-park-lake/",
        "/water/halsey-forebay/",
        "/water/lake-hemet/",
        "/water/portal-forebay/",
        "/tn/",
    }
)

NEAREST_LIST_MAX = 5
"""How many waters the nearest-this-week list on a water page names."""

NEAREST_LIST_MILES = 200
"""The nearest-this-week list leaves out waters farther than this, so a page
in Sonoma County does not offer a lake in Orange County. The status block's
single nearest water carries its distance instead, and is never cut."""

NEAR_STATUS_MAX = 3
"""How many waters the status block names when it falls back to a county or
region, before "and N more"."""

_EARTH_RADIUS_MILES = 3958.8

# Calendar quarters, by the season word a reader uses for them. The months are
# always printed next to the word, so "winter" is never left to mean the site's
# November-through-February winter (DECISIONS 0040).
_QUARTERS = (
    ("winter", "January", "March"),
    ("spring", "April", "June"),
    ("summer", "July", "September"),
    ("fall", "October", "December"),
)


def features(path: str) -> frozenset[str]:
    """The changes ``path`` gets; empty for every page not in the list."""
    return ANSWER_FIRST_PAGES.get(path, frozenset())


def for_page(path: str, feature: str, answer: dict[str, Any]) -> dict[str, Any] | None:
    """``answer`` when ``path`` gets ``feature``, else None."""
    return answer if feature in features(path) else None


def rollover_dates(path: str, source_week_start: str) -> list[str]:
    """The current week's start, for the lastmod of a page whose opening
    names this week (it changes at every rollover); empty for other pages."""
    return [source_week_start] if features(path) else []


def miles_between(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Great-circle distance between two ``[lat, lon, ...]`` points."""
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def rounded_miles(a: Sequence[Any], b: Sequence[Any]) -> int:
    """``miles_between`` to the nearest 5 miles, never below 5: the points
    are a lake's interior or a spot on a stream, not where anyone parks."""
    return max(5, 5 * round(miles_between(a, b) / 5))


def _row(w: Mapping[str, Any]) -> dict[str, Any]:
    counties = list(w["counties"])
    return {
        "slug": w["slug"],
        "name": w["name"],
        "county": f"{counties[0]} County"
        if len(counties) == 1
        else ", ".join(counties),
    }


def scheduled_near(
    w: Mapping[str, Any],
    scheduled: Iterable[Mapping[str, Any]],
    *,
    coords: Mapping[str, Sequence[Any]],
    region_name: str,
) -> dict[str, Any] | None:
    """Waters on this week's schedule near ``w``, and how "near" was decided.

    ``scheduled`` are the snapshot waters listed for the current week. With a
    point for ``w``, the placed ones are sorted by straight-line distance
    (``basis`` "distance"); waters with no point are not ranked, and the page
    says so. With no point for ``w``, the scheduled waters sharing one of its
    counties (``basis`` "county"), else its CDFW region (``basis`` "region"),
    alphabetical. None when there is nothing to name: the caller then shows
    nothing, never an empty list."""
    others = [s for s in scheduled if s["id"] != w["id"]]
    here = coords.get(w["slug"])
    if here is not None:
        placed = [s for s in others if s["slug"] in coords]
        if placed:
            placed.sort(
                key=lambda s: (miles_between(here, coords[s["slug"]]), s["name"])
            )
            return {
                "basis": "distance",
                "where": "",
                "waters": [
                    {**_row(s), "miles": rounded_miles(here, coords[s["slug"]])}
                    for s in placed
                ],
                "unranked": len(others) - len(placed),
            }
    by_name = sorted(others, key=lambda s: (s["name"], s["slug"]))
    for c in w["counties"]:
        same = [s for s in by_name if c in s["counties"]]
        if same:
            return {
                "basis": "county",
                "where": f"{c} County",
                "waters": [_row(s) for s in same],
                "unranked": 0,
            }
    same_region = [s for s in by_name if s["region"] == w["region"]]
    if same_region and region_name:
        return {
            "basis": "region",
            "where": f"the {region_name}",
            "waters": [_row(s) for s in same_region],
            "unranked": 0,
        }
    return None


def shortened(
    near: dict[str, Any] | None, limit: int, *, max_miles: int | None = None
) -> dict[str, Any] | None:
    """``near`` with at most ``limit`` waters, the rest counted in ``more``;
    with ``max_miles``, a distance match keeps only the waters within it.
    None when no water is left."""
    if near is None:
        return None
    waters = near["waters"]
    if max_miles is not None and near["basis"] == "distance":
        waters = [r for r in waters if r["miles"] <= max_miles]
    if not waters:
        return None
    return {**near, "waters": waters[:limit], "more": max(0, len(waters) - limit)}


def _listed_weeks(w: Mapping[str, Any]) -> list[str]:
    return sorted({p["week"]["start"] for p in w["plants"] if p["status"] == "listed"})


def last_season(
    w: Mapping[str, Any], *, source_week_start: str, recorded_since: str
) -> dict[str, Any] | None:
    """The weeks ``w`` was on the schedule in this week's calendar quarter a
    year ago: ``{"season", "label", "weeks"}``. ``weeks`` may be empty, which
    the page words as "not on the schedule in any week" -- a measured answer,
    because None is returned unless the record covers the whole quarter."""
    if not recorded_since:
        return None
    today = dt.date.fromisoformat(source_week_start)
    q = (today.month - 1) // 3
    year = today.year - 1
    start = dt.date(year, 3 * q + 1, 1)
    end = dt.date(year + (q == 3), (3 * q + 3) % 12 + 1, 1) - dt.timedelta(days=1)
    if dt.date.fromisoformat(recorded_since) > start:
        return None
    season, first, last = _QUARTERS[q]
    weeks = [d for d in _listed_weeks(w) if start.isoformat() <= d <= end.isoformat()]
    return {
        "season": season,
        "label": f"{first} through {last} {year}",
        "weeks": weeks,
    }


def water_answer(
    w: Mapping[str, Any], *, source_week_start: str
) -> dict[str, str] | None:
    """The one-sentence answer a water page opens with: this week, the next
    listed week, or the last one. None when the record has no listed week."""
    weeks = _listed_weeks(w)
    if source_week_start in weeks:
        return {"kind": "this_week", "week": source_week_start}
    later = [d for d in weeks if d > source_week_start]
    if later:
        return {"kind": "next", "week": later[0]}
    if weeks:
        return {"kind": "last", "week": weeks[-1]}
    return None


def county_answer(
    county: str,
    members: Sequence[Mapping[str, Any]],
    *,
    source_week_start: str,
) -> dict[str, Any]:
    """The facts a county page opens with (all from ``members``' listed weeks):

    - ``this_week``: the waters on this week's schedule, by name;
    - ``before``: for each of them, its previous listed week, if any;
    - ``latest_other``: the water not on this week's schedule that was listed
      most recently before it, with that week, or None;
    - ``city``: the water CDFW names "<county> City ..." (Fresno City Woodward
      Park Lake), shown by the rest of its name, with its last listed week
      through this week, when it is not on this week's schedule; or None.
    """
    this_week: list[dict[str, Any]] = []
    latest_other: dict[str, Any] | None = None
    for m in sorted(members, key=lambda m: (m["name"], m["slug"])):
        past = [d for d in _listed_weeks(m) if d < source_week_start]
        if source_week_start in _listed_weeks(m):
            this_week.append(
                {
                    "slug": m["slug"],
                    "name": m["name"],
                    "before": past[-1] if past else "",
                }
            )
        elif past and (latest_other is None or past[-1] > latest_other["week"]):
            latest_other = {"slug": m["slug"], "name": m["name"], "week": past[-1]}
    prefix = f"{county} City "
    city = None
    for m in members:
        weeks = _listed_weeks(m)
        through = [d for d in weeks if d <= source_week_start]
        if m["name"].startswith(prefix) and through and source_week_start not in weeks:
            city = {
                "slug": m["slug"],
                "name": m["name"][len(prefix) :],
                "week": through[-1],
            }
            break
    return {"this_week": this_week, "latest_other": latest_other, "city": city}


def week_count(
    this_week: Iterable[Mapping[str, Any]],
    waters_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    """How many distinct waters, and distinct counties among them, are on the
    current week's schedule. A water in two counties counts in both."""
    ids = {e["water_id"] for e in this_week}
    counties = {c for i in ids for c in waters_by_id[i]["counties"]}
    return {"waters": len(ids), "counties": len(counties)}
