"""Generate the static site from a built snapshot.

The one script this module can write is the Google Analytics 4 tag
(DECISIONS 0011, which replaces 0002's "no tracking" for the website only).
It is emitted only when a GA4 measurement ID is configured
(``GA4_MEASUREMENT_ID`` below); with none, no page has a third-party script,
cookies or a third-party request. The other script is the home page's own
``assets/closest.js`` ("closest to me", DECISIONS 0024), written when the
build has water locations: first-party, idle until a button is pressed, and
sending nothing anywhere. The about, privacy and support pages describe
whichever state the build is in. Nothing here ever writes an external
stylesheet host, a pixel or an iframe. The iOS app never carries analytics.

Pages may also carry one ``<script type="application/ld+json">`` block of
schema.org structured data (docs/adr/0013). That is data for search
engines, not JavaScript: a browser never executes it and it makes no
request. It only ever states what the snapshot says -- a planting is a
scheduled *week*, so there is no ``Event``. ``geo`` is given only for a water
whose federal match is a point inside the water, and the page shows it.
"""

from __future__ import annotations

import calendar
import datetime as dt
import itertools
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import jinja2

from . import ads as ads_mod
from . import feeds, guides, indexnow, llms, opendata, share_cards, site_states, weeks
from .snapshot import week_of

TEMPLATES_DIR = Path(__file__).parent / "templates"

# "Closest to me" and "View on map" (DECISIONS 0024): the home page's browser
# script and the static file of coordinates it reads. First-party files, no
# third-party script, tile or tracker.
CLOSEST_JS_FILE = "closest.js"
COORDS_FILE = "water-coords.json"
COORDS_SCHEMA = "trout-truck-water-coords-v1"
COORDS_SOURCE = (
    "U.S. Geological Survey, National Hydrography Dataset and Geographic Names "
    "Information System; every point is in pipeline/data/water_locations.json "
    "with its feature id"
)
# The one place a page may name this script. Tests remove exactly this string
# before they count a page's scripts.
CLOSEST_SCRIPT_TAG = f'<script src="assets/{CLOSEST_JS_FILE}" defer></script>'
OSM_URL = "https://www.openstreetmap.org/"


def map_url(lat: float, lon: float, *, approximate: bool) -> str:
    """A link to a map service's own page for a point. Nothing is embedded: no
    script, tile or iframe loads from the map service until a reader clicks."""
    zoom = 12 if approximate else 14
    return f"{OSM_URL}?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"


def water_coords(snapshot_v2: dict[str, Any] | None) -> dict[str, list[Any]]:
    """slug -> [lat, lon, "w" | "s"] for each California water v2 places.
    "w" is a point inside a lake or reservoir (or GNIS's own point for it);
    "s" is a point on a stream, which is approximate. A water with no single
    federal match has no entry, so nothing is placed that was not matched."""
    if snapshot_v2 is None:
        return {}
    out: dict[str, list[Any]] = {}
    for w in snapshot_v2["waters"]:
        loc = w.get("location")
        if w.get("state") == "CA" and loc:
            kind = "s" if loc["kind"] == "stream_point" else "w"
            out[w["slug"]] = [loc["lat"], loc["lon"], kind]
    return out


# The product name (DECISIONS 0010). It says nothing a searcher types, so
# every title and meta description keeps the descriptive "trout planting" /
# "stocking" phrase next to it -- the brand never replaces the search terms.
SITE_NAME = "Trout Truck"
# Appended after the brand on pages whose own label carries no search terms
# (about, privacy, support, 404).
SITE_TAGLINE = "CA trout planting schedule"

# Where the site has lived since it launched, and what the iOS app's snapshot
# URL and per-water links point at (ios/PlantingCore SnapshotEndpoint.swift;
# builds already in review hard-code it). With no SITE_BASE_URL the site is
# built for this URL, exactly as before a custom domain was possible.
LEGACY_BASE_URL = "https://chelseakr.github.io/ca-fish-planting-alerts"


def custom_domain(base_url: str) -> str | None:
    """The custom domain ``base_url`` names, or None when it names none.

    A custom domain is an ``https://`` URL at the root of a host that is not
    github.io, such as ``https://trouttruck.com``: the build then writes a
    ``CNAME`` file with that host, and the github.io URL can get the redirect
    pages from ``cfpa.legacy`` (DECISIONS 0019). Anything else (the github.io
    default, a URL with a path, ``http://``, a port) is not a custom domain,
    and the build is the one it was before this existed.
    """
    parts = urlsplit(base_url.rstrip("/"))
    if (
        parts.scheme != "https"
        or parts.path
        or parts.query
        or parts.fragment
        or parts.port is not None
        or parts.username is not None
    ):
        return None
    host = parts.hostname
    if not host or host == "github.io" or host.endswith(".github.io"):
        return None
    return host


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


# The iPhone app's App Store listing (DECISIONS 0018: US storefront only).
# The site says nothing about it until the owner turns on APP_STORE_LIVE
# after Apple approves the app (see ``app_store_live_or_false``). Then every
# page carries Safari's Smart App Banner tag and the home and support pages
# show Apple's "Download on the App Store" badge linking here.
APP_STORE_ID = "6818637427"
APP_STORE_CANONICAL_URL = f"https://apps.apple.com/us/app/id{APP_STORE_ID}"
# Apple's preferred black US-English badge, byte for byte as Apple serves it
# (never edited: Apple's guidelines forbid modifying the artwork). Fetched
# 2026-10-02 from Apple's marketing tools, toolbox.marketingtools.apple.com
# /api/v2/badges/download-on-the-app-store/black/en-us, SHA-256
# a26fc5b38380272c92e9019a2eb8b45542a66814b3e2b203772db8904b9fb99f. Used
# under Apple's App Store Marketing Artwork License Agreement, which allows it
# only for an app that is available on the App Store, hence the switch. See
# NOTICE. Natural size 119.66 x 40: shown at 40px tall, Apple's on-screen
# minimum, with a quarter of its height (10px) of clear space around it.
APP_STORE_BADGE_FILE = "app-store-badge.svg"

# The design system's two typefaces (style.css @font-face): Google Fonts'
# own Latin woff2 files, unmodified, under the SIL Open Font License 1.1 (see
# NOTICE). Served from assets/fonts/ rather than fonts.googleapis.com, so the
# site still makes no third-party request when analytics are off. Every page
# preloads them (base.html.jinja), and font-display: swap keeps text visible
# while they load.
FONTS_DIR = "fonts"
FONT_FILES: tuple[str, ...] = (
    "atkinson-hyperlegible-next-latin.woff2",
    "bitter-latin.woff2",
)
FONT_LICENSE_FILES: tuple[str, ...] = (
    "OFL-AtkinsonHyperlegibleNext.txt",
    "OFL-Bitter.txt",
)

# The status badge's words (the design system's StatusBadge). The word is the
# status: a water or county with nothing scheduled says "None scheduled",
# never a 0, a dash or an empty badge. _status_badge.html.jinja reads these.
STATUS_BADGE_WORDS: dict[str, str] = {
    "now": "This week",
    "next": "Next week",
    "none": "None scheduled",
}
# How many waters a county card names before "and N more".
COUNTY_CARD_MAX_WATERS = 5


# Words spelled with a vowel that start with a consonant sound ("a Eureka
# water", "a Union Lake"), and with a consonant that start with a vowel sound
# ("an hour"). Lowercase prefixes; the first match decides.
_CONSONANT_SOUND_PREFIXES = ("eu", "uni", "use", "usu", "uti", "one", "once")
_VOWEL_SOUND_PREFIXES = ("hour", "honest", "honor", "heir")


def indefinite_article(word: str) -> str:
    """ "a" or "an" for ``word``, by its first sound: "an Inyo County water",
    "a Modoc County water". A small rule, not a dictionary: a vowel letter
    takes "an" unless the word starts with one of the consonant-sound
    prefixes above, and a silent "h" in the list takes "an"."""
    w = word.strip().lower()
    if w.startswith(_VOWEL_SOUND_PREFIXES):
        return "an"
    if w.startswith(_CONSONANT_SOUND_PREFIXES):
        return "a"
    return "an" if w[:1] in ("a", "e", "i", "o", "u") else "a"


def schedule_status(*, this_week: bool, next_week: bool) -> str:
    """The badge state for a water or county: on CDFW's schedule this week
    wins over next week, and anything else is "none"."""
    if this_week:
        return "now"
    if next_week:
        return "next"
    return "none"


# The image link previews show (Open Graph and Twitter cards): one 1200x630
# card per kind of page, drawn at build time by share_cards.py. The kind a
# page uses is named in its template (``share_card_kind``); a page that names
# none gets the home card.
SHARE_CARD_DEFAULT_KIND = "home"

# THE LAUNCH SWITCH. This is the committed default for the App Store launch,
# and the one value to change, in one small reviewed pull request, on the day
# Apple approves the app (docs/LAUNCH-CHECKLIST.md). It is False until then.
# One value moves everything together: the Smart App Banner tag, the badge,
# the install links, the MobileApplication JSON-LD and the click event, all
# of which read the one ``app_store_live`` flag the build derives from it
# (tests/test_launch_switch.py fails if any of them disagrees with the flag).
# The APP_STORE_LIVE repository variable still wins when it is set to "true"
# or "false", so a bad launch can be switched off without a deploy of code.
APP_STORE_LIVE_DEFAULT = False

_APP_STORE_LIVE_ON = frozenset({"true"})
_APP_STORE_LIVE_OFF = frozenset({"false"})


def app_store_live_or_false(value: str | None) -> bool:
    """Read the APP_STORE_LIVE switch: "true" is on and "false" is off
    (case-insensitive, surrounding spaces ignored); unset or "" follows
    ``APP_STORE_LIVE_DEFAULT``, which is off until launch day.

    Anything else raises rather than guessing: a typo such as "ture" or
    "yes" must not leave the site silently showing no badge after the owner
    believes it is on, nor turn it on by accident.
    """
    if value is None or value.strip() == "":
        return APP_STORE_LIVE_DEFAULT
    v = value.strip().lower()
    if v in _APP_STORE_LIVE_ON:
        return True
    if v in _APP_STORE_LIVE_OFF:
        return False
    raise ValueError(f"APP_STORE_LIVE {value!r} is neither 'true' nor 'false'")


# Amazon Associates gear links (DECISIONS 0029). Website alone: the iOS app has
# no web view and never carries them. The store ID is the one value to change
# if the account's tag ever does. The links are plain Amazon search URLs, not
# products, so there is no product to go stale and no price or rating to
# state; they are added by the build and nothing else adds an Amazon URL.
AMAZON_ASSOCIATE_TAG = "trouttruck-20"
AMAZON_SEARCH_URL = "https://www.amazon.com/s"
# Amazon's required wording, byte for byte: do not paraphrase it.
AMAZON_ASSOCIATE_DISCLOSURE = "As an Amazon Associate I earn from qualifying purchases."


def gear_endorsement(agency_short_name: str = "CDFW") -> str:
    """The sentence that keeps a commercial link from implying that the
    agency whose data the page shows endorses it (DECISIONS 0029)."""
    return (
        f"The links are {SITE_NAME}'s, not {agency_short_name}'s, and "
        f"{agency_short_name} does not endorse them or Amazon."
    )


AFFILIATE_LINK_REL = "sponsored nofollow noopener"
# Label, then the search terms. Generic categories alone; the data carries no
# lake-or-stream field, so every water gets the same four.
GEAR_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Trout rod and reel combo", "trout rod and reel combo"),
    ("Trout lure and tackle assortment", "trout lure tackle assortment"),
    ("Fishing waders", "fishing waders"),
    ("Landing net for trout", "trout landing net"),
)


def amazon_search_url(terms: str) -> str:
    """An Amazon search URL for ``terms`` carrying the associate tag."""
    return f"{AMAZON_SEARCH_URL}?{urlencode({'k': terms, 'tag': AMAZON_ASSOCIATE_TAG})}"


