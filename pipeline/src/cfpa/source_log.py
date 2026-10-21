"""Notice when CDFW's schedule page has not changed for too long.

``assert_fresh`` compares the page's stated week with the run date, so a page
that keeps stating the right week passes while the table behind it never
changes. ``content_sha256`` (a hash of the fetched HTML) is the only signal for
that, and a single run cannot judge it. This module keeps one small committed
log of (date, hash) per run and says how many days the newest hash has gone
unchanged.

The warning never fails a run. A real lull in planting is normal, so this is a
heads-up for the owner, not a refusal; the data itself is unaffected.

Why 10 days: the page states the current week and the all-plants window, and
both roll every Sunday, so the HTML of a live page changes at least once a week
even when no plant is added. A normal week therefore shows 7 days at most, 8
around a Sunday boundary (``fetch.MAX_STALENESS_DAYS``). Ten days means a
Sunday rollover went missing, which a lull in planting cannot explain.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "cfpa-source-log-v1"
STALE_SOURCE_DAYS = 10
# Far more than STALE_SOURCE_DAYS needs, small enough to keep the file tiny.
MAX_ENTRIES = 60
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceLogError(ValueError):
    """The log file is not in the shape this module writes."""


@dataclasses.dataclass(slots=True)
class SourceLog:
    runs: list[tuple[dt.date, str]]  # (run date, content_sha256), oldest first

    @classmethod
    def load(cls, path: Path) -> SourceLog:
        if not path.exists():
            return cls(runs=[])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["schema"] != SCHEMA:
                raise SourceLogError(f"unknown schema {data['schema']!r}")
            runs = [
                (dt.date.fromisoformat(r["date"]), str(r["content_sha256"]))
                for r in data["runs"]
            ]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SourceLogError(f"{path} could not be read: {exc}") from exc
        if any(not _SHA_RE.match(sha) for _, sha in runs):
            raise SourceLogError(f"{path} holds a value that is not a SHA-256")
        return cls(runs=sorted(runs))

    def save(self, path: Path) -> None:
        payload = {
            "schema": SCHEMA,
            "runs": [
                {"date": d.isoformat(), "content_sha256": sha} for d, sha in self.runs
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def record(self, run_date: dt.date, content_sha256: str) -> None:
        """Add this run, replacing an earlier run on the same date."""
        kept = [(d, s) for d, s in self.runs if d != run_date]
        kept.append((run_date, content_sha256))
        self.runs = sorted(kept)[-MAX_ENTRIES:]

    def unchanged_days(self) -> int:
        """Days from the first of the newest unbroken streak of one hash to the
        newest run. 0 when the newest hash is new or the log is empty. A log that
        starts mid-streak undercounts, never overcounts."""
        if not self.runs:
            return 0
        newest_date, newest_sha = self.runs[-1]
        first = newest_date
        for d, sha in reversed(self.runs):
            if sha != newest_sha:
                break
            first = d
        return (newest_date - first).days


def print_report(days: int, *, cold_start: bool = False) -> bool:
    """Say how long the source has gone unchanged. Returns True when it warns.

    Always prints one ``coverage:`` line so the build output shows the number.
    At ``STALE_SOURCE_DAYS`` or more it also warns on stderr and, under GitHub
    Actions, emits a ``::warning`` so the run summary shows it. It never
    changes the exit status. ``cold_start`` means the log held no earlier run
    (a new, expired or unrestored artifact), so the count restarts at 0 and says
    so.
    """
    if cold_start:
        print(
            "coverage: source log was empty (new, expired or not restored), so the "
            "unchanged-page count restarts at 0"
        )
    print(
        f"coverage: source page unchanged for {days} "
        f"{'day' if days == 1 else 'days'} "
        f"(warns at {STALE_SOURCE_DAYS})"
    )
    if days < STALE_SOURCE_DAYS:
        return False
    print(
        f"cfpa: WARNING CDFW's schedule page has been byte-for-byte unchanged for "
        f"{days} days (a normal week changes it at least weekly, when the stated "
        "week rolls over). The freshness check still passes; check the source "
        "by hand. Nothing was withheld.",
        file=sys.stderr,
    )
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(
            "::warning title=CDFW schedule page unchanged::"
            f"the fetched page has had the same content hash for {days} days"
        )
    return True
