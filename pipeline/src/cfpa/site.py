"""Generate the static site from a built snapshot.

The one script this module can write is the Google Analytics 4 tag
(DECISIONS 0011, which replaces 0002's "no tracking" for the website only).
It is emitted only when a GA4 measurement ID is configured
(``GA4_MEASUREMENT_ID`` below); with none, every page has no JavaScript, no
cookies and no third-party request, exactly as before. The about, privacy
and support pages describe whichever of those two states the build is in.
Nothing here ever writes an external stylesheet host, a pixel or an iframe.
The iOS app never carries analytics.

Pages may also carry one ``<script type="application/ld+json">`` block of
schema.org structured data (docs/adr/0013). That is data for search
engines, not JavaScript: a browser never executes it and it makes no
request. It only ever states what the snapshot says -- a planting is a
scheduled *week*, so there is no ``Event``, and no coordinates are given
because the snapshot has none.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jinja2

TEMPLATES_DIR = Path(__file__).parent / "templates"

# The product name (DECISIONS 0010). It says nothing a searcher types, so
# every title and meta description keeps the descriptive "trout planting" /
# "stocking" phrase next to it -- the brand never replaces the search terms.
SITE_NAME = "Trout Truck"
# Appended after the brand on pages whose own label carries no search terms
# (about, privacy, support, 404).
SITE_TAGLINE = "CA trout planting schedule"

# The website's Google Analytics 4 measurement ID (DECISIONS 0011): the web
# stream of GA4 property 554849409. It is public by design (it appears in
# every page's HTML), so it is committed here rather than kept in a secret or
# a repository variable; this line is the one place it lives. Setting it to
# "" turns analytics off: the build then emits no <script> and no request to
# Google on any page, and the privacy copy says nothing is collected.
GA4_MEASUREMENT_ID = "G-ZYL3RMXCZF"

_GA4_MEASUREMENT_ID_RE = re.compile(r"G-[A-Z0-9]+")

# Consent Mode v2: analytics_storage defaults to denied in these regions (the
# EEA, the UK and Switzerland) and to granted everywhere else. The three ad
# signals are denied everywhere. ISO 3166-1 alpha-2 codes.
GA4_ANALYTICS_DENIED_REGIONS = (
    # the 27 EU member states
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE",
    # the rest of the EEA
    "IS", "LI", "NO",
    # the UK and Switzerland
    "GB", "CH",
)  # fmt: skip


def ga4_measurement_id_or_none(value: str | None) -> str | None:
    """Return a usable GA4 measurement ID, or None when none is configured.

    A malformed value raises instead of shipping a tag that silently records
    nothing (a Universal Analytics "UA-" ID, a stray space or lowercase).
    """
    if value is None or value == "":
        return None
    if not _GA4_MEASUREMENT_ID_RE.fullmatch(value):
        raise ValueError(
            f"GA4 measurement ID {value!r} is not of the form 'G-XXXXXXXXXX'"
        )
    return value


# Google Search Console ownership token for the URL-prefix property
# https://chelseakr.github.io/ca-fish-planting-alerts/ (docs/SEARCH-CONSOLE.md,
# docs/adr/0013). A github.io project site cannot be a Domain property: that
# needs a DNS TXT record on github.io. So the owner verifies the URL prefix
# with Google's HTML tag, and this is where its `content` value goes. Like the
# GA4 ID it is public (it appears in the home page's HTML), so it is committed
# here. "" = no tag. Only the home page carries it; that is the page Google
# checks, and the tag has to stay there for the property to stay verified.
GOOGLE_SITE_VERIFICATION = ""

_GOOGLE_SITE_VERIFICATION_RE = re.compile(r"[A-Za-z0-9_-]{10,100}")


def google_site_verification_or_none(value: str | None) -> str | None:
    """Return a usable Search Console token, or None when none is configured.

    A malformed value (the whole ``<meta ...>`` tag pasted in, quotes, a
    space) raises instead of shipping a tag Google cannot match.
    """
    if value is None or value == "":
        return None
    if not _GOOGLE_SITE_VERIFICATION_RE.fullmatch(value):
        raise ValueError(
            f"Google site verification token {value!r} is not the bare "
            "content value of Search Console's HTML tag"
        )
    return value


# The licence the compiled schedule history is offered under, as a URL, for
# the Dataset structured data on /about/ (docs/adr/0013). Unset on purpose:
# the CC-BY licence in docs/LICENSES-AND-ATTRIBUTION.md belongs to a
# different CDFW dataset (the Fishing Guide on data.ca.gov), and the schedule
# itself falls under CDFW's Conditions of Use, which the Dataset already
# cites through `isBasedOn`. Choosing a licence for Trout Truck's own
# compilation is the owner's call; until then the markup states none rather
# than one nobody chose.
DATASET_LICENSE_URL = ""

CDFW_NAME = "California Department of Fish and Wildlife"
CDFW_URL = "https://wildlife.ca.gov/"

REGION_NAME_BY_CODE = {
    "R1": "Northern Region",
    "R2": "North Central Region",
    "R3": "Bay Delta Region",
    "R4": "Central Region",
    "R5": "South Coast Region",
    "R6": "Inland Deserts Region",
}


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html.jinja"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _fmt_dt(iso_z: str) -> str:
    d = dt.datetime.fromisoformat(iso_z.replace("Z", "+00:00"))
    return d.strftime("%Y-%m-%d %H:%M UTC")


def _fmt_date_human(iso_date: str) -> str:
    d = dt.date.fromisoformat(iso_date)
    return d.strftime("%B %-d, %Y") if hasattr(d, "strftime") else iso_date


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def _ics_fold(line: str) -> str:
    # RFC 5545 §3.1: fold lines longer than 75 octets, continuation starts
    # with a single space. Our lines are short in practice; folding is
    # defensive.
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out = []
    while len(b) > 75:
        out.append(b[:75].decode("utf-8", errors="ignore"))
        b = b[75:]
    out.append(b.decode("utf-8", errors="ignore"))
    return "\r\n ".join(out)


def build_water_ics(*, water: dict[str, Any], base_url: str, species: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ca-fish-planting-alerts//snapshot v1//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(water['name'])} {species} planting schedule",
        f"X-WR-CALDESC:{_ics_escape('CDFW-scheduled plants at ' + water['name'] + '. Subject to change.')}",
    ]
    for p in water["plants"]:
        if p["status"] != "listed":
            continue
        week = p["week"]
        start = dt.date.fromisoformat(week["start"])
        end_exclusive = dt.date.fromisoformat(week["end"]) + dt.timedelta(days=1)
        uid = f"{water['id']}-{week['start']}-{re.sub(r'[^a-z0-9]+', '-', p['species'].lower())}@ca-fish-planting-alerts.invalid"
        # "scheduled", never "planted"/"stocked": CDFW's plants are subject
        # to change and this feed cannot confirm one happened.
        summary = (
            f"week of {week['start']}: {p['species']} scheduled at {water['name']}"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{p['last_observed_at'].replace('-', '').replace(':', '')}",
            f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_exclusive.strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape('CDFW plants are subject to change. ' + base_url)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"


def county_slug(county: str) -> str:
    """URL segment for a county page: "San Luis Obispo" -> "san-luis-obispo"."""
    return re.sub(r"[^a-z0-9]+", "-", county.lower()).strip("-")


def county_phrase(counties: list[str]) -> str:
    """ "Mono County", "Nevada and Yuba counties",
    "El Dorado, Placer and Sacramento counties"."""
    if len(counties) == 1:
        return f"{counties[0]} County"
    if len(counties) == 2:
        return f"{counties[0]} and {counties[1]} counties"
    return f"{', '.join(counties[:-1])} and {counties[-1]} counties"


def species_phrase(species: set[str]) -> str:
    """What a page says is planted, from the data: "trout" for a trout-only
    water, "catfish" for the three catfish-only park lakes, "trout and
    catfish" for the mixed ones. A catfish-only water's page must not call
    itself a trout schedule. More than two species collapse to "fish"."""
    names = sorted(species, key=lambda s: (s.lower() != "trout", s.lower()))
    if not names:
        return "fish"
    if len(names) <= 2:
        return " and ".join(n.lower() for n in names)
    return "fish"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _water_view(w: dict[str, Any], *, source_week_start: str) -> dict[str, Any]:
    plants_sorted = sorted(w["plants"], key=lambda p: p["week"]["start"], reverse=True)
    other_names = [n for n in w["aliases"] if n != w["name"]]
    counties = ", ".join(w["counties"])
    listed = [p for p in w["plants"] if p["status"] == "listed"]
    # Upcoming = a listed plant for a week after the snapshot's own current
    # week. Kept separate from last_listed_week (which never looks past the
    # current week), so a water whose only listing is next week is not
    # described as having nothing scheduled.
    upcoming = sorted(
        p["week"]["start"] for p in listed if p["week"]["start"] > source_week_start
    )
    listed_weeks = {p["week"]["start"] for p in listed}
    this_week = source_week_start in listed_weeks
    species = species_phrase({p["species"] for p in w["plants"]})
    place = f"{w['name']} ({county_phrase(w['counties'])})"
    return {
        "slug": w["slug"],
        "name": w["name"],
        # Five CDFW names (Silver Lake, Bass Lake, Deer Creek, Sacramento
        # River, Blue Lake Upper) are shared by 2-3 different waters; the
        # county is what tells their pages -- and their titles -- apart.
        "qualified_name": f"{w['name']} ({counties})",
        "place": place,
        "county_phrase": county_phrase(w["counties"]),
        "species": species,
        "counties": counties,
        "county_links": [{"name": c, "slug": county_slug(c)} for c in w["counties"]],
        "county": w["counties"][0] if w["counties"] else "",
        "region_name": REGION_NAME_BY_CODE.get(w["region"], w["region"]),
        "cdfw_map_url": w["cdfw_map_url"],
        "other_names": ", ".join(other_names) if other_names else "",
        "last_listed_label": w["last_listed_week"]["label"]
        if w["last_listed_week"]
        else "",
        "next_listed_label": f"week of {upcoming[0]}" if upcoming else "",
        "this_week": this_week,
        # Nothing listed for the current week or any later one. The page
        # says so plainly, and says what it does not mean: no plant is
        # scheduled, which is not "no fish".
        "nothing_current": not this_week and not upcoming,
        "latest_listed_start": max(listed_weeks) if listed_weeks else "",
        "listed_week_count": len(listed_weeks),
        "has_removed_weeks": any(p["status"] == "removed" for p in w["plants"]),
        "plants": [
            {
                "label": p["week"]["label"],
                "species": p["species"],
                "status": p["status"],
            }
            for p in plants_sorted
        ],
    }


def _water_description(view: dict[str, Any], *, source_week_label: str) -> str:
    """The meta description: the water, its county, the stocking wording
    people search with, then the weeks that answer the query, within the
    first ~150 characters a result shows."""
    if view["this_week"] and view["next_listed_label"]:
        status = (
            f"scheduled this week, the {source_week_label}, and next the "
            f"{view['next_listed_label']}."
        )
    elif view["this_week"]:
        status = f"scheduled this week, the {source_week_label}."
    elif view["next_listed_label"]:
        status = f"next scheduled the {view['next_listed_label']}."
    elif view["last_listed_label"]:
        status = (
            f"last scheduled the {view['last_listed_label']}. None listed "
            "this week or later."
        )
    else:
        status = "no week currently listed."
    weeks = _plural(view["listed_week_count"], "week", "weeks")
    return (
        f"{view['name']}, {view['county_phrase']} {view['species']} stocking: "
        f"{status} CDFW planting schedule and history, {weeks} on record."
    )


def _rollover_sensitive(w: dict[str, Any], *, source_week_start: str) -> bool:
    """True when the weekly rollover can change this water's wording: it has
    a listing in the previous, current or a later week, so "next" can become
    "this week", and "this week" can become "last scheduled"."""
    rollover_sensitive_from = (
        dt.date.fromisoformat(source_week_start) - dt.timedelta(days=7)
    ).isoformat()
    return any(
        p["status"] == "listed" and p["week"]["start"] >= rollover_sensitive_from
        for p in w["plants"]
    )


def _water_data_lastmod(w: dict[str, Any], *, source_week_start: str) -> str:
    """The date this water's own data last changed in substance.

    Not the build date: the site rebuilds every day, and a lastmod that
    always says "today" is one search engines learn to ignore. The data
    changes when a plant is first listed (first_observed_at), when one is
    removed (last_observed_at of a removed plant), and when the current week
    rolls over while the water has a listing near it (see
    ``_rollover_sensitive``). A removed-then-relisted plant is not
    detectable from the snapshot and is the one known under-report.

    The "last checked" freshness line on every page changes on every run and
    is deliberately not counted: it says when the data was read, not that it
    changed. For the same reason no sentence outside that line prints the
    current week's date unless the water has a listing near it.
    """
    dates: list[str] = [p["first_observed_at"][:10] for p in w["plants"]]
    dates += [
        p["last_observed_at"][:10] for p in w["plants"] if p["status"] == "removed"
    ]
    if _rollover_sensitive(w, source_week_start=source_week_start):
        dates.append(source_week_start)
    return max(dates)


def _water_first_seen(w: dict[str, Any]) -> str:
    """The date this water first appeared, and so first got a page (and a
    link from the other waters in its counties)."""
    return str(min(p["first_observed_at"][:10] for p in w["plants"]))


def _water_lastmod(
    w: dict[str, Any],
    *,
    source_week_start: str,
    siblings: list[dict[str, Any]] | None = None,
) -> str:
    """The date this water's page last changed in substance, for sitemap.xml:
    its own data (``_water_data_lastmod``), or the day a water sharing one of
    its counties first appeared, because the page links to every such water
    by name. Siblings are listed by name only, not with their weeks, so a
    sibling's new listing does not change this page."""
    dates = [_water_data_lastmod(w, source_week_start=source_week_start)]
    dates += [_water_first_seen(s) for s in siblings or []]
    return max(dates)


