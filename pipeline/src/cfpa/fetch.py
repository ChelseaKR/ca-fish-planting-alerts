"""Fetch the CDFW Fish Planting Schedule page.

One page, at most once per scheduled run (see
``docs/LICENSES-AND-ATTRIBUTION.md`` for the declared crawl budget). This
module is deliberately paranoid about staleness: the research behind this
product ("the 2026-09-13 research notes", idea 1, biggest risk) hit a *stale
2025 cache* on the very first fetch. A stale or failed fetch must never be
treated as "no plants this week" -- it must abort the whole run before any
snapshot is written.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import re
import urllib.robotparser
from urllib.parse import urljoin

import httpx

SCHEDULE_URL = "https://nrm.dfg.ca.gov/FishPlants/PublicPlantSearch"
ROBOTS_URL = "https://nrm.dfg.ca.gov/robots.txt"
USER_AGENT_TEMPLATE = (
    "ca-fish-planting-alerts/{version} "
    "(+https://github.com/ChelseaKR/ca-fish-planting-alerts)"
)

# The page states its own "today" via the Time Period radio widget, e.g.:
#   text="Current-Future Plants (9/13/2026 - 9/27/2026)"
# The start of that range is the date CDFW's page computed as "today" when it
# was rendered. This is a content-derived signal, independent of (and a
# check on top of) HTTP cache headers -- a cached response still carries this
# text, so a stale cache is still caught.
_TIME_PERIOD_RE = re.compile(
    r'text="Current-Future Plants \((\d{1,2}/\d{1,2}/\d{4}) - \d{1,2}/\d{1,2}/\d{4}\)"'
)

# The "All Plants (<start> - <end>)" radio option states the page's full
# rolling window -- used to tell whether an existing "listed" history record
# was inside the window CDFW could have shown this run (and so its absence
# means CDFW removed it) or outside it (ages off naturally, not a removal).
_ALL_PLANTS_RE = re.compile(
    r'text="All Plants \((\d{1,2}/\d{1,2}/\d{4}) - (\d{1,2}/\d{1,2}/\d{4})\)"'
)

# Allow a little slack: CDFW's server may compute "today" a few hours off
# from ours around midnight, and a scheduled run may lag its trigger time.
# Beyond this, we are looking at a cache, not "yesterday's data centre".
MAX_STALENESS_DAYS = 1


class FetchError(RuntimeError):
    """The page could not be retrieved at all. Never treat as 'no plants'."""


class StalePageError(RuntimeError):
    """The page was retrieved but its own stated date is too old to trust."""

    def __init__(self, page_today: dt.date, run_today: dt.date):
        self.page_today = page_today
        self.run_today = run_today
        super().__init__(
            f"schedule page says today is {page_today.isoformat()}, "
            f"but the run date is {run_today.isoformat()} "
            f"({(run_today - page_today).days} day(s) stale, "
            f"max allowed {MAX_STALENESS_DAYS}) -- refusing to use this page"
        )


class RobotsDisallowedError(RuntimeError):
    """robots.txt disallows the schedule path for our user agent."""


@dataclasses.dataclass(frozen=True, slots=True)
class FetchedPage:
    html: str
    fetched_at: dt.datetime  # UTC
    stated_today: dt.date
    stated_period_start: dt.date
    stated_period_end: dt.date
    content_sha256: str
    url: str


def check_robots(user_agent: str, client: httpx.Client) -> None:
    """Raise RobotsDisallowedError if robots.txt disallows the schedule path.

    A fetch failure of robots.txt itself is treated as "allowed" per the
    conventional interpretation (a missing/unreachable robots.txt implies no
    restriction) -- nrm.dfg.ca.gov's robots.txt was confirmed reachable and
    permissive on 2026-09-13 (see docs/LICENSES-AND-ATTRIBUTION.md).
    """
    parser = urllib.robotparser.RobotFileParser()
    try:
        resp = client.get(ROBOTS_URL, headers={"User-Agent": user_agent}, timeout=30)
        if resp.status_code >= 400:
            return
        parser.parse(resp.text.splitlines())
    except httpx.HTTPError:
        return
    if not parser.can_fetch(user_agent, SCHEDULE_URL):
        raise RobotsDisallowedError(
            f"robots.txt at {ROBOTS_URL} disallows {SCHEDULE_URL} for {user_agent!r}"
        )


def extract_stated_today(html: str) -> dt.date:
    """Pull CDFW's own 'today' out of the page's Time Period widget.

    Raises ValueError if the marker is missing -- this is itself a signal
    the page format drifted (the caller should treat this like a parse
    failure: fail loudly, never emit partial/assumed data).
    """
    m = _TIME_PERIOD_RE.search(html)
    if not m:
        raise ValueError(
            "could not find the 'Current-Future Plants (<date> - ...)' marker "
            "in the schedule page -- page format may have changed"
        )
    month, day, year = m.group(1).split("/")
    return dt.date(int(year), int(month), int(day))


def extract_stated_period(html: str) -> tuple[dt.date, dt.date]:
    """Pull the 'All Plants (<start> - <end>)' rolling window out of the page."""
    m = _ALL_PLANTS_RE.search(html)
    if not m:
        raise ValueError(
            "could not find the 'All Plants (<date> - <date>)' marker "
            "in the schedule page -- page format may have changed"
        )
    m1, d1, y1 = (int(x) for x in m.group(1).split("/"))
    m2, d2, y2 = (int(x) for x in m.group(2).split("/"))
    return dt.date(y1, m1, d1), dt.date(y2, m2, d2)


def assert_fresh(stated_today: dt.date, run_today: dt.date) -> None:
    """Refuse a page whose own stated date is too old. Never silently pass."""
    age = (run_today - stated_today).days
    if age > MAX_STALENESS_DAYS or age < -MAX_STALENESS_DAYS:
        raise StalePageError(stated_today, run_today)


def fetch_schedule(
    *,
    version: str,
    run_today: dt.date | None = None,
    client: httpx.Client | None = None,
) -> FetchedPage:
    """Fetch and freshness-check the schedule page. Raises, never guesses.

    ``run_today`` defaults to the real UTC date; tests pass a fixed date so
    fixtures stay valid regardless of when the suite runs.
    """
    run_today = run_today or dt.datetime.now(dt.timezone.utc).date()
    user_agent = USER_AGENT_TEMPLATE.format(version=version)
    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        check_robots(user_agent, client)
        try:
            resp = client.get(
                SCHEDULE_URL,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html",
                },
                timeout=60,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"fetch of {SCHEDULE_URL} failed: {exc}") from exc

        html = resp.text
        fetched_at = dt.datetime.now(dt.timezone.utc)
        stated_today = extract_stated_today(html)
        assert_fresh(stated_today, run_today)
        period_start, period_end = extract_stated_period(html)

        return FetchedPage(
            html=html,
            fetched_at=fetched_at,
            stated_today=stated_today,
            stated_period_start=period_start,
            stated_period_end=period_end,
            content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
            url=str(resp.url),
        )
    finally:
        if owns_client:
            client.close()


def load_fixture(path: str, *, fetched_at: dt.datetime | None = None) -> FetchedPage:
    """Build a FetchedPage from a saved HTML fixture, for tests and CI dry-runs."""
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    period_start, period_end = extract_stated_period(html)
    return FetchedPage(
        html=html,
        fetched_at=fetched_at or dt.datetime.now(dt.timezone.utc),
        stated_today=extract_stated_today(html),
        stated_period_start=period_start,
        stated_period_end=period_end,
        content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
        url=SCHEDULE_URL,
    )