# The home page's block adds cold-weather gear when the current CDFW week
# starts in November through February (DECISIONS 0040). Only the home page:
# its lastmod moves at every weekly rollover, so a list that changes with the
# month never changes a page whose lastmod says it did not. Water and county
# pages keep the fixed four.
WINTER_MONTHS = frozenset({11, 12, 1, 2})
COLD_MONTH_GEAR: tuple[tuple[str, str], ...] = (
    ("Insulated fishing gloves", "insulated fishing gloves"),
)


def is_winter_week(week_start: str) -> bool:
    """Whether a CDFW week starting on ``week_start`` starts in winter."""
    return bool(week_start) and dt.date.fromisoformat(week_start).month in WINTER_MONTHS


def gear_links(*, cold_months: bool = False) -> list[dict[str, str]]:
    """The gear block's links, built from ``GEAR_CATEGORIES``, plus
    ``COLD_MONTH_GEAR`` when ``cold_months``."""
    pairs = GEAR_CATEGORIES + (COLD_MONTH_GEAR if cold_months else ())
    return [{"label": label, "url": amazon_search_url(terms)} for label, terms in pairs]


# The "What to bring" guide at /gear/ (DECISIONS 0030). Section key, then
# (label, search terms) pairs. Searches for a category, never a product, so
# the page names no brand, price, rating or image. The prose around them lives
# in gear.html.jinja.
GEAR_GUIDE_LINKS: dict[str, tuple[tuple[str, str], ...]] = {
    "rod": (
        ("Ultralight spinning rod and reel combos", "ultralight spinning combo"),
        ("Trout fishing line", "trout fishing line monofilament"),
        ("Small fishing hooks, assorted", "small fishing hooks assortment"),
        ("Split shot sinkers", "split shot sinkers"),
        ("Fishing bobbers", "fishing bobbers"),
    ),
    "bait": (
        ("Trout dough bait", "trout dough bait"),
        ("Trout spinners and spoons", "trout spinners spoons assortment"),
        ("Fishing pliers with a line cutter", "fishing pliers line cutter"),
    ),
    "catfish": (
        ("Catfish rod and reel combos", "catfish rod and reel combo"),
        ("Catfish bait", "catfish bait"),
        ("Circle hooks", "circle hooks"),
    ),
    "cold": (
        ("Insulated gloves", "insulated gloves"),
        ("Insulated bottles", "insulated bottle"),
        ("Fishing waders", "fishing waders"),
        ("Waterproof boots", "waterproof boots"),
    ),
    "sun": (
        ("Polarized sunglasses", "polarized sunglasses"),
        ("Wide-brim sun hats", "wide brim sun hat"),
        ("Sunscreen", "sunscreen spf 30"),
        ("Insect repellent", "insect repellent"),
    ),
    "cooler": (
        ("Coolers", "cooler"),
        ("Fish stringers", "fish stringer"),
        ("Fillet knives", "fillet knife"),
        ("Trout landing nets", "trout landing net"),
    ),
}
# CDFW's own license page; the guide points to it and gives no legal advice.
CDFW_LICENSE_URL = "https://wildlife.ca.gov/Licensing/Fishing"
GEAR_GUIDE_TITLE = "What to bring fishing at a California trout water"
GEAR_GUIDE_DESCRIPTION = (
    "A packing list for a day at a water on California's trout planting "
    "schedule: license reminder, trout and catfish basics, tackle, cold and "
    "sun gear, and a cooler."
)


def gear_guide_links() -> dict[str, list[dict[str, str]]]:
    """The guide's links per section, built from ``GEAR_GUIDE_LINKS``."""
    return {
        key: [
            {"label": label, "url": amazon_search_url(terms)} for label, terms in pairs
        ]
        for key, pairs in GEAR_GUIDE_LINKS.items()
    }


# The license the compiled schedule history is offered under, as a URL, for
# the Dataset structured data on /about/ (docs/adr/0013). Unset on purpose:
# the CC-BY license in docs/LICENSES-AND-ATTRIBUTION.md belongs to a
# different CDFW dataset (the Fishing Guide on data.ca.gov), and the schedule
# itself falls under CDFW's Conditions of Use, which the Dataset already
# cites through `isBasedOn`. Choosing a license for Trout Truck's own
# compilation is the owner's call; until then the markup states none rather
# than one nobody chose. One constant drives the Dataset on /about/, the
# sentence beside it on /about/, and the sentence on /data/.
DATASET_LICENSE_URL = ""

CDFW_NAME = "California Department of Fish and Wildlife"
CDFW_SHORT_NAME = "CDFW"
CDFW_URL = "https://wildlife.ca.gov/"

# A species page lists every water with that species on record only when
# there are this few; a longer list is the county pages' job.
SPECIES_ON_RECORD_LIMIT = 60

REGION_NAME_BY_CODE = {
    "R1": "Northern Region",
    "R2": "North Central Region",
    "R3": "Bay Delta Region",
    "R4": "Central Region",
    "R5": "South Coast Region",
    "R6": "Inland Deserts Region",
}


def region_display_name(snapshot_name: str) -> str:
    """CDFW's region label without the code suffix the snapshot adds:
    "Bay Delta Region (R3)" -> "Bay Delta Region"."""
    return re.sub(r"\s*\(R\d\)$", "", snapshot_name)


def region_slug(snapshot_name: str) -> str:
    """URL segment for a region page, from CDFW's own label:
    "Bay Delta Region (R3)" -> "bay-delta"."""
    name = region_display_name(snapshot_name)
    name = re.sub(r"\s+Region$", "", name)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=jinja2.select_autoescape(["html.jinja"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # A global, not page context, so the imported badge macro can read it.
    env.globals["status_words"] = STATUS_BADGE_WORDS
    # "{{ county|a_an }} County water": "an Inyo", "a Modoc".
    env.filters["a_an"] = lambda word: f"{indefinite_article(word)} {word}"
    return env


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


def _water_view(
    w: dict[str, Any], *, source_week_start: str, shared_name: bool = False
) -> dict[str, Any]:
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
        # True for the few CDFW names that more than one water carries; just
        # those titles keep the county (_water_title).
        "shared_name": shared_name,
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
                "start": p["week"]["start"],
                "species": p["species"],
                "status": p["status"],
                # A listed week before the current one has a /week/ page
                # (weeks.week_entries) that names this water, so the row links
                # it. A removed week is not on that page, and the current or a
                # later week has no page, so neither links.
                "week_page": p["status"] == "listed"
                and p["week"]["start"] < source_week_start,
            }
            for p in plants_sorted
        ],
    }


def _water_status(
    w: dict[str, Any],
    *,
    source_week_start: str,
    checked_on: str,
    recorded_since: str,
) -> dict[str, Any]:
    """The facts behind a water page's status block, from the water's own
    recorded plants and the snapshot's current week, nothing estimated.

    ``checked_on`` is the date CDFW's schedule was last read (an ISO date);
    "days ago" counts from it, never from the build clock, so a given
    snapshot always renders the same words. ``recorded_since`` is the first
    week anywhere in the record ("" when there is none). A week counts only
    when its status is ``listed``: a week CDFW later removed is not "on the
    schedule".
    """
    week = dt.date.fromisoformat(source_week_start)
    next_week = (week + dt.timedelta(days=7)).isoformat()
    listed = sorted(
        {p["week"]["start"] for p in w["plants"] if p["status"] == "listed"}
    )
    past = [d for d in listed if d <= source_week_start]
    later = [d for d in listed if d > next_week]
    last = past[-1] if past else ""
    days_ago: int | None = None
    if last:
        days_ago = (
            dt.date.fromisoformat(checked_on) - dt.date.fromisoformat(last)
        ).days
    since = (
        f"the week of {recorded_since}" if recorded_since else "the start of its record"
    )
    count = len(listed)
    if last == source_week_start:
        last_text = f"this week, the week of {last}"
    elif last:
        last_text = (
            f"the week of {last}, which began "
            f"{_plural(days_ago or 0, 'day', 'days')} ago as of the schedule "
            f"check on {checked_on}"
        )
    elif listed:
        last_text = f"not before this week in the weeks we have recorded since {since}"
    else:
        last_text = (
            f"not on CDFW's schedule in the weeks we have recorded since {since}"
        )
    if last:
        meta = (
            f"Last on CDFW's schedule the week of {last} "
            f"({_plural(days_ago or 0, 'day', 'days')} ago); on the schedule "
            f"{_plural(count, 'week', 'weeks')} since {since}."
        )
    elif listed:
        meta = (
            "Not on CDFW's schedule before this week in the weeks recorded "
            f"since {since}; scheduled the week of {listed[0]}."
        )
    else:
        meta = f"Not on CDFW's schedule in the weeks we have recorded since {since}."
    return {
        "last_week": last,
        "days_ago": days_ago,
        "last_text": last_text,
        "last_sentence": f"{last_text[0].upper()}{last_text[1:]}.",
        "this_week": source_week_start,
        "in_this_week": source_week_start in listed,
        "next_week": next_week,
        "in_next_week": next_week in listed,
        "badge": schedule_status(
            this_week=source_week_start in listed, next_week=next_week in listed
        ),
        "later_week": later[0] if later else "",
        "weeks_on_schedule": count,
        "recorded_since": recorded_since,
        "since_text": since,
        "checked_on": checked_on,
        "meta_phrase": meta,
    }


# A search result shows about 60 characters of a title and about 155 of a
# description; past that the ending is cut. The 2026-10-20 audit found every
# old water title over 60 and 365 of 388 descriptions over 160.
WATER_TITLE_MAX = 60
WATER_DESCRIPTION_MAX = 160


def _water_title(view: dict[str, Any]) -> str:
    """The title: the water and both words people search with, "stocking"
    and "planting" ("planting schedule" is what the old titles said, and the
    waters that rank today rank under it). The county is left out unless
    another water shares the name; the h1, description and breadcrumb carry
    it. A long name drops the species word, then "planting", and never the
    water's name."""
    base = view["place"] if view["shared_name"] else view["name"]
    species = view["species"]
    candidates = (
        f"{base} {species} stocking and planting schedule | {SITE_NAME}",
        f"{base} stocking and planting schedule | {SITE_NAME}",
        f"{base} {species} stocking schedule | {SITE_NAME}",
        f"{base} stocking schedule | {SITE_NAME}",
    )
    for title in candidates:
        if len(title) <= WATER_TITLE_MAX:
            return title
    return candidates[-1]


RELATED_WATERS_TARGET = 8
"""A water page links to this many related waters when the snapshot has that
many: its own counties' waters first, then waters in the same CDFW region."""


