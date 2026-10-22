"""scripts/check_publish_health.py and .github/workflows/publish-health.yml.

No network: the fetch is a function the tests replace. The clock is a fixed
instant, and the snapshot is built here, never read from the daily-rewritten
data files. Each negative control asserts its sabotage changed the input
before it asserts the check noticed.
"""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_publish_health.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-health.yml"


def _load():
    spec = importlib.util.spec_from_file_location("check_publish_health", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ph = _load()
NOW = dt.datetime(2026, 10, 22, 17, 43, tzinfo=dt.UTC)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def healthy() -> dict:
    return {
        "generated_at": _iso(NOW - dt.timedelta(hours=4, minutes=26)),
        "states": [
            {"code": "CA", "current_week": {"start": "2026-10-18"}},
            {
                "code": "TN",
                "checks": {
                    "last_attempt_ok": True,
                    "last_success_at": _iso(NOW - dt.timedelta(hours=4)),
                },
            },
        ],
    }


def keys(snapshot: object) -> set[str]:
    return {f.key for f in ph.evaluate(snapshot, NOW)}


def tn(snapshot: dict) -> dict:
    return snapshot["states"][1]


def test_a_healthy_snapshot_has_no_findings():
    assert ph.evaluate(healthy(), NOW) == []


def test_the_thresholds_are_the_documented_constants():
    assert ph.STALE_PUBLISH_HOURS == 24
    assert ph.STATE_FAIL_DAYS == 3
    assert ph.CA_WEEK_MAX_AGE_DAYS == 9


def test_publish_age_boundary():
    snap = healthy()
    snap["generated_at"] = _iso(NOW - dt.timedelta(hours=ph.STALE_PUBLISH_HOURS))
    assert keys(snap) == set()
    snap["generated_at"] = _iso(
        NOW - dt.timedelta(hours=ph.STALE_PUBLISH_HOURS, minutes=1)
    )
    assert keys(snap) == {"publish-stale"}


def test_one_missed_daily_run_is_caught_the_same_day():
    # The run at 13:17 on the 22nd never happened; the last good one was the 21st.
    snap = healthy()
    snap["generated_at"] = "2026-10-21T13:30:00Z"
    assert (NOW - dt.datetime(2026, 10, 21, 13, 30, tzinfo=dt.UTC)) > dt.timedelta(
        hours=ph.STALE_PUBLISH_HOURS
    )
    assert keys(snap) == {"publish-stale"}


def test_state_failure_boundary_and_the_tennessee_case():
    snap = healthy()
    tn(snap)["checks"] = {
        "last_attempt_ok": False,
        "last_success_at": _iso(NOW - dt.timedelta(days=ph.STATE_FAIL_DAYS - 1)),
    }
    assert keys(snap) == set()
    tn(snap)["checks"]["last_success_at"] = _iso(
        NOW - dt.timedelta(days=ph.STATE_FAIL_DAYS)
    )
    assert keys(snap) == {"TN-failing"}
    # Tennessee, 2026-10-15 13:31Z to 2026-10-22 17:43Z: failing for 7 days.
    tn(snap)["checks"]["last_success_at"] = "2026-10-15T13:31:10Z"
    found = ph.evaluate(snap, NOW)
    assert [f.key for f in found] == ["TN-failing"]
    assert "7 days" in found[0].text


def test_a_failing_attempt_with_a_recent_success_is_not_yet_a_finding():
    snap = healthy()
    tn(snap)["checks"]["last_attempt_ok"] = False
    assert keys(snap) == set()


def test_ca_week_boundary():
    snap = healthy()
    snap["states"][0]["current_week"]["start"] = (
        NOW.date() - dt.timedelta(days=ph.CA_WEEK_MAX_AGE_DAYS)
    ).isoformat()
    assert keys(snap) == set()
    snap["states"][0]["current_week"]["start"] = (
        NOW.date() - dt.timedelta(days=ph.CA_WEEK_MAX_AGE_DAYS + 1)
    ).isoformat()
    assert keys(snap) == {"ca-week-stale"}


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda s: s.pop("generated_at"), "generated-missing"),
        (lambda s: s.update(generated_at="yesterday"), "generated-missing"),
        (lambda s: s.update(generated_at="2026-10-22T12:00:00"), "generated-missing"),
        (lambda s: s.pop("states"), "states-missing"),
        (lambda s: s.update(states=[]), "states-missing"),
        (lambda s: s["states"].pop(0), "ca-missing"),
        (lambda s: s["states"][0].pop("current_week"), "ca-week-missing"),
        (lambda s: s["states"][0].update(code="ca"), "state-code"),
        (lambda s: s["states"][1].pop("checks"), "TN-checks"),
        (lambda s: s["states"][1]["checks"].update(last_attempt_ok="no"), "TN-checks"),
        (
            lambda s: s["states"][1]["checks"].update(
                last_attempt_ok=False, last_success_at=None
            ),
            "TN-never",
        ),
    ],
)
def test_absence_is_a_finding_never_a_pass(mutate, expected):
    snap = healthy()
    before = copy.deepcopy(snap)
    mutate(snap)
    assert snap != before, "the sabotage did not apply"
    assert expected in keys(snap)


@pytest.mark.parametrize("bad", [None, [], "x", 3])
def test_a_snapshot_that_is_not_an_object_is_a_finding(bad):
    assert keys(bad) == {"snapshot-shape"}


