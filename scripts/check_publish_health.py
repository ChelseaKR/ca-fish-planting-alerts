#!/usr/bin/env python3
"""Is the live site fresh, and is every state source still being read?

The publish workflow already opens an issue when a run fails
(publish.yml, ``alert-on-failure``). That cannot see three things, and this
check, run by .github/workflows/publish-health.yml once a day, covers them by
reading what the site actually serves (``snapshot/v2.json``):

- the daily run never happened or never deployed (a disabled schedule, a
  Pages outage, a deploy that did not land), so the snapshot is old;
- a state whose last good read, as the site serves it, is older than its
  freshness allowance, the same limit and the same rule as the publish run's
  freshness job (``cfpa.freshness``, DECISIONS 0065): 7 days unless the
  state's module declares its own. A failing state keeps its last good data
  and only logs a warning (DECISIONS 0025), so this is how a stuck agency
  shows up on what is live. A state that is waiting (DECISIONS 0071: Hub's
  file is stale and the agency has not edited its layer within the allowance
  either) is reported apart and does not make the check unhealthy;
- the site is not answering, or answers something that is not a snapshot.

Every state's age, and California's week, is measured from when the
snapshot was built (``generated_at``), not from now: a publish that did not
deploy is one finding, ``publish-stale``, not one per state as well.

Unhealthy fails the workflow run, after the issue is opened or updated
(ADR 0076). Until 2026-11-19 it was only an issue comment on a green run,
and Tennessee and Massachusetts sat in #168 for days. The issue itself stays
quiet: --state-out always gets the sorted keys of the failing findings
(empty when healthy), the report ends with them in a hidden marker line, and
the workflow comments and rewrites the body only when they differ from the
marker in the open issue's body.

Absence is a finding, never a pass: a missing field, a date that does not
parse or a fetch that fails each say so and make the check fail.

Exit status: 0 healthy, 1 unhealthy (the report is in --out), 2 usage error.
The report holds only fixed text, state codes (two capital letters), agency
names from this code's own state registry and numbers and dates computed
here; nothing a remote server sent is copied into it, so it is safe to post
as an issue body.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from cfpa.freshness import DEFAULT_MAX_READ_AGE_DAYS, allowance, stale_copy_verdict
from cfpa.states import registered_sources

# Thresholds. Each is justified against the schedule in publish.yml (runs
# at 13:17 and 01:17 UTC; publish-health.yml checks at 17:43 UTC, so a
# healthy snapshot is about 4.5 hours old when this runs).
#
# A healthy snapshot is under 5 hours old at check time. A missed 13:17 run
# leaves the 01:17 one, about 16.5 hours old, which is the one-run-a-day
# freshness the site had before the second run and is not flagged. Missing
# both runs of a day makes it about 28.5 hours old. 24 hours therefore flags
# a lost day the same day, with 19 hours of margin for a delayed start.
STALE_PUBLISH_HOURS = 24
# A state's limit is not set here: it is the freshness watchdog's allowance
# (cfpa.freshness.DEFAULT_MAX_READ_AGE_DAYS, 7 days, or the state module's
# own), so this check and the publish run's freshness job never disagree.
# The 3 days this check used before 2026-11-19 put Tennessee's weekly
# hand-loaded file (DECISIONS 0061) in the issue four days of every seven.
# CDFW's page states a week and rolls it every Sunday; a normal week shows at
# most 7 days and 8 around the boundary (fetch.MAX_STALENESS_DAYS). Nine means
# a rollover went missing. assert_fresh already fails the run at that point,
# so this is a second, independent reading of what is live.
CA_WEEK_MAX_AGE_DAYS = 9

SECONDS_PER_DAY = 86400.0

# The workflow reads this line back from the open issue's body.
STATE_MARKER = "<!-- publish-health-state: {} -->"

SNAPSHOT_PATH = "snapshot/v2.json"
DEFAULT_BASE_URL = "https://chelseakr.github.io/ca-fish-planting-alerts"
FETCH_ATTEMPTS = 3
FETCH_TIMEOUT_SECONDS = 20.0
MAX_SNAPSHOT_BYTES = 8_000_000
_STATE_CODE = re.compile(r"^[A-Z]{2}$")

Fetch = Callable[[str], bytes]


class Finding:
    """One thing wrong, as a fixed sentence. ``fails`` is False only for a
    state that is waiting (DECISIONS 0071): reported, never unhealthy."""

    def __init__(self, key: str, text: str, *, fails: bool = True) -> None:
        self.key = key
        self.text = text
        self.fails = fails

    def __repr__(self) -> str:
        return f"Finding({self.key!r})"


def _parse_time(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        return None
    return when


def _parse_date(value: object) -> dt.date | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def evaluate(snapshot: object, now: dt.datetime) -> list[Finding]:
    """Findings for one parsed snapshot. Empty means healthy."""
    if not isinstance(snapshot, dict):
        return [Finding("snapshot-shape", "The snapshot is not a JSON object.")]
    findings: list[Finding] = []

    generated = _parse_time(snapshot.get("generated_at"))
    # Ages are measured from the build; without a readable one, from now.
    built = now if generated is None else generated
    if generated is None:
        findings.append(
            Finding("generated-missing", "The snapshot has no readable generated_at.")
        )
    else:
        hours = (now - generated).total_seconds() / 3600
        if hours > STALE_PUBLISH_HOURS:
            findings.append(
                Finding(
                    "publish-stale",
                    f"The live snapshot is {hours:.0f} hours old "
                    f"(limit {STALE_PUBLISH_HOURS}). The daily publish did "
                    "not deploy.",
                )
            )

    states = snapshot.get("states")
    if not isinstance(states, list) or not states:
        findings.append(Finding("states-missing", "The snapshot lists no states."))
        return findings

    seen_ca = False
    for state in states:
        code = state.get("code") if isinstance(state, dict) else None
        if not isinstance(code, str) or not _STATE_CODE.match(code):
            findings.append(
                Finding("state-code", "A state entry has no valid two-letter code.")
            )
            continue
        if code == "CA":
            seen_ca = True
            findings.extend(_check_ca(state, built))
        else:
            findings.extend(_check_state(code, state, built))
    if not seen_ca:
        findings.append(Finding("ca-missing", "California is not in the snapshot."))
    return findings


def _check_ca(state: dict[str, Any], built: dt.datetime) -> list[Finding]:
    week = state.get("current_week")
    start = _parse_date(week.get("start") if isinstance(week, dict) else None)
    if start is None:
        return [Finding("ca-week-missing", "California has no readable current week.")]
    age = (built.astimezone(dt.UTC).date() - start).days
    if age > CA_WEEK_MAX_AGE_DAYS:
        return [
            Finding(
                "ca-week-stale",
                f"California's stated week started {age} days before the "
                "snapshot was built "
                f"(limit {CA_WEEK_MAX_AGE_DAYS}).",
            )
        ]
    return []


def _check_state(code: str, state: dict[str, Any], built: dt.datetime) -> list[Finding]:
    checks = state.get("checks")
    if not isinstance(checks, dict) or not isinstance(
        checks.get("last_attempt_ok"), bool
    ):
        return [Finding(f"{code}-checks", f"{code} has no readable source checks.")]
    success = _parse_time(checks.get("last_success_at"))
    if success is None:
        return [Finding(f"{code}-never", f"{code} has no readable last good read.")]
    source = registered_sources().get(code)
    limit = (
        DEFAULT_MAX_READ_AGE_DAYS
        if source is None
        else allowance(source, DEFAULT_MAX_READ_AGE_DAYS)
    )
    age = (built - success).total_seconds() / SECONDS_PER_DAY
    if age <= limit:
        return []
    read = (
        f"its last good read was {age:.1f} days before the snapshot was "
        f"built (allowed {limit} days)"
    )
    stale = checks.get("stale_copy")
    detail = None
    if (
        source is not None
        and checks["last_attempt_ok"] is False
        and isinstance(stale, dict)
    ):
        waiting, detail = stale_copy_verdict(
            stale, source.agency_short_name, now=built, limit=limit
        )
        if waiting is not None:
            return [
                Finding(
                    f"{code}-waiting",
                    f"{code} is waiting, not stuck: {read}, {waiting}.",
                    fails=False,
                )
            ]
    tail = f"; {detail}" if detail else ""
    return [
        Finding(
            f"{code}-stuck",
            f"{code} is stuck: {read}; its data is from "
            f"{success.date().isoformat()}{tail}.",
        )
    ]


def state_key(findings: list[Finding]) -> str:
    """The sorted, de-duplicated keys of the failing findings: what the issue
    records. A waiting state is not in it, so it neither opens nor stirs the
    issue."""
    return ",".join(sorted({f.key for f in findings if f.fails}))


def snapshot_url(base_url: str) -> str:
    """The snapshot URL for a base, https only, no credentials or query."""
    base = base_url.strip() or DEFAULT_BASE_URL
    parts = urlsplit(base)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("the base URL must be plain https://host[/path]")
    return base.rstrip("/") + "/" + SNAPSHOT_PATH


def http_fetch(url: str) -> bytes:
    """One GET; raises on a network error or a non-200 answer."""
    with httpx.Client(follow_redirects=True, timeout=FETCH_TIMEOUT_SECONDS) as client:
        response = client.get(url, headers={"User-Agent": "cfpa-publish-health"})
    response.raise_for_status()
    if len(response.content) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot is larger than expected")
    return response.content


def check(url: str, now: dt.datetime, fetch: Fetch = http_fetch) -> list[Finding]:
    """Fetch the snapshot (with retries) and evaluate it."""
    body = b""
    for attempt in range(FETCH_ATTEMPTS):
        try:
            body = fetch(url)
            break
        except (httpx.HTTPError, ValueError, OSError):
            if attempt == FETCH_ATTEMPTS - 1:
                return [
                    Finding(
                        "fetch",
                        f"The site did not serve {SNAPSHOT_PATH} in "
                        f"{FETCH_ATTEMPTS} attempts.",
                    )
                ]
    try:
        snapshot = json.loads(body)
    except ValueError:
        return [Finding("snapshot-json", f"{SNAPSHOT_PATH} is not valid JSON.")]
    return evaluate(snapshot, now)


def report(findings: list[Finding], url: str, now: dt.datetime) -> str:
    waiting = [f for f in findings if not f.fails]
    lines = [
        "The daily health check read the live snapshot and found:",
        "",
        *(f"- {f.text}" for f in findings if f.fails),
        "",
    ]
    if waiting:
        lines += [
            "Not counted, waiting on the agency (DECISIONS 0071):",
            "",
            *(f"- {f.text}" for f in waiting),
            "",
        ]
    lines += [
        f"Checked {now.strftime('%Y-%m-%d %H:%MZ')} against {url}.",
        "The run fails while this is open. This issue closes itself on the "
        "first healthy check. It gets a new comment only when what the check "
        "finds changes, not every day.",
        "",
        STATE_MARKER.format(state_key(findings)),
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="", help="site root; default github.io")
    parser.add_argument("--out", type=Path, required=True, help="report file")
    parser.add_argument(
        "--state-out", type=Path, required=True, help="failing finding keys file"
    )
    args = parser.parse_args(argv)
    try:
        url = snapshot_url(args.base_url)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    now = dt.datetime.now(dt.UTC)
    findings = check(url, now)
    args.state_out.write_text(state_key(findings) + "\n", encoding="utf-8")
    for f in findings:
        print(f"{'UNHEALTHY' if f.fails else 'waiting'}: {f.text}")
    if not any(f.fails for f in findings):
        print(f"healthy: {url}")
        return 0
    args.out.write_text(report(findings, url, now), encoding="utf-8")
    return 1


if __name__ == "__main__":
    sys.exit(main())
