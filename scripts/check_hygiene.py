#!/usr/bin/env python3
"""Repository hygiene gate run by `make hygiene` (and so by `make verify`).

Three portfolio controls that are a text search, not a tool:

- CQ-34: a TODO, FIXME or HACK marker must name its issue on the same line,
  as `(#123)` or a full `/issues/123` URL. A bare marker is a promise nobody
  is tracking.
- CQ-35: a `noqa` or `type: ignore` suppression must carry both a rule code
  and an issue reference. A blanket suppression hides whatever it lands on.
- IR-15: no wildcard `git add` (`-A`, `--all`, `.`) in a workflow that runs
  unattended. The publish job commits data back to main every day, so it
  must name exactly the files it means to commit.

Written in Python rather than as `grep` lines in the Makefile because the
same target has to behave identically on a developer's machine and on the CI
runner, and the local `grep` is not always GNU grep.

`--self-test` feeds each check a line it must reject and a line it must
accept, and exits non-zero if any check fails to discriminate. `make
hygiene` runs the self-test first, so a check that has quietly stopped
matching anything cannot report a clean repository.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The marker words are assembled so this file does not trip its own check.
_MARKER = re.compile(
    r"\b(" + "|".join(("TO" + "DO", "FIX" + "ME", "HA" + "CK")) + r")\b"
)
_ISSUE_REF = re.compile(r"\(#\d+\)|https?://\S+/issues/\d+|#\d+\b")
_NOQA = re.compile(r"#\s*noqa\b(?P<rest>.*)", re.IGNORECASE)
_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?P<rest>.*)")
_WILDCARD_ADD = re.compile(r"\bgit\s+add\s+(?:[^\n#]*\s)?(?:-A\b|--all\b|\.(?=\s|$))")

SOURCE_GLOBS = (
    "pipeline/src/**/*.py",
    "pipeline/tests/**/*.py",
    "scripts/**/*.py",
    "ios/**/*.swift",
    ".github/workflows/*.yml",
    "Makefile",
)
WORKFLOW_GLOBS = (".github/workflows/*.yml", "scripts/**/*.sh")


def bare_marker(line: str) -> bool:
    """True when the line carries a TODO-class marker without an issue ref."""
    return bool(_MARKER.search(line)) and not _ISSUE_REF.search(line)


def blanket_suppression(line: str) -> bool:
    """True for a noqa / type-ignore missing its rule code or issue ref."""
    for pattern, code in ((_NOQA, r":\s*[A-Z]+\d+"), (_TYPE_IGNORE, r"\[[\w-]+")):
        m = pattern.search(line)
        if m is None:
            continue
        rest = m.group("rest")
        if not re.match(code, rest) or not _ISSUE_REF.search(rest):
            return True
    return False


def wildcard_add(line: str) -> bool:
    """True when a shell line stages files with a wildcard."""
    return bool(_WILDCARD_ADD.search(line))


def _files(globs: Iterable[str]) -> list[Path]:
    found: set[Path] = set()
    for pattern in globs:
        found.update(p for p in ROOT.glob(pattern) if p.is_file())
    this = Path(__file__).resolve()
    return sorted(p for p in found if p.resolve() != this and ".venv" not in p.parts)


def scan(globs: Iterable[str], check: Callable[[str], bool]) -> list[str]:
    hits = []
    for path in _files(globs):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if check(line):
                hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    return hits


def self_test() -> list[str]:
    """Each check must reject its bad line and accept its good line."""
    marker = "TO" + "DO"
    cases: list[tuple[str, Callable[[str], bool], str, str]] = [
        ("CQ-34", bare_marker, f"# {marker}: tidy this", f"# {marker}(#12): tidy this"),
        (
            "CQ-34 url",
            bare_marker,
            f"// {marker} later",
            f"// {marker} https://github.com/o/r/issues/7",
        ),
        (
            "CQ-35 noqa",
            blanket_suppression,
            "x = 1  # noqa",
            "x = 1  # noqa: S101 (#4)",
        ),
        (
            "CQ-35 noqa no issue",
            blanket_suppression,
            "x = 1  # noqa: S101",
            "x = 1",
        ),
        (
            "CQ-35 type",
            blanket_suppression,
            "y = f()  # type: ignore",
            "y = f()  # type: ignore[no-any-return] (#9)",
        ),
        ("IR-15 -A", wildcard_add, "git add -A", "git add pipeline/data/history.json"),
        ("IR-15 --all", wildcard_add, "  git add --all && git commit", "git add a b"),
        ("IR-15 dot", wildcard_add, "git add .", "git add ./pipeline/data/x.json"),
    ]
    failures = []
    for name, check, bad, good in cases:
        if not check(bad):
            failures.append(f"self-test {name}: did not reject {bad!r}")
        if check(good):
            failures.append(f"self-test {name}: rejected {good!r}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"hygiene self-test: {len(failures)} failure(s)")
        return 1 if failures else 0

    problems = [
        *(f"CQ-34 bare marker: {h}" for h in scan(SOURCE_GLOBS, bare_marker)),
        *(
            f"CQ-35 blanket suppression: {h}"
            for h in scan(SOURCE_GLOBS, blanket_suppression)
        ),
        *(f"IR-15 wildcard git add: {h}" for h in scan(WORKFLOW_GLOBS, wildcard_add)),
    ]
    for problem in problems:
        print(problem, file=sys.stderr)
    scanned = len(_files(SOURCE_GLOBS))
    if scanned == 0:
        print("hygiene: scanned zero files, which is not a pass", file=sys.stderr)
        return 1
    print(f"hygiene: {scanned} file(s) scanned, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
