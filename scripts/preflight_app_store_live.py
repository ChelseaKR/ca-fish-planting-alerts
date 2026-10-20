#!/usr/bin/env python3
"""Pre-flight for the App Store launch switch (site.py APP_STORE_LIVE_DEFAULT).

Run it after Apple approves the app and before the one-line pull request that
turns the website's App Store surfaces on:

    cd pipeline && uv run python ../scripts/preflight_app_store_live.py

It changes nothing and sends only read-only GET requests. It checks that:

1. the App Store address in the code is the right shape and carries the app's
   id (site.APP_STORE_ID);
2. that address opens (HTTP 200), so the badge will not lead to an error page;
3. Apple's public lookup for that id names this app (same id, and the bundle
   id in the Xcode project) and reports the version the project and the docs
   say (MARKETING_VERSION, docs/app-store/OWNER-STEPS.md). Apple publishes the
   version, not the build number, so the build number is checked between the
   project and the docs here, and against App Store Connect by the owner
   (docs/LAUNCH-CHECKLIST.md);
4. a site built with the switch on, offline from the committed fixture, has
   every App Store surface on and valid (banner, badge, install links,
   MobileApplication JSON-LD, click event), and one built with it off has
   every surface off (cfpa.launch_check).

It also says which way the committed default points now, so a run after the
flip reads "ON" and a run before it reads "off".

The network is a parameter (``Fetch``) so tests run it offline with fakes.
Exit status is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import httpx

from cfpa import cli, launch_check, site

ROOT = Path(__file__).resolve().parent.parent
PBXPROJ = ROOT / "ios" / "CAFishPlanting.xcodeproj" / "project.pbxproj"
OWNER_STEPS = ROOT / "docs" / "app-store" / "OWNER-STEPS.md"
FIXTURE = ROOT / "pipeline" / "tests" / "fixtures" / "schedule-fresh-2026-09-13.html"
SCHEMA = ROOT / "schema" / "snapshot.v1.json"
APP_BUNDLE_ID = "com.chelseakr.cafishplanting"
LOOKUP_URL = "https://itunes.apple.com/lookup?id={id}&country=us"
USER_AGENT = "trout-truck-preflight/1 (read-only; https://trouttruck.com)"
TIMEOUT_SECONDS = 20


class Response(NamedTuple):
    status: int
    body: bytes


Fetch = Callable[[str], Response]


def http_get(url: str) -> Response:
    """A read-only GET that follows redirects. A non-2xx answer is returned,
    not raised; a network failure is a status of 0."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https address: {url}")
    try:
        got = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return Response(0, b"")
    return Response(got.status_code, got.content)


class Result(NamedTuple):
    name: str
    ok: bool
    detail: str


def project_versions(pbxproj: str) -> tuple[set[str], set[str]]:
    """(marketing versions, build numbers) set anywhere in the project."""
    versions = set(re.findall(r"MARKETING_VERSION = ([^;\s]+);", pbxproj))
    builds = set(re.findall(r"CURRENT_PROJECT_VERSION = ([^;\s]+);", pbxproj))
    return versions, builds


def docs_version_and_build(owner_steps: str) -> tuple[str, str] | None:
    """The `Version, build` row of OWNER-STEPS.md: ('1.0.0', '2')."""
    m = re.search(
        r"\|\s*Version, build\s*\|\s*`([^`]+)`,\s*build\s*`([^`]+)`", owner_steps
    )
    return (m.group(1), m.group(2)) if m else None


def check_address() -> Result:
    url = site.APP_STORE_CANONICAL_URL
    ok = bool(re.fullmatch(r"\d{6,}", site.APP_STORE_ID)) and url == (
        f"https://apps.apple.com/us/app/id{site.APP_STORE_ID}"
    )
    return Result("address", ok, f"{url} (id {site.APP_STORE_ID})")


def check_listing_opens(fetch: Fetch) -> Result:
    url = site.APP_STORE_CANONICAL_URL
    got = fetch(url)
    return Result("listing opens", got.status == 200, f"GET {url} -> {got.status}")


def check_lookup(fetch: Fetch, pbxproj: str, owner_steps: str) -> list[Result]:
    versions, builds = project_versions(pbxproj)
    docs = docs_version_and_build(owner_steps)
    one = len(versions) == 1 and len(builds) == 1
    project = (next(iter(versions)), next(iter(builds))) if one else None
    results = [
        Result(
            "project has one version and one build",
            one,
            f"versions {sorted(versions)}, builds {sorted(builds)}",
        ),
        Result(
            "docs match the project",
            docs is not None and docs == project,
            f"docs {docs}, project {project}",
        ),
    ]
    url = LOOKUP_URL.format(id=site.APP_STORE_ID)
    got = fetch(url)
    if got.status != 200:
        results.append(Result("store lookup", False, f"GET {url} -> {got.status}"))
        return results
    try:
        payload = json.loads(got.body)
        app = payload["results"][0] if payload["resultCount"] == 1 else {}
    except (ValueError, KeyError, IndexError, TypeError):
        results.append(Result("store lookup", False, "not Apple's lookup JSON"))
        return results
    results.append(
        Result(
            "store lists this app",
            str(app.get("trackId")) == site.APP_STORE_ID
            and app.get("bundleId") == APP_BUNDLE_ID,
            f"trackId {app.get('trackId')}, bundleId {app.get('bundleId')}",
        )
    )
    store_version = app.get("version")
    results.append(
        Result(
            "store version matches project and docs",
            project is not None
            and docs is not None
            and store_version == project[0] == docs[0],
            f"store {store_version}, project {project}, docs {docs}",
        )
    )
    return results


def check_surfaces() -> list[Result]:
    """Build the site on and off, offline, and check every surface."""
    results: list[Result] = []
    with tempfile.TemporaryDirectory(prefix="preflight-") as tmp:
        for live in (True, False):
            root = Path(tmp) / ("on" if live else "off")
            root.mkdir()
            out = root / "site"
            cli.run(
                fixture_path=str(FIXTURE),
                history_path=root / "history.json",
                aliases_path=root / "aliases.json",
                schema_path=SCHEMA,
                site_out=out,
                base_url="https://example.invalid/preflight",
                fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
                run_today=dt.date(2026, 9, 13),
                ga4_measurement_id=site.GA4_MEASUREMENT_ID or "G-PREFLIGHT0",
                app_store_live=live,
            )
            problems = launch_check.surface_problems(out, live=live)
            results.append(
                Result(
                    f"site built {'on' if live else 'off'}: every surface agrees",
                    not problems,
                    "; ".join(problems[:5]) or "all consistent",
                )
            )
    return results


def run_all(
    fetch: Fetch, *, pbxproj: str | None = None, owner_steps: str | None = None
) -> list[Result]:
    pbx = PBXPROJ.read_text(encoding="utf-8") if pbxproj is None else pbxproj
    own = (
        OWNER_STEPS.read_text(encoding="utf-8") if owner_steps is None else owner_steps
    )
    results = [check_address(), check_listing_opens(fetch)]
    results += check_lookup(fetch, pbx, own)
    results += check_surfaces()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="App Store launch pre-flight (read-only)."
    )
    parser.parse_args(argv)
    print(
        "committed default (site.APP_STORE_LIVE_DEFAULT): "
        + ("ON" if site.APP_STORE_LIVE_DEFAULT else "off")
    )
    results = run_all(http_get)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name}: {r.detail}")
    failed = [r for r in results if not r.ok]
    print(
        "READY to flip" if not failed else f"NOT READY: {len(failed)} check(s) failed"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
