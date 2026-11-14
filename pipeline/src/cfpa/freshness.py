"""The freshness watchdog: has every live state been read successfully
recently enough? (DECISIONS 0065)

Why. On 2026-10-15 tn.gov began answering the runner's robots.txt request
with 403. Every publish run after that kept Tennessee's last good data,
printed one ``::warning`` and finished green (DECISIONS 0025: a failing
state stops nothing). publish-health.yml saw it on 10-22, opened issue #104
and commented on it every day for sixteen days, and its own run was green
too. Nobody read the issue until the 2026-11-07 freshness audit. What does
get seen is a red job in the publish run on main, so this check fails that
way, from the history files the run has just committed, and opens nothing.

What it measures: the age of each live state's last SUCCESSFUL read,
``checks.last_success_at`` in ``pipeline/data/states/<code>.json``, against
an allowance: ``DEFAULT_MAX_READ_AGE_DAYS`` unless the state's module
declares its own (``StateSource.max_read_age_days``). Not the newest record:
Michigan's DNR files a stocking days after it happens and New York's plan is
one spring publication, so record dates say nothing about whether the read
still works. A manual import (``checks.manual_file``, DECISIONS 0061) is a
good read as of the time the person downloaded the file; the later of the
two is the read that counts. A state behind an off flag (Oregon, DECISIONS
0032) is not live and is not checked.

One exception, a state that is waiting, not stuck (DECISIONS 0071): its
latest attempt failed on ArcGIS Hub's own stale flag (``checks.stale_copy``,
Massachusetts, DECISIONS 0063), and Hub's metadata, read on that same
attempt, says the agency last edited its layer longer ago than the
allowance. Nothing new is waiting upstream, so a red run would only say
again what the pages already say. A waiting state is printed, annotated as a
warning and put in the summary, and does not fail the job. The first run
after the agency edits again is red; so is a stale flag whose edit date
could not be read.

Absence is a failure, never a pass: a missing history file, no ``checks``,
no good read on record, or a time that will not parse each fail the check
with a line that says which. Every state gets one line, the same words in
the run log, in the job summary's table and in the ``::error`` annotation
that carries a stuck state to the run's front page.

Exit status: 0 every live state is fresh or waiting; 1 at least one is stuck or could
not be read; 2 usage error.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .states import StateSource, enabled_states, registered_sources
from .states.run import history_path

# How old a state's last successful read may be before its line goes red.
# The publish run fetches every live state twice a day, so seven days is at
# least fourteen refused reads: an outage, not a hiccup. Tennessee's was 23
# days old when this was written.
DEFAULT_MAX_READ_AGE_DAYS = 7
# A read stamped later than this job's clock is wrong data, not fresh data.
# This much lets the build runner's clock and this runner's disagree.
CLOCK_SKEW_ALLOWANCE = dt.timedelta(hours=1)
PIPELINE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_STATES_DIR = PIPELINE_DIR / "data" / "states"
SECONDS_PER_DAY = 86400.0


class FreshnessInputError(ValueError):
    """The history file cannot answer the question. A failure, never a pass."""


@dataclasses.dataclass(frozen=True, slots=True)
class Reading:
    """One live state's answer. ``problem`` is None when the state is fresh."""

    code: str
    name: str
    max_age_days: int
    last_good_read: dt.datetime | None = None
    read_method: str = "none"  # "automated" | "manual" | "none"
    age_days: float | None = None
    problem: str | None = None
    # Set when the state is waiting (DECISIONS 0071): why, in one clause.
    # ``problem`` is then None, so the job passes.
    waiting: str | None = None

    @property
    def fresh(self) -> bool:
        """Passes the job: fresh, or waiting."""
        return self.problem is None

    @property
    def status(self) -> str:
        if self.problem is not None:
            return "STUCK"
        return "waiting" if self.waiting is not None else "fresh"


def _fmt(when: dt.datetime) -> str:
    return when.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%MZ")


