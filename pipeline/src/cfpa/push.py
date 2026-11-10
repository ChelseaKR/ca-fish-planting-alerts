"""Web push for one water per browser (DECISIONS 0069): the build-time
settings, the diff that decides what to tell a subscriber, the words it is
told in, and the two commands the publish workflow runs around a deploy.

The site stays static. A water page of a schedule state (California, and
Tennessee under DECISIONS 0064) carries an "Alert me about this water"
control inside its calendar box; the browser's push subscription goes to a
small service in Trout Truck's own AWS account (infra/web-push). After each
publish this module compares the snapshot that was live with the one just
built and sends one message per water whose dated schedule changed, through
that service, to the browsers subscribed to that water.

The diff reads the same records the water's calendar feed does: a ``listed``
plant with a ``day`` or ``week`` period (``cfpa.ics._dated``). So a TBD
month, a month letter, a withdrawn record and a report of a past stocking
never become a message, for the same reasons they never become a calendar
event. Only this week or later counts: a correction to a past week is
history, not news. A water missing from the previous snapshot has had no
page to subscribe from, and a water missing from the new one is a water the
agency no longer lists (DECISIONS 0017), not a removal, so neither is a
message. With no previous snapshot at all nothing is sent: a cold start must
not announce every listing to everyone.

Every message says whose schedule it is, that the date is scheduled and not
confirmed, and links the water page. It never says "stocked" or "planted
on", and it never promises more than the page does.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import dataclasses
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import VERSION, ics

# Written into the built site when push is configured (site._write_assets).
WORKER_FILE = "push-worker.js"
PUSH_JS_FILE = "push.js"
MANIFEST_FILE = "manifest.webmanifest"

# How long a push service may hold a message for an offline browser. The
# schedules are weekly, so a message read three days late still reads right;
# a week-old one would not (RFC 8030 §5.2).
TTL_SECONDS = 3 * 24 * 3600

# The service refuses a larger /send call (infra/web-push/lambda/handler.mjs).
EVENTS_PER_CALL = 100

# The landing link's tags, so GA4 can count visits that came from a
# notification, under the same opt-outs as every other page view.
UTM_QUERY = "utm_source=web-push&utm_medium=push&utm_campaign=schedule-change"

USER_AGENT = f"TroutTruckPipeline/{VERSION} (+https://github.com/ChelseaKR/ca-fish-planting-alerts)"

# The environment variable the publish workflow passes the sender's bearer
# token in (a GitHub Actions secret); the Lambda holds the same value in SSM
# (infra/web-push/variables.tf, ssm_prefix).
SENDER_AUTH_VARIABLE = "PUSH_SENDER_TOKEN"

_API_URL_RE = re.compile(r"^https://[a-z0-9][a-z0-9.-]*[a-z0-9](/[A-Za-z0-9._~/-]*)?$")
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# An uncompressed P-256 point, as the Push API hands it out: 65 bytes, 87
# base64url characters with the padding stripped.
VAPID_PUBLIC_KEY_CHARS = 87
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_MONTHS_SHORT = tuple(m[:3] for m in _MONTHS)
_WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)  # fmt: skip


@dataclasses.dataclass(frozen=True, slots=True)
class PushConfig:
    """The two public values a page needs: where to send a subscription, and
    the VAPID public key to subscribe with. Both are public by design."""

    api_url: str
    vapid_public_key: str

    def to_template(self) -> dict[str, str]:
        return {"api_url": self.api_url, "vapid_public_key": self.vapid_public_key}


def push_config_or_none(
    api_url: str | None, vapid_public_key: str | None
) -> PushConfig | None:
    """Both unset: push is off and the build is what it was. Both set and
    well-formed: a config. Anything else refuses the run (``cli.main``), like
    a malformed GA4 id: a page with a half-configured button would ask
    people for a permission it can do nothing with."""
    api = (api_url or "").strip()
    key = (vapid_public_key or "").strip()
    if not api and not key:
        return None
    if not api or not key:
        raise ValueError(
            "PUSH_API_URL and PUSH_VAPID_PUBLIC_KEY must be set together "
            "(or both left empty to leave web push off)"
        )
    api = api.rstrip("/")
    parts = urlsplit(api)
    if (
        not _API_URL_RE.match(api)
        or parts.scheme != "https"
        or not parts.hostname
        or "." not in parts.hostname
        or parts.query
        or parts.fragment
        or parts.username
        or parts.password
    ):
        raise ValueError(
            f"PUSH_API_URL must be an https URL with a host and no query: got {api!r}"
        )
    if len(key) != VAPID_PUBLIC_KEY_CHARS or not _B64URL_RE.match(key):
        raise ValueError(
            "PUSH_VAPID_PUBLIC_KEY must be the 87-character base64url public "
            "key `web-push generate-vapid-keys` prints"
        )
    try:
        raw = base64.urlsafe_b64decode(key + "=")
    except (binascii.Error, ValueError) as exc:
        raise ValueError("PUSH_VAPID_PUBLIC_KEY is not base64url") from exc
    if len(raw) != 65 or raw[0] != 0x04:
        raise ValueError(
            "PUSH_VAPID_PUBLIC_KEY does not decode to an uncompressed P-256 point"
        )
    return PushConfig(api_url=api, vapid_public_key=key)


# ---- the diff ------------------------------------------------------------------

PeriodKey = tuple[str, str, str]  # (precision, start, end)


def has_push(state: dict[str, Any]) -> bool:
    """Whether a state's water pages get the control: California, and any
    state whose water pages have a calendar feed (``ics.has_feed``), since a
    push is the feed's events, delivered."""
    return bool(state["code"] == "CA" or ics.has_feed(state))


