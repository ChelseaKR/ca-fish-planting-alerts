"""The site's pages for states other than California (DECISIONS 0025).

Every California URL stays where it was. Each other state gets
``/<code>/`` (its hub: this week, what is coming or what was recently
stocked, and every water) and ``/<code>/water/<slug>/`` (one water's
history), plus one ``/states/`` index. All of it is built from
``snapshot/v2.json`` and nothing else.

The words follow each state's source:

- a **schedule** (California, Tennessee) says "scheduled", and a plant the
  agency dropped says "schedule changed";
- a **report** (Massachusetts, Michigan) says "stocked", because the agency
  reports stockings that happened, and shows how recent its newest record
  is, because Michigan's lag by weeks;
- a **plan** (New York, DECISIONS 0034) says "planned", never "scheduled"
  and never "stocked": a once-a-year plan in the agency's own words.

Every period is shown at the precision the agency gave: a day, the week of a
Sunday, a month, or the agency's own words ("April - third week"). Never
finer. "Stocking" is the word in every title, which is also each agency's
own word outside California.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jinja2

from . import state_coverage
from .states import SOURCES

UPCOMING_DAYS = 60
RECENT_DAYS = 45
# The example of an agency's own words shown on a plan state's pages.
APPROXIMATE_EXAMPLE = "April - third week"


@dataclasses.dataclass(frozen=True)
class StatesContext:
    env: jinja2.Environment
    out_dir: Path
    written: list[Path]
    base_url: str
    common: dict[str, Any]
    site_name: str
    write_page: Any  # site._write_page
    ld_graph: Any
    ld_breadcrumb: Any
    ld_page: Any
    relative_trail: Any
    # How much of a title a results page shows (site.WATER_TITLE_MAX), brand
    # included. Passed in because site.py imports this module.
    title_max: int = 60
    # The Amazon gear block (DECISIONS 0039): site.gear_links(),
    # site.AFFILIATE_LINK_REL and site.gear_endorsement, passed in for the
    # same reason. With no links, no state page carries the block.
    gear_links: tuple[dict[str, str], ...] = ()
    affiliate_rel: str = ""
    gear_endorsement: Callable[[str], str] | None = None


def gear_allowed(state: dict[str, Any], species: str) -> bool:
    """Whether a state's water page may carry the Amazon gear block
    (DECISIONS 0039): every license source the state's data comes from says
    commercial reuse is permitted, and the water's species word is trout, the
    only gear the block offers. Anything else, including a missing license
    list or an "unknown" answer, keeps the page free of affiliate links."""
    sources = state.get("license", {}).get("sources", [])
    if not sources:
        return False
    if any(s.get("commercial_reuse") != "permitted" for s in sources):
        return False
    return "trout" in species.lower()


def when_label(period: dict[str, str]) -> str:
    """The period as the agency gave it. A month says the day is not set."""
    if period["precision"] == "month":
        return f"{period['label']} (day not set yet)"
    return period["label"]


def words(state: dict[str, Any]) -> dict[str, str]:
    """A schedule's words, or a plan's (New York, DECISIONS 0034): a plan is
    "planned", never "scheduled", and never a confirmed stocking."""
    if state["semantics"] == "plan":
        return {"kind": "plan", "verb": "planned", "Verb": "Planned"}
    return {"kind": "schedule", "verb": "scheduled", "Verb": "Scheduled"}


def status_label(status: str, semantics: str = "schedule") -> str:
    if status == "listed" and semantics == "plan":
        return "Planned"
    return {
        "listed": "Scheduled",
        "removed": "Schedule changed",
        "reported": "Stocked",
    }[status]


def place_phrase(
    w: dict[str, Any],
    state_name: str,
    region_name: str = "",
    with_towns: bool = False,
) -> str:
    """Where a water is: its counties, else its towns, else the agency's
    region. ``with_towns`` puts the agency's town before the county
    ("North Elba, Essex County, New York"), for a water whose name and
    county another water of the state shares: New York lists a river once
    per town section, and the town is what tells those pages apart (it is
    also in each one's URL)."""
    if w["counties"]:
        cs = w["counties"]
        county = (
            f"{cs[0]} County"
            if len(cs) == 1
            else f"{', '.join(cs[:-1])} and {cs[-1]} counties"
        )
        if with_towns and w["towns"]:
            return f"{', '.join(w['towns'])}, {county}, {state_name}"
        return f"{county}, {state_name}"
    if w["towns"]:
        return f"{', '.join(w['towns'])}, {state_name}"
    if region_name:
        return f"{region_name}, {state_name}"
    return state_name


def short_place_phrase(
    w: dict[str, Any],
    state: dict[str, Any],
    region_name: str = "",
    with_towns: bool = False,
) -> str:
    """``place_phrase`` with the state's postal code in place of its name:
    "Monroe County, TN". Only for a title that would not fit otherwise; the
    h1, description and structured data keep the name."""
    return place_phrase(w, state["code"], region_name, with_towns)


def shared_names(waters: list[dict[str, Any]]) -> set[tuple[str, tuple[str, ...]]]:
    """The (name, counties) pairs more than one of a state's waters has. A
    water in one of them names its towns in its title, h1 and description
    (``place_phrase(with_towns=True)``), so no two pages share a title."""
    seen: dict[tuple[str, tuple[str, ...]], int] = {}
    for w in waters:
        key = (w["name"], tuple(w["counties"]))
        seen[key] = seen.get(key, 0) + 1
    return {k for k, n in seen.items() if n > 1}


def qualifiers(
    keys: dict[str, tuple[str, ...]], waters: list[dict[str, Any]]
) -> dict[str, str]:
    """A short, stable qualifier for each water whose title would still match
    another's after the town rule (``keys``: water id -> what its title is
    made of). The agency's own water ID when every water in the clash has a
    different one, else the water's stable id ("ny-essex-jay-foo-creek").
    Empty for every other water, which is all of them on today's data."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for w in waters:
        groups.setdefault(keys[w["id"]], []).append(w)
    out: dict[str, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        ids = [w["source_id"] for w in group]
        use_source = all(ids) and len(set(ids)) == len(ids)
        for w in group:
            out[w["id"]] = f"water ID {w['source_id']}" if use_source else w["id"]
    return out


def warn_titles(heading: str, lines: list[str]) -> None:
    """A loud stderr warning (and a ``::warning`` under GitHub Actions) that
    titles had to be told apart by a fallback. It never fails the build: a
    repeated title must not stop the daily publish (owner decision
    2026-10-29)."""
    print(f"cfpa: WARNING {heading}:", file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Repeated page titles::{heading}: {'; '.join(lines)}")


def fit_title(candidates: list[str], site_name: str, limit: int) -> str:
    """The first candidate whose whole title, " | <site name>" included, is
    within ``limit`` characters, else the last (shortest). A title never drops
    the water's name to get under the limit, so the last may still run over."""
    full = [f"{c} | {site_name}" for c in candidates]
    return next((t for t in full if len(t) <= limit), full[-1])


def _fmt_dt(iso_z: str) -> str:
    d = dt.datetime.fromisoformat(iso_z.replace("Z", "+00:00"))
    return d.strftime("%Y-%m-%d %H:%M UTC")


def _species_word(plants: list[dict[str, Any]], default: str = "fish") -> str:
    """ "trout" when every species is a trout, else "fish". A water with no
    dated record takes its state's word (``default``)."""
    names = {p["species"].lower() for p in plants}
    if not names:
        return default
    return "trout" if all("trout" in n for n in names) else "fish"


def _water_lastmod(w: dict[str, Any], state: dict[str, Any]) -> str:
    dates = [p["first_observed_at"][:10] for p in w["plants"]]
    dates += [
        p["last_observed_at"][:10] for p in w["plants"] if p["status"] == "removed"
    ]
    # A water listed only by month letters: when the source was last read.
    fetched: str = state["source"]["fetched_at"][:10]
    return max(dates, default=fetched)


def _place(w: dict[str, Any], state: dict[str, Any]) -> str:
    """Counties, else towns, else the agency's region (Oregon gives a zone
    and no county). A state that gives counties renders exactly as before."""
    named = w["counties"] or w["towns"]
    if named:
        return ", ".join(named)
    names = {r["code"]: r["name"] for r in state["regions"]}
    return str(names.get(w["region"] or "", ""))


def _precision_phrase(state: dict[str, Any]) -> str:
    """'the week starting on a Monday' for a state that gives only weeks;
    'its own words, such as "April - third week"' for New York's plan."""
    week = SOURCES[state["code"]].week_phrase
    words = {
        "day": "a day",
        "week": week,
        "month": "a month",
        "approximate": f'its own words, such as "{APPROXIMATE_EXAMPLE}"',
    }
    parts = [
        words[p]
        for p in ("day", "week", "month", "approximate")
        if p in state["date_precisions"]
    ]
    if len(parts) < 3:
        return " or ".join(parts)
    return f"{parts[0]}, {parts[1]}, or {parts[2]}"


def _row(w: dict[str, Any], p: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": w["slug"],
        "name": w["name"],
        "place": _place(w, state),
        "when": when_label(p["period"]),
        "start": p["period"]["start"],
        "species": p["species"],
        "count": p["count"],
        "status": status_label(p["status"], state["semantics"]),
    }


def _build_date(state: dict[str, Any], generated_at: str) -> dt.date:
    """The civil date the snapshot was built, in the state's time zone. This,
    not the date of the last good fetch, is what "now" means on a page: after
    a failed check the data is older than the calendar."""
    when = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    return when.astimezone(ZoneInfo(SOURCES[state["code"]].time_zone)).date()


def _date_range_label(waters: list[dict[str, Any]]) -> str:
    """The span of the dated records on file ("2026-02-22 to 2026-12-24"), or
    "" when there is none. Month-precision records have no day, so they stay
    out of the span."""
    periods = [
        p["period"]
        for w in waters
        for p in w["plants"]
        if p["period"]["precision"] != "month"
    ]
    if not periods:
        return ""
    return f"{min(p['start'] for p in periods)} to {max(p['end'] for p in periods)}"


def _hub_sections(
    state: dict[str, Any], waters: list[dict[str, Any]], today: dt.date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(this week, coming up) for a schedule state; (this week, recent) for a
    report state. Month-precision plants are never "this week"."""
    week = state["current_week"]
    this_week, other = [], []
    for w in waters:
        for p in w["plants"]:
            per = p["period"]
            if p["status"] == "removed":
                continue
            in_week = (
                per["precision"] not in ("month", "approximate")
                and per["start"] <= week["end"]
                and per["end"] >= week["start"]
            )
            if in_week:
                this_week.append(_row(w, p, state))
                continue
            start = dt.date.fromisoformat(per["start"])
            if state["semantics"] in ("schedule", "plan"):
                if today < start <= today + dt.timedelta(days=UPCOMING_DAYS):
                    other.append(_row(w, p, state))
            elif today - dt.timedelta(days=RECENT_DAYS) <= start <= today:
                other.append(_row(w, p, state))
    this_week.sort(key=lambda r: (r["start"], r["name"]))
    other.sort(
        key=lambda r: (r["start"], r["name"]),
        reverse=state["semantics"] == "report",
    )
    return this_week, other


def _state_common(
    ctx: StatesContext, state: dict[str, Any], root: str
) -> dict[str, Any]:
    seg = state["code"].lower()
    endorsement = (
        ctx.gear_endorsement(state["agency"]["short_name"])
        if ctx.gear_endorsement is not None
        else ""
    )
    return {
        **ctx.common,
        # The gear block names the agency whose data the page shows, never CDFW.
        "gear_endorsement": endorsement,
        "attribution_text": state["attribution"]["text"],
        "attribution_url": state["attribution"]["url"],
        "footer_disclaimer": state["disclaimer"],
        "header_tagline": f"{state['name']} trout stocking",
        "nav_links": [
            (f"{state['name']} this week", f"{root}{seg}/"),
            ("All states", f"{root}states/"),
            ("About & privacy", f"{root}about/"),
        ],
    }


def render_states(
    ctx: StatesContext, snap_v2: dict[str, Any] | None
) -> list[tuple[str, str | None]]:
    """Write every non-California page and /states/. Returns sitemap entries
    (url, lastmod). Writes nothing without v2 or when it has California alone."""
    if snap_v2 is None:
        return []
    others = [s for s in snap_v2["states"] if s["code"] != "CA"]
    if not others:
        return []
    by_state: dict[str, list[dict[str, Any]]] = {}
    for w in snap_v2["waters"]:
        by_state.setdefault(w["state"], []).append(w)

    entries: list[tuple[str, str | None]] = []
    hub_lastmods: dict[str, str] = {}
    for state in others:
        waters = sorted(by_state[state["code"]], key=lambda w: (w["name"], w["slug"]))
        lastmods = {w["id"]: _water_lastmod(w, state) for w in waters}
        state_species = _species_word([p for w in waters for p in w["plants"]])
        shared = shared_names(waters)
        towns_on = {
            w["id"]: (w["name"], tuple(w["counties"])) in shared for w in waters
        }
        keys: dict[str, tuple[str, ...]] = {
            w["id"]: (
                w["name"],
                _species_word(w["plants"], state_species),
                place_phrase(
                    w,
                    state["name"],
                    "" if w["counties"] or w["towns"] else _place(w, state),
                    towns_on[w["id"]],
                ),
            )
            for w in waters
        }
        extra = qualifiers(keys, waters)
        if extra:
            warn_titles(
                f"{len(extra)} {state['code']} water page(s) would still share a "
                "title after naming the town; each now carries a qualifier",
                [
                    f"{w['site_path']} -> {extra[w['id']]}"
                    for w in waters
                    if w["id"] in extra
                ],
            )
        for w in waters:
            entries.append(
                _render_water(
                    ctx,
                    state,
                    w,
                    waters,
                    lastmods[w["id"]],
                    state_species,
                    with_towns=towns_on[w["id"]],
                    qualifier=extra.get(w["id"], ""),
                )
            )
        hub_lastmods[state["code"]] = max(lastmods.values())
        entries.append(
            _render_hub(
                ctx,
                state,
                waters,
                hub_lastmods[state["code"]],
                _build_date(state, snap_v2["generated_at"]),
            )
        )
    entries.append(_render_index(ctx, snap_v2["states"], max(hub_lastmods.values())))
    return entries


def _trail_root(ctx: StatesContext) -> list[tuple[str, str]]:
    return [
        (ctx.site_name, f"{ctx.base_url}/"),
        ("States", f"{ctx.base_url}/states/"),
    ]


def _join_names(names: list[str]) -> str:
    """ "A", "A and B", "A, B and C"."""
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _index_description(live: list[str], soon: list[str]) -> str:
    """The /states/ meta description: what is live, what is coming, and that
    every other state links to its agency. Under 160 characters for the
    states as they are; a longer list still says the same thing."""
    text = f"{_join_names(live)} trout stocking schedules"
    if soon:
        text += f"; {_join_names(soon)} coming soon"
    return text + ". Every other state links to its agency's official page."


def _render_index(
    ctx: StatesContext, states: list[dict[str, Any]], lastmod: str
) -> tuple[str, str | None]:
    page_url = f"{ctx.base_url}/states/"
    rows = [
        {
            "name": s["name"],
            "href": "../" if s["code"] == "CA" else f"../{s['code'].lower()}/",
            "agency": s["agency"]["name"],
            "kind": "Weekly schedule"
            if s["code"] == "CA"
            else {"schedule": "Schedule", "plan": "Spring plan"}.get(
                s["semantics"], "Stocking report"
            ),
            "waters": s["waters_count"],
            "checked": _fmt_dt(s["checks"]["last_success_at"]),
        }
        for s in states
    ]
    title = f"Trout stocking schedules in all 50 states | {ctx.site_name}"
    live = {s["code"]: row["href"] for s, row in zip(states, rows, strict=True)}
    entries = state_coverage.coverage(live)
    live_names = [e["name"] for e in entries if e["status"] == "live"]
    soon_names = [e["name"] for e in entries if e["status"] == "soon"]
    trail = _trail_root(ctx)
    html = ctx.env.get_template("states.html.jinja").render(
        title=title,
        description=_index_description(live_names, soon_names),
        live_names=_join_names(live_names),
        coverage=entries,
        coverage_checked=state_coverage.LINKS_CHECKED,
        canonical_url=page_url,
        root="../",
        **ctx.common,
        structured_data=ctx.ld_graph(
            ctx.ld_page(
                "CollectionPage",
                page_url=page_url,
                name=title,
                base_url=ctx.base_url,
                about=[{"@type": "State", "name": s["name"]} for s in states],
            ),
            ctx.ld_breadcrumb(page_url, trail),
        ),
        breadcrumb=ctx.relative_trail(trail, base_url=ctx.base_url, root="../"),
        rows=rows,
    )
    ctx.write_page(ctx.out_dir, "states", html, ctx.written)
    return page_url, lastmod


def _render_hub(
    ctx: StatesContext,
    state: dict[str, Any],
    waters: list[dict[str, Any]],
    lastmod: str,
    today: dt.date,
) -> tuple[str, str | None]:
    seg = state["code"].lower()
    page_url = f"{ctx.base_url}/{seg}/"
    this_week, other = _hub_sections(state, waters, today)
    region_names = {r["code"]: r["name"] for r in state["regions"]}
    groups: dict[str, list[dict[str, str]]] = {}
    for w in waters:
        key = region_names.get(w["region"] or "", "")
        groups.setdefault(key, []).append(
            {
                "slug": w["slug"],
                "name": w["name"],
                "place": _place(w, state),
            }
        )
    water_groups = [{"name": k, "waters": v} for k, v in sorted(groups.items())]
    species = _species_word([p for w in waters for p in w["plants"]])
    schedule = state["semantics"] in ("schedule", "plan")
    wd = words(state)
    title = (
        f"{state['name']} {species} stocking {wd['kind']}"
        if schedule
        else f"{state['name']} {species} stocking report"
    ) + f", from {state['agency']['short_name']} | {ctx.site_name}"
    trail = [*_trail_root(ctx), (state["name"], page_url)]
    html = ctx.env.get_template("state_hub.html.jinja").render(
        title=title,
        description=(
            f"Where {state['agency']['name']} "
            + (
                f"has {wd['verb']} {species} stocking"
                if schedule
                else f"has stocked {species}"
            )
            + f" in {state['name']}: this week, "
            + ("what is coming up" if schedule else "recent stockings")
            + f", and the stocking history of all {state['waters_count']} waters."
        ),
        canonical_url=page_url,
        root="../",
        **_state_common(ctx, state, "../"),
        structured_data=ctx.ld_graph(
            ctx.ld_page(
                "CollectionPage",
                page_url=page_url,
                name=title,
                base_url=ctx.base_url,
                about={"@type": "State", "name": state["name"]},
            ),
            ctx.ld_breadcrumb(page_url, trail),
        ),
        breadcrumb=ctx.relative_trail(trail, base_url=ctx.base_url, root="../"),
        state=state,
        week_phrase=SOURCES[state["code"]].week_phrase,
        precision_phrase=_precision_phrase(state),
        schedule=schedule,
        w_kind=wd["kind"],
        w_verb=wd["verb"],
        species=species,
        this_week=this_week,
        other=other,
        upcoming_days=UPCOMING_DAYS,
        recent_days=RECENT_DAYS,
        water_groups=water_groups,
        fetched_label=_fmt_dt(state["checks"]["last_success_at"]),
        attempt_failed=not state["checks"]["last_attempt_ok"],
        attempt_label=_fmt_dt(state["checks"]["last_attempt_at"]),
        range_label=_date_range_label(waters),
        has_months=any(w["months_note"] for w in waters),
        has_counts=any(p["count"] is not None for w in waters for p in w["plants"]),
        newest_label=when_label(state["newest_record"])
        if state["newest_record"]
        else "",
    )
    ctx.write_page(ctx.out_dir, seg, html, ctx.written)
    return page_url, lastmod


def _render_water(
    ctx: StatesContext,
    state: dict[str, Any],
    w: dict[str, Any],
    waters: list[dict[str, Any]],
    lastmod: str,
    state_species: str,
    with_towns: bool = False,
    qualifier: str = "",
) -> tuple[str, str | None]:
    seg = state["code"].lower()
    page_url = f"{ctx.base_url}{w['site_path']}"
    schedule = state["semantics"] in ("schedule", "plan")
    wd = words(state)
    species = _species_word(w["plants"], state_species)
    place = place_phrase(
        w,
        state["name"],
        "" if w["counties"] or w["towns"] else _place(w, state),
        with_towns,
    )
    if qualifier:
        place = f"{place}, {qualifier}"
    plants = [
        {
            "when": when_label(p["period"]),
            "precision": p["period"]["precision"],
            "species": p["species"],
            "count": p["count"],
            "status": status_label(p["status"], state["semantics"]),
            "removed": p["status"] == "removed",
        }
        for p in sorted(
            w["plants"],
            key=lambda p: (p["period"]["start"], p["period"]["precision"]),
            reverse=True,
        )
    ]
    neighbors = sorted(
        (
            {"slug": o["slug"], "name": o["name"]}
            for o in waters
            if o["id"] != w["id"]
            and set(o["counties"] or o["towns"]) & set(w["counties"] or w["towns"])
        ),
        key=lambda o: o["name"],
    )
    noun = f"stocking {wd['kind']}" if schedule else "stocking history"
    head = f"{w['name']} {species} {noun}"
    short = short_place_phrase(
        w, state, "" if w["counties"] or w["towns"] else _place(w, state), with_towns
    )
    if qualifier:
        short = f"{short}, {qualifier}"
    title = fit_title(
        [f"{head} ({place})", f"{head} ({short})"], ctx.site_name, ctx.title_max
    )
    if schedule:
        if w["next_period"]:
            status = f"next {wd['verb']} {when_label(w['next_period'])}."
        elif w["last_period"]:
            status = f"last {wd['verb']} {when_label(w['last_period'])}; nothing later listed."
        elif w["months_note"]:
            status = f"listed by month ({w['months_note']}), no date set."
        else:
            status = "no date listed yet."
    else:
        status = (
            f"last stocked {w['last_period']['label']}, per the newest record."
            if w["last_period"]
            else "no stocking on record."
        )
    listed_count = sum(1 for p in w["plants"] if p["status"] != "removed")
    trail = [
        *_trail_root(ctx),
        (state["name"], f"{ctx.base_url}/{seg}/"),
        (w["name"], page_url),
    ]
    county_nodes = [
        {
            "@type": "AdministrativeArea",
            "name": f"{c} County",
            "containedInPlace": {"@type": "State", "name": state["name"]},
        }
        for c in w["counties"]
    ] or [{"@type": "State", "name": state["name"]}]
    water_node: dict[str, Any] = {
        "@type": "BodyOfWater",
        "@id": f"{page_url}#water",
        "name": w["name"],
        "containedInPlace": county_nodes,
    }
    if w["source_id"]:
        water_node["identifier"] = {
            "@type": "PropertyValue",
            "propertyID": f"{state['agency']['short_name']} water ID",
            "value": w["source_id"],
        }
    html = ctx.env.get_template("state_water.html.jinja").render(
        title=title,
        description=(
            f"{w['name']}, {place} {species} stocking: {status} "
            f"{state['agency']['short_name']} data, {listed_count} "
            f"{'date' if listed_count == 1 else 'dates'} on record."
        ),
        canonical_url=page_url,
        root="../../../",
        **_state_common(ctx, state, "../../../"),
        structured_data=ctx.ld_graph(
            ctx.ld_page(
                "WebPage",
                page_url=page_url,
                name=title,
                base_url=ctx.base_url,
                about={"@id": f"{page_url}#water"},
            ),
            ctx.ld_breadcrumb(page_url, trail),
            water_node,
        ),
        breadcrumb=ctx.relative_trail(trail, base_url=ctx.base_url, root="../../../"),
        state=state,
        water=w,
        head=head,
        place=place,
        schedule=schedule,
        w_kind=wd["kind"],
        w_verb=wd["verb"],
        plants=plants,
        has_counts=any(p["count"] is not None for p in plants),
        has_removed=any(p["removed"] for p in plants),
        neighbors=neighbors,
        gear_links=list(ctx.gear_links) if gear_allowed(state, species) else [],
        affiliate_rel=ctx.affiliate_rel,
        neighbors_heading=(
            f"Other {', '.join(w['counties'])} County waters on record"
            if w["counties"]
            else f"Other {', '.join(w['towns'])} waters on record"
        ),
        next_label=when_label(w["next_period"]) if w["next_period"] else "",
        last_label=when_label(w["last_period"]) if w["last_period"] else "",
        fetched_label=_fmt_dt(state["checks"]["last_success_at"]),
        attempt_failed=not state["checks"]["last_attempt_ok"],
        attempt_label=_fmt_dt(state["checks"]["last_attempt_at"]),
    )
    ctx.write_page(ctx.out_dir, w["site_path"].strip("/"), html, ctx.written)
    return page_url, lastmod