def _group_by_region(waters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for w in waters:
        out.setdefault(w["region"], []).append(w)
    return out


def _other_states(snapshot_v2: dict[str, Any] | None) -> list[dict[str, str]]:
    """The non-California states, as ``{name, seg}`` for the visible links to
    their hubs; empty without v2."""
    if snapshot_v2 is None:
        return []
    return [
        {"name": s["name"], "seg": s["code"].lower()}
        for s in snapshot_v2["states"]
        if s["code"] != "CA"
    ]


def _week_gaps(weeks: list[str]) -> list[int]:
    """Whole weeks between each pair of consecutive listed weeks."""
    days = [dt.date.fromisoformat(d) for d in weeks]
    return [(b - a).days // 7 for a, b in itertools.pairwise(days)]


MIN_WEEKS_FOR_MONTHS = 3
"""A water (or a county) shows a by-month count only from this many listed
weeks; fewer is too thin to call a pattern, so nothing is shown."""


def _month_label(ym: str) -> str:
    """ "2026-04" -> "April 2026" (calendar names, independent of locale)."""
    year, month = ym.split("-")
    return f"{calendar.month_name[int(month)]} {year}"


def _month_counts(weeks: list[str]) -> list[tuple[str, int]]:
    """Listed weeks per calendar month, oldest month first. A week belongs to
    the month its start date falls in. Months with no listed week are left
    out: the snapshot cannot say what happened in them, and a missing month
    is not a count of zero."""
    counts: dict[str, int] = {}
    for start in weeks:
        counts[start[:7]] = counts.get(start[:7], 0) + 1
    return sorted(counts.items())


def _most_months(months: list[tuple[str, int]]) -> tuple[list[str], int]:
    """The month labels with the highest count (all of them on a tie, oldest
    first) and that count."""
    if not months:
        return [], 0
    peak = max(n for _, n in months)
    return [_month_label(ym) for ym, n in months if n == peak], peak


def _join_months(labels: list[str]) -> str:
    if len(labels) <= 2:
        return " and ".join(labels)
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def _water_record(w: dict[str, Any]) -> dict[str, Any]:
    """Facts about one water's own recorded weeks, from the snapshot alone.

    Only weeks whose status is ``listed`` count, the same rule as
    ``_water_status``. Nothing here looks at the current week, so these facts
    change only when the water's own record does. The status block already
    says the last week, the count and where the record starts; this adds the
    water's first week, the span and the gaps between listed weeks."""
    weeks = sorted({p["week"]["start"] for p in w["plants"] if p["status"] == "listed"})
    gaps = _week_gaps(weeks)
    median_gap: float | None = None
    if gaps:
        ordered = sorted(gaps)
        mid = len(ordered) // 2
        median_gap = (
            float(ordered[mid])
            if len(ordered) % 2
            else (ordered[mid - 1] + ordered[mid]) / 2
        )
    months = _month_counts(weeks)
    return {
        "count": len(weeks),
        "months": months,
        "first_week": weeks[0] if weeks else "",
        "latest_week": weeks[-1] if weeks else "",
        "span_weeks": sum(gaps),
        "gap_count": len(gaps),
        "median_gap": _weeks_phrase(median_gap) if median_gap is not None else "",
        "min_gap": _weeks_phrase(min(gaps)) if gaps else "",
        "max_gap": _weeks_phrase(max(gaps)) if gaps else "",
        "single_gap": gaps[0] if len(gaps) == 1 else None,
        "region_name": REGION_NAME_BY_CODE.get(w["region"], w["region"]),
    }


def _months_view(
    months: list[tuple[str, int]], *, recorded_since: str
) -> dict[str, Any] | None:
    """The rows and wording for a by-month block, or None below the minimum.
    ``months`` come from listed weeks only (removed entries never reach here)."""
    total = sum(n for _, n in months)
    if total < MIN_WEEKS_FOR_MONTHS:
        return None
    labels, peak = _most_months(months)
    return {
        "rows": [{"month": _month_label(ym), "weeks": n} for ym, n in months],
        "total": total,
        "month_count": len(months),
        "peak_months": _join_months(labels),
        "peak_tied": len(labels) > 1,
        "peak_weeks": peak,
        "since_label": f"week of {recorded_since}",
    }


def _water_months(w: dict[str, Any], *, recorded_since: str) -> dict[str, Any] | None:
    """Listed weeks per calendar month for one water, from its own record."""
    return _months_view(_water_record(w)["months"], recorded_since=recorded_since)


def _county_months(
    members: list[dict[str, Any]], *, recorded_since: str
) -> dict[str, Any] | None:
    """Listed weeks per calendar month summed over a county's waters (a week
    that two waters share counts twice, once per water)."""
    totals: dict[str, int] = {}
    waters = 0
    for w in members:
        months = _water_record(w)["months"]
        waters += bool(months)
        for ym, n in months:
            totals[ym] = totals.get(ym, 0) + n
    view = _months_view(sorted(totals.items()), recorded_since=recorded_since)
    if view is not None:
        view["water_count"] = waters
    return view


# The winter sections (DECISIONS 0040). "Winter" is November through
# February, calendar months, not a CDFW term. The record holds a whole past
# winter, so a county page and the home page can say which waters CDFW's
# schedule listed in it, from the record alone and never as a forecast.
HOME_WINTER_COUNTIES = 10
"""The home page's winter block names this many counties at most, the ones
with the most waters listed last winter."""


def latest_complete_winter(
    source_week_start: str, recorded_since: str
) -> dict[str, str] | None:
    """The most recent November-to-February that ended before the current
    week, when the record covers it from its start; otherwise None.

    A winter counts only when the record begins on or before its November 1,
    so a county with no water listed in it is a fact about the record and
    never a gap in the record read as absence. ``end`` is exclusive (March 1).
    ``shown_from`` is the first CDFW week (Sunday) on or after ``end``: the
    rollover at which this winter became the latest complete one, which a
    page's lastmod counts."""
    if not source_week_start or not recorded_since:
        return None
    current = dt.date.fromisoformat(source_week_start)
    end_year = current.year if current.month >= 3 else current.year - 1
    start = dt.date(end_year - 1, 11, 1)
    end = dt.date(end_year, 3, 1)
    if recorded_since > start.isoformat():
        return None
    shown_from = dt.date.fromisoformat(week_of(end)["start"])
    if shown_from < end:
        shown_from += dt.timedelta(days=7)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": f"November {end_year - 1} through February {end_year}",
        "shown_from": shown_from.isoformat(),
    }


def _winter_weeks(w: dict[str, Any], season: dict[str, str]) -> set[str]:
    """The listed weeks of ``w`` that start inside ``season``."""
    return {
        p["week"]["start"]
        for p in w["plants"]
        if p["status"] == "listed"
        and season["start"] <= p["week"]["start"] < season["end"]
    }


def _county_winter(
    members: list[dict[str, Any]], season: dict[str, str] | None
) -> dict[str, Any] | None:
    """A county's waters listed in ``season``, most listed weeks first, then
    by name; None when no winter is covered. An empty ``rows`` means the
    record covers that winter and no county water was listed in it."""
    if season is None:
        return None
    rows: list[dict[str, Any]] = []
    all_weeks: set[str] = set()
    for w in members:
        listed = _winter_weeks(w, season)
        if listed:
            all_weeks |= listed
            rows.append({"slug": w["slug"], "name": w["name"], "weeks": len(listed)})
    rows.sort(key=lambda r: (r["name"], r["slug"]))
    rows.sort(key=lambda r: r["weeks"], reverse=True)
    return {"label": season["label"], "rows": rows, "week_count": len(all_weeks)}


def _home_winter(
    waters: list[dict[str, Any]],
    season: dict[str, str] | None,
    county_link: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    """Last winter statewide: how many waters and counties CDFW's schedule
    listed, and the counties with the most listed waters (at most
    ``HOME_WINTER_COUNTIES``, ties by name). None when no winter is covered
    or nothing was listed in it, so the home page never shows a zero."""
    if season is None:
        return None
    by_county: dict[str, set[str]] = {}
    listed_ids: set[str] = set()
    for w in waters:
        if not _winter_weeks(w, season):
            continue
        listed_ids.add(w["id"])
        for c in w["counties"]:
            if c in county_link:
                by_county.setdefault(c, set()).add(w["id"])
    if not listed_ids:
        return None
    ranked = sorted(by_county.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    counties: list[dict[str, Any]] = [
        {**county_link[c], "count": len(ids)} for c, ids in ranked
    ]
    return {
        "label": season["label"],
        "water_count": len(listed_ids),
        "county_count": len(counties),
        "counties": counties[:HOME_WINTER_COUNTIES],
    }


def _weeks_phrase(n: float) -> str:
    whole = int(n) if n == int(n) else n
    return f"{whole} {'week' if whole == 1 else 'weeks'}"


def _region_related(
    ctx: _PageContext, w: dict[str, Any], taken: set[str], want: int
) -> list[dict[str, Any]]:
    """Up to ``want`` waters of ``w``'s CDFW region that are not ``w`` and not
    in ``taken``, so a water with few county neighbors still links to others.
    The list starts after ``w`` in name order and wraps, so the links spread
    over the region's waters instead of piling onto its first few."""
    if want <= 0:
        return []
    pool = sorted(
        ctx.waters_by_region.get(w["region"], []), key=lambda s: (s["name"], s["slug"])
    )
    ids = [s["id"] for s in pool]
    start = ids.index(w["id"]) + 1 if w["id"] in ids else 0
    ring = pool[start:] + pool[:start]
    return [s for s in ring if s["id"] != w["id"] and s["id"] not in taken][:want]


def _water_description(view: dict[str, Any], *, source_week_label: str) -> str:
    """The meta description: the water, its county, the stocking wording
    people search with, then the schedule and the last-listed date, ahead of
    the cut a result makes. A water with nothing current says when it was
    last scheduled and what the page still has, and leaves the "none this
    week" sentence to the page body."""
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
        status = f"last scheduled the {view['last_listed_label']}."
    else:
        status = "no week currently listed."
    weeks = _plural(view["listed_week_count"], "week", "weeks")
    head = f"{view['place']} {view['species']} stocking schedule: {status}"
    # Longest tail that keeps the whole description within the limit.
    tails = (
        f" CDFW planting history, {weeks} on record, and a calendar feed.",
        " CDFW planting history and a calendar feed.",
        " CDFW planting history.",
    )
    for tail in tails:
        if len(head) + len(tail) <= WATER_DESCRIPTION_MAX:
            return head + tail
    return head


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
    nothing_current: bool = False,
) -> str:
    """The date this water's page last changed in substance, for sitemap.xml:
    its own data (``_water_data_lastmod``), or the day a water sharing one of
    its counties first appeared, because the page links to every such water
    by name. Siblings are listed by name only, not with their weeks, so a
    sibling's new listing does not change this page.

    The exception is a water with nothing current: its page also lists the
    siblings that are scheduled this week or later (``_scheduled_siblings``),
    so a sibling's own data change, or its rollover, changes this page too."""
    dates = [_water_data_lastmod(w, source_week_start=source_week_start)]
    dates += [_water_first_seen(s) for s in siblings or []]
    if nothing_current:
        dates += [
            _water_data_lastmod(s, source_week_start=source_week_start)
            for s in siblings or []
        ]
    return max(dates)


def _scheduled_siblings(
    ctx: _PageContext, county: str, w: dict[str, Any]
) -> list[dict[str, str]]:
    """The other waters in ``county`` that CDFW has scheduled for this week or
    later, each with the wording the page can stand behind: from the snapshot
    alone, never a guess about what will be stocked."""
    out = []
    for s in sorted(ctx.waters_by_county[county], key=lambda s: (s["name"], s["slug"])):
        if s["id"] == w["id"]:
            continue
        v = ctx.views[s["id"]]
        if v["this_week"]:
            when = f"scheduled this week, the {ctx.source_week_label}"
        elif v["next_listed_label"]:
            when = f"next scheduled the {v['next_listed_label']}"
        else:
            continue
        out.append({"slug": s["slug"], "name": s["name"], "when": when})
    return out


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


def _ld_water(
    w: dict[str, Any], *, page_url: str, point: list[Any] | None = None
) -> dict[str, Any]:
    """The water itself. BodyOfWater (a schema.org Place) is true of every
    CDFW planting water, lake, reservoir, creek or river section alike; the
    finer subtypes would be a guess from the name. ``geo`` only for a water
    whose point is inside the water itself (``point`` kind "w") and that the
    page shows as coordinates; a stream's point is approximate and a stream is
    not at one place, so a stream gets none, and a water with no single
    federal match gets none either."""
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
    if point is not None and point[2] == "w":
        node["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": point[0],
            "longitude": point[1],
        }
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


def _ld_app(base_url: str, listing_url: str) -> dict[str, Any]:
    """The iPhone app, as a MobileApplication. Built when the App Store
    switch is on, because before Apple approves the app there is nothing to
    install and no page may say so. States what the listing and the site's
    own copy state: iOS, free to install, the App Store URL. No rating,
    review count or download count: none is known here, so none is written."""
    return {
        "@type": "MobileApplication",
        "@id": f"{base_url}/#app",
        "name": SITE_NAME,
        "operatingSystem": "iOS",
        "applicationCategory": "SportsApplication",
        "description": (
            "Local notifications when a favorite water appears in CDFW's "
            "new week of the trout planting schedule. No account; alerts "
            "happen on the device."
        ),
        "url": listing_url,
        "downloadUrl": listing_url,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }


def _ld_faq(page_url: str, items: list[tuple[str, str]]) -> dict[str, Any]:
    """A FAQPage whose questions and answers are the visible ones, word for
    word (a test compares them with the rendered support page)."""
    return {
        "@type": "FAQPage",
        "@id": f"{page_url}#faq",
        "url": page_url,
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in items
        ],
    }


# The two app questions on the support page. The first of each pair is the
# live wording (the app is on the App Store); the second is what is true
# before launch, when the app is not on the App Store yet.
_APP_ALERTS_FAQ_LIVE = (
    "Why didn't the app alert me?",
    "Alerts are part of the one-time in-app purchase; favoriting and "
    "browsing are free. Notifications must be allowed for the app "
    "(Settings \u2192 Notifications). The app checks for a new schedule in "
    "the background, and iOS decides when that happens. Background App "
    "Refresh must be on for the app, Low Power Mode pauses it, and "
    "swiping the app away can stop it until you open it again. CDFW "
    "updates weekly, so an alert arrives within the week a water is "
    "added, not the minute it is.",
)
_APP_ALERTS_FAQ_NOT_YET = (
    "How will the app's alerts work?",
    "The iPhone app is not in the App Store yet, so it sends no alerts "
    "today. Once it is available: alerts are part of the one-time in-app "
    "purchase; favoriting and browsing are free. Notifications must be "
    "allowed for the app (Settings \u2192 Notifications). The app checks for "
    "a new schedule in the background, and iOS decides when that happens. "
    "Background App Refresh must be on for the app, Low Power Mode pauses "
    "it, and swiping the app away can stop it until you open it again. "
    "CDFW updates weekly, so an alert arrives within the week a water is "
    "added, not the minute it is.",
)
_APP_RESTORE_FAQ_LIVE = (
    "How do I restore my purchase on a new phone?",
    "In the app, open About \u2192 Unlock full access \u2192 Restore "
    "purchases. Use the same Apple Account you bought it with. There "
    "is no account with this app to sign in to.",
)
_APP_RESTORE_FAQ_NOT_YET = (
    "How will restoring a purchase on a new phone work?",
    "The iPhone app is not in the App Store yet, so there is nothing to "
    "restore today. Once it is available, open About \u2192 Unlock full "
    "access \u2192 Restore purchases in the app and use the same Apple "
    "Account you bought it with. There is no account with this app to "
    "sign in to.",
)


def _support_faq(
    source_fetched_label: str, *, app_store_live: bool = False
) -> list[tuple[str, str]]:
    """The support page's questions and answers as plain text. Each answer is
    the visible answer with its links reduced to their text. The last two
    are about the iPhone app, so they follow the launch switch: until the app
    is on the App Store they say so (support.html.jinja holds the same words)."""
    return [
        (
            "Where does the schedule come from?",
            "From the California Department of Fish and Wildlife's Fish "
            "Planting Schedule, checked once a day. The schedule was last "
            f"checked {source_fetched_label}. CDFW updates it weekly and lists "
            "plants by week, never by day, on purpose. Plants are subject to "
            "change, so everything here is scheduled, not confirmed.",
        ),
        (
            "Why does this site show more weeks than CDFW's page?",
            "CDFW's page only shows about a year. This site keeps every week "
            "it has recorded, so a water's history keeps growing after CDFW's "
            "page has moved on.",
        ),
        (
            "How do I subscribe to a water's calendar?",
            "Every water page links to a calendar feed (.ics). Copy that link "
            "and add it as a subscribed calendar: on iPhone, in the Calendar "
            "app's settings under Add Account \u2192 Other \u2192 Add Subscribed "
            "Calendar; in Google Calendar, under Other calendars \u2192 From URL. "
            "Each event spans the whole week CDFW scheduled.",
        ),
        _APP_ALERTS_FAQ_LIVE if app_store_live else _APP_ALERTS_FAQ_NOT_YET,
        _APP_RESTORE_FAQ_LIVE if app_store_live else _APP_RESTORE_FAQ_NOT_YET,
    ]


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


def _open_data_states(
    snap_v2: dict[str, Any], files: list[opendata.OpenFile], *, base_url: str
) -> list[dict[str, Any]]:
    """What /data/ shows for each state: its source, terms, dates and files,
    all read from the snapshot the files were built from."""
    out = []
    for state in snap_v2["states"]:
        mine = [f for f in files if f.state == state["code"]]
        history = [
            (p["period"]["start"], p["period"]["end"])
            for w in snap_v2["waters"]
            if w["state"] == state["code"]
            for p in w["plants"]
        ]
        out.append(
            {
                "code": state["code"],
                "name": state["name"],
                "agency": state["agency"],
                "source_name": state["source"]["name"],
                "source_url": state["source"]["url"],
                "attribution": state["attribution"],
                "disclaimer": state["disclaimer"],
                "license_summary": state["license"]["summary"],
                "terms_url": opendata.terms_url(state),
                "updated": state["source"]["fetched_at"][:10],
                "current_week_label": state["current_week"]["label"],
                "precisions": state["date_precisions"],
                "semantics": state["semantics"],
                "coverage": (
                    (min(h[0] for h in history), max(h[1] for h in history))
                    if history
                    else None
                ),
                "files": [
                    {
                        "kind": f.kind,
                        "fmt": f.fmt,
                        "records": f.records,
                        "path": f.path,
                        "url": f"{base_url}/{f.path}",
                    }
                    for f in mine
                ],
            }
        )
    return out


def _ld_open_dataset(
    entry: dict[str, Any], *, base_url: str, license_url: str | None
) -> dict[str, Any]:
    """One state's CSV and JSON files as a Dataset, on /data/. Same pattern
    as the Dataset on /about/: the source and its terms through
    ``isBasedOn``, the attribution as ``creditText``, and ``license`` only
    when the owner has chosen one (``DATASET_LICENSE_URL``)."""
    node: dict[str, Any] = {
        "@type": "Dataset",
        "@id": f"{base_url}/data/#{entry['code'].lower()}",
        "name": (
            f"{entry['name']} fish planting schedule, current and history "
            f"(CSV and JSON), from {entry['agency']['short_name']}"
        ),
        "description": (
            f"{entry['name']} fish planting records from the "
            f"{entry['agency']['name']}'s published schedule, as recorded by "
            f"{SITE_NAME}: the water, county, species, the scheduled period, "
            "and when each record was first and last seen. A current file "
            "lists this week and later; a history file lists every record "
            "observed. Entries are scheduled, not confirmed, and the agency "
            "can change them. Stable columns are documented on the page."
        ),
        "url": f"{base_url}/data/#{entry['code'].lower()}",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": SITE_NAME, "url": f"{base_url}/"},
        "isBasedOn": {
            "@type": "CreativeWork",
            "name": entry["source_name"],
            "url": entry["source_url"],
            "license": entry["terms_url"],
            "creator": {
                "@type": "GovernmentOrganization",
                "name": entry["agency"]["name"],
                "url": entry["agency"]["url"],
            },
        },
        "creditText": entry["attribution"]["text"],
        "keywords": [
            entry["name"],
            entry["agency"]["short_name"],
            "fish planting schedule",
            "trout stocking",
        ],
        "variableMeasured": [c[0] for c in opendata.COLUMNS],
        "spatialCoverage": {"@type": "State", "name": entry["name"]},
        "dateModified": entry["updated"],
        "distribution": [
            {
                "@type": "DataDownload",
                "name": f"{entry['code']} {f['kind']}, {f['fmt'].upper()}",
                "encodingFormat": "text/csv"
                if f["fmt"] == "csv"
                else "application/json",
                "contentUrl": f["url"],
            }
            for f in entry["files"]
        ],
    }
    if entry["coverage"]:
        node["temporalCoverage"] = "/".join(entry["coverage"])
    if license_url:
        node["license"] = license_url
    return node


def _write_open_data(
    env: jinja2.Environment,
    snapshot_v2: dict[str, Any],
    out_dir: Path,
    written: list[Path],
    *,
    base_url: str,
    common: dict[str, Any],
    license_url: str | None,
) -> str:
    """Write /data/ and the files it lists. Returns the data's last-updated
    date (the newest state's last successful check), for the sitemap.
    California is always in v2."""
    open_files = opendata.build_files(snapshot_v2, base_url=base_url)
    for f in open_files:
        f_path = out_dir / f.path
        f_path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" keeps the CSV's CRLF line endings as written.
        with f_path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(f.text)
        written.append(f_path)
    open_states = _open_data_states(snapshot_v2, open_files, base_url=base_url)
    data_updated = str(max(e["updated"] for e in open_states))
    data_html = env.get_template("data.html.jinja").render(
        title=f"Open data: CSV and JSON downloads | {SITE_NAME}, {SITE_TAGLINE}",
        description=(
            "Download the fish planting schedule this site mirrors as CSV and "
            "JSON: this week and later, and the full weekly history, with a "
            "documented column list. Source: CDFW; terms: see CDFW Conditions "
            "of Use."
        ),
        canonical_url=f"{base_url}/data/",
        root="../",
        **common,
        structured_data=_ld_graph(
            *(
                _ld_open_dataset(e, base_url=base_url, license_url=license_url)
                for e in open_states
            )
        ),
        states=open_states,
        columns=opendata.COLUMNS,
        schema_version=opendata.SCHEMA_VERSION,
        data_dir=opendata.DATA_DIR,
        data_updated=data_updated,
        dataset_license_url=license_url,
    )
    _write_page(out_dir, "data", data_html, written)
    return data_updated


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


_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def ensure_unique_titles(out_dir: Path, written: list[Path]) -> list[str]:
    """The last guard against two pages sharing a <title>, which a search
    engine reads as one page said twice. Never fails the build (owner
    decision 2026-10-29): each page in a clash gets its own path appended to
    its <title> ("... | Trout Truck (ny/water/foo/)"), short, stable and
    unique, and a warning names every page. Water pages are told apart
    earlier (site_states.shared_names, site_states.qualifiers), so on
    today's data this changes nothing. Returns the pages it changed."""
    pages: dict[str, list[Path]] = {}
    for path in written:
        if path.suffix != ".html":
            continue
        m = _TITLE_RE.search(path.read_text(encoding="utf-8"))
        if m:
            title = " ".join(m.group(1).split())
            pages.setdefault(title, []).append(path)
    changed: list[str] = []
    lines: list[str] = []
    for title, paths in sorted(pages.items()):
        if len(paths) < 2:
            continue
        for path in sorted(paths):
            rel = path.relative_to(out_dir).parent.as_posix()
            label = f"{rel}/" if rel != "." else path.name
            html = path.read_text(encoding="utf-8")
            m = _TITLE_RE.search(html)
            if m is None:  # pragma: no cover - every page in `pages` has one
                continue
            new = f"<title>{m.group(1).strip()} ({label})</title>"
            path.write_text(html[: m.start()] + new + html[m.end() :], encoding="utf-8")
            changed.append(label)
            lines.append(f"{label}: {title!r}")
    if lines:
        site_states.warn_titles(
            f"{len(changed)} page(s) shared a <title>; each now ends with its path",
            lines,
        )
    return changed


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
    source_checked_on: str = ""
    waters_by_region: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    coords: dict[str, list[Any]] = field(default_factory=dict)
    recorded_since: str = ""

    @property
    def home_crumb(self) -> tuple[str, str]:
        return (SITE_NAME, f"{self.base_url}/")

    @property
    def counties_crumb(self) -> tuple[str, str]:
        return ("Counties", f"{self.base_url}/county/")


def _water_map(point: list[Any] | None) -> dict[str, Any] | None:
    """What the water page shows for a placed water, or None."""
    if point is None:
        return None
    approximate = point[2] == "s"
    return {
        "lat": point[0],
        "lon": point[1],
        "approximate": approximate,
        "url": map_url(point[0], point[1], approximate=approximate),
    }


def _render_water_page(
    ctx: _PageContext, w: dict[str, Any], *, recorded_since: str
) -> str:
    """Write one water's page and calendar feed. Returns its lastmod."""
    base_url = ctx.base_url
    view = ctx.views[w["id"]]
    page_url = f"{base_url}/water/{w['slug']}/"

    def by_name(s: dict[str, Any]) -> tuple[str, str]:
        return (s["name"], s["slug"])

    # Waters sharing a county: the only nearness the page claims (not every
    # water has a location), so it says "other <county> County waters", never
    # "nearby".
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
    same_county_count = len(siblings)
    region_related = _region_related(
        ctx,
        w,
        set(siblings),
        RELATED_WATERS_TARGET - same_county_count,
    )
    # A water with nothing on the schedule says what is on it in its own
    # counties, so the page answers the visit instead of ending at "none".
    scheduled_elsewhere = (
        [
            {**ctx.county_link[c], "waters": _scheduled_siblings(ctx, c, w)}
            for c in w["counties"]
        ]
        if view["nothing_current"]
        else []
    )
    # The visible breadcrumb, and the BreadcrumbList that mirrors it, go
    # through the first county: the one the snapshot's region comes from.
    primary = w["counties"][0]
    trail = [
        ctx.home_crumb,
        ctx.counties_crumb,
        (f"{primary} County", f"{base_url}/county/{county_slug(primary)}/"),
        (w["name"], page_url),
    ]
    title = _water_title(view)
    point = ctx.coords.get(w["slug"])
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
            _ld_water(w, page_url=page_url, point=point),
        ),
        breadcrumb=_relative_trail(trail, base_url=base_url, root="../../"),
        water=view,
        water_map=_water_map(point),
        gear_links=gear_links(),
        affiliate_rel=AFFILIATE_LINK_REL,
        scheduled_elsewhere=scheduled_elsewhere,
        other_waters_by_county=other_waters_by_county,
        region_related=[{"slug": r["slug"], "name": r["name"]} for r in region_related],
        region_name=view["region_name"],
        water_record=_water_record(w),
        water_months=_water_months(w, recorded_since=recorded_since),
        source_week_label=ctx.source_week_label,
        source_fetched_label=ctx.source_fetched_label,
        recorded_since_label=f"week of {recorded_since}" if recorded_since else "",
        # Facts for _water_status.html.jinja. water_status["meta_phrase"] is a
        # truthful sentence a description may use; nothing here sets one.
        water_status=_water_status(
            w,
            source_week_start=ctx.source_week_start,
            checked_on=ctx.source_checked_on,
            recorded_since=recorded_since,
        ),
    )
    _write_page(ctx.out_dir, f"water/{w['slug']}", html, ctx.written)

    ics_path = ctx.out_dir / "water" / w["slug"] / "feed.ics"
    ics_path.write_text(
        build_water_ics(water=w, base_url=page_url, species=view["species"]),
        encoding="utf-8",
    )
    ctx.written.append(ics_path)

    # The region links are navigation, not this water's data: they are left
    # out of the lastmod (docs: a new water in the region can change them
    # without moving this date, a known under-report).
    return _water_lastmod(
        w,
        source_week_start=ctx.source_week_start,
        siblings=list(siblings.values()),
        nothing_current=view["nothing_current"],
    )


