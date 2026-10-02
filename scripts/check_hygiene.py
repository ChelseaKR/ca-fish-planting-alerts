#!/usr/bin/env python3
"""Repository hygiene gate run by `make hygiene` (and so by `make verify`).

Portfolio controls that are a text search, not a tool:

- CQ-34: a TODO, FIXME or HACK marker must name its issue on the same line,
  as `(#123)` or a full `/issues/123` URL. A bare marker is a promise nobody
  is tracking.
- CQ-35: a `noqa` or `type: ignore` suppression must carry both a rule code
  and an issue reference. A blanket suppression hides whatever it lands on.
- IR-15: no wildcard `git add` (`-A`, `--all`, `.`) in a workflow that runs
  unattended. The publish job commits data back to main every day, so it
  must name exactly the files it means to commit.
- A workflow `run:` body under `set -u` never expands an array bare. The
  macOS runners' /bin/bash is 3.2, where `"${a[@]}"` on an empty array is an
  "unbound variable" error; write `${a[@]+"${a[@]}"}`. The release preflight
  died this way on the first release, when there were no earlier tags.
- No merge-conflict markers in source. CI builds the Swift package but not
  the app target, so a marker left in an app view once reached main with
  every check green.
- App Intents metadata names no Apple device, platform or trademark. App
  Store processing rejects a build (ITMS-90626) whose intent title,
  description, parameter text, entity display name or App Shortcut phrase
  says "iPhone", "Siri", "Apple" and the like; build 1 of 1.0.0 was rejected
  for "on this iPhone" in a Shortcuts description. The check reads the string
  literals in those positions in any app Swift file that imports AppIntents.

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
# Built from parts so this file's own source never holds a marker line.
_CONFLICT = re.compile(
    "^(?:" + "<" * 7 + "(?: |$)|" + ">" * 7 + "(?: |$)|" + "=" * 7 + "$)"
)
_WILDCARD_ADD = re.compile(r"\bgit\s+add\s+(?:[^\n#]*\s)?(?:-A\b|--all\b|\.(?=\s|$))")

SOURCE_GLOBS = (
    "pipeline/src/**/*.py",
    "pipeline/tests/**/*.py",
    "scripts/**/*.py",
    "ios/**/*.swift",
    ".github/workflows/*.yml",
    "Makefile",
)
CONFLICT_GLOBS = (*SOURCE_GLOBS, "pipeline/src/**/*.jinja", "pipeline/src/**/*.css")
WORKFLOW_GLOBS = (".github/workflows/*.yml", "scripts/**/*.sh")
WORKFLOW_FILES = (".github/workflows/*.yml",)
_RUN_KEY = re.compile(r"^(\s*)(?:- )?run:\s*(.*)$")
_NOUNSET = re.compile(r"\bset\s+-[a-zA-Z]*u|\bset\s+-o\s+nounset\b")
_ARRAY_EXPANSION = re.compile(r"\$\{\w+\[[@*]\]\}")
_GUARDED_ARRAY = re.compile(r'\$\{(\w+)\[([@*])\]\+"\$\{\1\[\2\]\}"\}')


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


def run_blocks(text: str) -> list[list[tuple[int, str]]]:
    """Every `run:` body in a workflow, as (line number, line) pairs."""
    lines = text.splitlines()
    blocks: list[list[tuple[int, str]]] = []
    i = 0
    while i < len(lines):
        match = _RUN_KEY.match(lines[i])
        if not match:
            i += 1
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        if inline and inline[0] not in "|>":
            blocks.append([(i + 1, inline)])
            i += 1
            continue
        body: list[tuple[int, str]] = []
        i += 1
        while i < len(lines) and (
            not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent
        ):
            body.append((i + 1, lines[i]))
            i += 1
        blocks.append(body)
    return blocks


def unguarded_arrays(text: str) -> list[int]:
    """Line numbers where a `set -u` run body expands an array without the guard."""
    hits: list[int] = []
    for block in run_blocks(text):
        if not any(_NOUNSET.search(line) for _, line in block):
            continue
        hits.extend(
            number
            for number, line in block
            if _ARRAY_EXPANSION.search(_GUARDED_ARRAY.sub("", line))
        )
    return hits


def scan_unguarded_arrays() -> list[str]:
    hits = []
    for path in _files(WORKFLOW_FILES):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number in unguarded_arrays("\n".join(lines)):
            hits.append(
                f"{path.relative_to(ROOT)}:{number}: {lines[number - 1].strip()}"
            )
    return hits


# Apple's reserved words for App Intents metadata (ITMS-90626), matched
# case-insensitively as whole words inside string literals only, so an
# identifier such as `.applicationName` never counts.
_RESERVED_INTENT_TERM = re.compile(
    r"\b(?:iphone|ipad|ipod|ios|ipados|apple|siri|watchos|macos|mac|macbook|"
    r"airpods|homepod|carplay|facetime|imessage|icloud|app\s+store)\b",
    re.IGNORECASE,
)
# Where intent metadata starts: titles, descriptions, dialogs, summaries,
# entity display representations, short titles and App Shortcut phrases.
_INTENT_METADATA = re.compile(
    r"IntentDescription\(|LocalizedStringResource\s*=|\btitle:|\bdescription:|"
    r"\bshortTitle:|\bphrases:|TypeDisplayRepresentation\(|DisplayRepresentation\(|"
    r"\brequestValueDialog:|\bSummary\(|\bname:"
)
_STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')
INTENT_GLOBS = ("ios/**/*.swift",)


def reserved_intent_terms(text: str) -> list[int]:
    """Line numbers where intent metadata text names a reserved Apple term.

    A metadata opener that leaves a bracket open (a multi-line
    `IntentDescription(` or `phrases: [`) carries on until it closes.
    """
    if "import AppIntents" not in text:
        return []
    hits: list[int] = []
    depth = 0
    for number, line in enumerate(text.splitlines(), start=1):
        code = _STRING_LITERAL.sub('""', line)
        if depth == 0 and not _INTENT_METADATA.search(code):
            continue
        if any(
            _RESERVED_INTENT_TERM.search(lit) for lit in _STRING_LITERAL.findall(line)
        ):
            hits.append(number)
        code = code.split("//", 1)[0]
        depth = max(
            0,
            depth
            + code.count("(")
            + code.count("[")
            - code.count(")")
            - code.count("]"),
        )
    return hits


def scan_reserved_intent_terms() -> list[str]:
    hits = []
    for path in _files(INTENT_GLOBS):
        if any(part.endswith("Tests") for part in path.relative_to(ROOT).parts):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number in reserved_intent_terms("\n".join(lines)):
            hits.append(
                f"{path.relative_to(ROOT)}:{number}: {lines[number - 1].strip()}"
            )
    return hits


def conflict_marker(line: str) -> bool:
    """True for a line git writes when a merge conflict is left unresolved."""
    return bool(_CONFLICT.match(line))


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
        ("conflict ours", conflict_marker, "<" * 7 + " HEAD", "if a << b {"),
        ("conflict theirs", conflict_marker, ">" * 7 + " origin/main", "x >>= 1"),
        (
            "conflict split",
            conflict_marker,
            "=" * 7,
            "    " + "=" * 7 + " heading rule",
        ),
    ]
    failures = []
    for name, check, bad, good in cases:
        if not check(bad):
            failures.append(f"self-test {name}: did not reject {bad!r}")
        if check(good):
            failures.append(f"self-test {name}: rejected {good!r}")
    step = "      - run: |\n          set -euo pipefail\n          earlier=()\n"
    array_cases = [
        (step + '          foo "${earlier[@]}"\n', [4]),
        (step + '          foo "${earlier[*]}"\n', [4]),
        (step + '          foo ${earlier[@]+"${earlier[@]}"} "${#earlier[@]}"\n', []),
        ('      - run: |\n          foo "${args[@]}"\n', []),
        ('      - run: |\n          set -u\n      - run: foo "${a[@]}"\n', []),
    ]
    for text, expected in array_cases:
        if unguarded_arrays(text) != expected:
            failures.append(
                f"self-test bash-3.2 array: {text!r} gave {unguarded_arrays(text)}"
            )
    head = "import AppIntents\n"
    intent_cases = [
        (
            head
            + 'static let description = IntentDescription("From the schedule on this iPhone.")\n',
            [2],
        ),
        (
            head
            + 'static let description = IntentDescription("From the schedule saved in Trout Truck.")\n',
            [],
        ),
        (head + 'static let title: LocalizedStringResource = "Ask siri"\n', [2]),
        (head + '@Parameter(title: "Water", description: "On your iPad")\n', [2]),
        (
            head
            + "AppShortcut(\n    intent: X(),\n    phrases: [\n"
            + '        "When is it in \\(.applicationName)",\n'
            + '        "Ask Apple about \\(.applicationName)",\n'
            + "    ],\n"
            + '    shortTitle: "Next week on iOS",\n'
            + ")\n",
            [6, 8],
        ),
        (head + 'let note = "iPhone only"\n', []),
        ('static let description = IntentDescription("On this iPhone.")\n', []),
    ]
    for text, expected in intent_cases:
        if reserved_intent_terms(text) != expected:
            failures.append(
                f"self-test intent reserved term: {text!r} gave {reserved_intent_terms(text)}"
            )
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
        *(f"conflict marker: {h}" for h in scan(CONFLICT_GLOBS, conflict_marker)),
        *(
            f"bash-3.2 unguarded array under set -u: {h}"
            for h in scan_unguarded_arrays()
        ),
        *(
            f"ITMS-90626 reserved term in App Intents metadata: {h}"
            for h in scan_reserved_intent_terms()
        ),
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
