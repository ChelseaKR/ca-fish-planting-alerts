"""Generate the static site from a built snapshot.

The one script this module can write is the Google Analytics 4 tag
(DECISIONS 0011, which replaces 0002's "no tracking" for the website only).
It is emitted only when a GA4 measurement ID is configured
(``GA4_MEASUREMENT_ID`` below); with none, every page has no JavaScript, no
cookies and no third-party request, exactly as before. The about, privacy
and support pages describe whichever of those two states the build is in.
Nothing here ever writes an external stylesheet host, a pixel or an iframe.
The iOS app never carries analytics.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
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
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


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


def build_water_ics(*, water: dict, base_url: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ca-fish-planting-alerts//snapshot v1//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(water['name'])} trout planting schedule",
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
        summary = f"week of {week['start']}: {p['species']} scheduled at {water['name']}"
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
    return "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"


def _water_view(w: dict, *, source_week_start: str) -> dict:
    plants_sorted = sorted(w["plants"], key=lambda p: p["week"]["start"], reverse=True)
    other_names = [n for n in w["aliases"] if n != w["name"]]
    counties = ", ".join(w["counties"])
    # Upcoming = a listed plant for a week after the snapshot's own current
    # week. Kept separate from last_listed_week (which never looks past the
    # current week), so a water whose only listing is next week is not
    # described as having nothing scheduled.
    upcoming = sorted(
        p["week"]["start"]
        for p in w["plants"]
        if p["status"] == "listed" and p["week"]["start"] > source_week_start
    )
    listed_weeks = {p["week"]["start"] for p in w["plants"] if p["status"] == "listed"}
    return {
        "slug": w["slug"],
        "name": w["name"],
        # Five CDFW names (Silver Lake, Bass Lake, Deer Creek, Sacramento
        # River, Blue Lake Upper) are shared by 2-3 different waters; the
        # county is what tells their pages -- and their titles -- apart.
        "qualified_name": f"{w['name']} ({counties})",
        "counties": counties,
        "county": w["counties"][0] if w["counties"] else "",
        "region_name": REGION_NAME_BY_CODE.get(w["region"], w["region"]),
        "cdfw_map_url": w["cdfw_map_url"],
        "other_names": ", ".join(other_names) if other_names else "",
        "last_listed_label": w["last_listed_week"]["label"] if w["last_listed_week"] else "",
        "next_listed_label": f"week of {upcoming[0]}" if upcoming else "",
        "listed_week_count": len(listed_weeks),
        "plants": [
            {
                "label": p["week"]["label"],
                "species": p["species"],
                "status": p["status"],
            }
            for p in plants_sorted
        ],
    }


def _water_lastmod(w: dict, *, source_week_start: str) -> str:
    """The date this water's page last changed in substance, for sitemap.xml.

    Not the build date: the site rebuilds every day, and a lastmod that
    always says "today" is one search engines learn to ignore. The page
    changes when a plant is first listed (first_observed_at), when one is
    removed (last_observed_at of a removed plant), and when the current week
    rolls over while the water has a listing near it (its "most recent" /
    "next" wording can flip then). A removed-then-relisted plant is not
    detectable from the snapshot and is the one known under-report.
    """
    dates = [p["first_observed_at"][:10] for p in w["plants"]]
    dates += [p["last_observed_at"][:10] for p in w["plants"] if p["status"] == "removed"]
    rollover_sensitive_from = (
        dt.date.fromisoformat(source_week_start) - dt.timedelta(days=7)
    ).isoformat()
    if any(
        p["status"] == "listed" and p["week"]["start"] >= rollover_sensitive_from
        for p in w["plants"]
    ):
        dates.append(source_week_start)
    return max(dates)


def build_site(
    snapshot: dict,
    out_dir: Path,
    *,
    base_url: str,
    app_store_url: str | None = None,
    support_email: str | None = None,
    ga4_measurement_id: str | None = None,
) -> list[Path]:
    """Render the full static site into ``out_dir``. Returns written paths.

    ``ga4_measurement_id`` defaults to None (no analytics) rather than to
    ``GA4_MEASUREMENT_ID``, so a caller gets the tag only by asking for it;
    ``cli.main`` is the caller that passes the committed value.
    """
    # Checked before anything is written: a bad ID must not half-build.
    ga4_measurement_id = ga4_measurement_id_or_none(ga4_measurement_id)
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

    # ---- index
    this_week_by_region: dict[str, list[dict]] = {}
    for entry in snapshot["this_week"]:
        w = waters_by_id[entry["water_id"]]
        this_week_by_region.setdefault(w["region"], []).append(
            {
                "slug": w["slug"],
                "name": w["name"],
                "counties": ", ".join(w["counties"]),
                "species": entry["species"],
            }
        )
    regions = []
    for region in snapshot["regions"]:
        rows = sorted(this_week_by_region.get(region["code"], []), key=lambda r: r["name"])
        if rows:
            regions.append({"code": region["code"], "name": region["name"], "rows": rows})

    all_waters = sorted(
        (
            {"slug": w["slug"], "name": w["name"], "county": w["counties"][0] if w["counties"] else ""}
            for w in snapshot["waters"]
        ),
        key=lambda w: w["name"],
    )

    index_html = env.get_template("index.html.jinja").render(
        title=f"This week's CA trout planting schedule | {SITE_NAME}",
        description=(
            f"CDFW's California trout planting and stocking schedule for the {source_week_label}, "
            "by region, from the official weekly schedule."
        ),
        canonical_url=f"{base_url}/",
        root="./",
        **common,
        source_week_label=source_week_label,
        generated_at_label=generated_at_label,
        regions=regions,
        all_waters=all_waters,
    )
    index_path = out_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    written.append(index_path)

    # ---- about
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
        licence_summary=snapshot["licence"]["summary"],
        licence_sources=snapshot["licence"]["sources"],
        generated_at_label=generated_at_label,
        source_fetched_label=source_fetched_label,
    )
    about_path = out_dir / "about" / "index.html"
    about_path.parent.mkdir(parents=True, exist_ok=True)
    about_path.write_text(about_html, encoding="utf-8")
    written.append(about_path)

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
        page_path = out_dir / slug / "index.html"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(page_html, encoding="utf-8")
        written.append(page_path)

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
        (p["week"]["start"] for w in snapshot["waters"] for p in w["plants"]), default=""
    )
    # ---- per-water pages + ics
    water_lastmods: dict[str, str] = {}
    for w in snapshot["waters"]:
        view = _water_view(w, source_week_start=source_week_start)
        water_dir = out_dir / "water" / w["slug"]
        water_dir.mkdir(parents=True, exist_ok=True)

        page_url = f"{base_url}/water/{w['slug']}/"
        if view["last_listed_label"]:
            recency = f"most recently scheduled the {view['last_listed_label']}"
        elif view["next_listed_label"]:
            recency = f"next scheduled the {view['next_listed_label']}"
        else:
            recency = "no planting currently listed"
        html = env.get_template("water.html.jinja").render(
            title=f"{view['qualified_name']} trout stocking schedule & history | {SITE_NAME}",
            description=(
                f"{view['qualified_name']}: CDFW trout planting schedule and history, "
                f"{recency}. {view['listed_week_count']} planting week(s) recorded, "
                "plus a calendar feed."
            ),
            canonical_url=page_url,
            root="../../",
            **common,
            water=view,
            source_week_label=source_week_label,
            source_fetched_label=source_fetched_label,
            recorded_since_label=f"week of {recorded_since}" if recorded_since else "",
        )
        (water_dir / "index.html").write_text(html, encoding="utf-8")
        written.append(water_dir / "index.html")

        ics = build_water_ics(water=w, base_url=page_url)
        (water_dir / "feed.ics").write_text(ics, encoding="utf-8")
        written.append(water_dir / "feed.ics")

        water_lastmods[page_url] = _water_lastmod(w, source_week_start=source_week_start)

    # ---- sitemap.xml -- lastmod is when a page's substance last changed
    # (see _water_lastmod), not the daily build date. The home page lists
    # the current week, so it changes at least at each weekly rollover; the
    # about/privacy/support pages carry no per-page data date, so no lastmod.
    home_lastmod = max([source_week_start, *water_lastmods.values()])
    sitemap_entries: list[tuple[str, str | None]] = [
        (f"{base_url}/", home_lastmod),
        (f"{base_url}/about/", None),
        (f"{base_url}/privacy/", None),
        (f"{base_url}/support/", None),
        *water_lastmods.items(),
    ]
    sitemap_items = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{m}</lastmod></url>" if m else f"  <url><loc>{u}</loc></url>"
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

    # ---- robots.txt (ours -- the site's own, distinct from CDFW's)
    robots_txt = f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n"
    robots_path = out_dir / "robots.txt"
    robots_path.write_text(robots_txt, encoding="utf-8")
    written.append(robots_path)

    return written