# ---- schema.org structured data (docs/adr/0013)
#
# Every node here is built from the snapshot and nothing else. Types used:
# WebSite, WebPage, CollectionPage, BreadcrumbList/ListItem, BodyOfWater,
# AdministrativeArea, State, PropertyValue, Dataset, DataDownload,
# CreativeWork, GovernmentOrganization, Organization. Never Event: CDFW
# publishes a week, never a day or a time, and says every plant is subject to
# change, so an Event with a start date would state something the source
# does not.


def _ld_graph(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"@context": "https://schema.org", "@graph": list(nodes)}


def _ld_breadcrumb(page_url: str, trail: list[tuple[str, str]]) -> dict[str, Any]:
    """A BreadcrumbList that mirrors the visible breadcrumb exactly: the
    same names, in the same order, each with its absolute URL."""
    return {
        "@type": "BreadcrumbList",
        "@id": f"{page_url}#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(trail, start=1)
        ],
    }


def _ld_county(county: str) -> dict[str, Any]:
    return {
        "@type": "AdministrativeArea",
        "name": f"{county} County",
        "containedInPlace": {"@type": "State", "name": "California"},
    }


def _ld_water(w: dict[str, Any], *, page_url: str) -> dict[str, Any]:
    """The water itself. BodyOfWater (a schema.org Place) is true of every
    CDFW planting water, lake, reservoir, creek or river section alike; the
    finer subtypes would be a guess from the name. No ``geo``: the snapshot
    carries no location for any water, and none is invented."""
    node: dict[str, Any] = {
        "@type": "BodyOfWater",
        "@id": f"{page_url}#water",
        "name": w["name"],
        "containedInPlace": [_ld_county(c) for c in w["counties"]],
        "hasMap": w["cdfw_map_url"],
        "identifier": {
            "@type": "PropertyValue",
            "propertyID": "CDFW stock ID",
            "value": str(w["cdfw_stock_id"]),
        },
    }
    other_names = [n for n in w["aliases"] if n != w["name"]]
    if other_names:
        node["alternateName"] = other_names
    return node


