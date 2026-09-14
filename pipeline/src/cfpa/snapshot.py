"""Build schema/snapshot.v1.json from history + aliases + the fetched page,
and validate the result against the committed JSON Schema.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import statistics
from pathlib import Path

import jsonschema

from . import parse
from .aliases import AliasTable
from .fetch import FetchedPage
from .history import HistoryStore, PlantRecord

REGIONS = [
    {"code": "R1", "name": "Northern Region (R1)"},
    {"code": "R2", "name": "North Central Region (R2)"},
    {"code": "R3", "name": "Bay Delta Region (R3)"},
    {"code": "R4", "name": "Central Region (R4)"},
    {"code": "R5", "name": "South Coast Region (R5)"},
    {"code": "R6", "name": "Inland Deserts Region (R6)"},
]

ATTRIBUTION_TEXT = (
    "Data: California Department of Fish and Wildlife, Fish Planting Schedule "
    "(https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch). Schedule is subject "
    "to change; treat all plants as scheduled, not confirmed."
)
ATTRIBUTION_URL = "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch"

LICENCE_SUMMARY = (
    "CDFW's site-wide Conditions of Use place page content in the public "
    "domain with no commercial-use restriction; the related CDFW Fishing "
    "Guide dataset on data.ca.gov is explicitly CC-BY. We attribute "
    "unconditionally. See docs/LICENSES-AND-ATTRIBUTION.md for the verbatim "
    "quotes this is built from."
)
LICENCE_SOURCES = [
    {
        "name": "CDFW Fish Planting Schedule",
        "url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch",
        "terms_url": "https://wildlife.ca.gov/Conditions-of-Use",
        "terms_read_on": "2026-09-13",
        "commercial_reuse": "permitted",
        "attribution_required": True,
    },
    {
        "name": "CDFW Fishing Guide (data.ca.gov, CC-BY)",
        "url": "https://data.ca.gov/dataset/cdfw-fishing-guide2",
        "terms_url": "https://data.ca.gov/dataset/cdfw-fishing-guide2",
        "terms_read_on": "2026-09-13",
        "commercial_reuse": "permitted",
        "attribution_required": True,
    },
]


def week_of(d: dt.date) -> dict:
    # CDFW's own weeks run Sunday..Saturday; align any date to that week.
    start = d - dt.timedelta(days=(d.weekday() + 1) % 7)
    end = start + dt.timedelta(days=6)
    return {"start": start.isoformat(), "end": end.isoformat(), "label": f"week of {start.isoformat()}"}


def _iso_z(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_counties(county_options, region_county_options) -> list[dict]:
    region_by_county_id = {opt.value: opt.label for opt in region_county_options if opt.value}
    out = []
    for opt in county_options:
        region = region_by_county_id.get(opt.value)
        if not region:
            raise ValueError(f"county {opt.label!r} (id {opt.value}) has no region mapping")
        out.append({"name": opt.label, "region": region})
    return out


def build_waters(
    history: HistoryStore,
    aliases: AliasTable,
    rows: list[parse.RawRow],
    source_week_start: dt.date,
    counties_by_name: dict[str, str],
) -> list[dict]:
    by_water = history.by_water()
    # Most-recently-observed county list per water, from this run's rows
    # (falls back to nothing for waters with no rows this run, which is fine
    # -- their county list was already fixed by an earlier run's rows and
    # isn't re-derivable from this run alone, so we carry it via aliases'
    # first-seen data... in practice every water in `by_water` has at least
    # one PlantRecord and we recover counties from the rows of the run(s)
    # that produced it. Since history doesn't store counties directly, we
    # require the caller to have seen at least one row per known water across
    # all runs; for a fresh run that's this run's `rows`.
    counties_latest: dict[int, list[str]] = {}
    map_url_latest: dict[int, str] = {}
    for r in rows:
        counties_latest[r.cdfw_stock_id] = list(r.counties)
        map_url_latest[r.cdfw_stock_id] = f"https://apps.wildlife.ca.gov/fishing/?stockid={r.cdfw_stock_id}"

    waters = []
    for stock_id in sorted(by_water):
        alias = aliases.by_id.get(stock_id)
        if alias is None:
            raise ValueError(f"cdfw-{stock_id} has history but no alias table entry")
        counties = counties_latest.get(stock_id)
        if not counties:
            raise ValueError(
                f"cdfw-{stock_id} ({alias.canonical_name}) has history but no county "
                f"data from this run -- county is only ever sourced from a live row"
            )
        region = counties_by_name.get(counties[0])
        if not region:
            raise ValueError(f"county {counties[0]!r} has no known region")

        plants_sorted = sorted(by_water[stock_id], key=lambda r: (r.week_start, r.species))
        last_listed = None
        for rec in plants_sorted:
            if rec.status == "listed" and rec.week_start <= source_week_start:
                if last_listed is None or rec.week_start > last_listed.week_start:
                    last_listed = rec

        waters.append(
            {
                "id": f"cdfw-{stock_id}",
                "cdfw_stock_id": stock_id,
                "name": alias.canonical_name,
                "name_status": "reviewed" if alias.reviewed else "unreviewed",
                "slug": alias.slug,
                "aliases": alias.aliases,
                "counties": counties,
                "region": region,
                "cdfw_map_url": map_url_latest.get(
                    stock_id, f"https://apps.wildlife.ca.gov/fishing/?stockid={stock_id}"
                ),
                "location": None,
                "last_listed_week": week_of(last_listed.week_start) if last_listed else None,
                "plants": [
                    {
                        "week": {
                            "start": rec.week_start.isoformat(),
                            "end": rec.week_end.isoformat(),
                            "label": f"week of {rec.week_start.isoformat()}",
                        },
                        "species": rec.species,
                        "status": rec.status,
                        "first_observed_at": _iso_z(rec.first_observed_at),
                        "last_observed_at": _iso_z(rec.last_observed_at),
                    }
                    for rec in plants_sorted
                ],
            }
        )
    return waters


@dataclasses.dataclass(frozen=True, slots=True)
class Coverage:
    waters_this_week: int
    waters_known: int
    waters_with_history: int
    names_matched: int
    names_seen: int
    rows_parsed: int
    weeks_of_history_min: int
    weeks_of_history_median: float

    def to_json(self) -> dict:
        return dataclasses.asdict(self)

    def print_report(self) -> None:
        print(
            "coverage: "
            f"waters this week {self.waters_this_week}/{self.waters_known} known  |  "
            f"names matched {self.names_matched}/{self.names_seen} seen  |  "
            f"rows parsed {self.rows_parsed}  |  "
            f"weeks of history per water: min {self.weeks_of_history_min}, "
            f"median {self.weeks_of_history_median}"
        )


def compute_coverage(
    *,
    waters: list[dict],
    waters_known: int,
    names_matched: int,
    names_seen: int,
    rows_parsed: int,
    source_week_start: str,
) -> Coverage:
    this_week = [w for w in waters if any(
        p["week"]["start"] == source_week_start and p["status"] == "listed" for p in w["plants"]
    )]
    weeks_per_water = [len(w["plants"]) for w in waters] or [0]
    return Coverage(
        waters_this_week=len(this_week),
        waters_known=waters_known,
        waters_with_history=len(waters),
        names_matched=names_matched,
        names_seen=names_seen,
        rows_parsed=rows_parsed,
        weeks_of_history_min=min(weeks_per_water),
        weeks_of_history_median=statistics.median(weeks_per_water),
    )


def build_snapshot(
    *,
    page: FetchedPage,
    rows: list[parse.RawRow],
    history: HistoryStore,
    aliases: AliasTable,
    generated_at: dt.datetime,
    names_matched: int,
    names_seen: int,
    counties_options,
    region_county_options,
    waters_known: int,
) -> dict:
    source_week = week_of(page.stated_today)
    source_week_start = dt.date.fromisoformat(source_week["start"])

    counties = build_counties(counties_options, region_county_options)
    counties_by_name = {c["name"]: c["region"] for c in counties}

    waters = build_waters(history, aliases, rows, source_week_start, counties_by_name)
    species = sorted({p["species"] for w in waters for p in w["plants"]})

    this_week = [
        {"water_id": w["id"], "species": p["species"]}
        for w in waters
        for p in w["plants"]
        if p["week"]["start"] == source_week["start"] and p["status"] == "listed"
    ]

    coverage = compute_coverage(
        waters=waters,
        waters_known=waters_known,
        names_matched=names_matched,
        names_seen=names_seen,
        rows_parsed=len(rows),
        source_week_start=source_week["start"],
    )

    snapshot = {
        "schema_version": 1,
        "generated_at": _iso_z(generated_at),
        "source": {
            "name": "CDFW Fish Planting Schedule",
            "url": "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch",
            "fetched_at": _iso_z(page.fetched_at),
            "stated_today": page.stated_today.isoformat(),
            "stated_period": {
                "start": page.stated_period_start.isoformat(),
                "end": page.stated_period_end.isoformat(),
            },
            "content_sha256": page.content_sha256,
        },
        "source_week": source_week,
        "attribution": {"text": ATTRIBUTION_TEXT, "url": ATTRIBUTION_URL},
        "licence": {"summary": LICENCE_SUMMARY, "sources": LICENCE_SOURCES},
        "regions": REGIONS,
        "counties": counties,
        "species": species,
        "waters": waters,
        "this_week": this_week,
        "coverage": coverage.to_json(),
    }
    return snapshot


def validate_snapshot(snapshot: dict, schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=snapshot, schema=schema)
