#!/usr/bin/env python3
"""Fail the CodeQL job on a high-severity finding, read from local SARIF.

Code scanning was not available while this repository was private (GitHub
answered `GET /code-scanning/alerts` with 403 "not enabled"), so a SARIF
upload would have failed. The workflow analyzes with `upload: never` and this
script is the gate instead. The repository is public now, and the gate stays
until uploading is switched on.

A result gates the merge when either:

- its rule's `problem.severity` is `error`, or
- its rule's `security-severity` (the CVSS score of the weakness) is 7.0 or
  higher.

Both are needed. The two scales disagree: `py/incomplete-url-substring-
sanitization` is `problem.severity: warning` with `security-severity: 7.8`,
so a gate reading only `problem.severity` passes a HIGH finding. Every
result, gating or not, is printed with its file and line.

A directory with no SARIF, or a SARIF with no runs, fails: an analysis that
produced nothing must not read as a clean one.

`--self-test` runs the gate over five synthetic cases and exits non-zero if
it fails to tell any of them apart.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

SECURITY_SEVERITY_FLOOR = 7.0


def _rules(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tool = run.get("tool", {})
    components = [tool.get("driver", {}), *tool.get("extensions", [])]
    rules: dict[str, dict[str, Any]] = {}
    for component in components:
        for rule in component.get("rules", []):
            rules[rule.get("id", "")] = rule
    return rules


def _location(result: dict[str, Any]) -> str:
    for loc in result.get("locations", []):
        phys = loc.get("physicalLocation", {})
        uri = phys.get("artifactLocation", {}).get("uri", "?")
        line = phys.get("region", {}).get("startLine", "?")
        return f"{uri}:{line}"
    return "?:?"


def evaluate(sarif_dir: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (gating findings, other findings, errors about the input)."""
    files = sorted(sarif_dir.glob("*.sarif")) if sarif_dir.is_dir() else []
    if not files:
        return [], [], [f"no .sarif files under {sarif_dir}"]
    gating: list[str] = []
    other: list[str] = []
    errors: list[str] = []
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        runs = doc.get("runs", [])
        if not runs:
            errors.append(f"{path.name}: SARIF has no runs")
            continue
        for run in runs:
            rules = _rules(run)
            for result in run.get("results", []):
                rule_id = result.get("ruleId", "?")
                props = rules.get(rule_id, {}).get("properties", {})
                problem = str(props.get("problem.severity", "")).lower()
                try:
                    security = float(props.get("security-severity", 0) or 0)
                except (TypeError, ValueError):
                    security = 0.0
                line = (
                    f"{_location(result)} {rule_id} "
                    f"(problem.severity={problem or 'unset'}, "
                    f"security-severity={security:g})"
                )
                if problem == "error" or security >= SECURITY_SEVERITY_FLOOR:
                    gating.append(line)
                else:
                    other.append(line)
    return gating, other, errors


def _sarif(rule_props: dict[str, Any] | None) -> dict[str, Any]:
    rules = [] if rule_props is None else [{"id": "t/rule", "properties": rule_props}]
    results = (
        []
        if rule_props is None
        else [
            {
                "ruleId": "t/rule",
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": "src/x.py"},
                            "region": {"startLine": 3},
                        }
                    }
                ],
            }
        ]
    )
    return {"runs": [{"tool": {"driver": {"rules": rules}}, "results": results}]}


def self_test() -> list[str]:
    cases: list[tuple[str, dict[str, Any] | None, bool, bool]] = [
        # name, rule properties (None = clean run), write a file?, must gate
        ("no SARIF at all", None, False, True),
        ("clean SARIF", None, True, False),
        ("problem.severity error", {"problem.severity": "error"}, True, True),
        (
            "warning with security-severity 7.8",
            {"problem.severity": "warning", "security-severity": "7.8"},
            True,
            True,
        ),
        (
            "note with security-severity 5.0",
            {"problem.severity": "note", "security-severity": "5.0"},
            True,
            False,
        ),
    ]
    failures = []
    for name, props, write, must_gate in cases:
        with tempfile.TemporaryDirectory() as tmp:
            if write:
                Path(tmp, "t.sarif").write_text(json.dumps(_sarif(props)))
            gating, _other, errors = evaluate(Path(tmp))
            gated = bool(gating or errors)
            if gated != must_gate:
                failures.append(f"self-test '{name}': gated={gated}, want {must_gate}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sarif_dir", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"codeql gate self-test: {len(failures)} failure(s)")
        return 1 if failures else 0
    if args.sarif_dir is None:
        parser.error("sarif_dir is required unless --self-test is given")

    gating, other, errors = evaluate(args.sarif_dir)
    for error in errors:
        print(f"::error::{error}")
    for line in gating:
        print(f"::error::gating finding: {line}")
    for line in other:
        print(f"below the floor (reported, not gating): {line}")
    print(
        f"codeql gate: {len(gating)} gating, {len(other)} below the floor, "
        f"{len(errors)} input error(s)"
    )
    return 1 if gating or errors else 0


if __name__ == "__main__":
    sys.exit(main())
