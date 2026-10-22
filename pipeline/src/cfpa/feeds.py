"""Atom 1.0 (RFC 4287) feeds of the current week's CDFW schedule.

One feed for the statewide week, one per CDFW region and one per county that
has a page: the same grouping the site's pages already use, so a feed always
matches a page a reader can open. Per-water feeds are not added; the water
pages already have a calendar (.ics) file, and a feed per water would repeat
it for the same single entry.

Everything in a feed comes from the snapshot, never from the clock:

* an entry's ``id`` is the water's permalink plus the week it is scheduled
  for, so the same listing keeps the same id on every rebuild and a new week
  is a new entry;
* an entry's ``updated`` is the earliest time the pipeline saw that listing
  (``first_observed_at``), not the build time and not ``last_observed_at``
  (which moves on every daily fetch and would mark every entry changed
  every day);
* the feed's ``updated`` is its newest entry's. An empty feed (a valid
  schedule with no plants this week) uses the week's own start date.

Wording follows the site: a plant is "scheduled", never "planted" or
"stocked", because CDFW's schedule is subject to change and this site cannot
confirm that one happened.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ATOM_NS = "http://www.w3.org/2005/Atom"
FEED_MEDIA_TYPE = "application/atom+xml"
FEEDS_DIR = "feeds"

ET.register_namespace("", ATOM_NS)


def _q(tag: str) -> str:
    return f"{{{ATOM_NS}}}{tag}"


@dataclass(frozen=True)
class FeedEntry:
    """One water scheduled for the current week."""

    water_id: str
    slug: str
    name: str
    counties: list[str]
    species: str
    updated: str  # RFC 3339, from first_observed_at


def current_week_entries(
    snapshot: dict[str, Any],
    *,
    species_phrase: Callable[[set[str]], str],
) -> list[FeedEntry]:
    """One entry per water listed for the snapshot's current week, sorted by
    name then slug. A water with two species that week is one entry."""
    week = snapshot["source_week"]["start"]
    entries: list[FeedEntry] = []
    for w in snapshot["waters"]:
        listed = [
            p
            for p in w["plants"]
            if p["status"] == "listed" and p["week"]["start"] == week
        ]
        if not listed:
            continue
        entries.append(
            FeedEntry(
                water_id=w["id"],
                slug=w["slug"],
                name=w["name"],
                counties=list(w["counties"]),
                species=species_phrase({p["species"] for p in listed}),
                updated=max(p["first_observed_at"] for p in listed),
            )
        )
    return sorted(entries, key=lambda e: (e.name, e.slug))


def feed_path(kind: str, slug: str = "") -> str:
    """Site-relative path of a feed: "feeds/this-week.atom",
    "feeds/region/<slug>.atom" or "feeds/county/<slug>.atom"."""
    if kind == "this-week":
        return f"{FEEDS_DIR}/this-week.atom"
    return f"{FEEDS_DIR}/{kind}/{slug}.atom"


def build_feed(
    *,
    entries: list[FeedEntry],
    base_url: str,
    path: str,
    title: str,
    subtitle: str,
    page_url: str,
    week_label: str,
    week_start: str,
    site_name: str,
    attribution_text: str,
) -> str:
    """Render one Atom document. ``week_label`` is the snapshot's own label
    ("week of ..."), ``week_start`` its ISO date."""
    feed = ET.Element(
        _q("feed"), {"{http://www.w3.org/XML/1998/namespace}lang": "en-US"}
    )
    self_url = f"{base_url}/{path}"
    ET.SubElement(feed, _q("id")).text = self_url
    ET.SubElement(feed, _q("title")).text = title
    ET.SubElement(feed, _q("subtitle")).text = subtitle
    ET.SubElement(feed, _q("updated")).text = (
        max(e.updated for e in entries) if entries else f"{week_start}T00:00:00Z"
    )
    ET.SubElement(
        feed, _q("link"), {"rel": "self", "type": FEED_MEDIA_TYPE, "href": self_url}
    )
    ET.SubElement(
        feed, _q("link"), {"rel": "alternate", "type": "text/html", "href": page_url}
    )
    author = ET.SubElement(feed, _q("author"))
    ET.SubElement(author, _q("name")).text = site_name
    ET.SubElement(author, _q("uri")).text = f"{base_url}/"
    ET.SubElement(feed, _q("rights")).text = (
        f"{attribution_text} "
        f"{site_name} is independent and is not affiliated with or endorsed by CDFW."
    )
    ET.SubElement(feed, _q("generator")).text = site_name
    for e in entries:
        permalink = f"{base_url}/water/{e.slug}/"
        item = ET.SubElement(feed, _q("entry"))
        ET.SubElement(item, _q("id")).text = f"{permalink}#{week_start}"
        ET.SubElement(
            item, _q("title")
        ).text = f"{e.name}: {e.species} scheduled, {week_label}"
        ET.SubElement(item, _q("link"), {"rel": "alternate", "href": permalink})
        ET.SubElement(item, _q("updated")).text = e.updated
        ET.SubElement(item, _q("summary"), {"type": "text"}).text = (
            f"CDFW's schedule lists {e.species} at {e.name} "
            f"({', '.join(e.counties)}) for the {week_label}. "
            "Scheduled, not confirmed: plants are subject to change. "
            "Source: California Department of Fish and Wildlife."
        )
    ET.indent(feed)
    body = ET.tostring(feed, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"
