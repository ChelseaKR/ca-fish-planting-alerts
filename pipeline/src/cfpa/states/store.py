"""One state's append-only history: ``pipeline/data/states/<code>.json``.

The same rules as California's ``history.json`` (docs/DECISIONS.md 0005):
a record, once written, is never deleted, and its identity and
``first_observed_at`` never change. Only ``status``, ``count`` and
``last_observed_at`` may. A failed or refused fetch writes the attempt to
``checks`` and nothing else, so the last good data stays published and the
app can say when it was last checked.

Identity is ``(water_id, period start, precision, species)``. A Tennessee
"TBD 12/2026" month that later becomes "12/9/2026" is two records: the month
(which then reads as removed from the schedule) and the day.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any

from .base import ParsedFeed, Period, StateSource, WaterMeta

RecordKey = tuple[str, str, str, str]


class StateHistoryError(RuntimeError):
    """A write would drop or alter a recorded observation. Nothing written."""


def _iso_z(d: dt.datetime) -> str:
    return d.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclasses.dataclass(frozen=True, slots=True)
class StateRecord:
    water_id: str
    period: Period
    species: str
    status: str  # "listed" | "removed" | "reported"
    count: int | None
    first_observed_at: dt.datetime
    last_observed_at: dt.datetime

    def key(self) -> RecordKey:
        return (
            self.water_id,
            self.period.start.isoformat(),
            self.period.precision,
            self.species,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "water_id": self.water_id,
            "period": {
                "precision": self.period.precision,
                "start": self.period.start.isoformat(),
                "end": self.period.end.isoformat(),
            },
            "species": self.species,
            "status": self.status,
            "count": self.count,
            "first_observed_at": _iso_z(self.first_observed_at),
            "last_observed_at": _iso_z(self.last_observed_at),
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> StateRecord:
        return cls(
            water_id=d["water_id"],
            period=Period.from_json(d["period"]),
            species=d["species"],
            status=d["status"],
            count=d.get("count"),
            first_observed_at=_parse_dt(d["first_observed_at"]),
            last_observed_at=_parse_dt(d["last_observed_at"]),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Checks:
    """How the last attempts went. Not data; written on failure too."""

    last_attempt_at: dt.datetime | None = None
    last_success_at: dt.datetime | None = None
    last_attempt_ok: bool = False
    last_error: str | None = None
    content_sha256: str | None = None
    last_modified: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "last_attempt_at": _iso_z(self.last_attempt_at)
            if self.last_attempt_at
            else None,
            "last_success_at": _iso_z(self.last_success_at)
            if self.last_success_at
            else None,
            "last_attempt_ok": self.last_attempt_ok,
            "last_error": self.last_error,
            "content_sha256": self.content_sha256,
            "last_modified": self.last_modified,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Checks:
        def when(key: str) -> dt.datetime | None:
            v = d.get(key)
            return _parse_dt(v) if v else None

        return cls(
            last_attempt_at=when("last_attempt_at"),
            last_success_at=when("last_success_at"),
            last_attempt_ok=bool(d.get("last_attempt_ok")),
            last_error=d.get("last_error"),
            content_sha256=d.get("content_sha256"),
            last_modified=d.get("last_modified"),
        )


def _water_to_json(w: WaterMeta) -> dict[str, Any]:
    return {
        "id": w.id,
        "slug": w.slug,
        "name": w.name,
        "counties": list(w.counties),
        "towns": list(w.towns),
        "region": w.region,
        "source_id": w.source_id,
        "source_url": w.source_url,
        "months_note": w.months_note,
    }


def _water_from_json(d: dict[str, Any]) -> WaterMeta:
    return WaterMeta(
        id=d["id"],
        slug=d["slug"],
        name=d["name"],
        counties=tuple(d.get("counties", ())),
        towns=tuple(d.get("towns", ())),
        region=d.get("region"),
        source_id=d.get("source_id"),
        source_url=d.get("source_url", ""),
        months_note=d.get("months_note"),
    )


@dataclasses.dataclass(slots=True)
class StateHistory:
    state: str
    waters: dict[str, WaterMeta]
    records: list[StateRecord]
    checks: Checks
    # Every spelling the agency has used for a water id, oldest first.
    aliases: dict[str, list[str]] = dataclasses.field(default_factory=dict)

    @classmethod
    def empty(cls, state: str) -> StateHistory:
        return cls(state=state, waters={}, records=[], checks=Checks())

    @classmethod
    def load(cls, path: Path, state: str) -> StateHistory:
        if not path.exists():
            return cls.empty(state)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("state") != state:
            raise StateHistoryError(f"{path} is not {state}'s history")
        return cls(
            state=state,
            waters={w["id"]: _water_from_json(w) for w in data.get("waters", [])},
            records=[StateRecord.from_json(r) for r in data.get("records", [])],
            checks=Checks.from_json(data.get("checks", {})),
            aliases={k: list(v) for k, v in data.get("aliases", {}).items()},
        )

    def save(self, path: Path) -> None:
        old = StateHistory.load(path, self.state)
        assert_append_only(old, self)
        payload = {
            "schema": "cfpa-state-history-v1",
            "state": self.state,
            "checks": self.checks.to_json(),
            "waters": [_water_to_json(self.waters[k]) for k in sorted(self.waters)],
            "aliases": {k: self.aliases[k] for k in sorted(self.aliases)},
            "records": [r.to_json() for r in sorted(self.records, key=StateRecord.key)],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    @property
    def newest_period_start(self) -> dt.date | None:
        return max((r.period.start for r in self.records), default=None)


def assert_append_only(old: StateHistory, new: StateHistory) -> None:
    old_by_key = {r.key(): r for r in old.records}
    new_by_key = {r.key(): r for r in new.records}
    missing = set(old_by_key) - set(new_by_key)
    if missing:
        raise StateHistoryError(
            f"{len(missing)} {old.state} record(s) on disk are missing from the new "
            f"write, for example {sorted(missing)[:3]} -- refusing to overwrite history"
        )
    for key, rec in old_by_key.items():
        now = new_by_key[key]
        if rec.period != now.period or rec.first_observed_at != now.first_observed_at:
            raise StateHistoryError(
                f"{old.state} record {key} changed its period or first_observed_at "
                "-- refusing to overwrite history"
            )
    for wid, w in old.waters.items():
        if wid not in new.waters:
            raise StateHistoryError(f"{old.state} water {wid} would be dropped")
        if new.waters[wid].slug != w.slug:
            raise StateHistoryError(
                f"{old.state} water {wid} would change its slug {w.slug!r} -> "
                f"{new.waters[wid].slug!r}; a slug is a URL and never changes"
            )


def merge(
    history: StateHistory,
    feed: ParsedFeed,
    source: StateSource,
    *,
    as_of: dt.date,
) -> StateHistory:
    """Fold one fresh, parsed fetch into the state's history.

    - Every parsed record is (re)written: ``listed`` for a schedule source,
      ``reported`` for a report; ``first_observed_at`` kept if known.
    - Schedule sources only (docs/DECISIONS.md 0016): a ``listed`` record
      the fetch no longer has flips to ``removed``, but only while its period
      has not ended (``period.end >= as_of``). A past record that drops out
      of the agency's file aged off; that is not a removal.
    - Report sources never infer a removal. Nothing is ever deleted.
    - A water keeps the slug it was first given. Its name, counties and notes
      follow the agency's newest spelling, and old names are kept as aliases.
    """
    fetched_at = feed.fetched_at
    status = "listed" if source.semantics == "schedule" else "reported"
    by_key = {r.key(): r for r in history.records}
    seen: set[RecordKey] = set()
    for rec in feed.records:
        key = rec.key()
        seen.add(key)
        prior = by_key.get(key)
        by_key[key] = StateRecord(
            water_id=rec.water_id,
            period=rec.period,
            species=rec.species,
            status=status,
            count=rec.count,
            first_observed_at=prior.first_observed_at if prior else fetched_at,
            last_observed_at=fetched_at,
        )
    if source.removal_inference:
        for key, old in list(by_key.items()):
            if key in seen or old.status != "listed" or old.period.end < as_of:
                continue
            by_key[key] = dataclasses.replace(
                old, status="removed", last_observed_at=fetched_at
            )

    waters = dict(history.waters)
    aliases = {k: list(v) for k, v in history.aliases.items()}
    for wid, meta in feed.waters.items():
        prior_meta = waters.get(wid)
        if prior_meta is not None:
            if prior_meta.name != meta.name:
                names = aliases.setdefault(wid, [prior_meta.name])
                if meta.name not in names:
                    names.append(meta.name)
            meta = dataclasses.replace(meta, slug=prior_meta.slug)
        else:
            taken = {w.slug for w in waters.values()}
            if meta.slug in taken:
                meta = dataclasses.replace(
                    meta, slug=f"{meta.slug}-{wid.split('-', 1)[1]}"
                )
        waters[wid] = meta

    return StateHistory(
        state=history.state,
        waters=waters,
        records=sorted(by_key.values(), key=StateRecord.key),
        checks=Checks(
            last_attempt_at=fetched_at,
            last_success_at=fetched_at,
            last_attempt_ok=True,
            last_error=None,
            content_sha256=feed.content_sha256,
            last_modified=feed.last_modified,
        ),
        aliases=aliases,
    )


def record_failure(
    history: StateHistory, *, attempted_at: dt.datetime, error: str
) -> StateHistory:
    """The fetch failed or was refused: say so, change no data."""
    return dataclasses.replace(
        history,
        checks=dataclasses.replace(
            history.checks,
            last_attempt_at=attempted_at,
            last_attempt_ok=False,
            last_error=error[:500],
        ),
    )
