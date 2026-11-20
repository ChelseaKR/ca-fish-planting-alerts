"""scripts/check_publish_health.py and .github/workflows/publish-health.yml.

No network: the fetch is a function the tests replace. The clock is a fixed
instant, and the snapshot is built here, never read from the daily-rewritten
data files. Each negative control asserts its sabotage changed the input
before it asserts the check noticed.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

import httpx
import pytest

from cfpa import freshness
from cfpa.states import registered_sources

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


def failing_keys(snapshot: object) -> set[str]:
    return {f.key for f in ph.evaluate(snapshot, NOW) if f.fails}


def test_the_thresholds_are_the_documented_constants():
    assert ph.STALE_PUBLISH_HOURS == 24
    assert ph.CA_WEEK_MAX_AGE_DAYS == 9
    # A state's limit is the freshness watchdog's allowance (DECISIONS 0065),
    # not a second, shorter number of this check's own.
    assert not hasattr(ph, "STATE_FAIL_DAYS")
    assert ph.DEFAULT_MAX_READ_AGE_DAYS == freshness.DEFAULT_MAX_READ_AGE_DAYS == 7


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


def test_state_limit_boundary_is_the_freshness_allowance():
    limit = ph.DEFAULT_MAX_READ_AGE_DAYS
    snap = healthy()
    tn(snap)["checks"] = {
        "last_attempt_ok": False,
        "last_success_at": _iso(NOW - dt.timedelta(days=3)),
    }
    # Three days failing was a finding before; inside the allowance it is not.
    assert keys(snap) == set()
    # Equal to the allowance is not stuck; a minute past it is (0065).
    tn(snap)["checks"]["last_success_at"] = _iso(NOW - dt.timedelta(days=limit))
    assert keys(snap) == set()
    tn(snap)["checks"]["last_success_at"] = _iso(
        NOW - dt.timedelta(days=limit, minutes=1)
    )
    assert failing_keys(snap) == {"TN-stuck"}
    # Tennessee, 2026-10-15 13:31Z to 2026-10-22 17:43Z: 7.2 days, stuck.
    tn(snap)["checks"]["last_success_at"] = "2026-10-15T13:31:10Z"
    found = ph.evaluate(snap, NOW)
    assert [f.key for f in found] == ["TN-stuck"]
    assert found[0].fails
    assert found[0].text == (
        "TN is stuck: its last good read was 7.2 days ago (allowed 7 days); "
        "its data is from 2026-10-15."
    )


def test_a_state_past_its_limit_is_stuck_even_when_the_last_attempt_worked():
    snap = healthy()
    tn(snap)["checks"]["last_success_at"] = _iso(NOW - dt.timedelta(days=9))
    assert tn(snap)["checks"]["last_attempt_ok"] is True
    assert failing_keys(snap) == {"TN-stuck"}


def test_a_state_module_s_own_allowance_is_its_limit(monkeypatch):
    known = registered_sources()
    shorter = {**known, "TN": dataclasses.replace(known["TN"], max_read_age_days=2)}
    monkeypatch.setattr(ph, "registered_sources", lambda: shorter)
    snap = healthy()
    tn(snap)["checks"] = {
        "last_attempt_ok": False,
        "last_success_at": _iso(NOW - dt.timedelta(days=3)),
    }
    found = ph.evaluate(snap, NOW)
    assert [f.key for f in found] == ["TN-stuck"]
    assert "(allowed 2 days)" in found[0].text


def test_a_state_this_code_does_not_know_gets_the_default_allowance():
    snap = healthy()
    snap["states"].append(
        {
            "code": "ZZ",
            "checks": {
                "last_attempt_ok": False,
                "last_success_at": _iso(NOW - dt.timedelta(days=8)),
            },
        }
    )
    assert failing_keys(snap) == {"ZZ-stuck"}


# ---- Massachusetts: waiting, not stuck (DECISIONS 0071) --------------------

LIVE_NOW = dt.datetime(2026, 11, 19, 17, 47, tzinfo=dt.UTC)


def live_2026_11_19() -> dict:
    """The live snapshot's state checks on 2026-11-19, as the audit read them."""
    return {
        "generated_at": "2026-11-19T13:22:40Z",
        "states": [
            {"code": "CA", "current_week": {"start": "2026-11-15"}},
            {
                "code": "MA",
                "checks": {
                    "last_attempt_at": "2026-11-19T13:22:41Z",
                    "last_success_at": "2026-11-07T13:22:11Z",
                    "last_attempt_ok": False,
                    "stale_copy": {
                        "source_last_edit_at": "2026-10-13T17:06:39Z",
                        "source_record_count": 155,
                        "copy_record_count": 150,
                    },
                },
            },
            {
                "code": "TN",
                "checks": {
                    "last_attempt_at": "2026-11-19T13:22:41Z",
                    "last_success_at": "2026-11-14T17:05:23Z",
                    "last_attempt_ok": False,
                },
            },
        ],
    }


def ma(snapshot: dict) -> dict:
    return snapshot["states"][1]


