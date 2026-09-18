"""The per-water history store: the asset (DECISIONS 0005).

CDFW's page only ever shows a rolling ~1-year window. A pipeline that just
saved "whatever the page shows today" would silently lose every week that
ages off that window -- the exact "absence rendered as a value" bug class
this portfolio has hit before. So the store is a JSON file, committed to the
repo (chosen over a Release asset: it is small -- ~2,000 rows/year, well
under a megabyte for years -- and a committed file means every change is a
reviewable, `git blame`-able diff, which a binary/opaque Release asset asset
is not), and writing to it goes through an integrity check that refuses to
drop or mutate an already-recorded observation. Identity is
``(cdfw_stock_id, week_start, species)``; only ``status`` and
``last_observed_at`` may change after a record is first written.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any

RecordKey = tuple[int, str, str]  # (cdfw_stock_id, week_start ISO date, species)

# CDFW's stated "All Plants (<start> - <end>)" window moves once a week (its
# start is the current week's Sunday minus one year), but the rows the page
# actually shows age off one DAY at a time. Measured on a real fetch,
# Thursday 2026-09-17: the page still stated "All Plants (9/13/2025 -
# 9/27/2026)" but no longer listed a single plant for the week of
# 2025-09-14 -- 23 plants the 2026-09-13 fetch had listed. So the oldest
# week inside the stated window is partly or wholly aged off on most days,
# and a plant's absence there is NOT evidence that CDFW removed it. Removal
# is inferred only for weeks starting at least this far past the stated
# start: within any CDFW week the run date is at most start + 6 days, so a
# one-year age-off by date never reaches a week starting start + 7 or later.
AGE_OFF_MARGIN = dt.timedelta(days=7)


class HistoryIntegrityError(RuntimeError):
    """Raised when a write would drop or mutate an existing history record.

    This is the guard the append-only property rests on: it is what makes
    'an overwrite fails' a testable, enforced fact rather than a convention.
    """


@dataclasses.dataclass(frozen=True, slots=True)
class PlantRecord:
    cdfw_stock_id: int
    week_start: dt.date
    week_end: dt.date
    species: str
    status: str  # "listed" | "removed"
    first_observed_at: dt.datetime
    last_observed_at: dt.datetime

    def key(self) -> RecordKey:
        return (self.cdfw_stock_id, self.week_start.isoformat(), self.species)

    def to_json(self) -> dict[str, Any]:
        return {
            "cdfw_stock_id": self.cdfw_stock_id,
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "species": self.species,
            "status": self.status,
            "first_observed_at": _iso_z(self.first_observed_at),
            "last_observed_at": _iso_z(self.last_observed_at),
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> PlantRecord:
        return cls(
            cdfw_stock_id=int(d["cdfw_stock_id"]),
            week_start=dt.date.fromisoformat(d["week_start"]),
            week_end=dt.date.fromisoformat(d["week_end"]),
            species=d["species"],
            status=d["status"],
            first_observed_at=_parse_dt(d["first_observed_at"]),
            last_observed_at=_parse_dt(d["last_observed_at"]),
        )


def _parse_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iso_z(d: dt.datetime) -> str:
    return d.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def assert_append_only(
    old_records: list[PlantRecord], new_records: list[PlantRecord]
) -> None:
    """Raise HistoryIntegrityError if ``new_records`` would lose or alter any
    record already present in ``old_records``.

    Checked: every key in old must exist in new; week_end/first_observed_at
    (the immutable identity/provenance fields) must be byte-identical.
    status/last_observed_at are allowed to change (that is how a listed
    plant becomes 'removed').
    """
    old_by_key = {r.key(): r for r in old_records}
    new_by_key = {r.key(): r for r in new_records}

    missing = set(old_by_key) - set(new_by_key)
    if missing:
        sample = sorted(missing)[:5]
        raise HistoryIntegrityError(
            f"{len(missing)} history record(s) present on disk are missing from "
            f"the new write -- refusing to overwrite history. Sample missing keys "
            f"(cdfw_stock_id, week_start, species): {sample}"
        )

    for key, old in old_by_key.items():
        new = new_by_key[key]
        if (
            old.week_end != new.week_end
            or old.first_observed_at != new.first_observed_at
        ):
            raise HistoryIntegrityError(
                f"history record {key} changed an immutable field: "
                f"old week_end/first_observed_at={old.week_end}/{old.first_observed_at} "
                f"new={new.week_end}/{new.first_observed_at} -- refusing to overwrite history"
            )


@dataclasses.dataclass(slots=True)
class HistoryStore:
    records: list[PlantRecord]

    @classmethod
    def load(cls, path: Path) -> HistoryStore:
        if not path.exists():
            return cls(records=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(records=[PlantRecord.from_json(r) for r in data.get("plants", [])])

    def save(self, path: Path) -> None:
        """Write, after checking append-only against whatever is currently on
        disk at ``path``. Raises HistoryIntegrityError and writes nothing if
        the check fails -- the file on disk is untouched on failure."""
        old = HistoryStore.load(path)
        assert_append_only(old.records, self.records)
        ordered = sorted(self.records, key=lambda r: r.key())
        payload = {
            "schema": "cfpa-history-v1",
            "plants": [r.to_json() for r in ordered],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def by_water(self) -> dict[int, list[PlantRecord]]:
        out: dict[int, list[PlantRecord]] = {}
        for r in self.records:
            out.setdefault(r.cdfw_stock_id, []).append(r)
        for v in out.values():
            v.sort(key=lambda r: r.week_start)
        return out


def merge_observations(
    existing: list[PlantRecord],
    observed_this_run: set[RecordKey],
    parsed_rows: dict[RecordKey, tuple[int, dt.date, dt.date, str]],
    *,
    page_window_start: dt.date,
    page_window_end: dt.date,
    fetched_at: dt.datetime,
) -> list[PlantRecord]:
    """Fold one run's parsed rows into the existing history.

    - A key parsed this run is (re-)written with status "listed" and
      last_observed_at = fetched_at; first_observed_at is preserved if the
      key already existed, else set to fetched_at.
    - A key that existed with status "listed", whose week falls inside this
      run's page window (so CDFW *could* have shown it), but was NOT parsed
      this run, flips to "removed" (CDFW dropped a scheduled plant -- see
      DECISIONS 0005 / the source's own "subject to change" notice). The
      window's oldest week is excluded (``AGE_OFF_MARGIN``): the page drops
      those rows day by day while still stating the same window, so absence
      there means "aged off", not "removed".
    - Every other existing key (outside the page's window, in its oldest
      week, or already "removed") passes through unchanged. Nothing is ever
      deleted.
    """
    by_key = {r.key(): r for r in existing}

    for key in observed_this_run:
        stock_id, _week_start_iso, species = key
        _, week_start, week_end, _species = parsed_rows[key]
        prior = by_key.get(key)
        first_observed = prior.first_observed_at if prior else fetched_at
        by_key[key] = PlantRecord(
            cdfw_stock_id=stock_id,
            week_start=week_start,
            week_end=week_end,
            species=species,
            status="listed",
            first_observed_at=first_observed,
            last_observed_at=fetched_at,
        )

    for key, rec in list(by_key.items()):
        if key in observed_this_run:
            continue
        if rec.status != "listed":
            continue
        if page_window_start + AGE_OFF_MARGIN <= rec.week_start <= page_window_end:
            by_key[key] = dataclasses.replace(
                rec, status="removed", last_observed_at=fetched_at
            )

    return list(by_key.values())
