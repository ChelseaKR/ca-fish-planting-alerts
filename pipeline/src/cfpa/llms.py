"""/llms.txt in the format llmstxt.org specifies (read 2026-10-22): an H1
with the site's name, a blockquote summary, plain text, then H2 sections that
are lists of ``[name](url): note`` links.

Plain facts from the snapshot the site is built from. Every state, agency,
file and feed listed here is one the build wrote; nothing is listed from
memory. A plant is "scheduled", never "stocked" or "confirmed", wherever the
source is a schedule.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

SPEC_URL = "https://llmstxt.org/"

# How an assistant should read a page: the words the pages use, in the
# pages' own sense. Every clause here is true of the templates (the status
# badge, "Last on the schedule", the "as of" line and the failed-check
# sentence); none is a claim about fish.
READING_NOTES = (
    'How to read a page: every date is written YYYY-MM-DD, and a "week of" '
    'date is the Sunday that begins the agency\'s week. "None scheduled yet" '
    "means the agency's schedule had nothing for that water as of the check "
    "time printed on the page; it is not a statement about whether fish are "
    'present. "Last on the schedule" is the most recent week the agency '
    "listed the water. A page whose latest check failed says so in its first "
    'paragraph and shows the data from the last good read. Quote the "as of" '
    "time with any status."
)

# What a state's source kind is called in the States section.
_HUB_KIND = {
    "schedule": "stocking schedule (planned dates the agency can change)",
    "report": "stocking report (stockings already made)",
    "plan": "seasonal stocking plan, in the agency's own words",
}

# What a state's source is, in the order the file lists it. "schedule" is a
# planned plant for a week or day; "report" is a stocking that already
# happened; "plan" is a seasonal plan in the agency's own words (New York,
# DECISIONS 0034). The kinds come from the snapshot, not from this file.
_KINDS = ("schedule", "report", "plan")
_KIND_PLURAL = {"schedule": "schedules", "report": "reports", "plan": "plans"}


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _names_by_kind(states: list[dict[str, Any]]) -> dict[str, list[str]]:
    """State names per source kind, in snapshot order. With no snapshot the
    only source is California's weekly schedule."""
    if not states:
        return {"schedule": ["California"]}
    out: dict[str, list[str]] = {}
    for s in states:
        out.setdefault(s["semantics"], []).append(s["name"])
    unknown = set(out) - set(_KINDS)
    if unknown:
        raise ValueError(f"unknown source semantics in the snapshot: {sorted(unknown)}")
    return out


def _summary(kinds: dict[str, list[str]]) -> str:
    present = [_KIND_PLURAL[k] for k in _KINDS if k in kinds]
    return (
        "Trout Truck is a free static website that mirrors state fish agencies' "
        f"published trout planting and stocking {_join(present)}, organized by "
        "water, county and region, with the history of every week this site has "
        "recorded. It shows what an agency published, not where a stocking truck "
        "is; a schedule or a plan is not a record that a plant happened. It is "
        "independent and not affiliated with any agency."
    )


def _meaning(kinds: dict[str, list[str]]) -> str:
    parts = []
    if "schedule" in kinds:
        parts.append(
            f"For a schedule source ({_join(kinds['schedule'])}) each record is a "
            "planned plant for a week or day, which the agency can change; the "
            'site says "scheduled", never "stocked" or "confirmed".'
        )
    if "report" in kinds:
        parts.append(
            f"For a report source ({_join(kinds['report'])}) the agency reports "
            "stockings that already happened and the site says so."
        )
    if "plan" in kinds:
        parts.append(
            f"For a plan source ({_join(kinds['plan'])}) the agency publishes a "
            'seasonal plan in its own words for when, such as "April - third '
            'week"; the site says "planned", never "scheduled", "stocked" or '
            '"confirmed".'
        )
    return (
        "What the data means: "
        + " ".join(parts)
        + " Dates are shown at the precision the agency gave; none is made finer."
    )


def _hub_line(h: dict[str, Any]) -> str:
    """One state hub: what the agency publishes, how many water pages, the URL
    pattern, and the data's age in the same words as the hub page. A failed
    latest check is said here too, so a reader of this file alone cannot
    take stale data for current."""
    seg = h["url"].rstrip("/").rsplit("/", 1)[-1]
    waters = f"{h['water_count']} water page" + ("" if h["water_count"] == 1 else "s")
    text = (
        f"- [{h['name']}]({h['url']}): {h['agency_name']} ({h['agency_short']}) "
        f"{_HUB_KIND[h['semantics']]}; {waters} under /{seg}/water/<name>/."
    )
    if h["manual"]:
        text += f" {h['manual_sentence']}"
    else:
        text += f" {h['agency_short']}'s data was last read {h['fetched_label']}."
        if h["attempt_failed"]:
            text += (
                f" The check on {h['attempt_label']} failed, so the pages show "
                "the data from the last good read."
            )
    return text