def _ld_page(
    page_type: str,
    *,
    page_url: str,
    name: str,
    base_url: str,
    about: dict[str, Any],
) -> dict[str, Any]:
    return {
        "@type": page_type,
        "@id": page_url,
        "url": page_url,
        "name": name,
        "isPartOf": {"@id": f"{base_url}/#website"},
        "breadcrumb": {"@id": f"{page_url}#breadcrumb"},
        "about": about,
    }


def _ld_dataset(
    snapshot: dict[str, Any],
    *,
    base_url: str,
    date_modified: str,
    license_url: str | None,
) -> dict[str, Any]:
    """The schedule history as a Dataset, on /about/ (the page that
    describes it). Its source and CDFW's terms are stated through
    ``isBasedOn``; ``creditText`` is the attribution every page carries.
    ``license`` is only present when the owner has chosen one."""
    weeks = [p["week"] for w in snapshot["waters"] for p in w["plants"]]
    source = next(
        (
            s
            for s in snapshot["licence"]["sources"]
            if s["url"] == snapshot["attribution"]["url"]
        ),
        None,
    )
    based_on: dict[str, Any] = {
        "@type": "CreativeWork",
        "name": snapshot["source"]["name"],
        "url": snapshot["source"]["url"],
        "creator": {
            "@type": "GovernmentOrganization",
            "name": CDFW_NAME,
            "url": CDFW_URL,
        },
    }
    if source is not None:
        based_on["license"] = source["terms_url"]
    node: dict[str, Any] = {
        "@type": "Dataset",
        "@id": f"{base_url}/about/#data",
        "name": "California fish planting schedule history, from CDFW's weekly schedule",
        "description": (
            "Every week the California Department of Fish and Wildlife (CDFW) "
            "has listed a water on its weekly Fish Planting Schedule, as "
            f"recorded by {SITE_NAME}: the water, its CDFW stock ID, county "
            "and CDFW region, the species, and the scheduled week. CDFW "
            "publishes a week, never a day, and says every plant is subject "
            "to change, so each record is a scheduled week, not a confirmed "
            "plant. CDFW's own page shows a rolling window of about a year; "
            "this history keeps every week recorded after the window moves on."
        ),
        "url": f"{base_url}/about/#data",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": SITE_NAME, "url": f"{base_url}/"},
        "isBasedOn": based_on,
        "creditText": snapshot["attribution"]["text"],
        "keywords": [
            "California",
            "CDFW",
            "fish planting schedule",
            "trout planting",
            "trout stocking",
            "hatchery",
        ],
        "variableMeasured": [
            "water name",
            "CDFW stock ID",
            "county",
            "CDFW region",
            "species",
            "scheduled week",
        ],
        "spatialCoverage": {"@type": "State", "name": "California"},
        "dateModified": date_modified,
        "distribution": [
            {
                "@type": "DataDownload",
                "name": "Snapshot, schema version 1",
                "encodingFormat": "application/json",
                "contentUrl": f"{base_url}/snapshot/v1.json",
            }
        ],
    }
    if weeks:
        start = min(wk["start"] for wk in weeks)
        end = max(wk["end"] for wk in weeks)
        node["temporalCoverage"] = f"{start}/{end}"
    if license_url:
        node["license"] = license_url
    return node


