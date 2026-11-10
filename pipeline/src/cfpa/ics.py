"""iCalendar (RFC 5545) helpers, and the calendar feed of a schedule state's
water (DECISIONS 0064).

California's feed is ``site.build_water_ics``. It has the same escaping,
folding, PRODID and refresh interval as this module; they are kept equal by
test (``test_site_tn_calendar_feeds``) rather than by import for now, so the
open California water-page pull requests merge clean, and ``site.py`` can
switch to these helpers after they land. This module adds the same kind of
feed for a state whose agency publishes a forward schedule (Tennessee),
honest about the three shapes TWRA gives a date:

- a **day** is one all-day event on that day;
- a **week** ("week of" a Sunday) is one all-day event spanning the agency's
  whole week, titled "Week of <Sunday>: <water> stocking scheduled (<agency>)",
  so no day inside it is ever singled out;
- a **month** ("TBD 12/2027") is **no event**: the agency set no day or week,
  and a month-long block or a guessed day would render that absence as a
  date. It is named in words instead, in the calendar's description and in
  the description of the nearest dated event ("TBD in December 2027 per
  TWRA");
- the agency's **month letters** ("M, A, M, J, J, A, S", not dates) are never
  events either, only a sentence in the calendar's description.

Every event says whose schedule it is, that it is scheduled and not
confirmed, where the data came from (and, for a hand-loaded file, DECISIONS
0061, the download date), and links the water page. A calendar event is a
calendar event: nothing here calls it an alert or a notification.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# How often a subscribed calendar should poll a feed. The publish workflow
# runs twice a day (.github/workflows/publish.yml, 13:17 and 01:17 UTC), so a
# 12-hour poll matches it: a calendar shows a change within about half a day
# of the site having it, at two small requests a day per subscriber. RFC 7986
# REFRESH-INTERVAL for current clients, X-PUBLISHED-TTL for Outlook and older
# Apple clients.
REFRESH_INTERVAL = "PT12H"
# Pinned: a calendar app keys the feed's events on UID, and some on PRODID
# too, so a change here would duplicate events in people's calendars.
PRODID = "-//ca-fish-planting-alerts//snapshot v1//EN"
UID_DOMAIN = "ca-fish-planting-alerts.invalid"

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def escape(text: str) -> str:
    """RFC 5545 §3.3.11 TEXT escaping."""
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """RFC 5545 §3.1: fold a content line longer than 75 octets; each
    continuation line starts with one space, which counts toward its 75, and
    a multi-byte character is never split (``site._ics_fold`` lets a
    continuation run to 76 octets and splits on bytes; the strict reader in
    the tests holds this one to the RFC)."""
    if len(line.encode("utf-8")) <= 75:
        return line
    out: list[str] = []
    cur = ""
    limit = 75
    for ch in line:
        if len((cur + ch).encode("utf-8")) > limit:
            out.append(cur)
            cur = ch
            limit = 74
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def header(*, name: str, description: str) -> list[str]:
    """The VCALENDAR header every feed of this site starts with."""
    return [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        f"REFRESH-INTERVAL;VALUE=DURATION:{REFRESH_INTERVAL}",
        f"X-PUBLISHED-TTL:{REFRESH_INTERVAL}",
        f"X-WR-CALNAME:{escape(name)}",
        f"X-WR-CALDESC:{escape(description)}",
    ]


def render(lines: list[str]) -> str:
    """One document: CRLF line endings, every line folded."""
    return "\r\n".join(fold(line) for line in [*lines, "END:VCALENDAR"]) + "\r\n"


def _stamp(iso_z: str) -> str:
    return iso_z.replace("-", "").replace(":", "")


def _long_date(d: dt.date) -> str:
    return f"{d.strftime('%A')}, {_MONTHS[d.month - 1]} {d.day}, {d.year}"


def _month_name(start: str) -> str:
    d = dt.date.fromisoformat(start)
    return f"{_MONTHS[d.month - 1]} {d.year}"


def _join(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _where(water: dict[str, Any], state: dict[str, Any]) -> str:
    if water["counties"]:
        return f" ({', '.join(water['counties'])} County, {state['name']})"
    if water["towns"]:
        return f" ({', '.join(water['towns'])}, {state['name']})"
    return f" ({state['name']})"


def _provenance(state: dict[str, Any]) -> str:
    """Where the data came from, as the pages say it (DECISIONS 0061): a
    hand-loaded published file names its download date; the automated read
    names the date it was read."""
    short = state["agency"]["short_name"]
    if state["source"].get("read_method") == "manual":
        return f"from {short}'s published schedule file, downloaded {state['as_of']}"
    return f"from {short}'s published schedule, read {state['as_of']}"


def _dated(plants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The listed day and week records, grouped by period: one event per
    date the agency gave, every species for it in one line."""
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for p in plants:
        per = p["period"]
        if p["status"] != "listed" or per["precision"] not in ("day", "week"):
            continue
        key = (per["start"], per["end"], per["precision"])
        g = groups.setdefault(
            key,
            {
                "start": dt.date.fromisoformat(per["start"]),
                "end": dt.date.fromisoformat(per["end"]),
                "precision": per["precision"],
                "species": [],
                "stamp": p["last_observed_at"],
            },
        )
        if p["species"] not in g["species"]:
            g["species"].append(p["species"])
        g["stamp"] = max(g["stamp"], p["last_observed_at"])
    for g in groups.values():
        g["species"].sort()
    return [groups[k] for k in sorted(groups)]


