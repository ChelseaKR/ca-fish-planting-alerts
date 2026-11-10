"""Load TWRA's downloadable CSV by hand (DECISIONS 0061).

tn.gov answers the pipeline's automated read with HTTP 403 (issue #97), and
Trout Truck does not work around a site's security settings. TWRA's page
offers its schedule as a CSV download, so the owner downloads it in a
browser now and then and runs::

    make import-tn-csv CSV="$HOME/Downloads/Trout Fishing and Stockings in Tennessee.csv"

or, from ``pipeline/``::

    uv run --frozen python -I -m cfpa.import_tn_csv PATH [--downloaded-at WHEN]

The CSV has the same eight columns, in the same order, as the JSON the page
loads, with the same values, so its rows go through the reader's own
``tn.parse_rows``: the same TBD months, week-of Sundays, month letters,
skipped non-Sunday weeks and TWRA's own spellings ("Caroll"). The header is
checked exactly and any drift is refused, as is a file older than the data
already on file. The history is written with the file's provenance
(``Checks.manual_file``); the daily automated read keeps running and failing
honestly, and a failed run changes only its own attempt fields.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import hashlib
import io
import sys
from collections.abc import Sequence
from pathlib import Path
from zoneinfo import ZoneInfo

from .states import tn
from .states.base import StateFormatError
from .states.run import civil_date, history_path
from .states.store import (
    Checks,
    ManualFile,
    StateHistory,
    StateHistoryError,
    merge,
)

SOURCE_LABEL = "TWRA's downloadable CSV"
# Relative to pipeline/, where the Makefile target runs it.
DEFAULT_STATES_DIR = Path("data/states")


class ImportRefused(RuntimeError):
    """The file was not loaded. Nothing was written."""


def read_rows(data: bytes) -> list[dict[str, str]]:
    """The CSV's rows as the reader's row dicts. Refuses anything that is not
    exactly TWRA's eight columns: a renamed, missing, extra or reordered
    column, a short or long row, or a blank line before the end."""
    try:
        # A byte-order mark is an encoding detail, not a column name.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportRefused(f"the file is not UTF-8 text: {exc}") from exc
    try:
        parsed = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as exc:
        raise ImportRefused(f"the file is not a well-formed CSV: {exc}") from exc
    while parsed and not parsed[-1]:
        parsed.pop()  # trailing blank lines (TWRA's file ends with one)
    if not parsed:
        raise ImportRefused("the file is empty")
    header = parsed[0]
    if tuple(header) != tn.COLUMNS:
        raise ImportRefused(
            f"the header is {header!r}, not TWRA's {list(tn.COLUMNS)!r}; "
            "the file's columns changed, so it is not read"
        )
    rows: list[dict[str, str]] = []
    for line, row in enumerate(parsed[1:], start=2):
        if len(row) != len(tn.COLUMNS):
            raise ImportRefused(
                f"line {line} has {len(row)} fields, not {len(tn.COLUMNS)}"
            )
        rows.append({c: v.strip() for c, v in zip(tn.COLUMNS, row, strict=True)})
    return rows


def parse_downloaded_at(text: str | None, path: Path) -> dt.datetime:
    """``--downloaded-at``: an ISO date-time with an offset, or a date (read
    as noon in Tennessee's time zone). Without it, the file's modification
    time, which a browser download sets to when it was saved."""
    if text is None:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
    try:
        if len(text) == 10:
            day = dt.date.fromisoformat(text)
            return dt.datetime(
                day.year, day.month, day.day, 12, tzinfo=ZoneInfo(tn.SOURCE.time_zone)
            ).astimezone(dt.UTC)
        when = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportRefused(f"--downloaded-at {text!r} is not a date: {exc}") from exc
    if when.tzinfo is None:
        raise ImportRefused(
            f"--downloaded-at {text!r} has no time zone offset; add one, "
            "for example 2026-11-07T11:23-08:00"
        )
    return when.astimezone(dt.UTC)


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    history: StateHistory
    path: Path
    message: str


def import_csv(
    path: Path,
    *,
    states_dir: Path,
    downloaded_at: dt.datetime,
    now: dt.datetime,
    min_rows: int | None = None,
) -> ImportResult:
    """Read the file and fold it into Tennessee's history. Writes nothing;
    ``ImportResult.history.save(ImportResult.path)`` does."""
    source = tn.SOURCE
    if downloaded_at > now:
        raise ImportRefused(f"the download time {downloaded_at} is in the future")
    data = path.read_bytes()
    rows = read_rows(data)
    sha = hashlib.sha256(data).hexdigest()
    try:
        feed = tn.parse_rows(
            rows, fetched_at=downloaded_at, content_sha256=sha, last_modified=None
        )
    except StateFormatError as exc:
        raise ImportRefused(f"TWRA's rows do not read: {exc}") from exc
    floor = source.min_rows if min_rows is None else min_rows
    if len(feed.records) < floor:
        raise ImportRefused(
            f"the file parsed to {len(feed.records)} records, fewer than {floor}; "
            "a truncated file is not read as 'nothing scheduled'"
        )
    hpath = history_path(states_dir, source.code)
    if not hpath.exists():
        raise ImportRefused(
            f"{hpath} does not exist; run this from pipeline/ or pass --states-dir"
        )
    history = StateHistory.load(hpath, source.code)
    prior = history.checks
    if prior.last_success_at is not None and downloaded_at <= prior.last_success_at:
        raise ImportRefused(
            f"the file was downloaded {downloaded_at:%Y-%m-%d %H:%M}Z, not after "
            f"the data on file ({prior.last_success_at:%Y-%m-%d %H:%M}Z); an older "
            "file would mark newer dates as removed"
        )
    if prior.manual_file is not None and prior.manual_file.sha256 == sha:
        raise ImportRefused("this exact file is already loaded")
    as_of = civil_date(downloaded_at, source.time_zone)
    try:
        merged = merge(history, feed, source, as_of=as_of)
    except StateHistoryError as exc:
        raise ImportRefused(str(exc)) from exc
    # The automated read's own attempt fields stay as they were: the import
    # is not a check of tn.gov. The validators belong to the last automated
    # read's file, not this one, so they are cleared.
    merged.checks = Checks(
        last_attempt_at=prior.last_attempt_at,
        last_success_at=downloaded_at,
        last_attempt_ok=prior.last_attempt_ok,
        last_error=prior.last_error,
        content_sha256=sha,
        last_modified=None,
        etag=None,
        manual_file=ManualFile(
            source=SOURCE_LABEL,
            source_url=tn.PAGE_URL,
            file_name=path.name,
            sha256=sha,
            rows=len(rows),
            downloaded_at=downloaded_at,
            imported_at=now,
        ),
    )
    before = {r.key() for r in history.records if r.status == "listed"}
    removed = sum(
        1 for r in merged.records if r.status == "removed" and r.key() in before
    )
    message = (
        f"{len(rows)} rows, {len(feed.records)} records, {len(feed.waters)} waters"
        + (
            f", {feed.skipped} {'row' if feed.skipped == 1 else 'rows'} skipped"
            if feed.skipped
            else ""
        )
        + (f", {removed} no longer on TWRA's schedule (removed)" if removed else "")
        + f"; downloaded {as_of.isoformat()}"
        + "".join(f"; {note}" for note in feed.skipped_notes)
    )
    return ImportResult(history=merged, path=hpath, message=message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cfpa.import_tn_csv",
        description="Load TWRA's downloadable trout stocking CSV into "
        "pipeline/data/states/tn.json (DECISIONS 0061).",
    )
    parser.add_argument("csv", type=Path, help="the CSV downloaded from TWRA's page")
    parser.add_argument(
        "--downloaded-at",
        help="when the file was downloaded: 2026-11-07 or 2026-11-07T11:23-08:00 "
        "(default: the file's modification time)",
    )
    parser.add_argument("--states-dir", type=Path, default=DEFAULT_STATES_DIR)
    args = parser.parse_args(argv)
    try:
        downloaded_at = parse_downloaded_at(args.downloaded_at, args.csv)
        result = import_csv(
            args.csv,
            states_dir=args.states_dir,
            downloaded_at=downloaded_at,
            now=dt.datetime.now(dt.UTC),
        )
        result.history.save(result.path)
    except (ImportRefused, StateHistoryError, OSError) as exc:
        print(f"import-tn-csv: refused, nothing written: {exc}", file=sys.stderr)
        return 1
    print(f"import-tn-csv: TN updated: {result.message}")
    print(f"import-tn-csv: wrote {result.path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