def _relative_trail(
    trail: list[tuple[str, str]], *, base_url: str, root: str
) -> list[tuple[str, str]]:
    """The visible breadcrumb links relative to the page, like every other
    internal link, so the site works under any host (a local check server
    included); the structured data keeps the absolute URLs."""
    prefix = f"{base_url}/"
    out = []
    for name, url in trail:
        if not url.startswith(prefix):
            raise ValueError(f"breadcrumb URL {url!r} is not under {prefix!r}")
        out.append((name, root + url[len(prefix) :]))
    return out


def _write_page(out_dir: Path, rel_dir: str, html: str, written: list[Path]) -> None:
    page_dir = out_dir / rel_dir if rel_dir else out_dir
    page_dir.mkdir(parents=True, exist_ok=True)
    path = page_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    written.append(path)


@dataclass(frozen=True)
class _PageContext:
    """What every water and county page render shares."""

    env: jinja2.Environment
    out_dir: Path
    written: list[Path]
    base_url: str
    common: dict[str, Any]
    views: dict[str, dict[str, Any]]
    waters_by_county: dict[str, list[dict[str, Any]]]
    county_link: dict[str, dict[str, str]]
    source_week_start: str
    source_week_label: str
    source_fetched_label: str

    @property
    def home_crumb(self) -> tuple[str, str]:
        return (SITE_NAME, f"{self.base_url}/")

    @property
    def counties_crumb(self) -> tuple[str, str]:
        return ("Counties", f"{self.base_url}/county/")


