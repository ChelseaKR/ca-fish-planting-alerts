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

# The page states its own current week via the Time Period radio widget, e.g.:
#   text="Current-Future Plants (9/13/2026 - 9/27/2026)"
# The start of that range is the SUNDAY that begins CDFW's current week as
# the page computed it when rendered -- NOT the day it was rendered. The
# original code read it as "today", which only ever held on a Sunday: every
# scheduled publish run from 2026-09-15 to 2026-09-17 was refused as "2, 3,
# 4 day(s) stale" while the page was in fact live. The evidence that it is a
# week start, all real CDFW responses:
#   - tests/fixtures/schedule-empty-week-2026-09-14.html, fetched Monday
#     2026-09-14, states 9/13/2026;
#   - publish.yml's scheduled runs on Tue 09-15, Wed 09-16 and Thu 09-17
#     each logged "schedule page says today is 2026-09-13";
#   - a one-off diagnostic fetch on Thu 2026-09-17 (03:10 UTC 09-18,
#     `Cache-Control: private`, so not an intermediary cache) also stated
#     9/13/2026 while listing 29 plants (weeks of 9/13 and 9/20) that the
#     2026-09-13 fetch did not have -- a live page, not a stale copy;
#   - the stale-cache reproduction states 9/14/2025, also a Sunday.
# This is a content-derived signal, independent of (and a check on top of)
# HTTP cache headers -- a cached response still carries this text, so a
# stale cache is still caught; see ``assert_fresh``.
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

# Allow a little slack at the week boundary: CDFW's server may compute its
# date a few hours off from ours around midnight, and a scheduled run may lag
# its trigger time. So the page's week is accepted if it is the week
# containing the run date, or the day before it, or the day after it. In
# practice: any day of the week accepts that week's Sunday; a Sunday run
# also accepts the previous week (CDFW not yet rolled over), and a Saturday
# run also accepts the next week (CDFW already rolled over). Anything else
# is a cache, not "yesterday's data centre".
MAX_STALENESS_DAYS = 1


def week_start_containing(day: dt.date) -> dt.date:
    """The Sunday that begins the CDFW week (Sunday..Saturday) containing ``day``."""
    # date.weekday(): Monday=0 .. Sunday=6, so Sunday -> 0 days back.
    return day - dt.timedelta(days=(day.weekday() + 1) % 7)


def acceptable_week_starts(run_today: dt.date) -> set[dt.date]:
    """Every current-week start the freshness check accepts for ``run_today``."""
    return {
        week_start_containing(run_today + dt.timedelta(days=offset))
        for offset in range(-MAX_STALENESS_DAYS, MAX_STALENESS_DAYS + 1)
    }


class FetchError(RuntimeError):
    """The page could not be retrieved at all. Never treat as 'no plants'."""


class StalePageError(RuntimeError):
    """The page was retrieved but its own stated week is too old to trust."""

    def __init__(self, page_today: dt.date, run_today: dt.date):
        # ``page_today`` keeps its historical name (it is ``stated_today`` in
        # the snapshot contract); it is the page's current-week start.
        self.page_today = page_today
        self.run_today = run_today
        run_week = week_start_containing(run_today)
        weeks_off = (run_week - page_today).days / 7
        super().__init__(
            f"schedule page says its current week starts {page_today.isoformat()}, "
            f"but the run date {run_today.isoformat()} is in the week starting "
            f"{run_week.isoformat()} ({weeks_off:+g} week(s) off, allowed: the week "
            f"of the run date +/- {MAX_STALENESS_DAYS} day) -- refusing to use this page"
        )


class PageFormatError(ValueError):
    """The page's own date markers are missing or no longer mean what they did.

    A ValueError subclass so callers that already expected ValueError from
    the extractors keep working; ``cli`` reports it as a refused run.
    """


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
    """Pull CDFW's own current-week start out of the page's Time Period widget.

    The name is historical (the snapshot contract calls the value
    ``source.stated_today``); the value is the Sunday that begins CDFW's
    current week as the page computed it, not the day it was rendered.

    Raises ValueError if the marker is missing, or if the date is not a
    Sunday -- either is itself a signal the page format drifted (the caller
    should treat this like a parse failure: fail loudly, never emit
    partial/assumed data). The Sunday check matters because ``assert_fresh``
    compares week starts: a page that started stating a real "today" again
    must be noticed, not silently accepted on its own Sundays only.
    """
    m = _TIME_PERIOD_RE.search(html)
    if not m:
        raise PageFormatError(
            "could not find the 'Current-Future Plants (<date> - ...)' marker "
            "in the schedule page -- page format may have changed"
        )
    month, day, year = m.group(1).split("/")
    stated = dt.date(int(year), int(month), int(day))
    if stated.weekday() != 6:
        raise PageFormatError(
            f"the 'Current-Future Plants' range starts {stated.isoformat()}, a "
            f"{stated.strftime('%A')} -- CDFW's weeks start on a Sunday, so the "
            "page format may have changed"
        )
    return stated


def extract_stated_period(html: str) -> tuple[dt.date, dt.date]:
    """Pull the 'All Plants (<start> - <end>)' rolling window out of the page."""
    m = _ALL_PLANTS_RE.search(html)
    if not m:
        raise PageFormatError(
            "could not find the 'All Plants (<date> - <date>)' marker "
            "in the schedule page -- page format may have changed"
        )
    m1, d1, y1 = (int(x) for x in m.group(1).split("/"))
    m2, d2, y2 = (int(x) for x in m.group(2).split("/"))
    return dt.date(y1, m1, d1), dt.date(y2, m2, d2)


def assert_fresh(stated_today: dt.date, run_today: dt.date) -> None:
    """Refuse a page whose own current week is not the run's week. Never
    silently pass.

    ``stated_today`` is the page's current-week start (a Sunday; see
    ``extract_stated_today``). It must be the start of the week containing
    ``run_today``, allowing ``MAX_STALENESS_DAYS`` of clock skew either side
    of a week boundary. A page from any earlier week -- the 2025 cache the
    research hit, or last week's copy -- is refused.
    """
    if stated_today not in acceptable_week_starts(run_today):
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