def _dated_listed(water: dict[str, Any], floor: str) -> dict[PeriodKey, list[str]]:
    """The water's listed day and week periods ending on or after ``floor``
    (this week's first day), each with its species. The same selection as
    ``ics._dated``: a month, a month letter and a removed record are out."""
    out: dict[PeriodKey, list[str]] = {}
    for p in water["plants"]:
        per = p["period"]
        if p["status"] != "listed" or per["precision"] not in ("day", "week"):
            continue
        if per["end"] < floor:
            continue
        species = out.setdefault((per["precision"], per["start"], per["end"]), [])
        if p["species"] not in species:
            species.append(p["species"])
    for species in out.values():
        species.sort()
    return out


@dataclasses.dataclass(frozen=True, slots=True)
class Notification:
    """One message for one water. ``tag`` is the water id, so a newer message
    about the same water replaces an unread older one on the device."""

    water_id: str
    state: str
    title: str
    body: str
    url: str
    tag: str

    def to_json(self) -> dict[str, str]:
        return dataclasses.asdict(self)


def _long(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    return f"{_WEEKDAYS[d.weekday()]}, {_MONTHS[d.month - 1]} {d.day}, {d.year}"


def _short(date_iso: str) -> str:
    d = dt.date.fromisoformat(date_iso)
    return f"{_MONTHS_SHORT[d.month - 1]} {d.day}"


def _when(key: PeriodKey, *, long: bool) -> str:
    precision, start, _end = key
    if precision == "week":
        return f"the week of {_long(start)}" if long else f"week of {_short(start)}"
    return _long(start) if long else _short(start)


def _join(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _dates(keys: list[PeriodKey]) -> str:
    """Up to three dates by name; more as a count and a span. A new agency
    file can add a dozen dates to one water, and a message has to stay short
    enough to read and to pass the service's limit."""
    if len(keys) <= 3:
        return _join([_when(k, long=True) for k in keys])
    ordered = sorted(keys, key=lambda k: k[1])
    return (
        f"{len(keys)} dates, from {_when(ordered[0], long=True)} to "
        f"{_when(ordered[-1], long=True)}"
    )


def _caveat(state: dict[str, Any]) -> str:
    """The page's own caveat, in the page's own words: California's water
    page says "CDFW's plans can change"; a Tennessee feed carries TWRA's
    sentence (``cfpa.ics``)."""
    short = state["agency"]["short_name"]
    if state["code"] == "CA":
        return f"Scheduled, not confirmed: {short}'s plans can change."
    return (
        f"Scheduled, not confirmed: {short} says any stocking could be "
        "postponed or cancelled."
    )


def _week_note(key: PeriodKey, state: dict[str, Any]) -> str:
    """TWRA's rule for a week-of date, as the feed says it. California's
    weeks are the unit CDFW schedules in, so they need no note."""
    if key[0] == "week" and state["code"] != "CA":
        short = state["agency"]["short_name"]
        return f"; {short} says a week-of stocking falls within five days after that Sunday"
    return ""


def _notification(
    water: dict[str, Any],
    state: dict[str, Any],
    added: list[PeriodKey],
    removed: list[PeriodKey],
    now_listed: dict[PeriodKey, list[str]],
    *,
    base_url: str,
) -> Notification:
    name = water["name"]
    short = state["agency"]["short_name"]
    noun = "planting" if state["code"] == "CA" else "stocking"
    caveat = _caveat(state)
    if len(added) == 1 and not removed:
        key = added[0]
        # California's page says "planting"; a Tennessee row names TWRA's
        # species, as its feed does.
        what = (
            f"{name} for planting"
            if state["code"] == "CA"
            else f"{_join(now_listed[key])} at {name} for"
        )
        title = f"{name}: scheduled, {_when(key, long=False)}"
        body = (
            f"{short} lists {what} {_when(key, long=True)}"
            f"{_week_note(key, state)}. {caveat}"
        )
    elif len(removed) == 1 and not added:
        key = removed[0]
        title = f"{name}: schedule changed"
        body = (
            f"{short} took {_when(key, long=True)} off its {noun} schedule. "
            f"{short}'s plans can change."
        )
    elif len(added) == 1 and len(removed) == 1 and added[0][0] == removed[0][0]:
        title = f"{name}: schedule changed"
        body = (
            f"{short} moved {name} from {_when(removed[0], long=True)} to "
            f"{_when(added[0], long=True)}{_week_note(added[0], state)}. {caveat}"
        )
    else:
        title = f"{name}: schedule changed"
        parts = []
        if added:
            parts.append(f"Now listed: {_dates(added)}.")
        if removed:
            parts.append(f"No longer listed: {_dates(removed)}.")
        parts.append(caveat)
        body = " ".join(parts)
    return Notification(
        water_id=water["id"],
        state=state["code"],
        title=title,
        body=body,
        url=f"{base_url.rstrip('/')}{water['site_path']}?{UTM_QUERY}",
        tag=water["id"],
    )


def diff_snapshots(
    before: dict[str, Any] | None, after: dict[str, Any], *, base_url: str
) -> list[Notification]:
    """One notification per water whose dated, listed, current-or-later
    schedule differs between the snapshot that was live (``before``) and the
    one just built (``after``). Empty with no ``before`` at all."""
    if before is None:
        return []
    states = {s["code"]: s for s in after["states"]}
    before_by_id = {w["id"]: w for w in before["waters"]}
    out: list[Notification] = []
    for w in after["waters"]:
        state = states.get(w["state"])
        if state is None or not has_push(state):
            continue
        old = before_by_id.get(w["id"])
        if old is None:
            continue
        floor = state["current_week"]["start"]
        now_listed = _dated_listed(w, floor)
        was_listed = _dated_listed(old, floor)
        added = sorted(k for k in now_listed if k not in was_listed)
        removed = sorted(k for k in was_listed if k not in now_listed)
        if not added and not removed:
            continue
        out.append(
            _notification(w, state, added, removed, now_listed, base_url=base_url)
        )
    return out


# ---- the two workflow commands -------------------------------------------------


def fetch_live_snapshot(url: str, *, timeout: float = 30.0) -> dict[str, Any] | None:
    """The live ``snapshot/v2.json``, or None when it cannot be read: a None
    means "unknown", and the diff then sends nothing."""
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) and "waters" in data else None


def send_events(
    events: list[dict[str, str]], *, api_url: str, token: str, timeout: float = 150.0
) -> dict[str, Any]:
    """POST the notifications to the service's ``/send`` route, at most
    ``EVENTS_PER_CALL`` at a time (a new agency file can change every water in
    one run). The service fans each one out to that water's subscribers and
    answers with counts, which are added up here."""
    totals: dict[str, Any] = {}
    for i in range(0, len(events), EVENTS_PER_CALL):
        r = httpx.post(
            f"{api_url.rstrip('/')}/send",
            json={"events": events[i : i + EVENTS_PER_CALL]},
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError(
                "the push service answered with something other than an object"
            )
        for key, value in data.items():
            totals[key] = totals.get(key, 0) + value
    return totals


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold a JSON object")
    return data


def _cmd_diff(args: argparse.Namespace) -> int:
    after = _load(Path(args.after))
    before: dict[str, Any] | None
    if args.before:
        before = _load(Path(args.before))
    else:
        before = fetch_live_snapshot(args.before_url)
    events = (
        []
        if before is None
        else [
            n.to_json() for n in diff_snapshots(before, after, base_url=args.base_url)
        ]
    )
    Path(args.out).write_text(
        json.dumps({"events": events}, indent=1) + "\n", encoding="utf-8"
    )
    if before is None:
        print(
            "::warning title=Web push::the live snapshot could not be read, so "
            "no schedule change is sent this run"
        )
    elif events:
        print(
            f"::notice title=Web push::{len(events)} water"
            f"{'' if len(events) == 1 else 's'} with a schedule change to send"
        )
    else:
        print("::notice title=Web push::no schedule change to send this run")
    return 0


def _cmd_send(args: argparse.Namespace) -> int:
    events = _load(Path(args.events)).get("events", [])
    if not events:
        print("::notice title=Web push::nothing to send")
        return 0
    token = os.environ.get(SENDER_AUTH_VARIABLE, "")
    if not token:
        print(
            f"::error title=Web push::{SENDER_AUTH_VARIABLE} is not set",
            file=sys.stderr,
        )
        return 1
    try:
        result = send_events(events, api_url=args.api_url, token=token)
    except (httpx.HTTPError, ValueError) as exc:
        # The status line, never the response body: a body could echo the
        # request, and the token travels in a header the service never logs.
        print(f"::error title=Web push::the send failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        "::notice title=Web push::"
        f"{result.get('events', '?')} events, {result.get('subscribers', '?')} "
        f"subscriptions, {result.get('sent', '?')} sent, "
        f"{result.get('failed', '?')} failed, {result.get('removed', '?')} dead "
        "endpoints removed"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cfpa.push", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("diff", help="compare the live snapshot with this build")
    src = d.add_mutually_exclusive_group(required=True)
    src.add_argument("--before", help="the previous snapshot/v2.json, as a file")
    src.add_argument("--before-url", help="the live snapshot/v2.json, fetched")
    d.add_argument("--after", required=True, help="this build's snapshot/v2.json")
    d.add_argument("--base-url", required=True, help="the site's root URL")
    d.add_argument("--out", required=True, help="where to write the events file")
    d.set_defaults(func=_cmd_diff)
    s = sub.add_parser("send", help="send an events file to the push service")
    s.add_argument("--events", required=True)
    s.add_argument("--api-url", required=True)
    s.set_defaults(func=_cmd_send)
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
    except (OSError, ValueError) as exc:
        print(f"::error title=Web push::{exc}", file=sys.stderr)
        return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
