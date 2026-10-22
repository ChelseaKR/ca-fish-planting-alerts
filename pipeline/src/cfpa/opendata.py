"""The open-data files: CSV and JSON for each state, written by the site build.

Both file kinds carry the same flat records, one per (water, period,
species), with one fixed list of columns (``COLUMNS``). The files are built
from the finished v2 snapshot and nothing else, so they cannot disagree with
``snapshot/v2.json``; and every value that says when the data was last
refreshed comes from the data (the source fetch time), never the build clock,
so rebuilding unchanged data writes byte-identical files.

Two files per state and format:

- ``current``: records for this week and later that the agency still lists
  (status ``listed`` or ``reported``). A removed record is not current.
- ``history``: every record this site has observed, all statuses.

Paths are versioned (``data/v1/``). A column's name or meaning never changes
inside a version; a change that would break a reader gets ``v2``.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
DATA_DIR = f"data/v{SCHEMA_VERSION}"

# (name, type, description). The order is the CSV column order and the order
# of keys in each JSON record. The data dictionary on /data/ prints this list,
# so the page, the files and the tests cannot drift apart.
COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("state", "text", "Two-letter state code: CA or TN."),
    (
        "water_id",
        "text",
        "This site's stable id for the water, the same id as in snapshot/v2.json. "
        "California: cdfw- plus CDFW's StockingWaterID. Never reused.",
    ),
    (
        "water_name",
        "text",
        "The water's display name, as this site shows it. CDFW's spelling "
        "is kept unless this site has reviewed and corrected it.",
    ),
    (
        "source_water_id",
        "text",
        "The agency's own key for the water. Empty when the agency has none "
        "(Tennessee).",
    ),
    (
        "counties",
        "text",
        "Counties the agency lists for the water. In CSV, several are joined "
        "with a semicolon and a space; in JSON, an array.",
    ),
    (
        "region",
        "text",
        "The agency's region code for the water. Empty when unknown.",
    ),
    ("species", "text", "The species as the agency names it."),
    (
        "period_precision",
        "text",
        "How exact the agency's date is: week, day or month. California is "
        "always week.",
    ),
    (
        "period_start",
        "date",
        "Start of the period, YYYY-MM-DD. For a week, a Sunday.",
    ),
    (
        "period_end",
        "date",
        "End of the period, YYYY-MM-DD. For a week, the Saturday that "
        "follows; for a day, the same as period_start.",
    ),
    (
        "period_label",
        "text",
        "The period as this site displays it, such as week of 2026-10-18. "
        "Show it as given; do not shorten a week to a day.",
    ),
    (
        "status",
        "text",
        "listed: on the agency's schedule as of the last check. removed: was "
        "on the schedule and dropped before its period ended (used for states "
        "that publish schedules). reported: the agency reports the stocking "
        "as done (used for states that publish reports).",
    ),
    (
        "count",
        "integer",
        "Fish count when the agency gives one. Empty when it does not "
        "(California never does).",
    ),
    (
        "first_observed_at",
        "datetime",
        "When this site began seeing the record, UTC, YYYY-MM-DDTHH:MM:SSZ.",
    ),
    (
        "last_observed_at",
        "datetime",
        "When this site last saw the record, UTC, YYYY-MM-DDTHH:MM:SSZ.",
    ),
    ("water_page", "url", "The water's page on this site."),
    ("source_url", "url", "The agency's own link for the water."),
)
COLUMN_NAMES = tuple(c[0] for c in COLUMNS)

FILE_KINDS = ("current", "history")


@dataclass(frozen=True)
class OpenFile:
    """One written file: its path under the site root and its content."""

    state: str
    kind: str  # "current" or "history"
    fmt: str  # "csv" or "json"
    path: str
    records: int
    text: str


def _record(w: dict[str, Any], p: dict[str, Any], base_url: str) -> dict[str, Any]:
    per = p["period"]
    return {
        "state": w["state"],
        "water_id": w["id"],
        "water_name": w["name"],
        "source_water_id": w["source_id"] or "",
        "counties": list(w["counties"]),
        "region": w["region"] or "",
        "species": p["species"],
        "period_precision": per["precision"],
        "period_start": per["start"],
        "period_end": per["end"],
        "period_label": per["label"],
        "status": p["status"],
        "count": p["count"],
        "first_observed_at": p["first_observed_at"],
        "last_observed_at": p["last_observed_at"],
        "water_page": f"{base_url}{w['site_path']}",
        "source_url": w["source_url"],
    }


def records_for_state(
    snap_v2: dict[str, Any], state: dict[str, Any], *, base_url: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(current, history) records for one state, in a fixed order."""
    week_start = state["current_week"]["start"]
    history: list[dict[str, Any]] = []
    for w in snap_v2["waters"]:
        if w["state"] != state["code"]:
            continue
        for p in w["plants"]:
            history.append(_record(w, p, base_url))
    history.sort(
        key=lambda r: (
            r["water_name"],
            r["water_id"],
            r["period_start"],
            r["period_end"],
            r["species"],
        )
    )
    current = [
        r
        for r in history
        if r["status"] in ("listed", "reported") and r["period_end"] >= week_start
    ]
    return current, history


def _csv_text(records: list[dict[str, Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMN_NAMES)
    for r in records:
        row = []
        for name in COLUMN_NAMES:
            v = r[name]
            if name == "counties":
                v = "; ".join(v)
            row.append("" if v is None else v)
        writer.writerow(row)
    return out.getvalue()


def terms_url(state: dict[str, Any]) -> str:
    """The terms page of the source the state's attribution names (else the
    first source listed)."""
    sources = state["license"]["sources"]
    for s in sources:
        if s["url"] == state["attribution"]["url"]:
            return str(s["terms_url"])
    return str(sources[0]["terms_url"])


def _json_text(
    records: list[dict[str, Any]], *, state: dict[str, Any], kind: str
) -> str:
    terms = terms_url(state)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "state": state["code"],
        "kind": kind,
        "updated": state["source"]["fetched_at"][:10],
        "source_fetched_at": state["source"]["fetched_at"],
        "current_week": state["current_week"],
        "agency": state["agency"],
        "attribution": state["attribution"],
        "terms_url": terms,
        "disclaimer": state["disclaimer"],
        "columns": [{"name": n, "type": t} for n, t, _ in COLUMNS],
        "records": records,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def build_files(snap_v2: dict[str, Any], *, base_url: str) -> list[OpenFile]:
    """Every open-data file for every state in ``snap_v2``."""
    files: list[OpenFile] = []
    for state in snap_v2["states"]:
        code = state["code"].lower()
        current, history = records_for_state(snap_v2, state, base_url=base_url)
        for kind, recs in (("current", current), ("history", history)):
            files.append(
                OpenFile(
                    state=state["code"],
                    kind=kind,
                    fmt="csv",
                    path=f"{DATA_DIR}/{code}-{kind}.csv",
                    records=len(recs),
                    text=_csv_text(recs),
                )
            )
            files.append(
                OpenFile(
                    state=state["code"],
                    kind=kind,
                    fmt="json",
                    path=f"{DATA_DIR}/{code}-{kind}.json",
                    records=len(recs),
                    text=_json_text(recs, state=state, kind=kind),
                )
            )
    return files