def _render_water_page(
    ctx: _PageContext, w: dict[str, Any], *, recorded_since: str
) -> str:
    """Write one water's page and calendar feed. Returns its lastmod."""
    base_url = ctx.base_url
    view = ctx.views[w["id"]]
    page_url = f"{base_url}/water/{w['slug']}/"

    def by_name(s: dict[str, Any]) -> tuple[str, str]:
        return (s["name"], s["slug"])

    # Waters sharing a county: the only nearness the snapshot supports (it
    # has no locations), so the page says "other <county> County waters",
    # never "nearby".
    siblings = {
        s["id"]: s
        for c in w["counties"]
        for s in ctx.waters_by_county[c]
        if s["id"] != w["id"]
    }
    other_waters_by_county = [
        {
            **ctx.county_link[c],
            "waters": [
                {"slug": s["slug"], "name": s["name"]}
                for s in sorted(ctx.waters_by_county[c], key=by_name)
                if s["id"] != w["id"]
            ],
        }
        for c in w["counties"]
    ]
    # The visible breadcrumb, and the BreadcrumbList that mirrors it, go
    # through the first county: the one the snapshot's region comes from.
    primary = w["counties"][0]
    trail = [
        ctx.home_crumb,
        ctx.counties_crumb,
        (f"{primary} County", f"{base_url}/county/{county_slug(primary)}/"),
        (w["name"], page_url),
    ]
    title = f"{view['place']} {view['species']} planting schedule | {SITE_NAME}"
    html = ctx.env.get_template("water.html.jinja").render(
        title=title,
        description=_water_description(view, source_week_label=ctx.source_week_label),
        canonical_url=page_url,
        root="../../",
        **ctx.common,
        structured_data=_ld_graph(
            _ld_page(
                "WebPage",
                page_url=page_url,
                name=title,
                base_url=base_url,
                about={"@id": f"{page_url}#water"},
            ),
            _ld_breadcrumb(page_url, trail),
            _ld_water(w, page_url=page_url),
        ),
        breadcrumb=_relative_trail(trail, base_url=base_url, root="../../"),
        water=view,
        other_waters_by_county=other_waters_by_county,
        source_week_label=ctx.source_week_label,
        source_fetched_label=ctx.source_fetched_label,
        recorded_since_label=f"week of {recorded_since}" if recorded_since else "",
    )
    _write_page(ctx.out_dir, f"water/{w['slug']}", html, ctx.written)

    ics_path = ctx.out_dir / "water" / w["slug"] / "feed.ics"
    ics_path.write_text(
        build_water_ics(water=w, base_url=page_url, species=view["species"]),
        encoding="utf-8",
    )
    ctx.written.append(ics_path)

    return _water_lastmod(
        w,
        source_week_start=ctx.source_week_start,
        siblings=list(siblings.values()),
    )


def _render_county_page(
    ctx: _PageContext,
    county: str,
    *,
    this_week: list[dict[str, Any]],
    region_name: str,
) -> str:
    """Write one county's page. Returns its URL."""
    members = ctx.waters_by_county[county]
    page_url = f"{ctx.base_url}/county/{county_slug(county)}/"
    species = species_phrase({p["species"] for w in members for p in w["plants"]})
    this_week_rows = sorted(
        (
            {
                "slug": ctx.views[e["water_id"]]["slug"],
                "name": ctx.views[e["water_id"]]["name"],
                "species": e["species"],
            }
            for e in this_week
        ),
        key=lambda r: (r["name"], r["slug"]),
    )
    rows = [
        {
            "slug": v["slug"],
            "name": v["name"],
            "latest_start": v["latest_listed_start"],
            "upcoming": v["latest_listed_start"] > ctx.source_week_start,
            "weeks": v["listed_week_count"],
        }
        for v in (ctx.views[w["id"]] for w in members)
    ]
    # Most recently scheduled first, ties alphabetical (two stable sorts).
    rows.sort(key=lambda r: (r["name"], r["slug"]))
    rows.sort(key=lambda r: r["latest_start"], reverse=True)
    trail = [ctx.home_crumb, ctx.counties_crumb, (f"{county} County", page_url)]
    title = (
        f"{county} County {species} planting schedule: fish plants this week"
        f" | {SITE_NAME}"
    )
    html = ctx.env.get_template("county.html.jinja").render(
        title=title,
        description=(
            f"Which {county} County waters are on CDFW's {species} planting "
            f"schedule this week, and the latest scheduled week at each of its "
            f"{_plural(len(members), 'water', 'waters')}, with every water's "
            "stocking history."
        ),
        canonical_url=page_url,
        root="../../",
        **ctx.common,
        structured_data=_ld_graph(
            _ld_page(
                "CollectionPage",
                page_url=page_url,
                name=title,
                base_url=ctx.base_url,
                about=_ld_county(county),
            ),
            _ld_breadcrumb(page_url, trail),
        ),
        breadcrumb=_relative_trail(trail, base_url=ctx.base_url, root="../../"),
        county=county,
        species=species,
        region_name=region_name,
        water_count=len(members),
        this_week_rows=this_week_rows,
        rows=rows,
        source_week_label=ctx.source_week_label,
        source_fetched_label=ctx.source_fetched_label,
    )
    _write_page(ctx.out_dir, f"county/{county_slug(county)}", html, ctx.written)
    return page_url


