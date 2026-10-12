"""What every non-California state source shares: the record shapes, the
honest HTTP client, and the strict robots.txt rule.

The robots rule here is stricter than California's (``cfpa.fetch``), on the
owner's rulings of 2026-10-12 (DECISIONS 0025):

- HTTP 200 ``text/plain`` on the same host: its rules apply.
- HTTP 404, no file: "no rules", so the fetch may go ahead.
- Anything else is off-limits, and nothing else on the host is requested:
  a 403 (Massachusetts' host), a redirect to a page that is not a robots
  file (Michigan's host), any other 4xx, a 5xx, a timeout, or a 200 that is
  not ``text/plain``. Redirects are never followed.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import re
import time
import urllib.robotparser
from collections.abc import Callable, Mapping
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

Precision = Literal["day", "week", "month"]
Semantics = Literal["schedule", "report"]
Status = Literal["listed", "removed", "reported"]

USER_AGENT_TEMPLATE = (
    "ca-fish-planting-alerts/{version} "
    "(+https://github.com/ChelseaKR/ca-fish-planting-alerts)"
)

# Seconds between two requests to the same host in one run. The research
# lane used 5; so does this.
POLITE_DELAY_SECONDS = 5.0

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class StateFetchError(RuntimeError):
    """The state's data could not be fetched. Its last good data stays."""


class RobotsUnreadableError(StateFetchError):
    """The host's robots.txt could not be read, so the host is off-limits."""


class RobotsDisallowedError(StateFetchError):
    """The host's robots.txt disallows the data path for our user agent."""


class StateFormatError(ValueError):
    """The feed no longer looks the way this code reads it. Refused whole."""


