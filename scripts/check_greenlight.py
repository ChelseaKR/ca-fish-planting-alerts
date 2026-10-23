#!/usr/bin/env python3
"""Greenlight store-rejection preflight, run by `make greenlight` (and so by
`make verify`).

Greenlight (https://github.com/RevylAI/greenlight, MIT, third party) reads the
app's source for the things App Review and Google Play bounce an upload for:
a missing or incomplete privacy manifest, Required Reason APIs called without
a declared reason, private APIs, hardcoded secrets, a restricted Android
permission, a stale target API level, an exported component without
`android:exported`. This gate runs its static `preflight` command on the app
targets and fails on any CRITICAL or HIGH finding or a scanner crash.

Pinned, not floating
--------------------
The scanner is built from source with `go install` at a full commit, never
`@latest`:

    github.com/RevylAI/greenlight/cmd/greenlight@db0ec50f0f8bdefc8d3d4e525cb935f2ef9014c5

That commit is the v0.2.0 tag (tag object a8729772ad706b9af41ee6f31ac2eab030daaf96).
A commit rather than a tag, because a tag can be moved and a commit cannot.
It installs into `build/tools/bin` inside the checkout (git-ignored), never
into `~/go/bin`, so two checkouts cannot disagree about the version. After the
install the module's content hash is read back with `go version -m` and must
equal GREENLIGHT_MODULE_HASH below, which is the hash the Go checksum database
vouches for. A binary that is present but built from anything else is rebuilt.
Bumping the scanner means changing the commit, the version and the hash here
together; the self-test fails if they stop looking like one release.

What is scanned, and why not the repository root
------------------------------------------------
Measured against this tree, not assumed:

- Its privacy scanner greps every Swift file it can reach, test files
  included, and the `.greenlight.yml` `ignore:` list applies only to the code
  scanner. A root scan therefore judges the UI tests and the Swift package's
  tests as if they shipped. Only directories that ship are scanned:
  `ios/CAFishPlanting` (the app), `ios/CAFishPlantingWidgets` (the widget
  extension) and `android` (the Gradle project; the scanner finds the
  manifest and Gradle files itself and ignores `build/`).
- The Apple Watch targets are not scanned: the 1.0.0 binary does not ship
  them (CHANGELOG, Unreleased). Add them to TARGETS the day they ship.

Known blind spots, stated so a green run is not over-read
---------------------------------------------------------
- Every Info.plist takes its bundle id from a build variable, so Greenlight
  prints `Bundle: $(PRODUCT_BUNDLE_IDENTIFIER)`. Any check keyed on the real
  bundle identifier (a reverse-DNS naming rule, a mismatch with the store
  listing) cannot see it. This gate notes that instead of hiding it.
  scripts/check_app_store.py reads the project file and covers the build
  settings.
- Android: a source scan reads the manifest before the Gradle merge, so a
  permission contributed by a library manifest is invisible. Scanning a built
  artifact (`--apk`/`--aab`) closes that, and needs a build this gate does not do.
- The checks are regular expressions over source text. They can miss a call
  made through an indirection and can flag a string that only looks like one.

Exit status and skipping
------------------------
No Go toolchain and no installed scanner is the only thing that skips the gate
locally. It then prints `SKIPPED: greenlight not installed`, records the skip
in the status file, and `--summary` (the last line of `make verify`) says the
run is not a full pass. Under CI (`CI` or `GITHUB_ACTIONS` set) the same
condition fails: a skipped gate in CI is a gate that cannot fail.

The scanner's network commands (`scan`, `verify`, `--verify`) are never used;
`preflight` on a directory reads files and sends nothing.

`--self-test` checks the pin and the verdict logic on canned reports. The
negative controls that run the real scanner on seeded copies are in
pipeline/tests/test_check_greenlight.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GREENLIGHT_MODULE = "github.com/RevylAI/greenlight"
GREENLIGHT_VERSION = "v0.2.0"
GREENLIGHT_COMMIT = "db0ec50f0f8bdefc8d3d4e525cb935f2ef9014c5"
# The h1: line `go version -m` prints for the module, i.e. what sum.golang.org
# holds for github.com/RevylAI/greenlight@v0.2.0.
GREENLIGHT_MODULE_HASH = "h1:IqoEUPzz+JV4C0jd4Lfbg/VoHZRT+CBxNlOIDkXban4="
INSTALL_REF = f"{GREENLIGHT_MODULE}/cmd/greenlight@{GREENLIGHT_COMMIT}"

TOOL_BIN = ROOT / "build" / "tools" / "bin"
SKIP_LINE = "SKIPPED: greenlight not installed"


@dataclass(frozen=True)
class Target:
    """One directory that ships, and what a real scan of it must show."""

    name: str
    path: str
    android: bool


TARGETS = (
    Target("ios app", "ios/CAFishPlanting", android=False),
    Target("ios widgets", "ios/CAFishPlantingWidgets", android=False),
    Target("android", "android", android=True),
)


def in_ci() -> bool:
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def tool_path() -> Path:
    return TOOL_BIN / "greenlight"


def installed_module_hash(binary: Path) -> str | None:
    """The module hash baked into the binary, or None if it cannot be read."""
    go = shutil.which("go")
    if go is None or not binary.is_file():
        return None
    done = subprocess.run(
        [go, "version", "-m", str(binary)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return None
    for line in done.stdout.splitlines():
        fields = line.split()
        if fields[:2] == ["mod", GREENLIGHT_MODULE] and len(fields) >= 4:
            return fields[3]
    return None


def pinned_binary_ready(binary: Path) -> bool:
    return installed_module_hash(binary) == GREENLIGHT_MODULE_HASH


def install_pinned() -> bool:
    """Build the pinned commit into build/tools/bin. False if it cannot."""
    go = shutil.which("go")
    if go is None:
        return False
    TOOL_BIN.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GOBIN": str(TOOL_BIN)}
    print(f"installing greenlight {GREENLIGHT_VERSION} ({GREENLIGHT_COMMIT[:12]})")
    done = subprocess.run([go, "install", INSTALL_REF], env=env, check=False)
    return done.returncode == 0


def ensure_tool() -> Path | None:
    """The verified pinned binary, installing it if needed; None if impossible."""
    binary = tool_path()
    if pinned_binary_ready(binary):
        return binary
    if not install_pinned():
        return None
    if not pinned_binary_ready(binary):
        print(
            f"greenlight built but its module hash is not {GREENLIGHT_MODULE_HASH}",
            file=sys.stderr,
        )
        return None
    return binary


def judge(target: Target, report: dict[str, object], exit_code: int) -> list[str]:
    """Problems with one scan: findings that gate, and a scan that proved nothing."""
    problems: list[str] = []
    summary = report.get("summary")
    counts = summary if isinstance(summary, dict) else {}
    critical = int(counts.get("critical", 0))
    high = int(counts.get("high", 0))
    if critical or high:
        problems.append(f"{critical} critical and {high} high finding(s)")
    if exit_code != 0 and not (critical or high):
        problems.append(f"scanner exited {exit_code} with no gating finding (crash?)")
    # A scan of an empty or wrong directory reports "no issues" too. Require
    # the evidence that it read what it was meant to.
    if target.android:
        if report.get("is_android") is not True:
            problems.append("did not recognise an Android project")
        if not report.get("package_name") or not report.get("target_sdk"):
            problems.append("read no package name or target SDK from the manifest")
    else:
        if report.get("is_android") is True:
            problems.append("an iOS target was scanned as Android")
        if not report.get("app_name"):
            problems.append("read no app name from an Info.plist")
    return problems


def scan(binary: Path, root: Path, target: Target) -> tuple[bool, dict[str, object]]:
    """Run one preflight; return (clean, parsed report)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "report.json"
        done = subprocess.run(
            [
                str(binary),
                "preflight",
                str(root / target.path),
                "--exit-code",
                "--format",
                "json",
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        raw = out.read_text(encoding="utf-8") if out.is_file() else ""
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        report = {}
    if not isinstance(report, dict):
        report = {}
    problems = judge(target, report, done.returncode)
    if not report:
        problems.append(
            "no readable report (stderr: " + done.stderr.strip()[:200] + ")"
        )
    for finding in report.get("findings") or []:
        if isinstance(finding, dict):
            print(
                f"  [{finding.get('severity')}] [{finding.get('source')}] "
                f"{finding.get('title')} ({finding.get('file', '')})"
            )
    for problem in problems:
        print(f"  FAIL {target.name}: {problem}")
    return not problems, report


def note_unexpanded(report: dict[str, object]) -> None:
    bundle = str(report.get("bundle_id") or "")
    if "$(" in bundle:
        print(
            f"  note: bundle id reads as {bundle}, an unexpanded build variable; "
            "checks keyed on the real identifier cannot see it"
        )


def write_status(path: Path | None, status: str) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(status + "\n", encoding="utf-8")


def run_gate(root: Path, targets: Sequence[Target], status_file: Path | None) -> int:
    binary = ensure_tool()
    if binary is None:
        print(SKIP_LINE, file=sys.stderr)
        print(SKIP_LINE)
        write_status(status_file, "skipped")
        if in_ci():
            print("greenlight: a skip is a failure under CI", file=sys.stderr)
            return 1
        print("greenlight: not counted as passed; install Go to run this gate")
        return 0
    failed = 0
    for target in targets:
        print(f"greenlight preflight {target.path}")
        if not (root / target.path).is_dir():
            print(f"  FAIL {target.name}: {target.path} does not exist")
            failed += 1
            continue
        clean, report = scan(binary, root, target)
        note_unexpanded(report)
        failed += 0 if clean else 1
    write_status(status_file, "failed" if failed else "passed")
    print(
        f"greenlight {GREENLIGHT_VERSION}: "
        + (
            f"{failed} target(s) FAILED"
            if failed
            else f"{len(targets)} target(s) clean"
        )
    )
    return 1 if failed else 0


def summary(status_file: Path) -> int:
    """Last line of `make verify`: say what the greenlight gate really did."""
    status = (
        status_file.read_text(encoding="utf-8").strip() if status_file.is_file() else ""
    )
    if status == "passed":
        print("verify: every gate ran and passed, greenlight included")
        return 0
    if status == "skipped" and not in_ci():
        print(
            "verify: all other gates passed, but greenlight was SKIPPED and is "
            "NOT counted as passed"
        )
        return 0
    print(f"verify: greenlight status is {status or 'missing'}; not a full pass")
    return 1


def self_test() -> list[str]:
    failures: list[str] = []
    ios = Target("ios app", "x", android=False)
    droid = Target("android", "y", android=True)
    good_ios: dict[str, object] = {
        "app_name": "A",
        "summary": {"critical": 0, "high": 0},
    }
    good_droid: dict[str, object] = {
        "is_android": True,
        "package_name": "p",
        "target_sdk": 36,
        "summary": {"critical": 0, "high": 0},
    }
    cases: list[tuple[str, Target, dict[str, object], int, bool]] = [
        ("clean ios", ios, good_ios, 0, True),
        ("clean android", droid, good_droid, 0, True),
        (
            "high finding",
            ios,
            {**good_ios, "summary": {"critical": 0, "high": 1}},
            1,
            False,
        ),
        (
            "critical finding",
            ios,
            {**good_ios, "summary": {"critical": 2, "high": 0}},
            1,
            False,
        ),
        ("crash", ios, good_ios, 2, False),
        ("empty ios report", ios, {"summary": {}}, 0, False),
        ("android read as ios", droid, good_ios, 0, False),
        ("ios read as android", ios, {**good_ios, "is_android": True}, 0, False),
    ]
    for name, target, report, code, want_clean in cases:
        if (not judge(target, report, code)) is not want_clean:
            failures.append(f"self-test {name}: wrong verdict")
    if not re.fullmatch(r"[0-9a-f]{40}", GREENLIGHT_COMMIT):
        failures.append("self-test pin: commit is not a full 40-hex SHA")
    if "@latest" in INSTALL_REF or not INSTALL_REF.endswith(GREENLIGHT_COMMIT):
        failures.append("self-test pin: install ref is not the pinned commit")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", GREENLIGHT_VERSION):
        failures.append("self-test pin: version is not a release tag")
    if not re.fullmatch(r"h1:[A-Za-z0-9+/]{43}=", GREENLIGHT_MODULE_HASH):
        failures.append("self-test pin: module hash is not an h1: hash")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="tree holding the targets"
    )
    parser.add_argument(
        "--status-file", type=Path, help="record passed/failed/skipped here"
    )
    parser.add_argument("--summary", type=Path, metavar="STATUS_FILE")
    parser.add_argument(
        "--only",
        action="append",
        choices=[t.name for t in TARGETS],
        help="scan just this target (tests seed a copy of one)",
    )
    args = parser.parse_args(argv)
    if args.summary:
        return summary(args.summary)
    if args.self_test:
        failures = self_test()
        for failure in failures:
            print(failure)
        print(f"greenlight self-test: {len(failures)} failure(s)")
        return 1 if failures else 0
    chosen = [t for t in TARGETS if not args.only or t.name in args.only]
    return run_gate(args.root, chosen, args.status_file)


if __name__ == "__main__":
    sys.exit(main())