COUNTY_RECENT_WEEKS = 4
"""A county page lists this many of its most recent past weeks with a listed
water, newest first, when the record has that many."""

COUNTY_DESCRIPTION_MAX = WATER_DESCRIPTION_MAX


def _county_recent_weeks(
    members: list[dict[str, Any]], *, source_week_start: str
) -> dict[str, Any]:
    """The county's most recent past weeks with a listed plant, at most
    ``COUNTY_RECENT_WEEKS`` of them, as one row per listed plant (week, water,
    species), newest week first and then by name: the same shape as the
    later-weeks table.

    "Past" means before the snapshot's current week, the same rule as the
    /week/ pages (weeks.week_entries), so every week here has a page to link.
    A removed entry is never shown. A county with no such week gets no rows,
    and the page says so in words, not as a zero."""
    listed = [
        (p["week"]["start"], w, p["species"])
        for w in members
        for p in w["plants"]
        if p["status"] == "listed" and p["week"]["start"] < source_week_start
    ]
    weeks = sorted({start for start, _, _ in listed}, reverse=True)
    kept = set(weeks[:COUNTY_RECENT_WEEKS])
    rows = [
        {"week": start, "slug": w["slug"], "name": w["name"], "species": species}
        for start, w, species in listed
        if start in kept
    ]
    rows.sort(key=lambda r: (r["name"], r["slug"], r["species"]))
    rows.sort(key=lambda r: r["week"], reverse=True)
    return {"rows": rows, "week_count": len(kept)}