def _tbd_months(plants: list[dict[str, Any]]) -> list[str]:
    """The months the agency listed with no day set ("TBD 12/2027"), as
    "December 2027", oldest first. Never an event."""
    starts = sorted(
        {
            p["period"]["start"]
            for p in plants
            if p["status"] == "listed" and p["period"]["precision"] == "month"
        }
    )
    return [_month_name(s) for s in starts]


def _nearest(events: list[dict[str, Any]], month_start: dt.date) -> int | None:
    """Index of the dated event closest to the month's first day; the earlier
    one on a tie. None with no dated event."""
    if not events:
        return None
    return min(
        range(len(events)),
        key=lambda i: (abs((events[i]["start"] - month_start).days), i),
    )


def build_schedule_ics(
    *,
    water: dict[str, Any],
    state: dict[str, Any],
    page_url: str,
    species: str,
) -> str:
    """The calendar feed of one water of a schedule state (a v2 snapshot's
    water and state entries). ``species`` is the page's word ("trout" or
    "fish"), so the calendar's name and the page agree."""
    short = state["agency"]["short_name"]
    long_name = state["agency"]["name"]
    where = _where(water, state)
    provenance = _provenance(state)
    tbd = _tbd_months(water["plants"])
    events = _dated(water["plants"])
    independent = f"Trout Truck is independent and is not endorsed by {short}."

    caldesc = [
        f"{short}'s scheduled stocking dates for {water['name']}{where}, "
        f"{provenance}. A day is an all-day event; a week-of date is one event "
        f"spanning {short}'s whole week, starting on its Sunday. Scheduled, "
        f"not confirmed: {short} says any stocking could be postponed or "
        "cancelled."
    ]
    if tbd:
        caldesc.append(
            f"TBD in {_join(tbd)} per {short}: no day or week set yet, so no "
            "event for it."
        )
    if water.get("months_note"):
        caldesc.append(
            f"{short} also lists this water by month letters "
            f"({water['months_note']}), which are not dates and are not events."
        )
    caldesc.append(independent)
    lines = header(
        name=f"{water['name']} {species} stocking schedule ({short})",
        description=" ".join(caldesc),
    )

    notes: dict[int, list[str]] = {}
    for month in tbd:
        first = dt.date(int(month[-4:]), _MONTHS.index(month[:-5]) + 1, 1)
        i = _nearest(events, first)
        if i is not None:
            notes.setdefault(i, []).append(month)

    for i, e in enumerate(events):
        start: dt.date = e["start"]
        end_exclusive: dt.date = e["end"] + dt.timedelta(days=1)
        species_list = _join(e["species"])
        if e["precision"] == "week":
            summary = (
                f"Week of {start.isoformat()}: {water['name']} stocking "
                f"scheduled ({short})"
            )
            when = (
                f"the week of {_long_date(start)}. {short} says a week-of "
                "stocking falls within five days after that Sunday"
            )
        else:
            summary = f"{water['name']} stocking scheduled ({short})"
            when = _long_date(start)
        description = (
            f"{short}'s published stocking schedule lists {species_list} at "
            f"{water['name']} for {when}. Scheduled, not confirmed: {short} says "
            "any stocking could be postponed or cancelled."
        )
        if i in notes:
            description += (
                f" Also TBD in {_join(notes[i])} per {short}: no day or week "
                "set yet, so it is not an event here."
            )
        description += (
            f" Data: {long_name} ({short}), {provenance}. {independent} {page_url}"
        )
        uid = f"{water['id']}-{start.isoformat()}-{e['precision']}@{UID_DOMAIN}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_stamp(e['stamp'])}",
            f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_exclusive.strftime('%Y%m%d')}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{escape(description)}",
            f"URL:{page_url}",
            "END:VEVENT",
        ]
    return render(lines)


def has_feed(state: dict[str, Any]) -> bool:
    """Whether a state's water pages get a calendar feed: a forward schedule
    with days or weeks (Tennessee). A report of past stockings (Massachusetts,
    Michigan) and a once-a-year plan in the agency's own words (New York) do
    not, each for its own reason (DECISIONS 0064)."""
    return bool(state["semantics"] == "schedule" and state["code"] != "CA")


__all__ = [
    "PRODID",
    "REFRESH_INTERVAL",
    "UID_DOMAIN",
    "build_schedule_ics",
    "escape",
    "fold",
    "has_feed",
    "header",
    "render",
]
