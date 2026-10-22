"""A permanent page for each past week on record (/week/YYYY-MM-DD/) and an
index of them (/week/), built from the snapshot's plants and nothing else
(DECISIONS 0038).

A week gets a page when CDFW's schedule listed at least one water for it and
the week is over (it starts before the snapshot's current week). The current
week is the home page; a week after it can still change and has no page here.
Entries with status "removed" are never shown. A week with fewer than
``WEEK_INDEX_MIN_WATERS`` waters keeps its page but is noindex,follow and out
of the sitemap. Kept in its own module so the
change to ``site.py`` stays a few additive lines.

Nothing on a week page depends on the day it was built: no "last checked"
line, no count of days. A past week's page changes only when its own entries
do, and its sitemap lastmod says when that was.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import jinja2

from .snapshot import week_of

TITLE_MAX = 60
DESCRIPTION_MAX = 155
# A week with fewer listed waters than this still has a page and is linked from
# /week/, but carries a robots noindex,follow tag and is left out of the
# sitemap (owner decision 2026-10-22; DECISIONS 0038).
WEEK_INDEX_MIN_WATERS = 8


def week_entries(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Past weeks with at least one listed water: week start -> waters.

    Each water is ``{"water": <snapshot water>, "species": {...}}``, sorted by
    name then slug. A week at or after the snapshot's current week is left
    out, as is every plant whose status is not "listed"."""
    current = snapshot["source_week"]["start"]
    found: dict[str, dict[str, dict[str, Any]]] = {}
    for w in snapshot["waters"]:
        for p in w["plants"]:
            start = p["week"]["start"]
            if p["status"] != "listed" or start >= current:
                continue
            entry = found.setdefault(start, {}).setdefault(
                w["slug"], {"water": w, "species": set()}
            )
            entry["species"].add(p["species"])
    return {
        start: sorted(
            by_slug.values(), key=lambda e: (e["water"]["name"], e["water"]["slug"])
        )
        for start, by_slug in found.items()
    }


def week_lastmod(snapshot: dict[str, Any], start: str) -> str:
    """When this week's page last changed in substance: the newest date any of
    its plants was first listed, or was marked removed. It never moves just
    because the site was rebuilt."""
    dates: list[str] = []
    for w in snapshot["waters"]:
        for p in w["plants"]:
            if p["week"]["start"] != start:
                continue
            dates.append(p["first_observed_at"][:10])
            if p["status"] == "removed":
                dates.append(p["last_observed_at"][:10])
    return max(dates)


def week_title(start: str, site_name: str) -> str:
    return f"CDFW planting schedule, week of {start} | {site_name}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def week_description(start: str, n: int) -> str:
    return (
        f"CDFW's planting schedule listed {_plural(n, 'water', 'waters')} for the week of "
        f"{start}, by county. Scheduled, not confirmed; subject to change."
    )


def _by_county(
    entries: list[dict[str, Any]],
    *,
    county_slug: Callable[[str], str],
    species_phrase: Callable[[set[str]], str],
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        w = e["water"]
        for c in w["counties"] or [""]:
            groups.setdefault(c, []).append(
                {
                    "slug": w["slug"],
                    "name": w["name"],
                    "species": species_phrase(e["species"]),
                }
            )
    return [
        {"name": c, "slug": county_slug(c) if c else "", "rows": groups[c]}
        for c in sorted(groups, key=lambda c: (c == "", c))
    ]


def render_weeks(
    *,
    env: jinja2.Environment,
    out_dir: Any,
    written: list[Any],
    base_url: str,
    common: dict[str, Any],
    site_name: str,
    snapshot: dict[str, Any],
    county_slug: Callable[[str], str],
    species_phrase: Callable[[set[str]], str],
    write_page: Callable[..., None],
    ld_graph: Callable[..., dict[str, Any]],
    ld_breadcrumb: Callable[..., dict[str, Any]],
    ld_page: Callable[..., dict[str, Any]],
    relative_trail: Callable[..., list[tuple[str, str]]],
) -> list[tuple[str, str | None]]:
    """Write /week/ and one page per past week with a listing. Returns the
    sitemap entries; with no such week, writes nothing and returns []."""
    weeks = week_entries(snapshot)
    if not weeks:
        return []
    about = {"@type": "State", "name": "California"}
    home = (site_name, f"{base_url}/")
    index_url = f"{base_url}/week/"
    index_crumb = ("Weeks", index_url)
    ordered = sorted(weeks, reverse=True)
    lastmods = {s: week_lastmod(snapshot, s) for s in ordered}
    entries: list[tuple[str, str | None]] = []

    for start in ordered:
        n = len(weeks[start])
        thin = n < WEEK_INDEX_MIN_WATERS
        url = f"{index_url}{start}/"
        trail = [home, index_crumb, (f"Week of {start}", url)]
        title = week_title(start, site_name)
        html = env.get_template("week.html.jinja").render(
            title=title,
            description=week_description(start, n),
            canonical_url=url,
            noindex=thin,
            noindex_follow=thin,
            root="../../",
            **common,
            structured_data=ld_graph(
                ld_page(
                    "CollectionPage",
                    page_url=url,
                    name=title,
                    base_url=base_url,
                    about=about,
                ),
                ld_breadcrumb(url, trail),
            ),
            breadcrumb=relative_trail(trail, base_url=base_url, root="../../"),
            week_start=start,
            week_end=week_of(dt.date.fromisoformat(start))["end"],
            water_count=n,
            counties=_by_county(
                weeks[start], county_slug=county_slug, species_phrase=species_phrase
            ),
        )
        write_page(out_dir, f"week/{start}", html, written)
        if not thin:
            entries.append((url, lastmods[start]))

    # The index changes when a week joins it: the day the week became a past
    # week (the Sunday after it began) or when its entries last changed.
    index_lastmod = max(
        max(
            lastmods[s],
            (dt.date.fromisoformat(s) + dt.timedelta(days=7)).isoformat(),
        )
        for s in ordered
    )
    trail = [home, index_crumb]
    title = f"CDFW planting schedule by week | {site_name}"
    description = (
        "Past weeks of California's CDFW planting schedule on record here, "
        "most recent to oldest, with the number of waters CDFW listed for each week."
    )
    html = env.get_template("week_index.html.jinja").render(
        title=title,
        description=description,
        canonical_url=index_url,
        root="../",
        **common,
        structured_data=ld_graph(
            ld_page(
                "CollectionPage",
                page_url=index_url,
                name=title,
                base_url=base_url,
                about=about,
            ),
            ld_breadcrumb(index_url, trail),
        ),
        breadcrumb=relative_trail(trail, base_url=base_url, root="../"),
        week_rows=[{"start": s, "count": len(weeks[s])} for s in ordered],
    )
    write_page(out_dir, "week", html, written)
    entries.insert(0, (index_url, index_lastmod))
    return entries
