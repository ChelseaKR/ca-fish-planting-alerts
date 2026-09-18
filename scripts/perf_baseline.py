#!/usr/bin/env python3
"""Compare a Lighthouse CI run against perf/baseline.json (PERFORMANCE-STANDARD §2).

Reads every `lhr-*.json` Lighthouse report in a directory and derives the
two metrics this site has a baseline for:

- lighthouse_performance: the worst page's median performance score across
  runs (higher is better).
- js_kb_gzip: the largest script transfer size of any page, in KiB (lower
  is better). This is first-party script only, because the run blocks
  Google Analytics (see tools/site-checks/run.sh).

A metric fails when it is more than 10% worse than the baseline in its
declared direction. A metric that is null in the baseline is a declared
N/A and is skipped. A directory with no reports fails, so a Lighthouse run
that produced nothing cannot pass.

`--self-test` runs the comparison over synthetic reports and exits non-zero
if it fails to tell a regression from a pass.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

TOLERANCE = 0.10


def measure(lhr_dir: Path) -> dict[str, float]:
    """Derive the baseline metrics from a directory of Lighthouse reports."""
    reports = sorted(lhr_dir.glob("lhr-*.json"))
    if not reports:
        raise ValueError(f"no lhr-*.json reports under {lhr_dir}")
    scores: dict[str, list[float]] = {}
    script_bytes: dict[str, float] = {}
    for path in reports:
        lhr: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        url = str(
            lhr["finalDisplayedUrl"]
            if "finalDisplayedUrl" in lhr
            else lhr["requestedUrl"]
        )
        score = lhr["categories"]["performance"]["score"]
        if score is None:
            raise ValueError(f"{path.name}: performance score is null")
        scores.setdefault(url, []).append(float(score))
        items = lhr["audits"]["resource-summary"]["details"]["items"]
        script = next((i for i in items if i.get("resourceType") == "script"), None)
        if script is None:
            raise ValueError(f"{path.name}: resource-summary has no script row")
        transfer = float(script.get("transferSize", 0))
        script_bytes[url] = max(script_bytes.get(url, 0.0), transfer)
    return {
        "lighthouse_performance": min(statistics.median(v) for v in scores.values()),
        "js_kb_gzip": max(script_bytes.values()) / 1024,
    }


def compare(baseline: dict[str, Any], current: dict[str, float]) -> list[str]:
    """Return one line per metric that regressed beyond the tolerance."""
    failures = []
    for name, base in baseline["metrics"].items():
        if base is None:
            continue
        if name not in current:
            failures.append(f"{name}: in the baseline but not measured")
            continue
        now = current[name]
        direction = baseline["direction"][name]
        if direction == "higher_is_better":
            worse = now < base * (1 - TOLERANCE)
        elif direction == "lower_is_better":
            worse = now > base * (1 + TOLERANCE)
        else:
            failures.append(f"{name}: unknown direction {direction!r}")
            continue
        if worse:
            failures.append(
                f"{name}: {now:.3f} vs baseline {base:.3f} ({direction}, "
                f"more than {TOLERANCE:.0%} worse)"
            )
    return failures


def _report(dir_: Path, n: int, score: float, script: int) -> None:
    lhr = {
        "requestedUrl": "http://x/",
        "categories": {"performance": {"score": score}},
        "audits": {
            "resource-summary": {
                "details": {
                    "items": [{"resourceType": "script", "transferSize": script}]
                }
            }
        },
    }
    (dir_ / f"lhr-{n}.json").write_text(json.dumps(lhr), encoding="utf-8")


def self_test() -> list[str]:
    baseline = {
        "metrics": {"lighthouse_performance": 1.0, "js_kb_gzip": 2.0, "p95_ms": None},
        "direction": {
            "lighthouse_performance": "higher_is_better",
            "js_kb_gzip": "lower_is_better",
            "p95_ms": "lower_is_better",
        },
    }
    cases = [
        ("same as baseline", 1.0, 2048, False),
        ("score 9% lower", 0.91, 2048, False),
        ("score 11% lower", 0.89, 2048, True),
        ("script 11% bigger", 1.0, 2274, True),
    ]
    failures = []
    for name, score, script, must_fail in cases:
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(3):
                _report(Path(tmp), n, score, script)
            failed = bool(compare(baseline, measure(Path(tmp))))
        if failed != must_fail:
            failures.append(f"self-test '{name}': failed={failed}, want {must_fail}")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            measure(Path(tmp))
            failures.append("self-test 'no reports': measured nothing without failing")
        except ValueError:
            pass
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lhr_dir", nargs="?", type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("perf/baseline.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        failures = self_test()
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"perf baseline self-test: {len(failures)} failure(s)")
        return 1 if failures else 0
    if args.lhr_dir is None:
        parser.error("lhr_dir is required unless --self-test is given")

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = measure(args.lhr_dir)
    for name, value in sorted(current.items()):
        print(
            f"measured {name} = {value:.3f} (baseline {baseline['metrics'].get(name)})"
        )
    failures = compare(baseline, current)
    for failure in failures:
        print(f"regression: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