def _render_counties_index(
    ctx: _PageContext,
    *,
    regions: list[dict[str, Any]],
    species: str,
    county_count: int,
) -> str:
    """Write /county/. Returns its URL."""
    page_url = f"{ctx.base_url}/county/"
    trail = [ctx.home_crumb, ctx.counties_crumb]
    title = f"California {species} planting schedule by county | {SITE_NAME}"
    html = ctx.env.get_template("counties.html.jinja").render(
        title=title,
        description=(
            f"CDFW's California {species} planting schedule by county: every "
            "county with a water on the schedule, by CDFW region, with each "
            "water's stocking history and this week's fish plants."
        ),
        canonical_url=page_url,
        root="../",
        **ctx.common,
        structured_data=_ld_graph(
            _ld_page(
                "CollectionPage",
                page_url=page_url,
                name=title,
                base_url=ctx.base_url,
                about={"@type": "State", "name": "California"},
            ),
            _ld_breadcrumb(page_url, trail),
        ),
        breadcrumb=_relative_trail(trail, base_url=ctx.base_url, root="../"),
        regions=regions,
        species=species,
        county_count=county_count,
    )
    _write_page(ctx.out_dir, "county", html, ctx.written)
    return page_url


def _home_regions(
    snapshot: dict[str, Any],
    waters_by_id: dict[str, dict[str, Any]],
    county_link: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """This week's listings grouped by CDFW region, for the home page."""
    this_week_by_region: dict[str, list[dict[str, Any]]] = {}
    for entry in snapshot["this_week"]:
        w = waters_by_id[entry["water_id"]]
        this_week_by_region.setdefault(w["region"], []).append(
            {
                "slug": w["slug"],
                "name": w["name"],
                "counties": ", ".join(w["counties"]),
                "county_links": [county_link[c] for c in w["counties"]],
                "species": entry["species"],
            }
        )
    regions = []
    for region in snapshot["regions"]:
        rows = sorted(
            this_week_by_region.get(region["code"], []), key=lambda r: r["name"]
        )
        if rows:
            regions.append(
                {"code": region["code"], "name": region["name"], "rows": rows}
            )
    return regions


def build_site(
    snapshot: dict[str, Any],
    out_dir: Path,
    *,
    base_url: str,
    app_store_url: str | None = None,
    support_email: str | None = None,
    ga4_measurement_id: str | None = None,
    google_site_verification: str | None = None,
    dataset_license_url: str | None = DATASET_LICENSE_URL,
) -> list[Path]:
    """Render the full static site into ``out_dir``. Returns written paths.

    ``ga4_measurement_id`` defaults to None (no analytics) rather than to
    ``GA4_MEASUREMENT_ID``, so a caller gets the tag only by asking for it;
    ``cli.main`` is the caller that passes the committed value. The same
    goes for ``google_site_verification`` (``GOOGLE_SITE_VERIFICATION``).
    """
    # Checked before anything is written: a bad ID must not half-build.
    ga4_measurement_id = ga4_measurement_id_or_none(ga4_measurement_id)
    google_site_verification = google_site_verification_or_none(
        google_site_verification
    )
    env = _env()
    written: list[Path] = []
    base_url = base_url.rstrip("/")

    attribution_text = snapshot["attribution"]["text"]
    attribution_url = snapshot["attribution"]["url"]
    generated_at_label = _fmt_dt(snapshot["generated_at"])
    source_fetched_label = _fmt_dt(snapshot["source"]["fetched_at"])
    source_week_label = snapshot["source_week"]["label"]
    source_week_start = snapshot["source_week"]["start"]
    app_store_url = app_store_url or None
    support_email = support_email or None
    # Shared by every template: the app is only linked once it exists.
    common = {
        "attribution_text": attribution_text,
        "attribution_url": attribution_url,
        "app_store_url": app_store_url,
        "support_email": support_email,
        "site_name": SITE_NAME,
        # base.html.jinja includes the GA4 tag only when this is set, and the
        # about/privacy/support copy switches on it too, so the pages never
        # describe a state the build is not in.
        "ga4_measurement_id": ga4_measurement_id,
        "ga4_denied_regions": list(GA4_ANALYTICS_DENIED_REGIONS),
    }

    # ---- assets/style.css
    style_src = (TEMPLATES_DIR / "style.css").read_text(encoding="utf-8")
    style_path = out_dir / "assets" / "style.css"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text(style_src, encoding="utf-8")
    written.append(style_path)

    waters_by_id = {w["id"]: w for w in snapshot["waters"]}
    region_by_county = {c["name"]: c["region"] for c in snapshot["counties"]}
    region_name_by_code = {r["code"]: r["name"] for r in snapshot["regions"]}

    # ---- the per-water and per-county views, and their lastmods, before
    # anything is rendered: the home page, the county pages and the Dataset
    # on /about/ all need them.
    waters_by_county: dict[str, list[dict[str, Any]]] = {}
    for w in snapshot["waters"]:
        for c in w["counties"]:
            waters_by_county.setdefault(c, []).append(w)
    views = {
        w["id"]: _water_view(w, source_week_start=source_week_start)
        for w in snapshot["waters"]
    }
    data_lastmods = {
        w["id"]: _water_data_lastmod(w, source_week_start=source_week_start)
        for w in snapshot["waters"]
    }
    first_seen = {w["id"]: _water_first_seen(w) for w in snapshot["waters"]}
    county_names = sorted(waters_by_county)
    county_link = {c: {"name": c, "slug": county_slug(c)} for c in county_names}
    # Site-wide pages say "trout": nearly every water is trout, and the about
    # page says catfish are occasional. Water and county pages use their own
    # species, so a catfish-only park lake is never called a trout water.
    site_species = "trout"

    # Home: the current week's date is in its heading, so it changes at every
    # rollover, plus whenever any water's page does.
    home_lastmod = max([source_week_start, *data_lastmods.values()])

    # ---- index
    regions = _home_regions(snapshot, waters_by_id, county_link)
    all_waters = sorted(
        (
            {
                "slug": w["slug"],
                "name": w["name"],
                "county": w["counties"][0] if w["counties"] else "",
            }
            for w in snapshot["waters"]
        ),
        key=lambda w: w["name"],
    )
    county_counts = [
        {**county_link[c], "count": len(waters_by_county[c])} for c in county_names
    ]

    index_html = env.get_template("index.html.jinja").render(
        title=f"California {site_species} planting schedule this week, from CDFW | {SITE_NAME}",
        description=(
            f"Every California water on CDFW's fish planting schedule for the "
            f"{source_week_label}, by region and county, with each water's "
            f"{site_species} stocking history."
        ),
        canonical_url=f"{base_url}/",
        root="./",
        **common,
        google_site_verification=google_site_verification,
        structured_data=_ld_graph(
            {
                "@type": "WebSite",
                "@id": f"{base_url}/#website",
                "url": f"{base_url}/",
                "name": SITE_NAME,
                "description": (
                    f"CDFW's weekly California {site_species} planting schedule, "
                    "by water and county, with each water's planting history."
                ),
                "inLanguage": "en-US",
            }
        ),
        source_week_label=source_week_label,
        generated_at_label=generated_at_label,
        regions=regions,
        all_waters=all_waters,
        county_counts=county_counts,
    )
    _write_page(out_dir, "", index_html, written)

    # ---- about (carries the Dataset: it is the page that describes the data)
    if ga4_measurement_id:
        about_collects = (
            "what its website measures (Google Analytics) and its app collects "
            "(nothing)"
        )
    else:
        about_collects = "what it collects (nothing)"
    about_html = env.get_template("about.html.jinja").render(
        title=f"About, attribution & privacy | {SITE_NAME}, {SITE_TAGLINE}",
        description=(
            f"What {SITE_NAME} is, {about_collects}, and where its trout planting "
            "and stocking data and licence terms come from."
        ),
        canonical_url=f"{base_url}/about/",
        root="../",
        **common,
        structured_data=_ld_graph(
            _ld_dataset(
                snapshot,
                base_url=base_url,
                date_modified=home_lastmod,
                license_url=dataset_license_url or None,
            )
        ),
        licence_summary=snapshot["licence"]["summary"],
        licence_sources=snapshot["licence"]["sources"],
        generated_at_label=generated_at_label,
        source_fetched_label=source_fetched_label,
    )
    _write_page(out_dir, "about", about_html, written)

    # ---- privacy + support: the URLs App Store Connect asks for
    if ga4_measurement_id:
        privacy_description = (
            f"What the {SITE_NAME} trout planting site and iOS app collect: the "
            "website uses Google Analytics; the app collects nothing. No account, "
            "no ads."
        )
    else:
        privacy_description = (
            f"What the {SITE_NAME} trout planting site and iOS app collect: "
            "nothing. No account, no analytics, no tracking."
        )
    for slug, template, title, description in (
        (
            "privacy",
            "privacy.html.jinja",
            f"Privacy policy | {SITE_NAME}, {SITE_TAGLINE}",
            privacy_description,
        ),
        (
            "support",
            "support.html.jinja",
            f"Support & FAQ | {SITE_NAME}, {SITE_TAGLINE}",
            "How the trout planting schedule, stocking calendar feeds and iOS app alerts work, "
            "and why an alert may not arrive.",
        ),
    ):
        page_html = env.get_template(template).render(
            title=title,
            description=description,
            canonical_url=f"{base_url}/{slug}/",
            root="../",
            **common,
            source_fetched_label=source_fetched_label,
        )
        _write_page(out_dir, slug, page_html, written)

    # ---- 404 (GitHub Pages serves /404.html for any missing path, at any
    # depth, so its links are root-relative -- the site's own path prefix,
    # e.g. /ca-fish-planting-alerts/ -- rather than ./ or ../; never
    # indexed, no canonical)
    not_found_html = env.get_template("404.html.jinja").render(
        title=f"Page not found | {SITE_NAME}, {SITE_TAGLINE}",
        description="This page does not exist.",
        canonical_url=None,
        noindex=True,
        root=urlsplit(base_url).path.rstrip("/") + "/",
        **common,
    )
    not_found_path = out_dir / "404.html"
    not_found_path.write_text(not_found_html, encoding="utf-8")
    written.append(not_found_path)

    recorded_since = min(
        (p["week"]["start"] for w in snapshot["waters"] for p in w["plants"]),
        default="",
    )
    ctx = _PageContext(
        env=env,
        out_dir=out_dir,
        written=written,
        base_url=base_url,
        common=common,
        views=views,
        waters_by_county=waters_by_county,
        county_link=county_link,
        source_week_start=source_week_start,
        source_week_label=source_week_label,
        source_fetched_label=source_fetched_label,
    )

    # ---- per-water pages + ics
    water_lastmods = {
        f"{base_url}/water/{w['slug']}/": _render_water_page(
            ctx, w, recorded_since=recorded_since
        )
        for w in snapshot["waters"]
    }

    # ---- county pages: every county with at least one water page. They
    # answer "<county> fish plants": what is scheduled this week, and the
    # latest scheduled week at each of the county's waters. Each one's
    # lastmod is its member waters' own data: its "scheduled this week" list
    # flips at a rollover only for a water with a listing near it, which
    # _water_data_lastmod already counts.
    this_week_by_county: dict[str, list[dict[str, Any]]] = {}
    for e in snapshot["this_week"]:
        for c in waters_by_id[e["water_id"]]["counties"]:
            this_week_by_county.setdefault(c, []).append(e)
    county_lastmods: dict[str, str] = {}
    counties_by_region: dict[str, list[dict[str, Any]]] = {}
    for c in county_names:
        members = waters_by_county[c]
        page_url = _render_county_page(
            ctx,
            c,
            this_week=this_week_by_county.get(c, []),
            region_name=region_name_by_code.get(region_by_county.get(c, ""), ""),
        )
        county_lastmods[page_url] = max(data_lastmods[w["id"]] for w in members)
        counties_by_region.setdefault(region_by_county.get(c, ""), []).append(
            {**county_link[c], "count": len(members)}
        )

    # ---- counties index: every county page, grouped by CDFW region, with
    # its number of waters. Changes when a water first appears.
    counties_index_url = _render_counties_index(
        ctx,
        regions=[
            {
                "code": r["code"],
                "name": r["name"],
                "counties": counties_by_region[r["code"]],
            }
            for r in snapshot["regions"]
            if r["code"] in counties_by_region
        ],
        species=site_species,
        county_count=len(county_names),
    )
    counties_index_lastmod = max(first_seen.values(), default=source_week_start)

    # ---- sitemap.xml -- lastmod is when a page's substance last changed
    # (see _water_data_lastmod), not the daily build date. The about,
    # privacy and support pages carry no per-page data date, so no lastmod.
    sitemap_entries: list[tuple[str, str | None]] = [
        (f"{base_url}/", home_lastmod),
        (counties_index_url, counties_index_lastmod),
        (f"{base_url}/about/", None),
        (f"{base_url}/privacy/", None),
        (f"{base_url}/support/", None),
        *county_lastmods.items(),
        *water_lastmods.items(),
    ]
    sitemap_items = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{m}</lastmod></url>"
        if m
        else f"  <url><loc>{u}</loc></url>"
        for u, m in sitemap_entries
    )
    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{sitemap_items}\n"
        "</urlset>\n"
    )
    sitemap_path = out_dir / "sitemap.xml"
    sitemap_path.write_text(sitemap_xml, encoding="utf-8")
    written.append(sitemap_path)

    # ---- robots.txt (ours -- the site's own, distinct from CDFW's). Crawlers
    # only read robots.txt at a host's root. On the github.io project URL
    # this file sits at /ca-fish-planting-alerts/robots.txt, where no crawler
    # looks, so there the sitemap has to be submitted in Search Console
    # (docs/SEARCH-CONSOLE.md). It takes effect as written once the site has
    # a domain of its own (SITE_BASE_URL at a host root).
    robots_txt = f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n"
    robots_path = out_dir / "robots.txt"
    robots_path.write_text(robots_txt, encoding="utf-8")
    written.append(robots_path)

    return written
