"""Build ``snapshot/v2.json``: California plus every other state with data.

California's part is derived from the finished v1 snapshot, never rebuilt
from the page, so v1 stays exactly what it was and the two can't disagree
about California. Water ids do not change (``cdfw-<id>``), so a favorite and
its alert baseline carry over from an app that read v1.

Every other state comes from its own history (``cfpa.states``). A state with
no record in its publish window is left out, not shown empty.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jsonschema

from .locations import location_for
from .states.base import Period, StateSource, week_start_containing
from .states.store import StateHistory, StateRecord

CA_AGENCY = {
    "name": "California Department of Fish and Wildlife",
    "short_name": "CDFW",
    "url": "https://wildlife.ca.gov/",
}
CA_DISCLAIMER = (
    "Trout Truck is independent and is not affiliated with or endorsed by CDFW. "
    'CDFW: "all fish plants are subject to change depending on road, water, '
    'weather and operational conditions."'
)
# Verbatim from docs/LICENSES-AND-ATTRIBUTION.md, keyed by v1's source names.
CA_TERMS_QUOTES = {
    "CDFW Fish Planting Schedule": (
        "Ownership — In general, information presented on this web site, unless "
        "otherwise indicated, is considered in the public domain. It may be "
        "distributed or copied as permitted by law."
    ),
    "CDFW Fishing Guide (data.ca.gov, CC-BY)": (
        'License: "Creative Commons Attribution". Rights: "No restrictions on '
        'public use."'
    ),
}
CA_TIME_ZONE = "America/Los_Angeles"


class SnapshotV2Error(ValueError):
    """The v2 snapshot breaks a rule the schema can't express."""


def _iso_z(d: dt.datetime) -> str:
    return d.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _week(start: dt.date) -> dict[str, str]:
    return {
        "start": start.isoformat(),
        "end": (start + dt.timedelta(days=6)).isoformat(),
        "label": f"week of {start.isoformat()}",
    }


def _week_period(week: dict[str, str]) -> dict[str, str]:
    return {
        "precision": "week",
        "start": week["start"],
        "end": week["end"],
        "label": week["label"],
    }


# ---- California, from v1


def _ca_state(v1: dict[str, Any]) -> dict[str, Any]:
    fetched_at = v1["source"]["fetched_at"]
    as_of = (
        dt.datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        .astimezone(ZoneInfo(CA_TIME_ZONE))
        .date()
    )
    newest = max(
        (p["week"] for w in v1["waters"] for p in w["plants"]),
        key=lambda wk: wk["start"],
        default=None,
    )
    return {
        "code": "CA",
        "name": "California",
        "agency": CA_AGENCY,
        "semantics": "schedule",
        "date_precisions": ["week"],
        "removal_inference": True,
        "current_week": v1["source_week"],
        "as_of": as_of.isoformat(),
        "newest_record": _week_period(newest) if newest else None,
        "recency_note": None,
        "source": {
            "name": v1["source"]["name"],
            "url": v1["source"]["url"],
            "fetched_at": fetched_at,
            "content_sha256": v1["source"]["content_sha256"],
            "last_modified": None,
        },
        # A California fetch that fails publishes nothing at all, so a v2
        # with California in it always comes from a good fetch.
        "checks": {
            "last_attempt_at": fetched_at,
            "last_success_at": fetched_at,
            "last_attempt_ok": True,
        },
        "attribution": v1["attribution"],
        "disclaimer": CA_DISCLAIMER,
        "license": {
            "summary": v1["licence"]["summary"],
            "sources": [
                {**s, "terms_quote": CA_TERMS_QUOTES.get(s["name"], "")}
                for s in v1["licence"]["sources"]
            ],
        },
        "regions": v1["regions"],
        "counties": v1["counties"],
        "waters_count": len(v1["waters"]),
    }