def test_the_live_case_of_2026_11_19():
    found = ph.evaluate(live_2026_11_19(), LIVE_NOW)
    # Tennessee's hand-loaded file is 5 days old, inside 7: not a finding.
    # Massachusetts is past 7 days, but waiting: MassWildlife has not edited
    # its layer since 2026-10-13, so nothing new is upstream.
    assert [(f.key, f.fails) for f in found] == [("MA-waiting", False)]
    assert found[0].text == (
        "MA is waiting, not stuck: its last good read was 12.2 days ago "
        "(allowed 7 days), Hub's file is stale, and MassWildlife has not "
        "edited its layer since 2026-10-13 17:06Z (37.0 days ago); red again "
        "as soon as it does."
    )


def test_tennessee_goes_red_the_day_its_file_passes_the_allowance():
    later = LIVE_NOW + dt.timedelta(days=3)
    found = ph.evaluate(live_2026_11_19(), later)
    assert [(f.key, f.fails) for f in found] == [
        ("publish-stale", True),
        ("MA-waiting", False),
        ("TN-stuck", True),
    ]


@pytest.mark.parametrize(
    ("mutate", "detail"),
    [
        # MassWildlife edited its layer two days ago: something new is upstream.
        (
            lambda c: c["stale_copy"].update(
                source_last_edit_at="2026-11-17T09:00:00Z"
            ),
            "Hub's file is stale and MassWildlife edited its layer "
            "2026-11-17 09:00Z, 2.4 days ago",
        ),
        # The edit date could not be read: never a pass.
        (
            lambda c: c["stale_copy"].update(source_last_edit_at=None),
            "Hub's file is stale and MassWildlife's last edit to its layer "
            "could not be read",
        ),
        (lambda c: c["stale_copy"].update(source_last_edit_at="soon"), "could not"),
        # The latest failure was not Hub's stale flag.
        (lambda c: c.pop("stale_copy"), None),
        (lambda c: c.update(stale_copy="stale"), None),
        # A good attempt cannot be waiting.
        (lambda c: c.update(last_attempt_ok=True), None),
    ],
)
def test_waiting_needs_the_stale_flag_and_an_idle_agency(mutate, detail):
    snap = live_2026_11_19()
    before = copy.deepcopy(snap)
    mutate(ma(snap)["checks"])
    assert snap != before, "the sabotage did not apply"
    found = [f for f in ph.evaluate(snap, LIVE_NOW) if f.key.startswith("MA-")]
    assert [(f.key, f.fails) for f in found] == [("MA-stuck", True)]
    if detail is not None:
        assert detail in found[0].text


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
        (
            lambda s: s["states"][1]["checks"].update(last_success_at="last week"),
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
    assert "TN is stuck: its last good read was 7.2 days ago" in text


def test_the_report_lists_a_waiting_state_apart_from_the_findings():
    snap = live_2026_11_19()
    later = LIVE_NOW + dt.timedelta(days=3)
    text = ph.report(ph.evaluate(snap, later), "https://e.test/s.json", later)
    found, waiting = text.split("Not counted")
    assert "- TN is stuck" in found and "MA" not in found
    assert "- MA is waiting, not stuck" in waiting


def test_main_exit_codes(tmp_path, monkeypatch):
    out = tmp_path / "r.md"
    monkeypatch.setattr(ph, "check", lambda url, now: [])
    assert ph.main(["--out", str(out)]) == 0
    assert not out.exists()
    # A waiting state alone is healthy: no report, so no issue and no red.
    waiting = ph.Finding("MA-waiting", "Waiting.", fails=False)
    monkeypatch.setattr(ph, "check", lambda url, now: [waiting])
    assert ph.main(["--out", str(out)]) == 0
    assert not out.exists()
    monkeypatch.setattr(
        ph, "check", lambda url, now: [ph.Finding("k", "Something."), waiting]
    )
    assert ph.main(["--out", str(out)]) == 1
    assert "Something." in out.read_text(encoding="utf-8")
    assert "Waiting." in out.read_text(encoding="utf-8")
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
    assert len(bodies) == 3
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


def _steps(text: str) -> list[str]:
    """The job's steps, each as its YAML block, in order."""
    return re.split(r"\n      - (?=name: |uses: )", text)[1:]


def test_an_unhealthy_check_fails_the_run_after_the_issue_is_updated():
    # Until 2026-11-19 an unhealthy reading was only an issue comment and the
    # run stayed green (Tennessee and Massachusetts, #168).
    steps = _steps(_wf())
    names = [re.match(r"name: (.*)", s).group(1) for s in steps if s.startswith("name")]
    issue = names.index("open, update or close the health issue")
    assert names[issue + 1 :] == ["fail the run while unhealthy"]
    last = steps[-1]
    assert "if: steps.health.outputs.healthy == 'false'" in last
    assert "exit 1" in last
    # The issue step still runs on every outcome and still closes on recovery.
    issue_step = steps[-2]
    assert "if:" not in issue_step.split("run:")[0]
    assert "gh issue close" in issue_step
    assert "exit 1" not in issue_step


def test_the_red_step_check_catches_a_missing_condition():
    sabotaged = _wf().replace("if: steps.health.outputs.healthy == 'false'\n", "")
    assert sabotaged != _wf()
    assert "if: steps.health.outputs.healthy == 'false'" not in _steps(sabotaged)[-1]