def test_fetch_retries_then_reports_the_site_down():
    calls = []

    def down(url):
        calls.append(url)
        raise httpx.ConnectError("refused")

    found = ph.check("https://example.test/snapshot/v2.json", NOW, down)
    assert [f.key for f in found] == ["fetch"]
    assert len(calls) == ph.FETCH_ATTEMPTS


def test_fetch_recovers_on_a_later_attempt():
    answers = [httpx.ConnectError("blip"), json.dumps(healthy()).encode()]

    def flaky(url):
        item = answers.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    assert ph.check("https://example.test/s.json", NOW, flaky) == []


def test_a_body_that_is_not_json_is_a_finding():
    found = ph.check("https://example.test/s.json", NOW, lambda u: b"<html>")
    assert [f.key for f in found] == ["snapshot-json"]


def test_a_stale_body_through_the_whole_path():
    snap = healthy()
    snap["generated_at"] = "2026-10-01T00:00:00Z"
    found = ph.check("https://e.test/s.json", NOW, lambda u: json.dumps(snap).encode())
    assert [f.key for f in found] == ["publish-stale"]


def test_snapshot_url_accepts_https_only_and_defaults():
    assert ph.snapshot_url("") == ph.DEFAULT_BASE_URL + "/snapshot/v2.json"
    assert (
        ph.snapshot_url("https://trouttruck.com/")
        == "https://trouttruck.com/snapshot/v2.json"
    )
    for bad in (
        "http://trouttruck.com",
        "https://user:pw@trouttruck.com",
        "https://trouttruck.com/?a=1",
        "file:///etc/passwd",
        "trouttruck.com",
    ):
        with pytest.raises(ValueError):
            ph.snapshot_url(bad)


def test_the_report_holds_only_fixed_text_and_numbers():
    snap = healthy()
    tn(snap)["checks"] = {
        "last_attempt_ok": False,
        "last_success_at": "2026-10-15T13:31:10Z",
        "last_error": "<script>alert(1)</script> @everyone",
    }
    text = ph.report(ph.evaluate(snap, NOW), "https://e.test/s.json", NOW)
    assert "script" not in text and "@everyone" not in text
    assert "TN has failed to fetch for 7 days" in text


def test_main_exit_codes(tmp_path, monkeypatch):
    out = tmp_path / "r.md"
    monkeypatch.setattr(ph, "check", lambda url, now: [])
    assert ph.main(["--out", str(out)]) == 0
    assert not out.exists()
    monkeypatch.setattr(ph, "check", lambda url, now: [ph.Finding("k", "Something.")])
    assert ph.main(["--out", str(out)]) == 1
    assert "Something." in out.read_text(encoding="utf-8")
    assert ph.main(["--base-url", "http://x", "--out", str(out)]) == 2


# ---- the workflow's shape ------------------------------------------------


def _wf() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _uses_lines(text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"uses: \S+", text)]


def test_every_action_is_pinned_to_a_full_sha():
    uses = _uses_lines(_wf())
    assert uses
    for line in uses:
        assert re.fullmatch(r"uses: [\w./-]+@[0-9a-f]{40}", line), line


def test_pin_check_catches_a_tag(monkeypatch):
    sabotaged = _wf().replace("@93cb6efe18208431cddfb8368fd83d5badbf9bfd", "@v5")
    assert sabotaged != _wf()
    assert any(
        not re.fullmatch(r"uses: [\w./-]+@[0-9a-f]{40}", u)
        for u in _uses_lines(sabotaged)
    )


def test_permissions_are_least_privilege():
    text = _wf()
    top = text[: text.index("jobs:")]
    assert "permissions:\n  contents: read\n" in top
    job = text[text.index("jobs:") :]
    assert "issues: write" in job
    for forbidden in ("contents: write", "actions:", "pull-requests:", "id-token"):
        assert forbidden not in text


def test_no_expression_is_interpolated_into_a_run_script():
    text = _wf()
    bodies = re.findall(r"run: \|\n((?:          .*\n|\n)+)", text)
    assert len(bodies) == 2
    for body in bodies:
        assert "${{" not in body


def test_interpolation_check_catches_an_expression():
    text = _wf().replace('"$SITE_BASE_URL"', '"${{ vars.SITE_BASE_URL }}"')
    assert text != _wf()
    bodies = re.findall(r"run: \|\n((?:          .*\n|\n)+)", text)
    assert any("${{" in b for b in bodies)


def test_one_fixed_title_one_label_and_a_body_file():
    text = _wf()
    assert text.count("ISSUE_TITLE:") == 1
    assert "--label bug" in text
    assert "--body-file" in text and "--body " not in text
    assert text.count("gh issue create") == 1


def test_schedule_runs_after_the_publish_and_is_not_on_the_hour():
    cron = re.search(r'cron: "(\d+) (\d+) \* \* \*"', _wf())
    assert cron
    minute, hour = int(cron.group(1)), int(cron.group(2))
    publish = re.search(
        r'cron: "(\d+) (\d+) \* \* \*"', (WORKFLOW.parent / "publish.yml").read_text()
    )
    assert publish
    assert (hour, minute) > (int(publish.group(2)), int(publish.group(1)))
    assert minute not in (0, 30)