def _parse_when(value: object, what: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise FreshnessInputError(f"{what} is missing")
    try:
        when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FreshnessInputError(f"{what} {value!r} is not a time") from exc
    if when.tzinfo is None:
        raise FreshnessInputError(f"{what} {value!r} has no time zone")
    return when


def last_good_read(checks: Mapping[str, Any]) -> tuple[dt.datetime, str]:
    """When the state's data was last read successfully, and how: the later
    of the automated ``last_success_at`` and a manual import's
    ``manual_file.downloaded_at`` (DECISIONS 0061). Read from the file's own
    JSON, so it works on either side of the import's arrival. Raises when
    neither is on record."""
    automated = (
        _parse_when(checks.get("last_success_at"), "last_success_at")
        if checks.get("last_success_at") is not None
        else None
    )
    manual_file = checks.get("manual_file")
    manual: dt.datetime | None = None
    if manual_file is not None:
        if not isinstance(manual_file, Mapping):
            raise FreshnessInputError("manual_file is not an object")
        manual = _parse_when(
            manual_file.get("downloaded_at"), "manual_file.downloaded_at"
        )
    if manual is not None and (automated is None or manual >= automated):
        return manual, "manual"
    if automated is None:
        raise FreshnessInputError("no good read on record")
    return automated, "automated"


def _load_checks(path: Path, code: str) -> Mapping[str, Any]:
    if not path.exists():
        raise FreshnessInputError(f"no history file at {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FreshnessInputError(f"{path.name} is not readable JSON: {exc}") from exc
    if not isinstance(data, Mapping) or data.get("state") != code:
        raise FreshnessInputError(f"{path.name} is not {code}'s history")
    checks = data.get("checks")
    if not isinstance(checks, Mapping):
        raise FreshnessInputError(f"{path.name} has no checks")
    return checks


def waiting_reason(
    checks: Mapping[str, Any], source: StateSource, *, now: dt.datetime, limit: int
) -> tuple[str | None, str | None]:
    """For a state older than its allowance: (waiting, None) when DECISIONS
    0071's exception holds, (None, extra words for the stuck line) when the
    latest failure was Hub's stale flag but the exception does not hold, and
    (None, None) otherwise. The facts must come from the latest attempt:
    a failed attempt with ``stale_copy.checked_at`` equal to
    ``last_attempt_at``."""
    stale = checks.get("stale_copy")
    if checks.get("last_attempt_ok") is not False or not isinstance(stale, Mapping):
        return None, None
    try:
        attempt = _parse_when(checks.get("last_attempt_at"), "last_attempt_at")
        checked = _parse_when(stale.get("checked_at"), "stale_copy.checked_at")
    except FreshnessInputError:
        return None, None
    if checked != attempt:
        return None, None
    agency = source.agency_short_name
    try:
        edited = _parse_when(
            stale.get("source_last_edit_at"), "stale_copy.source_last_edit_at"
        )
    except FreshnessInputError:
        return None, (
            f"Hub's file is stale and {agency}'s last edit to its layer could "
            "not be read"
        )
    edit_age = (now - edited).total_seconds() / SECONDS_PER_DAY
    if edit_age > limit:
        return (
            f"Hub's file is stale, and {agency} has not edited its layer since "
            f"{_fmt(edited)} ({edit_age:.1f} days ago); red again as soon as it does"
        ), None
    return None, (
        f"Hub's file is stale and {agency} edited its layer {_fmt(edited)}, "
        f"{max(edit_age, 0.0):.1f} days ago"
    )


def allowance(source: StateSource, default_days: int) -> int:
    """The state module's own allowance, or the default."""
    days = source.max_read_age_days
    return default_days if days is None else days


def read_state(
    states_dir: Path, source: StateSource, *, now: dt.datetime, default_days: int
) -> Reading:
    """One state's reading from its committed history file."""
    limit = allowance(source, default_days)
    base = Reading(code=source.code, name=source.name, max_age_days=limit)
    try:
        checks = _load_checks(history_path(states_dir, source.code), source.code)
        when, method = last_good_read(checks)
    except FreshnessInputError as exc:
        return dataclasses.replace(base, problem=str(exc))
    age = (now - when).total_seconds() / SECONDS_PER_DAY
    reading = dataclasses.replace(
        base, last_good_read=when, read_method=method, age_days=max(age, 0.0)
    )
    if when - now > CLOCK_SKEW_ALLOWANCE:
        return dataclasses.replace(reading, problem=f"later than now ({_fmt(now)})")
    if age > limit:
        waiting, detail = waiting_reason(checks, source, now=now, limit=limit)
        if waiting is not None:
            return dataclasses.replace(reading, waiting=waiting)
        problem = "older than allowed" + (f"; {detail}" if detail else "")
        return dataclasses.replace(reading, problem=problem)
    return reading


def check(
    states_dir: Path,
    sources: Mapping[str, StateSource],
    *,
    now: dt.datetime,
    default_days: int = DEFAULT_MAX_READ_AGE_DAYS,
) -> list[Reading]:
    """Every given state's reading, in the order given."""
    return [
        read_state(states_dir, source, now=now, default_days=default_days)
        for source in sources.values()
    ]


def line(reading: Reading) -> str:
    """One state in one line, the same words everywhere it is reported."""
    head = f"{reading.code} ({reading.name}): {reading.status}: "
    if reading.last_good_read is None or reading.age_days is None:
        return f"{head}{reading.problem}; allowed {reading.max_age_days} days"
    body = (
        f"last good read {_fmt(reading.last_good_read)} ({reading.read_method}), "
        f"{reading.age_days:.1f} days ago, allowed {reading.max_age_days} days"
    )
    if reading.waiting is not None:
        return f"{head}{body}; {reading.waiting}"
    return head + body if reading.fresh else f"{head}{body}; {reading.problem}"


def verdict(readings: Sequence[Reading], now: dt.datetime) -> str:
    stuck = sum(1 for r in readings if not r.fresh)
    waiting = sum(1 for r in readings if r.waiting is not None)
    total = len(readings)
    states = "state" if total == 1 else "states"
    also = f", {waiting} waiting" if waiting else ""
    if stuck:
        return (
            f"freshness: {stuck} of {total} live {states} stuck{also}; "
            f"checked {_fmt(now)}"
        )
    if waiting:
        return (
            f"freshness: no live state stuck ({total - waiting} fresh{also}); "
            f"checked {_fmt(now)}"
        )
    return f"freshness: all {total} live {states} fresh; checked {_fmt(now)}"


def print_report(readings: Sequence[Reading], now: dt.datetime) -> None:
    """The run log: one line per state and a verdict. Under GitHub Actions a
    stuck state is also an ``::error`` annotation, so it shows on the run's
    front page without opening the log."""
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for reading in readings:
        text = line(reading)
        print(text)
        if annotate and not reading.fresh:
            print(f"::error title={reading.name} is stuck::{text}")
        elif annotate and reading.waiting is not None:
            print(f"::warning title={reading.name} is waiting::{text}")
    print(verdict(readings, now))


def _cell_when(reading: Reading) -> str:
    if reading.last_good_read is None:
        return "none on record"
    return f"{_fmt(reading.last_good_read)} ({reading.read_method})"


def _cell_age(reading: Reading) -> str:
    return "none" if reading.age_days is None else f"{reading.age_days:.1f} days"


def summary_markdown(readings: Sequence[Reading], now: dt.datetime) -> str:
    """The job summary: a table naming each state, its last good read, the
    age and the allowance, and the verdict."""
    sentence = verdict(readings, now).removeprefix("freshness: ")
    rows = [
        "## Freshness watchdog",
        "",
        f"{sentence[0].upper()}{sentence[1:]}.",
        "A live state is stuck when its last successful read is older than its "
        "allowance (DECISIONS 0065), unless it is waiting: Hub's file is stale "
        "and the agency has not edited its layer within the allowance either "
        "(DECISIONS 0071).",
        "",
        "| State | Last good read | Age | Allowed | Result |",
        "|---|---|---|---|---|",
    ]
    for r in readings:
        result = (
            f"STUCK: {r.problem}"
            if not r.fresh
            else f"waiting: {r.waiting}"
            if r.waiting is not None
            else "fresh"
        )
        rows.append(
            f"| {r.code} {r.name} | {_cell_when(r)} | {_cell_age(r)} | "
            f"{r.max_age_days} days | {result} |"
        )
    return "\n".join(rows) + "\n"


def write_summary(readings: Sequence[Reading], now: dt.datetime, path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(summary_markdown(readings, now))


def select_sources(spec: str | None) -> dict[str, StateSource]:
    """The states to check: the live ones (``enabled_states``, which adds a
    flagged state only when its flag is on), or the comma-separated codes
    given. A code this run does not know, including a flagged state whose
    flag is off, is a usage error; so is an empty list, which would pass by
    checking nothing."""
    known = registered_sources()
    codes = (
        enabled_states()
        if spec is None
        else tuple(c.strip().upper() for c in spec.split(",") if c.strip())
    )
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ValueError(
            f"unknown state code(s) {unknown}; a state behind an off flag is not live"
        )
    if not codes:
        raise ValueError("no states to check")
    return {c: known[c] for c in codes}


def _summary_path(given: Path | None) -> Path | None:
    if given is not None:
        return given
    from_env = os.environ.get("GITHUB_STEP_SUMMARY")
    return Path(from_env) if from_env else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cfpa.freshness", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("--states-dir", type=Path, default=DEFAULT_STATES_DIR)
    parser.add_argument(
        "--states",
        default=None,
        help="comma-separated state codes; default: the live states",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_READ_AGE_DAYS,
        help="the allowance for a state whose module declares none",
    )
    parser.add_argument(
        "--now", default=None, help="an ISO instant, to reproduce a run; default now"
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="append the Markdown table here; default $GITHUB_STEP_SUMMARY if set",
    )
    args = parser.parse_args(argv)
    try:
        sources = select_sources(args.states)
        now = (
            _parse_when(args.now, "--now")
            if args.now is not None
            else dt.datetime.now(dt.UTC)
        )
        if args.max_age_days < 1:
            raise ValueError("--max-age-days must be at least 1")
    except ValueError as exc:
        print(f"freshness: error: {exc}", file=sys.stderr)
        return 2
    readings = check(args.states_dir, sources, now=now, default_days=args.max_age_days)
    print_report(readings, now)
    summary = _summary_path(args.summary)
    if summary is not None:
        write_summary(readings, now, summary)
    return 0 if all(r.fresh for r in readings) else 1


if __name__ == "__main__":
    sys.exit(main())