def week_start_containing(day: dt.date) -> dt.date:
    """The Sunday that begins the Sunday..Saturday week containing ``day``."""
    return day - dt.timedelta(days=(day.weekday() + 1) % 7)


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class Period:
    """When a record says fish come (or came), at the precision the agency
    gave. Never finer: a week is never shown as a day."""

    start: dt.date
    end: dt.date
    precision: Precision

    @classmethod
    def day(cls, d: dt.date) -> Period:
        return cls(d, d, "day")

    @classmethod
    def week(cls, sunday: dt.date) -> Period:
        if sunday.weekday() != 6:
            raise StateFormatError(f"a week must start on a Sunday, got {sunday}")
        return cls(sunday, sunday + dt.timedelta(days=6), "week")

    @classmethod
    def month(cls, year: int, month: int) -> Period:
        first = dt.date(year, month, 1)
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        return cls(first, nxt - dt.timedelta(days=1), "month")

    @property
    def label(self) -> str:
        if self.precision == "day":
            return self.start.isoformat()
        if self.precision == "week":
            return f"week of {self.start.isoformat()}"
        return f"{_MONTHS[self.start.month - 1]} {self.start.year}"

    def to_json(self) -> dict[str, str]:
        return {
            "precision": self.precision,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
        }

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> Period:
        precision = d["precision"]
        if precision not in ("day", "week", "month"):
            raise StateFormatError(f"unknown precision {precision!r}")
        return cls(
            dt.date.fromisoformat(d["start"]),
            dt.date.fromisoformat(d["end"]),
            precision,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class WaterMeta:
    """One water as the agency describes it. ``id`` and ``slug`` are assigned
    the first time the water is seen and never change."""

    id: str
    slug: str
    name: str
    counties: tuple[str, ...] = ()
    towns: tuple[str, ...] = ()
    region: str | None = None
    source_id: str | None = None
    source_url: str = ""
    months_note: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedRecord:
    water_id: str
    period: Period
    species: str
    count: int | None = None

    def key(self) -> tuple[str, str, str, str]:
        return (
            self.water_id,
            self.period.start.isoformat(),
            self.period.precision,
            self.species,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ParsedFeed:
    """One successful fetch, parsed. ``skipped`` counts rows with no usable
    date, said in the run log rather than silently dropped."""

    waters: dict[str, WaterMeta]
    records: list[ParsedRecord]
    fetched_at: dt.datetime
    content_sha256: str
    last_modified: str | None
    skipped: int = 0


@dataclasses.dataclass(frozen=True, slots=True)
class FetchedBody:
    url: str
    text: str
    fetched_at: dt.datetime
    last_modified: str | None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True, slots=True)
class LicenseSource:
    name: str
    url: str
    terms_url: str
    terms_read_on: str
    commercial_reuse: Literal["permitted", "not-permitted", "unknown"]
    attribution_required: bool
    terms_quote: str

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class StateSource:
    """Everything about one state's feed that is not the data itself."""

    code: str
    name: str
    time_zone: str
    agency_name: str
    agency_short_name: str
    agency_url: str
    source_name: str
    source_url: str  # the agency page people can read
    data_urls: tuple[str, ...]  # what the pipeline requests
    semantics: Semantics
    date_precisions: tuple[Precision, ...]
    attribution_text: str
    attribution_url: str
    disclaimer: str
    license_summary: str
    license_sources: tuple[LicenseSource, ...]
    regions: tuple[tuple[str, str], ...]
    recency_note: str | None
    # Fewer parsed rows than this looks like a truncated or reshaped feed,
    # and the fetch is refused rather than read as "nothing scheduled".
    min_rows: int
    # Records before this date are kept in history but left out of the
    # snapshot and the site, to keep the app's download small. None = all.
    publish_since: dt.date | None
    # (client, user agent, sleep, newest record already on file) -> bodies.
    fetch: Callable[
        [httpx.Client, str, Callable[[float], None], dt.date | None],
        list[FetchedBody],
    ]
    parse: Callable[[list[FetchedBody]], ParsedFeed]

    @property
    def removal_inference(self) -> bool:
        # docs/DECISIONS.md 0016: a missing row only means "dropped" for a
        # source that publishes its whole forward schedule. A report of past
        # stockings that ages rows off says nothing about a removal.
        return self.semantics == "schedule"

    @property
    def path_segment(self) -> str:
        return self.code.lower()


def check_robots_strict(client: httpx.Client, data_url: str, user_agent: str) -> None:
    """Refuse unless the data host's robots.txt is readable and allows us."""
    parts = urlsplit(data_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        resp = client.get(
            robots_url,
            headers={"User-Agent": user_agent},
            timeout=30,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise RobotsUnreadableError(
            f"robots.txt at {robots_url} could not be fetched ({exc}); the host "
            "is off-limits"
        ) from exc
    if resp.status_code == 404:
        # The owner's ruling: no file means no rules.
        return
    if resp.status_code != 200:
        where = resp.headers.get("location")
        detail = f" (redirects to {where})" if where else ""
        raise RobotsUnreadableError(
            f"robots.txt at {robots_url} answered HTTP {resp.status_code}{detail}; "
            "an unreadable robots.txt puts the host off-limits"
        )
    content_type = resp.headers.get("content-type", "")
    if not content_type.lower().startswith("text/plain"):
        raise RobotsUnreadableError(
            f"robots.txt at {robots_url} is {content_type or 'untyped'}, not "
            "text/plain; the host is off-limits"
        )
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())
    if not parser.can_fetch(user_agent, data_url):
        raise RobotsDisallowedError(
            f"robots.txt at {robots_url} disallows {data_url} for {user_agent!r}"
        )


def get_text(
    client: httpx.Client,
    url: str,
    user_agent: str,
    *,
    params: Mapping[str, str] | None = None,
    accept: str = "application/json",
) -> FetchedBody:
    """One honest GET. Never a browser User-Agent, never a cache buster."""
    try:
        resp = client.get(
            url,
            params=params,
            headers={"User-Agent": user_agent, "Accept": accept},
            timeout=60,
            follow_redirects=False,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise StateFetchError(f"fetch of {url} failed: {exc}") from exc
    return FetchedBody(
        url=str(resp.url),
        text=resp.text,
        fetched_at=dt.datetime.now(dt.UTC),
        last_modified=resp.headers.get("last-modified"),
    )


def no_sleep(_seconds: float) -> None:
    """For tests and fixtures: nothing to be polite to."""


def real_sleep(seconds: float) -> None:
    time.sleep(seconds)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(*parts: str) -> str:
    text = " ".join(parts).lower().replace("&", " and ").replace("'", "")
    return _SLUG_RE.sub("-", text).strip("-")


def combined_sha256(bodies: list[FetchedBody]) -> str:
    h = hashlib.sha256()
    for b in bodies:
        h.update(b.text.encode("utf-8"))
    return h.hexdigest()
