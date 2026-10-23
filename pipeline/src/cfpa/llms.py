"""/llms.txt in the format llmstxt.org specifies (read 2026-10-22): an H1
with the site's name, a blockquote summary, plain text, then H2 sections that
are lists of ``[name](url): note`` links.

Plain facts from the snapshot the site is built from. Every state, agency,
file and feed listed here is one the build wrote; nothing is listed from
memory. A plant is "scheduled", never "stocked" or "confirmed", wherever the
source is a schedule.
"""

from __future__ import annotations

from typing import Any

SPEC_URL = "https://llmstxt.org/"

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


def render(
    *,
    site_name: str,
    base_url: str,
    attribution_text: str,
    states: list[dict[str, Any]],
    region_feeds: list[tuple[str, str]],
    week_label: str,
) -> str:
    """``states`` are site._open_data_states() entries (empty when the build
    has no v2 snapshot); ``region_feeds`` are (display name, feed URL)."""
    kinds = _names_by_kind(states)
    lines = [
        f"# {site_name}",
        "",
        f"> {_summary(kinds)}",
        "",
        _meaning(kinds),
        "",
        "Update cadence: the site is rebuilt once a day (13:17 UTC). California's "
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
