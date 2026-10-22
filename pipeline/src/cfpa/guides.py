"""Plain informational pages under /guide/ (DECISIONS 0031).

Each guide explains something about the schedule that the site already
shows, and every claim in one is either computed here from the snapshot or
quoted from a CDFW page that was fetched and read on ``CDFW_READ_ON``. A claim
with neither is not written. There are no product recommendations and no
outbound affiliate links on these pages.

Kept in its own module so the change to ``site.py`` stays a few additive
lines: one call, one sitemap extension.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jinja2

# The day the CDFW pages cited in the guide templates were fetched and read.
# Shown on every guide that cites them; change it only after re-reading them.
CDFW_READ_ON = "2026-10-21"

CDFW_SCHEDULE_URL = "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch"
CDFW_CRITERIA_URL = "https://www.wildlife.ca.gov/Fishing/Hatcheries/Criteria"


@dataclass(frozen=True)
class Guide:
    slug: str
    template: str
    title: str  # the browser title, including the site name
    h1: str
    crumb: str  # the short name in the breadcrumb
    description: str
    summary: str  # one line on the /guide/ index


GUIDES: tuple[Guide, ...] = (
    Guide(
        slug="how-to-read-the-schedule",
        crumb="How to read the schedule",
        template="guide_how_to_read.html.jinja",
        title="How to read CDFW's trout planting schedule | {site}",
        h1="How to read California's trout planting schedule",
        description=(
            "What the weeks, waters, counties and CDFW regions on California's "
            "fish planting schedule mean, and what a blank week does and does "
            "not tell you."
        ),
        summary="Weeks, waters, counties and regions, and what a blank week means.",
    ),
    Guide(
        slug="scheduled-vs-confirmed",
        crumb="Scheduled vs. confirmed",
        template="guide_scheduled_vs_confirmed.html.jinja",
        title="Scheduled vs. confirmed trout planting | {site}",
        h1="Scheduled vs. confirmed: what a planting schedule can promise",
        description=(
            "Why every entry on California's trout planting schedule is "
            "scheduled, not confirmed, what can change a plant, and what this "
            "site can and cannot tell you."
        ),
        summary="Why every entry is scheduled, not confirmed, and what can change.",
    ),
    Guide(
        slug="what-is-a-trout-plant",
        crumb="What is a trout plant?",
        template="guide_what_is_a_plant.html.jinja",
        title="What is a trout plant? CDFW stocking explained | {site}",
        h1="What is a trout plant?",
        description=(
            "A trout plant is a scheduled delivery of catchable-size hatchery "
            "fish to a California water. The temperature and flow limits CDFW "
            "sets for stocking."
        ),
        summary="What a plant is, and the temperature and flow limits CDFW sets.",
    ),
)


def guide_facts(snapshot: dict[str, Any], *, recorded_since: str) -> dict[str, Any]:
    """Counts the guides state, taken from the snapshot and nothing else."""
    entries = [p for w in snapshot["waters"] for p in w["plants"]]
    removed = sum(1 for p in entries if p["status"] != "listed")
    return {
        "water_count": len(snapshot["waters"]),
        "plant_entries": len(entries),
        "removed_entries": removed,
        "recorded_since_label": f"week of {recorded_since}" if recorded_since else "",
    }


def render_guides(
    *,
    env: jinja2.Environment,
    out_dir: Any,
    written: list[Any],
    base_url: str,
    common: dict[str, Any],
    site_name: str,
    facts: dict[str, Any],
    region_links: list[dict[str, Any]],
    county_counts: list[dict[str, Any]],
    source_week_label: str,
    source_fetched_label: str,
    write_page: Callable[..., None],
    ld_graph: Callable[..., dict[str, Any]],
    ld_breadcrumb: Callable[..., dict[str, Any]],
    ld_page: Callable[..., dict[str, Any]],
    relative_trail: Callable[..., list[tuple[str, str]]],
) -> list[tuple[str, str | None]]:
    """Write /guide/ and one page per guide. Returns sitemap entries."""
    home = (site_name, f"{base_url}/")
    index_url = f"{base_url}/guide/"
    index_crumb = ("Guides", index_url)
    about = {"@type": "State", "name": "California"}
    entries: list[tuple[str, str | None]] = []
    page_common = {
        **common,
        **facts,
        "region_links": region_links,
        "county_counts": county_counts,
        "source_week_label": source_week_label,
        "source_fetched_label": source_fetched_label,
        "cdfw_read_on": CDFW_READ_ON,
        "cdfw_schedule_url": CDFW_SCHEDULE_URL,
        "cdfw_criteria_url": CDFW_CRITERIA_URL,
        "guides": GUIDES,
    }

    trail = [home, index_crumb]
    title = f"Guides to the California trout planting schedule | {site_name}"
    html = env.get_template("guide_index.html.jinja").render(
        title=title,
        description=(
            "Plain explanations of California's trout planting schedule: how "
            "to read it, what scheduled means, and what a plant is, with the "
            "CDFW pages each rests on."
        ),
        canonical_url=index_url,
        root="../",
        **page_common,
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
    )
    write_page(out_dir, "guide", html, written)
    entries.append((index_url, None))

    for g in GUIDES:
        url = f"{index_url}{g.slug}/"
        trail = [home, index_crumb, (g.crumb, url)]
        page_title = g.title.format(site=site_name)
        html = env.get_template(g.template).render(
            title=page_title,
            description=g.description,
            canonical_url=url,
            root="../../",
            **page_common,
            guide=g,
            structured_data=ld_graph(
                ld_page(
                    "WebPage",
                    page_url=url,
                    name=page_title,
                    base_url=base_url,
                    about=about,
                ),
                ld_breadcrumb(url, trail),
            ),
            breadcrumb=relative_trail(trail, base_url=base_url, root="../../"),
        )
        write_page(out_dir, f"guide/{g.slug}", html, written)
        entries.append((url, None))
    return entries
