"""Render the geocoder's result document as a Markdown match report.

The report is for the owner: counts first, then every ambiguous water with
its candidates (so one can be picked in the overrides file), then every water
with no match and why, then the exact matches found through a name variant
(worth a glance), then the plain exact matches.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

KIND_TEXT = {
    "waterbody": "inside the NHD lake polygon",
    "named_point": "GNIS primary point",
    "stream_point": "on the stream, approximate",
}


def _pt(loc: dict[str, Any] | None) -> str:
    if not loc:
        return "no point"
    return f"{loc['lat']:.5f}, {loc['lon']:.5f} ({KIND_TEXT.get(loc['kind'], loc['kind'])})"


def _cand(c: dict[str, Any]) -> str:
    gp = c.get("gnis_point")
    gp_text = f"{gp['lat']:.5f}, {gp['lon']:.5f}" if gp else "none"
    would = c.get("would_be")
    tail = f"; would be {_pt(would)}" if "would_be" in c else ""
    return (
        f"GNIS {c['gnis_feature_id']} {c['name']} ({c['class']}, "
        f"{c['county']} County; GNIS point {gp_text}){tail}"
    )


def _water(r: dict[str, Any]) -> str:
    return f"cdfw-{r['cdfw_stock_id']} {r['name']} ({', '.join(r['counties'])})"


def _section(title: str, lines: Sequence[str], waters: int | None = None) -> list[str]:
    n = len(lines) if waters is None else waters
    out = [f"## {title} ({n})", ""]
    out += list(lines) if lines else ["None."]
    out.append("")
    return out


def render_report(doc: dict[str, Any]) -> str:
    waters = doc["waters"]
    c = doc["counts"]
    total = len(waters)
    by = {s: [w for w in waters if w["status"] == s] for s in c}
    kinds: dict[str, int] = {}
    for w in waters:
        if w["location"]:
            k = w["location"]["kind"]
            kinds[k] = kinds.get(k, 0) + 1
    out = [
        "# Water locations: match report",
        "",
        f"Generated {doc['generated_on']} by `cfpa-geocode` from "
        f"{total} waters in the published snapshot. Every water has exactly "
        "one status. Only `exact` and `owner_resolved` waters get a point;",
        "the rest stay `null`.",
        "",
        "| Status | Waters |",
        "|---|---|",
        *(f"| {s} | {n} |" for s, n in c.items()),
        f"| total | {total} |",
        "",
        "Points by kind: "
        + (", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) or "none")
        + ".",
        "",
        "To settle an ambiguous water, add an entry to "
        "`pipeline/data/water_location_overrides.json` with the GNIS id you "
        "choose (or `null` for no location), your name, the date and a note, "
        "then rerun `cfpa-geocode`.",
        "",
        "Sources:",
        "",
        *(f"- {i['name']}: {i['url']} ({i['terms']})" for i in doc["inputs"]),
        "",
    ]
    amb = []
    for w in by.get("ambiguous", []):
        amb.append(f"- **{_water(w)}**: {w['reason']}")
        amb += [f"  - {_cand(x)}" for x in w["candidates"]]
    out += _section("Ambiguous: pick one, or none", amb, len(by.get("ambiguous", [])))
    none = []
    for w in by.get("none", []):
        none.append(f"- {_water(w)}: {w['reason']}")
        none += [f"  - elsewhere: {_cand(x)}" for x in w.get("near_misses", [])]
    out += _section("No match", none, len(by.get("none", [])))
    variant = [
        f'- {_water(w)}: matched as "{w["matched_name"]}" ({w["method"]}), '
        f"GNIS {w['location']['source_feature_id']}, {_pt(w['location'])}"
        for w in by.get("exact", [])
        if w["method"] not in ("name", "alias")
    ]
    out += _section("Exact, through a name variant (worth a glance)", variant)
    owner = [
        f"- {_water(w)}: {w['override']['resolved_by']}, "
        f"{w['override']['resolved_on']}: {w['override']['note']} -> "
        f"{_pt(w['location'])}"
        for w in by.get("owner_resolved", []) + by.get("owner_none", [])
    ]
    out += _section("Owner overrides", owner)
    plain = [
        f"- {_water(w)}: GNIS {w['location']['source_feature_id']}, "
        f"{_pt(w['location'])}"
        for w in by.get("exact", [])
        if w["method"] in ("name", "alias")
    ]
    out += _section("Exact, by name", plain)
    return "\n".join(out).rstrip() + "\n"
