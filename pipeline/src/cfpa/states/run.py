"""One run's work for the non-California states: fetch (or read fixtures),
parse, merge into each state's history, and report. Nothing is written here:
``cli.run`` writes the histories only after the v2 snapshot has been built
and validated, the same order California's history follows.

A state that fails is isolated: its last good data stays, its ``checks``
say what happened, and California and every other state carry on.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from . import SOURCES
from .base import (
    FetchContext,
    FetchedBody,
    NotModified,
    StateFetchError,
    StateFormatError,
    StateSource,
    real_sleep,
)
from .store import (
    StateHistory,
    StateHistoryError,
    merge,
    record_failure,
    record_unchanged,
)


@dataclasses.dataclass(frozen=True, slots=True)
class StateRun:
    source: StateSource
    history: StateHistory
    path: Path
    # "updated": a fresh fetch was merged. "failed": a fetch was tried and
    # refused; only ``checks`` changed. "skipped": not fetched this run.
    outcome: str
    message: str

    @property
    def needs_write(self) -> bool:
        return self.outcome != "skipped"


def history_path(states_dir: Path, code: str) -> Path:
    return states_dir / f"{code.lower()}.json"


def civil_date(when: dt.datetime, time_zone: str) -> dt.date:
    return when.astimezone(ZoneInfo(time_zone)).date()


def load_fixture_bodies(
    fixtures_dir: Path, code: str, fetched_at: dt.datetime
) -> list[FetchedBody]:
    """``<code>.<ext>`` (one body) or ``<code>-<n>.<ext>`` (pages, in order),
    where the extension is the source's own: ``.json`` (Tennessee, New
    York), ``.csv`` (Massachusetts, Michigan) or ``.html`` (Oregon)."""
    lower = code.lower()
    paths: list[Path] = []
    for ext in ("json", "csv", "html"):
        single = fixtures_dir / f"{lower}.{ext}"
        paths = (
            [single]
            if single.exists()
            else sorted(
                fixtures_dir.glob(f"{lower}-*.{ext}"),
                key=lambda p: int(p.stem.rsplit("-", 1)[1]),
            )
        )
        if paths:
            break
    if not paths:
        raise StateFetchError(f"no fixture for {code} in {fixtures_dir}")
    return [
        FetchedBody(
            url=f"file://{p.name}",
            text=p.read_text(encoding="utf-8"),
            fetched_at=fetched_at,
            last_modified=None,
        )
        for p in paths
    ]


def _fetch_live(
    source: StateSource,
    history: StateHistory,
    *,
    user_agent: str,
    client: httpx.Client | None,
    sleep: Callable[[float], None],
) -> list[FetchedBody]:
    owns = client is None
    client = client or httpx.Client()
    try:
        # The newest record on file lets a long report re-read only the
        # recent past (Michigan); a whole-file source ignores it.
        context = FetchContext(
            newest=history.newest_period_start,
            etag=history.checks.etag,
            last_modified=history.checks.last_modified,
        )
        return source.fetch(client, user_agent, sleep, context)
    finally:
        if owns:
            client.close()


def run_states(
    *,
    states_dir: Path,
    fetch_codes: Iterable[str],
    user_agent: str,
    now: dt.datetime,
    fixtures_dir: Path | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = real_sleep,
) -> list[StateRun]:
    """Every known state's history, after this run's fetches. A state not in
    ``fetch_codes`` is loaded as it is on disk and marked skipped."""
    wanted = {c.upper() for c in fetch_codes}
    unknown = wanted - set(SOURCES)
    if unknown:
        raise StateFetchError(f"unknown state code(s): {sorted(unknown)}")
    runs: list[StateRun] = []
    for code, source in SOURCES.items():
        path = history_path(states_dir, code)
        history = StateHistory.load(path, code)
        if code not in wanted:
            runs.append(StateRun(source, history, path, "skipped", "not fetched"))
            continue
        try:
            if fixtures_dir is not None:
                bodies = load_fixture_bodies(fixtures_dir, code, now)
            else:
                bodies = _fetch_live(
                    source, history, user_agent=user_agent, client=client, sleep=sleep
                )
            feed = source.parse(bodies)
            if len(feed.records) < source.min_rows:
                raise StateFormatError(
                    f"{source.agency_short_name}'s feed parsed to {len(feed.records)} "
                    f"records, fewer than {source.min_rows}; a truncated or reshaped "
                    "feed is not read as 'nothing scheduled'"
                )
            as_of = civil_date(feed.fetched_at, source.time_zone)
            merged = merge(history, feed, source, as_of=as_of)
            removed = sum(
                1
                for new in merged.records
                if new.status == "removed" and new.last_observed_at == feed.fetched_at
            )
            message = (
                f"{len(feed.records)} records, {len(feed.waters)} waters"
                + (
                    f", {feed.skipped} {'row' if feed.skipped == 1 else 'rows'}"
                    " with no usable date skipped"
                    if feed.skipped
                    else ""
                )
                + (f", {removed} newly removed from the schedule" if removed else "")
            )
            runs.append(StateRun(source, merged, path, "updated", message))
        except NotModified:
            # A 304: the file on file is still the agency's current one.
            unchanged = record_unchanged(history, checked_at=now)
            runs.append(StateRun(source, unchanged, path, "unchanged", "not modified"))
        except (StateFetchError, StateFormatError, StateHistoryError) as exc:
            failed = record_failure(history, attempted_at=now, error=str(exc))
            runs.append(StateRun(source, failed, path, "failed", str(exc)))
    return runs


def print_report(runs: Iterable[StateRun]) -> None:
    for r in runs:
        if r.outcome == "skipped":
            continue
        if r.outcome in ("updated", "unchanged"):
            print(f"states: {r.source.code} {r.outcome}: {r.message}")
            continue
        print(
            f"cfpa: WARNING {r.source.code} ({r.source.name}) was not updated; its "
            f"last good data is kept: {r.message}",
            file=sys.stderr,
        )
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title={r.source.name} not updated::{r.message[:300]}")


def write(runs: Iterable[StateRun]) -> None:
    for r in runs:
        if r.needs_write:
            r.history.save(r.path)