def render(
    *,
    site_name: str,
    base_url: str,
    attribution_text: str,
    states: list[dict[str, Any]],
    region_feeds: list[tuple[str, str]],
    week_label: str,
    fetched_label: str | None = None,
    state_hubs: Sequence[dict[str, Any]] = (),
    county_hubs: Sequence[dict[str, Any]] = (),
    ics_pattern: str | None = None,
) -> str:
    """``states`` are site._open_data_states() entries (empty when the build
    has no v2 snapshot); ``region_feeds`` are (display name, feed URL).

    ``fetched_label`` is when California's schedule was read, as the pages
    print it. ``state_hubs`` are the other states' hub pages (name, url,
    agency_name, agency_short, semantics, water_count, and the freshness
    words from site_states._freshness). ``county_hubs`` are California's
    county pages (name, url, count, feed_url). ``ics_pattern`` is the
    address pattern of a California water's calendar feed. Each list holds
    only what this build wrote."""
    kinds = _names_by_kind(states)
    lines = [
        f"# {site_name}",
        "",
        f"> {_summary(kinds)}",
        "",
        _meaning(kinds),
        "",
        "Update cadence: the site is rebuilt twice a day (13:17 and 01:17 UTC). California's "
        f"schedule is published weekly; the current week in this build is the {week_label}."
        + (
            ' Each state\'s "last successful check" date is on the open data page.'
            if states
            else ""
        ),
        "",
        f"How to cite: credit the agency as the source and name this site. {attribution_text} "
        f"Example: \"{site_name} ({base_url}/), mirroring the agency's schedule; check the "
        "agency's own page before you go.\"",
        "",
        "Some water pages carry disclosed affiliate links for fishing gear. They are "
        "labeled on the page and are never in the feeds.",
        "",
        READING_NOTES,
        *(
            [
                "",
                f"Data in this build: California's schedule was read {fetched_label}. "
                'Every page prints the read time its status is "as of"; that is '
                "the data's age, not the time the page was fetched."
                + (
                    " The other states' read times are in the States section below."
                    if state_hubs
                    else ""
                ),
            ]
            if fetched_label
            else []
        ),
        "",
        f"This file follows the llms.txt format described at {SPEC_URL}.",
        "",
        "## Pages",
        "",
        f"- [Home]({base_url}/): this week's California schedule",
        f"- [Counties]({base_url}/county/): every California county with a page; one page per water under /water/<name>/",
        f"- [About, attribution and privacy]({base_url}/about/): sources and license terms, quoted",
        *(
            [
                f"- [Other states]({base_url}/states/): states beyond California and what each agency publishes"
            ]
            if len(states) > 1
            else []
        ),
        f"- [Sitemap]({base_url}/sitemap.xml)",
        "",
        "## Feeds (Atom 1.0)",
        "",
        f"- [California this week]({base_url}/feeds/this-week.atom): waters on the agency's schedule for the current week; entry dates are when this site first saw the listing",
    ]
    for name, url in region_feeds:
        lines.append(f"- [{name}]({url}): the same, for one agency region")
    lines.append(
        f"- County feeds: {base_url}/feeds/county/<county>.atom, one per county page"
    )
    if ics_pattern:
        lines += [
            "",
            "## Calendar feeds (iCalendar)",
            "",
            f"- Every California water page has a calendar feed at {ics_pattern} "
            "(the same address works as webcal://): one all-day event for each "
            "week the agency scheduled the water, spanning the agency's week, "
            'worded "scheduled". Calendar apps refresh it about every 12 hours. '
            "The address is printed on each water page.",
        ]
    if state_hubs:
        lines += ["", "## States", ""]
        lines += [_hub_line(h) for h in state_hubs]
    if county_hubs:
        lines += ["", "## California counties", ""]
        for c in county_hubs:
            waters = f"{c['count']} water" + ("" if c["count"] == 1 else "s")
            lines.append(
                f"- [{c['name']}]({c['url']}): {waters} on the record; "
                f"Atom feed {c['feed_url']}"
            )
    if states:
        lines += ["", "## Sources and open data", ""]
        for s in states:
            lines.append(
                f"- [{s['agency']['name']}]({s['source_url']}): source for {s['name']} ({s['semantics']}); "
                f"terms: {s['terms_url']}"
            )
        lines.append(
            f"- [Open data page]({base_url}/data/): CSV and JSON files, current and history, with columns documented"
        )
        for s in states:
            for f in s["files"]:
                lines.append(
                    f"- [{s['code']} {f['kind']} ({f['fmt'].upper()})]({f['url']}): {f['records']} records"
                )
    lines.append("")
    return "\n".join(lines)