def _join_names(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _fit_names(prefix: str, names: list[str], suffix: str, limit: int) -> str | None:
    """``prefix`` + as many of ``names`` as fit + ``suffix`` within ``limit``,
    the rest counted as "and N more"; None when not even one name fits."""
    for keep in range(len(names), 0, -1):
        rest = len(names) - keep
        shown = names[:keep]
        listed = (
            _join_names(shown) if rest == 0 else f"{', '.join(shown)} and {rest} more"
        )
        text = f"{prefix}{listed}{suffix}"
        if len(text) <= limit:
            return text
    return None


def _county_description(
    county: str,
    *,
    species: str,
    water_count: int,
    this_week_names: list[str],
    source_week_label: str,
    next_week: str,
    next_names: list[str],
    last_week: str,
) -> str:
    """The meta description: the county, the stocking wording people search
    with, then what the schedule says now, from the snapshot alone.

    This week's waters, by name, when there are any; otherwise the soonest
    later week and its waters; otherwise the last week a county water was
    listed. A county with none of those says no week is listed. The current
    week's date appears only when a water is listed for it, so the
    description changes at a rollover only for a county whose lastmod already
    counts that rollover (``_rollover_sensitive``)."""
    head = f"{county} County {species} stocking schedule: "
    history = (
        " CDFW planting history for the water."
        if water_count == 1
        else f" CDFW planting history for its {water_count} waters."
    )
    # Longest tail first; a water's name outranks the tail, so the tail
    # shortens before the names give way to a count.
    tails = (history, " CDFW planting history.", "")
    if this_week_names:
        prefix = f"{head}scheduled this week, the {source_week_label}, at "
        names = this_week_names
    elif next_week:
        prefix = f"{head}none scheduled this week; next the week of {next_week}, at "
        names = next_names
    else:
        prefix, names = "", []
    if names:
        for tail in tails:
            fitted = _fit_names(prefix, names, f".{tail}", COUNTY_DESCRIPTION_MAX)
            if fitted is not None:
                return fitted
        return _with_tail(f"{prefix}{_plural(len(names), 'water', 'waters')}.", tails)
    if last_week:
        return _with_tail(
            f"{head}nothing scheduled this week or later; last scheduled "
            f"the week of {last_week}.",
            tails,
        )
    return _with_tail(f"{head}no week currently listed.", tails)


def _with_tail(body: str, tails: tuple[str, ...]) -> str:
    """``body`` with the longest of ``tails`` that keeps it within
    ``COUNTY_DESCRIPTION_MAX``; ``body`` alone when none does."""
    for tail in tails:
        if len(body) + len(tail) <= COUNTY_DESCRIPTION_MAX:
            return body + tail
    return body


def _county_card(
    this_week_rows: list[dict[str, Any]],
    later_rows: list[dict[str, Any]],
    *,
    next_week_start: str,
) -> dict[str, Any]:
    """The county page's first answer (the design system's CountyCard): its
    badge state and the waters behind it, one entry per water, alphabetical,
    the first COUNTY_CARD_MAX_WATERS by name and a count of the rest. With
    nothing this week or next the list is empty and the page says so in
    words; the card never shows a count of zero."""
    this_week = {r["slug"]: r["name"] for r in this_week_rows}
    next_week = {
        r["slug"]: r["name"] for r in later_rows if r["week"] == next_week_start
    }
    state = schedule_status(this_week=bool(this_week), next_week=bool(next_week))
    chosen = this_week if state == "now" else next_week
    waters = sorted(
        ({"slug": s, "name": n} for s, n in chosen.items()),
        key=lambda w: (w["name"], w["slug"]),
    )
    return {
        "state": state,
        "count": len(waters),
        "waters": waters[:COUNTY_CARD_MAX_WATERS],
        "more": max(0, len(waters) - COUNTY_CARD_MAX_WATERS),
        "next_week": next_week_start,
        "also_next": state == "now" and bool(next_week),
    }


def _render_county_page(
    ctx: _PageContext,
    county: str,
    *,
    this_week: list[dict[str, Any]],
    region_name: str,
    region_link: dict[str, str] | None = None,
    region_counties: list[dict[str, str]] | None = None,
) -> str:
    """Write one county's page. Returns its URL.

    ``region_counties`` are the other counties of the same CDFW region that
    have a page, for the "more counties" links; the caller counts the day
    each first appeared in this page's lastmod."""
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
    # Past and upcoming are kept apart. A week after the snapshot's current
    # one is upcoming; everything else listed is this week or earlier. The
    # history table reports each water's latest week through this week, so a
    # plant scheduled for a later week never hides one that is current.
    rows: list[dict[str, Any]] = []
    later_rows: list[dict[str, Any]] = []
    for w in members:
        view = ctx.views[w["id"]]
        listed = [p for p in w["plants"] if p["status"] == "listed"]
        through_now = [
            p["week"]["start"]
            for p in listed
            if p["week"]["start"] <= ctx.source_week_start
        ]
        rows.append(
            {
                "slug": view["slug"],
                "name": view["name"],
                "latest_start": max(through_now) if through_now else "",
                "weeks": view["listed_week_count"],
            }
        )
        later_rows.extend(
            {
                "slug": view["slug"],
                "name": view["name"],
                "week": p["week"]["start"],
                "species": p["species"],
            }
            for p in listed
            if p["week"]["start"] > ctx.source_week_start
        )
    # Most recent first, ties alphabetical (two stable sorts); a water with
    # nothing through this week (empty string) sorts last.
    rows.sort(key=lambda r: (r["name"], r["slug"]))
    rows.sort(key=lambda r: r["latest_start"], reverse=True)
    # Soonest week first, then alphabetical.
    later_rows.sort(key=lambda r: (r["week"], r["name"], r["slug"], r["species"]))
    trail = [ctx.home_crumb, ctx.counties_crumb, (f"{county} County", page_url)]
    title = (
        f"{county} County {species} planting schedule: fish plants this week"
        f" | {SITE_NAME}"
    )
    next_week = later_rows[0]["week"] if later_rows else ""
    next_names = sorted(
        {r["name"] for r in later_rows if r["week"] == next_week},
    )
    last_week = max((r["latest_start"] for r in rows), default="")
    html = ctx.env.get_template("county.html.jinja").render(
        county_card=_county_card(
            this_week_rows,
            later_rows,
            next_week_start=(
                dt.date.fromisoformat(ctx.source_week_start) + dt.timedelta(days=7)
            ).isoformat(),
        ),
        title=title,
        description=_county_description(
            county,
            species=species,
            water_count=len(members),
            # One name per water, even when it has two species this week.
            this_week_names=sorted({r["name"] for r in this_week_rows}),
            source_week_label=ctx.source_week_label,
            next_week=next_week,
            next_names=next_names,
            last_week=last_week,
        ),
        canonical_url=page_url,
        root="../../",
        **ctx.common,
        feed_path=feeds.feed_path("county", county_slug(county)),
        feed_title=f"{county} County trout schedule, {SITE_NAME} (Atom)",
        feed_scope=f"{county} County",
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
        region_link=region_link,
        water_count=len(members),
        county_months=_county_months(members, recorded_since=ctx.recorded_since),
        county_winter=_county_winter(
            members, latest_complete_winter(ctx.source_week_start, ctx.recorded_since)
        ),
        this_week_rows=this_week_rows,
        later_rows=later_rows,
        recent_weeks=_county_recent_weeks(
            members, source_week_start=ctx.source_week_start
        ),
        region_counties=region_counties or [],
        rows=rows,
        source_week_label=ctx.source_week_label,
        source_fetched_label=ctx.source_fetched_label,
        gear_links=gear_links(),
        affiliate_rel=AFFILIATE_LINK_REL,
    )
    _write_page(ctx.out_dir, f"county/{county_slug(county)}", html, ctx.written)
    return page_url


def _render_gear_page(ctx: _PageContext) -> str:
    """Write /gear/, the "What to bring" guide. Returns its URL."""
    page_url = f"{ctx.base_url}/gear/"
    trail = [ctx.home_crumb, ("What to bring", page_url)]
    html = ctx.env.get_template("gear.html.jinja").render(
        title=f"{GEAR_GUIDE_TITLE} | {SITE_NAME}, {SITE_TAGLINE}",
        description=GEAR_GUIDE_DESCRIPTION,
        canonical_url=page_url,
        root="../",
        **ctx.common,
        structured_data=_ld_graph(
            _ld_page(
                "WebPage",
                page_url=page_url,
                name=GEAR_GUIDE_TITLE,
                base_url=ctx.base_url,
                about={"@type": "State", "name": "California"},
            ),
            _ld_breadcrumb(page_url, trail),
        ),
        breadcrumb=_relative_trail(trail, base_url=ctx.base_url, root="../"),
        guide=gear_guide_links(),
        affiliate_rel=AFFILIATE_LINK_REL,
        cdfw_license_url=CDFW_LICENSE_URL,
    )
    _write_page(ctx.out_dir, "gear", html, ctx.written)
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
        # "DFG": CDFW's name before 2013, which people still search with;
        # the home page's description says the same.
        description=(
            f"CDFW's (formerly DFG) {species} planting schedule by county: "
            "every California county with a water on it, by region, with this "
            "week's plants and stocking history."
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
        gear_links=gear_links(),
        affiliate_rel=AFFILIATE_LINK_REL,
    )
    _write_page(ctx.out_dir, "county", html, ctx.written)
    return page_url


def _render_region_page(
    ctx: _PageContext,
    region: dict[str, Any],
    *,
    all_regions: list[dict[str, Any]],
    waters: list[dict[str, Any]],
    counties: list[dict[str, Any]],
) -> str:
    """Write one CDFW region's page (/region/<slug>/). Returns its URL.

    Lists the waters CDFW has scheduled for the snapshot's current week and
    for the week after it, the region's counties, and the per-water calendar
    feeds (there is no county or region feed). The region's name is CDFW's
    own label from the snapshot, never a place the site names itself.
    """
    name = region_display_name(region["name"])
    page_url = f"{ctx.base_url}/region/{region['slug']}/"
    next_week = (
        dt.date.fromisoformat(ctx.source_week_start) + dt.timedelta(days=7)
    ).isoformat()
    next_week_label = f"week of {next_week}"

    def rows_for(week_start: str) -> list[dict[str, Any]]:
        out = []
        for w in waters:
            species = {
                p["species"]
                for p in w["plants"]
                if p["status"] == "listed" and p["week"]["start"] == week_start
            }
            if species:
                out.append(
                    {
                        "slug": w["slug"],
                        "name": w["name"],
                        "species": species_phrase(species),
                        "county_links": [ctx.county_link[c] for c in w["counties"]],
                    }
                )
        return sorted(out, key=lambda r: (r["name"], r["slug"]))

    this_week_rows = rows_for(ctx.source_week_start)
    next_week_rows = rows_for(next_week)
    trail = [ctx.home_crumb, (name, page_url)]
    title = f"{name} trout stocking schedule | {SITE_NAME}"
    description = (
        f"Waters on CDFW's trout stocking schedule in its {name}: "
        f"{_plural(len(counties), 'county', 'counties')} and "
        f"{_plural(len(waters), 'water', 'waters')}, scheduled the "
        f"{ctx.source_week_label} and the week after."
    )
    html = ctx.env.get_template("region.html.jinja").render(
        title=title,
        description=description,
        canonical_url=page_url,
        root="../../",
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
        breadcrumb=_relative_trail(trail, base_url=ctx.base_url, root="../../"),
        region_name=name,
        feed_path=feeds.feed_path("region", region["slug"]),
        feed_title=f"{name} trout schedule, {SITE_NAME} (Atom)",
        feed_scope=name,
        county_count=len(counties),
        water_count=len(waters),
        counties=counties,
        this_week_rows=this_week_rows,
        next_week_rows=next_week_rows,
        next_week_label=next_week_label,
        other_regions=[r for r in all_regions if r["slug"] != region["slug"]],
        source_week_label=ctx.source_week_label,
        source_fetched_label=ctx.source_fetched_label,
    )
    _write_page(ctx.out_dir, f"region/{region['slug']}", html, ctx.written)
    return page_url


def species_slug(species: str) -> str:
    """URL segment for a species page: "Catfish" -> "catfish"."""
    return re.sub(r"[^a-z0-9]+", "-", species.lower()).strip("-")


def _species_rows(
    snapshot: dict[str, Any], species: str, week_start: str
) -> list[dict[str, Any]]:
    """The waters with a listed ``species`` plant in the week starting
    ``week_start``, grouped by CDFW region in the snapshot's region order and
    sorted by name inside each region. Straight from the snapshot's plants."""
    by_region: dict[str, list[dict[str, Any]]] = {}
    for w in snapshot["waters"]:
        if any(
            p["status"] == "listed"
            and p["species"] == species
            and p["week"]["start"] == week_start
            for p in w["plants"]
        ):
            by_region.setdefault(w["region"], []).append(
                {
                    "slug": w["slug"],
                    "name": w["name"],
                    "county_links": [
                        {"name": c, "slug": county_slug(c)} for c in w["counties"]
                    ],
                }
            )
    return [
        {
            "code": r["code"],
            "name": r["name"],
            "rows": sorted(by_region[r["code"]], key=lambda x: (x["name"], x["slug"])),
        }
        for r in snapshot["regions"]
        if r["code"] in by_region
    ]


def species_pages_in(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    """One entry per species the snapshot has a listed plant for: the species
    exactly as CDFW spells it, and its URL segment. Nothing is assumed about
    which species exist (today "Trout" and "Catfish")."""
    present = sorted(
        {
            p["species"]
            for w in snapshot["waters"]
            for p in w["plants"]
            if p["status"] == "listed"
        },
        key=lambda s: (s.lower() != "trout", s.lower()),
    )
    return [
        {"name": s, "word": s.lower(), "slug": species_slug(s)}
        for s in present
        if species_slug(s)
    ]


def _render_species_page(
    ctx: _PageContext, snapshot: dict[str, Any], species: dict[str, str]
) -> tuple[str, str]:
    """Write /species/<slug>/. Returns (URL, lastmod)."""
    word = species["word"]
    page_url = f"{ctx.base_url}/species/{species['slug']}/"
    this_start = ctx.source_week_start
    next_week = week_of(dt.date.fromisoformat(this_start) + dt.timedelta(days=7))
    this_regions = _species_rows(snapshot, species["name"], this_start)
    next_regions = _species_rows(snapshot, species["name"], next_week["start"])
    n_this = sum(len(r["rows"]) for r in this_regions)
    n_next = sum(len(r["rows"]) for r in next_regions)
    # Every water with a listed plant of this species on record, when the
    # list is short enough to be a page rather than the whole site again.
    # Longer lists stay on the county pages.
    on_record = []
    for w in snapshot["waters"]:
        weeks = sorted(
            p["week"]["start"]
            for p in w["plants"]
            if p["status"] == "listed" and p["species"] == species["name"]
        )
        if weeks:
            on_record.append(
                {
                    "slug": w["slug"],
                    "name": w["name"],
                    "county_links": [
                        {"name": c, "slug": county_slug(c)} for c in w["counties"]
                    ],
                    "latest": weeks[-1],
                    "upcoming": weeks[-1] > this_start,
                    "weeks": len(weeks),
                }
            )
    on_record.sort(key=lambda r: (r["name"], r["slug"]))
    on_record.sort(key=lambda r: r["latest"], reverse=True)
    water_total = len(on_record)
    show_on_record = water_total <= SPECIES_ON_RECORD_LIMIT
    trail = [
        ctx.home_crumb,
        (f"{species['name']} schedule", page_url),
    ]
    title = f"California {word} stocking schedule: this week and next | {SITE_NAME}"
    html = ctx.env.get_template("species.html.jinja").render(
        title=title,
        description=(
            f"California {word} stocking schedule: "
            f"{_plural(n_this, 'water', 'waters')} scheduled this week and "
            f"{n_next} next week, by CDFW region and county, with each "
            "water's history."
            if n_this or n_next
            else f"California {word} stocking schedule: no water is on CDFW's "
            f"schedule for this week or next. {_plural(water_total, 'water', 'waters')} "
            "on record, with each water's history."
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
                about={"@type": "State", "name": "California"},
            ),
            _ld_breadcrumb(page_url, trail),
        ),
        breadcrumb=_relative_trail(trail, base_url=ctx.base_url, root="../../"),
        species_word=word,
        this_label=ctx.source_week_label,
        next_label=next_week["label"],
        this_regions=this_regions,
        next_regions=next_regions,
        n_this=n_this,
        n_next=n_next,
        water_total=water_total,
        on_record=on_record if show_on_record else [],
        source_fetched_label=ctx.source_fetched_label,
        other_species=[
            s for s in species_pages_in(snapshot) if s["slug"] != species["slug"]
        ],
    )
    _write_page(ctx.out_dir, f"species/{species['slug']}", html, ctx.written)
    lastmod = max(
        _water_data_lastmod(w, source_week_start=this_start)
        for w in snapshot["waters"]
        if any(p["species"] == species["name"] for p in w["plants"])
    )
    return page_url, lastmod


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


def _home_row(
    w: dict[str, Any],
    week: dict[str, Any],
    species: list[str],
    county_link: dict[str, dict[str, str]],
) -> dict[str, Any]:
    return {
        "slug": w["slug"],
        "name": w["name"],
        "county_links": [county_link[c] for c in w["counties"]],
        "species": ", ".join(sorted(species)),
        "week_start": week["start"],
        "week_label": week["label"],
    }


def _home_nearest_weeks(
    snapshot: dict[str, Any], county_link: dict[str, dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """For a home page whose current week lists nothing: the waters CDFW has
    scheduled for a later week, soonest first, and the waters on the most
    recent earlier week with any listing. Each row carries its own week.

    Only ``listed`` plants count: a week CDFW took off its schedule is
    neither "next" nor "recent". Nothing is inferred, so either list can be
    empty. Callers reach this only with a snapshot ``cli.run`` accepted, which
    has passed ``fetch.assert_fresh``: a failed or stale fetch never gets
    here, so an empty week is CDFW's own page saying so.
    """
    current = snapshot["source_week"]["start"]
    Entry = tuple[dict[str, Any], dict[str, Any], list[str]]
    later: dict[tuple[str, str], Entry] = {}
    earlier: dict[tuple[str, str], Entry] = {}
    for w in snapshot["waters"]:
        for p in w["plants"]:
            if p["status"] != "listed" or p["week"]["start"] == current:
                continue
            bucket = later if p["week"]["start"] > current else earlier
            key = (w["id"], p["week"]["start"])
            bucket.setdefault(key, (w, p["week"], []))[2].append(p["species"])
    upcoming = [_home_row(w, wk, sp, county_link) for w, wk, sp in later.values()]
    upcoming.sort(key=lambda r: (r["week_start"], r["name"], r["slug"]))
    recent_week = max((k[1] for k in earlier), default=None)
    recent = [
        _home_row(w, wk, sp, county_link)
        for (_, start), (w, wk, sp) in earlier.items()
        if start == recent_week
    ]
    recent.sort(key=lambda r: (r["name"], r["slug"]))
    return upcoming, recent


def _home_description(
    source_week_label: str, species: str, *, week_is_empty: bool
) -> str:
    if week_is_empty:
        return (
            f"CDFW's schedule lists no California fish plants for the "
            f"{source_week_label}. The waters it scheduled next and most "
            f"recently, with each water's {species} stocking history."
        )
    return (
        f"Every California water on CDFW's (formerly DFG) fish planting schedule for the "
        f"{source_week_label}, by region and county, with each water's "
        f"{species} stocking history."
    )


def _region_links(
    snapshot: dict[str, Any],
    county_names: list[str],
    region_by_county: dict[str, str],
) -> list[dict[str, Any]]:
    """CDFW regions that have a county page and a water, each with the slug
    of its page. A region with neither gets no page and no link."""
    counties_in_region: dict[str, int] = {}
    for c in county_names:
        code = region_by_county.get(c, "")
        counties_in_region[code] = counties_in_region.get(code, 0) + 1
    with_water = {w["region"] for w in snapshot["waters"]}
    return [
        {
            "code": r["code"],
            "name": r["name"],
            "display_name": region_display_name(r["name"]),
            "slug": region_slug(r["name"]),
            "county_count": counties_in_region[r["code"]],
        }
        for r in snapshot["regions"]
        if r["code"] in counties_in_region and r["code"] in with_water
    ]


def _render_region_pages(
    ctx: _PageContext,
    snapshot: dict[str, Any],
    region_links: list[dict[str, Any]],
    counties_by_region: dict[str, list[dict[str, Any]]],
    data_lastmods: dict[str, str],
) -> dict[str, str]:
    """Write every region page. Returns {page URL: lastmod}."""
    lastmods: dict[str, str] = {}
    for r in region_links:
        waters = [w for w in snapshot["waters"] if w["region"] == r["code"]]
        url = _render_region_page(
            ctx,
            r,
            all_regions=region_links,
            waters=waters,
            counties=counties_by_region[r["code"]],
        )
        lastmods[url] = max(data_lastmods[w["id"]] for w in waters)
    return lastmods


def _write_feeds(
    ctx: _PageContext,
    snapshot: dict[str, Any],
    *,
    region_links: list[dict[str, Any]],
    county_names: list[str],
) -> None:
    """Write feeds/this-week.atom plus one feed per region and per county."""
    entries = feeds.current_week_entries(snapshot, species_phrase=species_phrase)
    week_label = snapshot["source_week"]["label"]
    week_start = snapshot["source_week"]["start"]
    region_of_water = {w["id"]: w["region"] for w in snapshot["waters"]}

    def write(
        path: str,
        subset: list[feeds.FeedEntry],
        *,
        title: str,
        subtitle: str,
        page_url: str,
    ) -> None:
        target = ctx.out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            feeds.build_feed(
                entries=subset,
                base_url=ctx.base_url,
                path=path,
                title=title,
                subtitle=subtitle,
                page_url=page_url,
                week_label=week_label,
                week_start=week_start,
                site_name=SITE_NAME,
                attribution_text=snapshot["attribution"]["text"],
            ),
            encoding="utf-8",
        )
        ctx.written.append(target)

    scheduled = "Scheduled, not confirmed: CDFW's plants are subject to change."
    write(
        feeds.feed_path("this-week"),
        entries,
        title=f"{SITE_NAME}: California trout schedule, {week_label}",
        subtitle=f"Waters on CDFW's schedule for the {week_label}. {scheduled}",
        page_url=f"{ctx.base_url}/",
    )
    for r in region_links:
        write(
            feeds.feed_path("region", r["slug"]),
            [e for e in entries if region_of_water[e.water_id] == r["code"]],
            title=f"{r['display_name']} trout schedule, {week_label}",
            subtitle=(
                f"Waters on CDFW's schedule in its {r['display_name']} for the "
                f"{week_label}. {scheduled}"
            ),
            page_url=f"{ctx.base_url}/region/{r['slug']}/",
        )
    for c in county_names:
        write(
            feeds.feed_path("county", county_slug(c)),
            [e for e in entries if c in e.counties],
            title=f"{c} County trout schedule, {week_label}",
            subtitle=(
                f"Waters in {c} County on CDFW's schedule for the {week_label}. "
                f"{scheduled}"
            ),
            page_url=f"{ctx.base_url}/county/{county_slug(c)}/",
        )


_CSS_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|/\*.*?\*/', re.DOTALL)


def minify_css(css: str) -> str:
    """Strip comments and redundant whitespace from a stylesheet.

    Deterministic and conservative: string literals are carried through
    untouched, and whitespace is only dropped where CSS never needs it
    (around ``{ } ; ,``, after ``:``, and the last ``;`` of a block). It never
    touches whitespace before ``:`` or around ``+ > /``, which can change the
    meaning of a selector or a value.
    """
    strings: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        if m.group(0).startswith("/*"):
            return " "
        strings.append(m.group(0))
        return f"\x00{len(strings) - 1}\x00"

    out = _CSS_TOKEN.sub(_stash, css)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r" ?([{};,]) ?", r"\1", out)
    out = out.replace(": ", ":")
    out = out.replace(";}", "}").strip()
    return re.sub(r"\x00(\d+)\x00", lambda m: strings[int(m.group(1))], out)


def _write_assets(
    out_dir: Path,
    written: list[Path],
    *,
    app_store_live: bool,
    coords: dict[str, list[Any]] | None = None,
) -> None:
    """assets/style.css, plus the App Store badge and its CSS when live.

    The badge CSS is appended only when the switch is on, and the badge file
    is only written then, so a build with the switch off writes exactly the
    assets it wrote before the switch existed.
    """
    style_src = (TEMPLATES_DIR / "style.css").read_text(encoding="utf-8")
    if app_store_live:
        style_src += (TEMPLATES_DIR / "app-store.css").read_text(encoding="utf-8")
    style_path = out_dir / "assets" / "style.css"
    style_path.parent.mkdir(parents=True, exist_ok=True)
    style_path.write_text(minify_css(style_src), encoding="utf-8")
    written.append(style_path)
    # The two web fonts style.css names, with their licenses, copied as they
    # are: first-party files, so no page requests another server for them.
    fonts_dir = out_dir / "assets" / FONTS_DIR
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for name in (*FONT_FILES, *FONT_LICENSE_FILES):
        font_path = fonts_dir / name
        font_path.write_bytes((TEMPLATES_DIR / FONTS_DIR / name).read_bytes())
        written.append(font_path)
    if coords:
        js_path = out_dir / "assets" / CLOSEST_JS_FILE
        js_path.write_text(
            (TEMPLATES_DIR / CLOSEST_JS_FILE).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        written.append(js_path)
        coords_path = out_dir / "assets" / COORDS_FILE
        coords_path.write_text(
            json.dumps(
                {
                    "schema": COORDS_SCHEMA,
                    "source": COORDS_SOURCE,
                    "waters": dict(sorted(coords.items())),
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        written.append(coords_path)
    if app_store_live:
        badge_path = out_dir / "assets" / APP_STORE_BADGE_FILE
        badge_path.write_bytes((TEMPLATES_DIR / APP_STORE_BADGE_FILE).read_bytes())
        written.append(badge_path)


def _share_card_kinds(
    snapshot: dict[str, Any], snapshot_v2: dict[str, Any] | None
) -> list[str]:
    """The share card kinds this build's pages use, in file order."""
    kinds = ["home", "county", "water"]
    if any(w["region"] for w in snapshot["waters"]):
        kinds.append("region")
    if species_pages_in(snapshot):
        kinds.append("species")
    if snapshot_v2 is not None and len(snapshot_v2["states"]) > 1:
        kinds.append("state")
    return kinds


def _privacy_description(*, ads_enabled: bool, analytics: bool) -> str:
    """The privacy page's meta description, for the build's state."""
    if ads_enabled:
        return (
            f"What the {SITE_NAME} trout planting site and iOS app collect: the "
            "website uses Google Analytics and shows non-personalized Google "
            "ads; the app collects nothing. No account."
        )
    if analytics:
        return (
            f"What the {SITE_NAME} trout planting site and iOS app collect: the "
            "website uses Google Analytics; the app collects nothing. No account, "
            "no ads."
        )
    return (
        f"What the {SITE_NAME} trout planting site and iOS app collect: "
        "nothing. No account, no analytics, no tracking."
    )


def build_site(
    snapshot: dict[str, Any],
    out_dir: Path,
    *,
    base_url: str,
    app_store_url: str | None = None,
    app_store_live: bool = False,
    support_email: str | None = None,
    ga4_measurement_id: str | None = None,
    google_site_verification: str | None = None,
    dataset_license_url: str | None = DATASET_LICENSE_URL,
    cname: str | None = None,
    snapshot_v2: dict[str, Any] | None = None,
    ads: ads_mod.AdsConfig | None = None,
) -> list[Path]:
    """Render the full static site into ``out_dir``. Returns written paths.

    ``cname`` (``custom_domain(base_url)``, passed by ``cli.run``) writes a
    ``CNAME`` file naming the custom domain. None writes no file, so a build
    without a custom domain is byte for byte what it was before.

    ``snapshot_v2`` (``cli.run`` passes it) adds the other states' pages,
    ``/states/``, their sitemap entries, and an "Other states" link in the
    California pages' header (DECISIONS 0025). Without it, or with a v2 that
    has California alone, the build is byte for byte what it was before.

    ``ga4_measurement_id`` defaults to None (no analytics) rather than to
    ``GA4_MEASUREMENT_ID``, so a caller gets the tag only by asking for it;
    ``cli.main`` is the caller that passes the committed value. The same
    goes for ``google_site_verification`` (``GOOGLE_SITE_VERIFICATION``).

    ``app_store_live`` (the APP_STORE_LIVE switch) adds the Smart App Banner
    tag to every page and the App Store badge to the home and support pages,
    and links the app to ``APP_STORE_CANONICAL_URL`` unless ``app_store_url``
    names another URL. Off, the build is exactly what it was without it.

    ``ads`` (cfpa/ads.py, docs/adr/0040) defaults to the committed ads
    settings, which are off. Off, the build is exactly what it was without
    it; on, the pages in ``ads.AD_PAGES`` carry one ad unit, the footer
    links to the ad choices and the root has an ads.txt.
    """
    # Checked before anything is written: a bad ID must not half-build.
    ga4_measurement_id = ga4_measurement_id_or_none(ga4_measurement_id)
    ads = ads_mod.for_build(ads, analytics=ga4_measurement_id is not None)
    google_site_verification = google_site_verification_or_none(
        google_site_verification
    )
    env = _env()
    ads_common = ads_mod.install(env, ads)
    written: list[Path] = []
    base_url = base_url.rstrip("/")

    attribution_text = snapshot["attribution"]["text"]
    attribution_url = snapshot["attribution"]["url"]
    generated_at_label = _fmt_dt(snapshot["generated_at"])
    source_fetched_label = _fmt_dt(snapshot["source"]["fetched_at"])
    source_week_label = snapshot["source_week"]["label"]
    source_week_start = snapshot["source_week"]["start"]
    # One flag decides every App Store surface. An explicit URL (the
    # APP_STORE_URL variable) replaces the listing's address while the
    # switch is on and does nothing while it is off: nothing then links to
    # the App Store at all.
    app_store_url = (
        (app_store_url or APP_STORE_CANONICAL_URL) if app_store_live else None
    )
    support_email = support_email or None
    # Share cards: one per kind of page in use. A page type that arrives later
    # adds its kind to _share_card_kinds and names it in its template.
    checked_on = snapshot["source"]["fetched_at"][:10]
    share_card_kinds = _share_card_kinds(snapshot, snapshot_v2)
    # Shared by every template: the app is only linked once it exists.
    common = {
        "attribution_text": attribution_text,
        "attribution_url": attribution_url,
        "app_store_url": app_store_url,
        # Off: no banner tag, no badge, no badge file, no extra CSS.
        "app_store_live": app_store_live,
        "app_store_id": APP_STORE_ID,
        "share_cards": {
            kind: share_cards.card_meta(
                kind, base_url=base_url, site_name=SITE_NAME, checked_on=checked_on
            )
            for kind in share_card_kinds
        },
        "share_card_default_kind": SHARE_CARD_DEFAULT_KIND,
        # base.html.jinja preloads each, relative to the page's root.
        "font_files": [f"assets/{FONTS_DIR}/{name}" for name in FONT_FILES],
        "support_email": support_email,
        "site_name": SITE_NAME,
        "amazon_disclosure": AMAZON_ASSOCIATE_DISCLOSURE,
        "gear_endorsement": gear_endorsement(CDFW_SHORT_NAME),
        # base.html.jinja includes the GA4 tag only when this is set, and the
        # about/privacy/support copy switches on it too, so the pages never
        # describe a state the build is not in.
        "ga4_measurement_id": ga4_measurement_id,
        "ga4_denied_regions": list(GA4_ANALYTICS_DENIED_REGIONS),
        **ads_common,
    }
    # The header's "Other states" link, only when v2 has another state, so a
    # California-only build keeps its header byte for byte.
    common["open_data"] = snapshot_v2 is not None
    common["states_nav"] = snapshot_v2 is not None and len(snapshot_v2["states"]) > 1
    # The other states' hubs, for the visible links on the home page and the
    # county index; empty (so nothing renders) in a California-only build.
    common["other_states"] = _other_states(snapshot_v2)

    # The species pages exist for the species the snapshot has listed plants
    # for; the home and county-index pages link to them.
    species_pages = species_pages_in(snapshot)
    common["species_links"] = [
        {"name": f"California {sp['word']} stocking schedule", "slug": sp["slug"]}
        for sp in species_pages
    ]

    # The past-week pages (DECISIONS 0038); the home page and the county index
    # link to /week/ only when it exists.
    common["week_archive"] = bool(weeks.week_entries(snapshot))

    # ---- assets/
    coords = water_coords(snapshot_v2)
    _write_assets(out_dir, written, app_store_live=app_store_live, coords=coords)
    ads_mod.write_files(out_dir, written, ads, minify=minify_css)
    share_cards.write_cards(
        out_dir,
        share_card_kinds,
        site_name=SITE_NAME,
        checked_on=checked_on,
        written=written,
    )

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
    name_counts = Counter(w["name"] for w in snapshot["waters"])
    waters_by_region = _group_by_region(snapshot["waters"])
    views = {
        w["id"]: _water_view(
            w,
            source_week_start=source_week_start,
            shared_name=name_counts[w["name"]] > 1,
        )
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
    region_links = _region_links(snapshot, county_names, region_by_county)
    region_link_by_code = {r["code"]: r for r in region_links}

    # The first week on record, and the last whole winter it covers (the
    # winter blocks on the home and county pages, DECISIONS 0040).
    recorded_since = min(
        (p["week"]["start"] for w in snapshot["waters"] for p in w["plants"]),
        default="",
    )
    winter_season = latest_complete_winter(source_week_start, recorded_since)

    week_is_empty = not snapshot["this_week"]
    upcoming_rows, recent_rows = (
        _home_nearest_weeks(snapshot, county_link) if week_is_empty else ([], [])
    )
    index_html = env.get_template("index.html.jinja").render(
        title=f"California {site_species} planting schedule this week | {SITE_NAME}",
        description=_home_description(
            source_week_label, site_species, week_is_empty=week_is_empty
        ),
        canonical_url=f"{base_url}/",
        root="./",
        **common,
        feed_path=feeds.feed_path("this-week"),
        feed_title=f"{SITE_NAME}: this week's California trout schedule (Atom)",
        feed_scope="statewide this-week",
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
            },
            *(
                [_ld_app(base_url, app_store_url or APP_STORE_CANONICAL_URL)]
                if app_store_live
                else []
            ),
        ),
        source_week_label=source_week_label,
        generated_at_label=generated_at_label,
        regions=regions,
        week_is_empty=week_is_empty,
        upcoming_rows=upcoming_rows,
        recent_rows=recent_rows,
        region_links=region_links,
        all_waters=all_waters,
        county_counts=county_counts,
        closest_enabled=bool(coords),
        closest_script_tag=CLOSEST_SCRIPT_TAG,
        coords_path=f"assets/{COORDS_FILE}",
        winter=_home_winter(snapshot["waters"], winter_season, county_link),
        gear_links=gear_links(cold_months=is_winter_week(source_week_start)),
        affiliate_rel=AFFILIATE_LINK_REL,
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
        locations_placed=len(coords) if coords else None,
        locations_total=len(snapshot["waters"]),
        title=f"About, attribution & privacy | {SITE_NAME}, {SITE_TAGLINE}",
        description=(
            f"What {SITE_NAME} is, {about_collects}, and where its trout planting "
            "and stocking data and license terms come from."
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
        license_summary=snapshot["licence"]["summary"],
        dataset_license_url=dataset_license_url or None,
        license_sources=snapshot["licence"]["sources"],
        generated_at_label=generated_at_label,
        source_fetched_label=source_fetched_label,
    )
    _write_page(out_dir, "about", about_html, written)

    # ---- /data/ and the CSV and JSON files it lists, from v2. A build with
    # no v2 (a hand-made snapshot in a test) has no such page, and then no
    # page links to it (``open_data`` in ``common``).
    data_updated = (
        _write_open_data(
            env,
            snapshot_v2,
            out_dir,
            written,
            base_url=base_url,
            common=common,
            license_url=dataset_license_url or None,
        )
        if snapshot_v2 is not None
        else None
    )

    # ---- privacy + support: the URLs App Store Connect asks for
    privacy_description = _privacy_description(
        ads_enabled=ads.enabled, analytics=ga4_measurement_id is not None
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
            structured_data=(
                _ld_graph(
                    _ld_faq(
                        f"{base_url}/{slug}/",
                        _support_faq(
                            source_fetched_label,
                            app_store_live=app_store_live,
                        ),
                    ),
                    *(
                        [_ld_app(base_url, app_store_url or APP_STORE_CANONICAL_URL)]
                        if app_store_live
                        else []
                    ),
                )
                if slug == "support"
                else None
            ),
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
        source_checked_on=snapshot["source"]["fetched_at"][:10],
        waters_by_region=waters_by_region,
        coords=coords,
        recorded_since=recorded_since,
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
    # A county page links the other counties of its CDFW region by name only,
    # so its lastmod also counts the day each of them first got a page (its
    # first water's first appearance), and nothing else about them.
    county_first_seen = {
        c: min(first_seen[w["id"]] for w in waters_by_county[c]) for c in county_names
    }
    for c in county_names:
        members = waters_by_county[c]
        code = region_by_county.get(c, "")
        region_counties = (
            [
                county_link[o]
                for o in county_names
                if o != c and region_by_county.get(o, "") == code
            ]
            if code
            else []
        )
        page_url = _render_county_page(
            ctx,
            c,
            this_week=this_week_by_county.get(c, []),
            region_name=region_name_by_code.get(code, ""),
            region_link=region_link_by_code.get(code),
            region_counties=region_counties,
        )
        # The winter section changes at the rollover that makes a new
        # winter the latest complete one (latest_complete_winter).
        county_lastmods[page_url] = max(
            [
                *(data_lastmods[w["id"]] for w in members),
                *(county_first_seen[o["name"]] for o in region_counties),
                *([winter_season["shown_from"]] if winter_season else []),
            ]
        )
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
                "slug": region_slug(r["name"]),
            }
            for r in snapshot["regions"]
            if r["code"] in counties_by_region
        ],
        species=site_species,
        county_count=len(county_names),
    )
    counties_index_lastmod = max(first_seen.values(), default=source_week_start)
    gear_url = _render_gear_page(ctx)

    # ---- region pages: one per CDFW region with a county page. The
    # lastmod is the newest of its waters' own data dates, which already
    # counts the weekly rollover, so the this-week and next-week lists
    # changing is a change here too.
    region_lastmods = _render_region_pages(
        ctx, snapshot, region_links, counties_by_region, data_lastmods
    )

    # ---- species pages: this week's and next week's scheduled waters for
    # each species in the data.
    species_entries = [_render_species_page(ctx, snapshot, sp) for sp in species_pages]

    # ---- past-week pages under /week/ (DECISIONS 0038)
    week_entries = weeks.render_weeks(
        env=env,
        out_dir=out_dir,
        written=written,
        base_url=base_url,
        common=common,
        site_name=SITE_NAME,
        snapshot=snapshot,
        county_slug=county_slug,
        species_phrase=species_phrase,
        write_page=_write_page,
        ld_graph=_ld_graph,
        ld_breadcrumb=_ld_breadcrumb,
        ld_page=_ld_page,
        relative_trail=_relative_trail,
    )

    # ---- guides: plain explanations under /guide/ (DECISIONS 0031)
    guide_entries = guides.render_guides(
        env=env,
        out_dir=out_dir,
        written=written,
        base_url=base_url,
        common=common,
        site_name=SITE_NAME,
        facts=guides.guide_facts(snapshot, recorded_since=recorded_since),
        region_links=region_links,
        county_counts=county_counts,
        source_week_label=source_week_label,
        source_fetched_label=source_fetched_label,
        write_page=_write_page,
        ld_graph=_ld_graph,
        ld_breadcrumb=_ld_breadcrumb,
        ld_page=_ld_page,
        relative_trail=_relative_trail,
    )

    # ---- the other states (DECISIONS 0025), from v2. Their pages carry their
    # own attribution, disclaimer and header; nothing here changes a
    # California page beyond the header link above.
    state_entries = site_states.render_states(
        site_states.StatesContext(
            env=env,
            out_dir=out_dir,
            written=written,
            base_url=base_url,
            common=common,
            site_name=SITE_NAME,
            write_page=_write_page,
            ld_graph=_ld_graph,
            ld_breadcrumb=_ld_breadcrumb,
            ld_page=_ld_page,
            relative_trail=_relative_trail,
            title_max=WATER_TITLE_MAX,
            gear_links=tuple(gear_links()),
            affiliate_rel=AFFILIATE_LINK_REL,
            gear_endorsement=gear_endorsement,
        ),
        snapshot_v2,
    )

    # ---- Atom feeds: statewide, per region and per county that has a page.
    # They are data files like the .ics calendars, not pages: no sitemap
    # entry, and the pages point to them with rel="alternate" instead.
    _write_feeds(ctx, snapshot, region_links=region_links, county_names=county_names)

    # ---- sitemap.xml -- lastmod is when a page's substance last changed
    # (see _water_data_lastmod), not the daily build date. The about,
    # privacy, support and gear pages carry no per-page data date, so no lastmod.
    sitemap_entries: list[tuple[str, str | None]] = [
        (f"{base_url}/", home_lastmod),
        (counties_index_url, counties_index_lastmod),
        (f"{base_url}/about/", None),
        (gear_url, None),
        *([(f"{base_url}/data/", data_updated)] if data_updated else []),
        (f"{base_url}/privacy/", None),
        (f"{base_url}/support/", None),
        *guide_entries,
        *region_lastmods.items(),
        *species_entries,
        *week_entries,
        *county_lastmods.items(),
        *water_lastmods.items(),
        *state_entries,
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

    # ---- llms.txt (llmstxt.org): a plain-text description of the site, its
    # sources, feeds and update cadence. Lists only what this build wrote.
    open_states = (
        _open_data_states(
            snapshot_v2,
            opendata.build_files(snapshot_v2, base_url=base_url),
            base_url=base_url,
        )
        if snapshot_v2 is not None
        else []
    )
    llms_path = out_dir / "llms.txt"
    llms_path.write_text(
        llms.render(
            site_name=SITE_NAME,
            base_url=base_url,
            attribution_text=attribution_text,
            states=open_states,
            region_feeds=[
                (
                    r["display_name"],
                    f"{base_url}/{feeds.feed_path('region', r['slug'])}",
                )
                for r in region_links
            ],
            week_label=source_week_label,
        ),
        encoding="utf-8",
    )
    written.append(llms_path)

    # ---- CNAME, only for a custom domain. A Pages site published from a
    # branch takes its custom domain from this file, so it has to be in
    # every build that is pushed there (DECISIONS 0019).
    if cname:
        cname_path = out_dir / "CNAME"
        cname_path.write_text(f"{cname}\n", encoding="utf-8")
        written.append(cname_path)
        # The IndexNow ownership file (pipeline/src/cfpa/indexnow.py), served
        # from the domain's root. Public by design; only the custom-domain
        # build carries it because the key proves ownership of that host.
        # find_key reads TEMPLATES_DIR, which holds exactly one such file.
        written.append(indexnow.copy_key_file(TEMPLATES_DIR, out_dir))

    ensure_unique_titles(out_dir, written)
    return written