def _ca_waters(
    v1: dict[str, Any], locations: Mapping[int, dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """v1's waters as v2 waters. ``locations`` (``cfpa.locations``, DECISIONS
    0024) places a water in v2 only; v1 keeps ``location: null``."""
    source_start = v1["source_week"]["start"]
    out = []
    for w in v1["waters"]:
        upcoming = sorted(
            (
                p["week"]
                for p in w["plants"]
                if p["status"] == "listed" and p["week"]["start"] > source_start
            ),
            key=lambda wk: wk["start"],
        )
        out.append(
            {
                "id": w["id"],
                "state": "CA",
                "name": w["name"],
                "name_status": w["name_status"],
                "slug": w["slug"],
                "aliases": w.get("aliases", []),
                "counties": w["counties"],
                "towns": [],
                "region": w["region"],
                "source_id": str(w["cdfw_stock_id"]),
                "source_url": w["cdfw_map_url"],
                "site_path": f"/water/{w['slug']}/",
                "location": location_for(locations, w["cdfw_stock_id"])
                if locations is not None
                else w["location"],
                "last_period": _week_period(w["last_listed_week"])
                if w["last_listed_week"]
                else None,
                "next_period": _week_period(upcoming[0]) if upcoming else None,
                "months_note": None,
                "plants": [
                    {
                        "period": _week_period(p["week"]),
                        "species": p["species"],
                        "status": p["status"],
                        "count": None,
                        "first_observed_at": p["first_observed_at"],
                        "last_observed_at": p["last_observed_at"],
                    }
                    for p in w["plants"]
                ],
            }
        )
    return out


# ---- other states, from their histories


def _published(
    source: StateSource, records: Iterable[StateRecord]
) -> list[StateRecord]:
    since = source.publish_since
    return [r for r in records if since is None or r.period.start >= since]


def _plant(r: StateRecord) -> dict[str, Any]:
    return {
        "period": r.period.to_json(),
        "species": r.species,
        "status": r.status,
        "count": r.count,
        "first_observed_at": _iso_z(r.first_observed_at),
        "last_observed_at": _iso_z(r.last_observed_at),
    }


def _state_waters(
    source: StateSource,
    history: StateHistory,
    records: list[StateRecord],
    as_of: dt.date,
) -> list[dict[str, Any]]:
    by_water: dict[str, list[StateRecord]] = {}
    for r in records:
        by_water.setdefault(r.water_id, []).append(r)
    # A water the agency lists only by month letters (Tennessee's tailwaters)
    # has no dated record, but it is on the agency's list, so it gets an
    # entry that says so through its months_note.
    for wid, meta in history.waters.items():
        if meta.months_note and wid not in by_water:
            by_water[wid] = []
    out = []
    for wid in sorted(by_water):
        meta = history.waters[wid]
        recs = sorted(
            by_water[wid], key=lambda r: (r.period.start, r.period.precision, r.species)
        )
        current = [r for r in recs if r.status in ("listed", "reported")]
        past = [r for r in current if r.period.start <= as_of]
        future = [r for r in current if r.period.start > as_of and r.status == "listed"]
        aliases = history.aliases.get(wid, [meta.name])
        out.append(
            {
                "id": wid,
                "state": source.code,
                "name": meta.name,
                "name_status": "unreviewed",
                "slug": meta.slug,
                "aliases": aliases,
                "counties": list(meta.counties),
                "towns": list(meta.towns),
                "region": meta.region,
                "source_id": meta.source_id,
                "source_url": meta.source_url or source.source_url,
                "site_path": f"/{source.path_segment}/water/{meta.slug}/",
                "location": None,
                "last_period": past[-1].period.to_json() if past else None,
                "next_period": future[0].period.to_json() if future else None,
                "months_note": meta.months_note,
                "plants": [_plant(r) for r in recs],
            }
        )
    return out


def _state_entry(
    source: StateSource,
    history: StateHistory,
    records: list[StateRecord],
    waters: list[dict[str, Any]],
    as_of: dt.date,
) -> dict[str, Any]:
    checks = history.checks
    if checks.last_success_at is None:
        raise SnapshotV2Error(f"{source.code} has never been fetched successfully")
    newest = max(records, key=lambda r: (r.period.start, r.period.end))
    counties = sorted({c for w in waters for c in w["counties"]})
    region_of = {c: w["region"] for w in waters for c in w["counties"]}
    return {
        "code": source.code,
        "name": source.name,
        "agency": {
            "name": source.agency_name,
            "short_name": source.agency_short_name,
            "url": source.agency_url,
        },
        "semantics": source.semantics,
        "date_precisions": list(source.date_precisions),
        "removal_inference": source.removal_inference,
        "current_week": _week(week_start_containing(as_of)),
        "as_of": as_of.isoformat(),
        "newest_record": newest.period.to_json(),
        "recency_note": source.recency_note,
        "source": {
            "name": source.source_name,
            "url": source.source_url,
            "fetched_at": _iso_z(checks.last_success_at),
            "content_sha256": checks.content_sha256 or "0" * 64,
            "last_modified": checks.last_modified,
        },
        "checks": {
            "last_attempt_at": _iso_z(checks.last_attempt_at or checks.last_success_at),
            "last_success_at": _iso_z(checks.last_success_at),
            "last_attempt_ok": checks.last_attempt_ok,
        },
        "attribution": {"text": source.attribution_text, "url": source.attribution_url},
        "disclaimer": source.disclaimer,
        "license": {
            "summary": source.license_summary,
            "sources": [s.to_json() for s in source.license_sources],
        },
        "regions": [{"code": c, "name": n} for c, n in source.regions],
        "counties": [{"name": c, "region": region_of.get(c)} for c in counties],
        "waters_count": len(waters),
    }


def _this_week(
    waters: list[dict[str, Any]], week: dict[str, str]
) -> list[dict[str, str]]:
    out = []
    for w in waters:
        for p in w["plants"]:
            per = p["period"]
            if (
                per["precision"] in ("day", "week")
                and p["status"] in ("listed", "reported")
                and per["start"] <= week["end"]
                and per["end"] >= week["start"]
            ):
                out.append({"water_id": w["id"], "species": p["species"]})
    return out


def build_snapshot_v2(
    v1: dict[str, Any],
    histories: Iterable[tuple[StateSource, StateHistory]],
    *,
    generated_at: dt.datetime,
    locations: Mapping[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    states = [_ca_state(v1)]
    waters = _ca_waters(v1, locations)
    this_week = list(v1["this_week"])
    others = []
    for source, history in histories:
        records = _published(source, history.records)
        if not records or history.checks.last_success_at is None:
            continue
        as_of = history.checks.last_success_at.astimezone(
            ZoneInfo(source.time_zone)
        ).date()
        state_waters = _state_waters(source, history, records, as_of)
        entry = _state_entry(source, history, records, state_waters, as_of)
        others.append((entry, state_waters))
    for entry, state_waters in sorted(others, key=lambda e: e[0]["name"]):
        states.append(entry)
        waters.extend(state_waters)
        this_week.extend(_this_week(state_waters, entry["current_week"]))
    return {
        "schema_version": 2,
        "generated_at": _iso_z(generated_at),
        "states": states,
        "waters": waters,
        "this_week": this_week,
    }


def _check_plant(w: dict[str, Any], p: dict[str, Any], state: dict[str, Any]) -> None:
    per = Period.from_json(p["period"])
    if per.label != p["period"]["label"] or per.end < per.start:
        raise SnapshotV2Error(f"water {w['id']} has a bad period {p['period']}")
    if per.precision == "week" and per.start.weekday() != 6:
        raise SnapshotV2Error(f"water {w['id']} has a week not on a Sunday")
    if per.precision not in state["date_precisions"]:
        raise SnapshotV2Error(
            f"water {w['id']} has a {per.precision} the state never gives"
        )
    if p["status"] == "removed" and not state["removal_inference"]:
        raise SnapshotV2Error(f"water {w['id']} has a removed plant in a report state")
    if (p["status"] == "reported") != (state["semantics"] == "report"):
        raise SnapshotV2Error(
            f"water {w['id']} has status {p['status']} in a {state['semantics']} state"
        )


def check_invariants(snap: dict[str, Any]) -> None:
    """Rules JSON Schema can't state. Raises SnapshotV2Error."""
    states = {s["code"]: s for s in snap["states"]}
    ids: set[str] = set()
    paths: set[str] = set()
    for w in snap["waters"]:
        state = states.get(w["state"])
        if state is None:
            raise SnapshotV2Error(f"water {w['id']} names unknown state {w['state']}")
        if w["id"] in ids or w["site_path"] in paths:
            raise SnapshotV2Error(f"water {w['id']} repeats an id or a site path")
        ids.add(w["id"])
        paths.add(w["site_path"])
        for p in w["plants"]:
            _check_plant(w, p, state)
    for code, state in states.items():
        count = sum(1 for w in snap["waters"] if w["state"] == code)
        if count != state["waters_count"] or count == 0:
            raise SnapshotV2Error(
                f"{code} has {count} waters, says {state['waters_count']}"
            )
    unknown = {e["water_id"] for e in snap["this_week"]} - ids
    if unknown:
        raise SnapshotV2Error(f"this_week names unknown waters {sorted(unknown)[:3]}")


def validate_snapshot_v2(snap: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=snap, schema=schema)
    check_invariants(snap)
