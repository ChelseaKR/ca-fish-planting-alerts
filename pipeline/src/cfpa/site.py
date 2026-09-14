"""Generate the static site from a built snapshot.

No JavaScript, no cookies, no third-party requests: DECISIONS 0002 ("data
posture: none"). The about page says this in plain language; this module is
what has to stay true to it -- nothing here writes a <script> tag, an
external stylesheet host, an analytics pixel, or an iframe.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import jinja2

TEMPLATES_DIR = Path(__file__).parent / "templates"

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
        summary = f"week of {week['start']}: {p['species']} planted at {water['name']}"
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


def _water_view(w: dict) -> dict:
    plants_sorted = sorted(w["plants"], key=lambda p: p["week"]["start"], reverse=True)
    other_names = [n for n in w["aliases"] if n != w["name"]]
    return {
        "slug": w["slug"],
        "name": w["name"],
        "counties": ", ".join(w["counties"]),
        "county": w["counties"][0] if w["counties"] else "",
        "region_name": REGION_NAME_BY_CODE.get(w["region"], w["region"]),
        "cdfw_map_url": w["cdfw_map_url"],
        "other_names": ", ".join(other_names) if other_names else "",
        "last_listed_label": w["last_listed_week"]["label"] if w["last_listed_week"] else "",
        "plants": [
            {
                "label": p["week"]["label"],
                "species": p["species"],
                "status": p["status"],
            }
            for p in plants_sorted
        ],
    }


def build_site(snapshot: dict, out_dir: Path, *, base_url: str) -> list[Path]:
    """Render the full static site into ``out_dir``. Returns written paths."""
    env = _env()
    written: list[Path] = []
    base_url = base_url.rstrip("/")

    attribution_text = snapshot["attribution"]["text"]
    attribution_url = snapshot["attribution"]["url"]
    generated_at_label = _fmt_dt(snapshot["generated_at"])
    source_fetched_label = _fmt_dt(snapshot["source"]["fetched_at"])
    source_week_label = snapshot["source_week"]["label"]

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
        title="This week's CA trout planting schedule | CA Trout Planting Alerts",
        description=f"CDFW-scheduled trout plants for the {source_week_label}, by region, from the official weekly schedule.",
        canonical_url=f"{base_url}/",
        root="./",
        attribution_text=attribution_text,
        attribution_url=attribution_url,
        source_week_label=source_week_label,
        generated_at_label=generated_at_label,
        regions=regions,
        all_waters=all_waters,
    )
    index_path = out_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    written.append(index_path)

    # ---- about
    about_html = env.get_template("about.html.jinja").render(
        title="About, attribution & privacy | CA Trout Planting Alerts",
        description="What this site is, what it collects (nothing), and where its data and licence terms come from.",
        canonical_url=f"{base_url}/about/",
        root="../",
        attribution_text=attribution_text,
        attribution_url=attribution_url,
        licence_summary=snapshot["licence"]["summary"],
        licence_sources=snapshot["licence"]["sources"],
        generated_at_label=generated_at_label,
        source_fetched_label=source_fetched_label,
    )
    about_path = out_dir / "about" / "index.html"
    about_path.parent.mkdir(parents=True, exist_ok=True)
    about_path.write_text(about_html, encoding="utf-8")
    written.append(about_path)

    # ---- per-water pages + ics
    sitemap_urls = [f"{base_url}/", f"{base_url}/about/"]
    for w in snapshot["waters"]:
        view = _water_view(w)
        water_dir = out_dir / "water" / w["slug"]
        water_dir.mkdir(parents=True, exist_ok=True)

        page_url = f"{base_url}/water/{w['slug']}/"
        html = env.get_template("water.html.jinja").render(
            title=f"{w['name']} trout stocking schedule & history | CA Trout Planting Alerts",
            description=f"When was {w['name']} ({view['counties']}) last stocked with trout? Full CDFW planting history and a subscribable calendar.",
            canonical_url=page_url,
            root="../../",
            attribution_text=attribution_text,
            attribution_url=attribution_url,
            water=view,
        )
        (water_dir / "index.html").write_text(html, encoding="utf-8")
        written.append(water_dir / "index.html")

        ics = build_water_ics(water=w, base_url=page_url)
        (water_dir / "feed.ics").write_text(ics, encoding="utf-8")
        written.append(water_dir / "feed.ics")

        sitemap_urls.append(page_url)

    # ---- sitemap.xml
    lastmod = snapshot["generated_at"][:10]
    sitemap_items = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{lastmod}</lastmod></url>" for u in sitemap_urls
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
