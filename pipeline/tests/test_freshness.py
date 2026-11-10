"""The freshness watchdog (cfpa.freshness, DECISIONS 0065): a live state
whose last successful read is older than its allowance is a red job, named
with its last good read and the age.

No network and no clock: every history file is written here, never read
from the daily-rewritten data files, and ``now`` is a fixed instant. Each
negative control asserts its sabotage changed the input before it asserts
the check noticed.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from cfpa import cli, freshness
from cfpa.states import SOURCES, enabled_states

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish.yml"
MAKEFILE = REPO_ROOT / "Makefile"
NOW = dt.datetime(2026, 11, 7, 13, 40, tzinfo=dt.UTC)
NOW_ARG = "2026-11-07T13:40:00Z"
LIVE = ("TN", "MI", "MA", "NY")
# Tennessee's committed checks on 2026-11-07: the case this exists for.
TN_LAST_GOOD = dt.datetime(2026, 10, 15, 13, 31, 10, tzinfo=dt.UTC)
TN_STUCK_LINE = (
    "TN (Tennessee): STUCK: last good read 2026-10-15 13:31Z (automated), "
    "23.0 days ago, allowed 7 days; older than allowed"
)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _checks(
    success: dt.datetime | None, *, ok: bool = True, manual: dt.datetime | None = None
) -> dict:
    checks: dict = {
        "last_attempt_at": _iso(NOW - dt.timedelta(minutes=19)),
        "last_success_at": _iso(success) if success else None,
        "last_attempt_ok": ok,
        "last_error": None if ok else "robots.txt answered HTTP 403",
        "content_sha256": "0" * 64,
        "last_modified": None,
    }
    if manual is not None:
        # The shape PR #159 (DECISIONS 0061) writes for a hand-loaded file.
        checks["read_method"] = "manual"
        checks["manual_file"] = {
            "source": "TWRA's downloadable CSV",
            "source_url": "https://www.tn.gov/twra/fishing/trout-information-stockings.html",
            "file_name": "stocking.csv",
            "sha256": "1" * 64,
            "rows": 713,
            "downloaded_at": _iso(manual),
            "imported_at": _iso(manual + dt.timedelta(hours=2)),
        }
    return checks


def _write(
    states_dir: Path, code: str, checks: dict, *, state: str | None = None
) -> Path:
    path = states_dir / f"{code.lower()}.json"
    doc = {
        "schema": "cfpa-state-history-v1",
        "state": state or code,
        "checks": checks,
        "waters": [],
        "aliases": {},
        "records": [],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def fresh_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every live state read successfully four hours before NOW, with the
    runner's environment variables out of the way."""
    monkeypatch.delenv("CFPA_ENABLE_OREGON", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    states_dir = tmp_path / "states"
    states_dir.mkdir()
    for code in LIVE:
        _write(states_dir, code, _checks(NOW - dt.timedelta(hours=4)))
    return states_dir


def _main(states_dir: Path, *extra: str) -> int:
    return freshness.main(["--states-dir", str(states_dir), "--now", NOW_ARG, *extra])


def _live_sources() -> dict:
    return {code: SOURCES[code] for code in LIVE}


# ---- the allowance


def test_the_default_allowance_is_seven_days():
    assert freshness.DEFAULT_MAX_READ_AGE_DAYS == 7


def test_every_live_state_today_takes_the_default():
    """No state declares its own yet; all four are fetched twice a day."""
    for code in LIVE:
        assert SOURCES[code].max_read_age_days is None
        assert freshness.allowance(SOURCES[code], 7) == 7


def test_the_default_states_dir_is_the_pipeline_s_committed_one():
    assert freshness.DEFAULT_STATES_DIR == cli.DEFAULT_STATES_DIR


# ---- fresh and stuck


def test_every_fresh_live_state_passes_and_is_named(fresh_dir, capsys):
    assert _main(fresh_dir) == 0
    out = capsys.readouterr().out
    assert "freshness: all 4 live states fresh; checked 2026-11-07 13:40Z" in out
    for code in LIVE:
        assert (
            f"{code} ({SOURCES[code].name}): fresh: last good read 2026-11-07 09:40Z "
            "(automated), 0.2 days ago, allowed 7 days"
        ) in out
    assert "::error" not in out


def test_tennessee_as_committed_on_2026_11_07_is_stuck_and_the_line_says_so(
    fresh_dir, capsys, monkeypatch
):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _write(fresh_dir, "TN", _checks(TN_LAST_GOOD, ok=False))
    assert _main(fresh_dir) == 1
    out = capsys.readouterr().out
    assert TN_STUCK_LINE in out
    assert f"::error title=Tennessee is stuck::{TN_STUCK_LINE}" in out
    assert "freshness: 1 of 4 live states stuck; checked 2026-11-07 13:40Z" in out
    # The other three are still reported, as fresh, and not annotated.
    assert "MA (Massachusetts): fresh" in out
    assert out.count("::error") == 1


def test_an_attempt_flagged_ok_does_not_rescue_an_old_success(fresh_dir):
    """The age is what counts, not ``last_attempt_ok``."""
    _write(fresh_dir, "MA", _checks(NOW - dt.timedelta(days=10), ok=True))
    [reading] = freshness.check(fresh_dir, {"MA": SOURCES["MA"]}, now=NOW)
    assert not reading.fresh
    assert freshness.line(reading) == (
        "MA (Massachusetts): STUCK: last good read 2026-10-28 13:40Z (automated), "
        "10.0 days ago, allowed 7 days; older than allowed"
    )


def test_stuck_means_strictly_older_than_the_allowance(fresh_dir):
    sources = {"TN": SOURCES["TN"]}
    _write(fresh_dir, "TN", _checks(NOW - dt.timedelta(days=7, hours=-1)))
    [inside] = freshness.check(fresh_dir, sources, now=NOW)
    assert inside.fresh
    _write(fresh_dir, "TN", _checks(NOW - dt.timedelta(days=7, hours=1)))
    [over] = freshness.check(fresh_dir, sources, now=NOW)
    assert not over.fresh
    assert over.problem == "older than allowed"


def test_the_command_line_allowance_applies_to_states_without_their_own(fresh_dir):
    _write(fresh_dir, "TN", _checks(TN_LAST_GOOD, ok=False))
    assert _main(fresh_dir) == 1
    assert _main(fresh_dir, "--max-age-days", "30") == 0
    assert _main(fresh_dir, "--max-age-days", "0") == 2


# ---- the exemptions and the overrides


def test_a_state_behind_an_off_flag_is_not_checked(fresh_dir, capsys, monkeypatch):
    """Oregon (DECISIONS 0032) has no history file here. With its flag off it
    is not live and the check passes; with the flag on it is live, and the
    missing file is a failure, not a pass."""
    assert not (fresh_dir / "or.json").exists()
    assert "OR" not in enabled_states()
    assert _main(fresh_dir) == 0
    assert not re.search(r"\bOR \(Oregon\)", capsys.readouterr().out)

    monkeypatch.setenv("CFPA_ENABLE_OREGON", "1")
    assert "OR" in enabled_states()
    assert _main(fresh_dir) == 1
    out = capsys.readouterr().out
    assert "OR (Oregon): STUCK: no history file at or.json; allowed 7 days" in out
    assert "freshness: 1 of 5 live states stuck" in out


def test_naming_a_flagged_state_while_its_flag_is_off_is_a_usage_error(
    fresh_dir, capsys
):
    assert _main(fresh_dir, "--states", "OR") == 2
    assert "unknown state code(s) ['OR']" in capsys.readouterr().err


def test_naming_no_state_at_all_is_a_usage_error_not_a_pass(fresh_dir, capsys):
    assert _main(fresh_dir, "--states", " , ") == 2
    assert "no states to check" in capsys.readouterr().err


def test_named_states_are_checked_in_the_order_given(fresh_dir):
    sources = freshness.select_sources("ny, tn")
    assert list(sources) == ["NY", "TN"]
    assert freshness.select_sources(None) == {c: SOURCES[c] for c in enabled_states()}


def test_a_state_module_may_declare_its_own_allowance(fresh_dir):
    """A source read on a longer cycle says so on its StateSource; the
    default is unchanged for everyone else."""
    _write(fresh_dir, "NY", _checks(NOW - dt.timedelta(days=30)))
    patient = dataclasses.replace(SOURCES["NY"], max_read_age_days=120)
    [own] = freshness.check(fresh_dir, {"NY": patient}, now=NOW)
    assert own.fresh
    assert own.max_age_days == 120
    assert freshness.line(own) == (
        "NY (New York): fresh: last good read 2026-10-08 13:40Z (automated), "
        "30.0 days ago, allowed 120 days"
    )
    [default] = freshness.check(fresh_dir, {"NY": SOURCES["NY"]}, now=NOW)
    assert not default.fresh
    assert default.max_age_days == 7


# ---- the manual import (DECISIONS 0061)


def test_a_manual_import_counts_as_a_good_read_at_its_download_time(fresh_dir):
    """TWRA's file loaded by hand while the automated read is refused. Read
    from the file's own JSON, not ``Checks``, so this holds whether or not
    the import's code has landed."""
    downloaded = NOW - dt.timedelta(days=1)
    _write(fresh_dir, "TN", _checks(TN_LAST_GOOD, ok=False, manual=downloaded))
    [reading] = freshness.check(fresh_dir, {"TN": SOURCES["TN"]}, now=NOW)
    assert reading.fresh
    assert reading.read_method == "manual"
    assert reading.last_good_read == downloaded
    assert freshness.line(reading) == (
        "TN (Tennessee): fresh: last good read 2026-11-06 13:40Z (manual), "
        "1.0 days ago, allowed 7 days"
    )


def test_the_import_s_own_shape_where_last_success_equals_the_download(fresh_dir):
    """PR #159 writes ``last_success_at`` as the download time too."""
    downloaded = NOW - dt.timedelta(days=1)
    _write(fresh_dir, "TN", _checks(downloaded, ok=False, manual=downloaded))
    [reading] = freshness.check(fresh_dir, {"TN": SOURCES["TN"]}, now=NOW)
    assert reading.fresh
    assert reading.read_method == "manual"


def test_a_later_automated_read_outranks_an_older_manual_file(fresh_dir):
    _write(
        fresh_dir,
        "TN",
        _checks(NOW - dt.timedelta(hours=4), manual=NOW - dt.timedelta(days=20)),
    )
    [reading] = freshness.check(fresh_dir, {"TN": SOURCES["TN"]}, now=NOW)
    assert reading.fresh
    assert reading.read_method == "automated"


def test_an_old_manual_import_is_stuck_like_any_other_read(fresh_dir):
    _write(fresh_dir, "TN", _checks(None, ok=False, manual=NOW - dt.timedelta(days=9)))
    [reading] = freshness.check(fresh_dir, {"TN": SOURCES["TN"]}, now=NOW)
    assert not reading.fresh
    assert reading.read_method == "manual"
    assert reading.problem == "older than allowed"


# ---- absence is a failure


def _unlink(path: Path) -> None:
    path.unlink()


def _edit(mutate: Callable[[dict], None]) -> Callable[[Path], None]:
    def apply(path: Path) -> None:
        doc = json.loads(path.read_text(encoding="utf-8"))
        mutate(doc)
        path.write_text(json.dumps(doc), encoding="utf-8")

    return apply


def _set_success(value: object) -> Callable[[Path], None]:
    return _edit(lambda d: d["checks"].__setitem__("last_success_at", value))


@pytest.mark.parametrize(
    ("sabotage", "problem"),
    [
        (_unlink, "no history file at tn.json"),
        (_set_success(None), "no good read on record"),
        (_set_success("yesterday"), "last_success_at 'yesterday' is not a time"),
        (
            _set_success("2026-11-07T09:40:00"),
            "last_success_at '2026-11-07T09:40:00' has no time zone",
        ),
        (_edit(lambda d: d.pop("checks")), "tn.json has no checks"),
        (_edit(lambda d: d.__setitem__("state", "MI")), "tn.json is not TN's history"),
        (
            _edit(lambda d: d["checks"].__setitem__("manual_file", "x")),
            "manual_file is not an object",
        ),
        (
            _edit(lambda d: d["checks"].__setitem__("manual_file", {"rows": 1})),
            "manual_file.downloaded_at is missing",
        ),
    ],
)
def test_absence_is_a_failure_never_a_pass(fresh_dir, sabotage, problem):
    path = fresh_dir / "tn.json"
    before = path.read_text(encoding="utf-8")
    sabotage(path)
    # Negative control: the sabotage must have changed the input.
    assert not path.exists() or path.read_text(encoding="utf-8") != before
    [reading] = freshness.check(fresh_dir, {"TN": SOURCES["TN"]}, now=NOW)
    assert not reading.fresh
    assert reading.problem == problem
    assert reading.last_good_read is None
    assert (
        freshness.line(reading) == f"TN (Tennessee): STUCK: {problem}; allowed 7 days"
    )


def test_a_file_that_is_not_json_is_a_failure(fresh_dir):
    path = fresh_dir / "tn.json"
    path.write_text("{not json", encoding="utf-8")
    [reading] = freshness.check(fresh_dir, {"TN": SOURCES["TN"]}, now=NOW)
    assert not reading.fresh
    assert reading.problem is not None
    assert reading.problem.startswith("tn.json is not readable JSON: ")


def test_a_read_stamped_in_the_future_is_a_problem_not_fresh(fresh_dir):
    sources = {"TN": SOURCES["TN"]}
    _write(fresh_dir, "TN", _checks(NOW + dt.timedelta(hours=2)))
    [future] = freshness.check(fresh_dir, sources, now=NOW)
    assert not future.fresh
    assert future.problem == "later than now (2026-11-07 13:40Z)"
    assert future.age_days == 0.0
    # Two runners' clocks may disagree by minutes; that is not a problem.
    _write(fresh_dir, "TN", _checks(NOW + dt.timedelta(minutes=5)))
    [skew] = freshness.check(fresh_dir, sources, now=NOW)
    assert skew.fresh
    assert skew.age_days == 0.0


def test_negative_control_the_same_files_fail_after_one_date_moves_back(
    fresh_dir, capsys
):
    assert _main(fresh_dir) == 0
    capsys.readouterr()
    path = fresh_dir / "mi.json"
    before = path.read_text(encoding="utf-8")
    _set_success(_iso(NOW - dt.timedelta(days=30)))(path)
    assert path.read_text(encoding="utf-8") != before
    assert _main(fresh_dir) == 1
    out = capsys.readouterr().out
    assert (
        "MI (Michigan): STUCK: last good read 2026-10-08 13:40Z (automated), "
        "30.0 days ago, allowed 7 days; older than allowed"
    ) in out


# ---- the job summary


def test_the_job_summary_names_each_state_its_last_good_read_and_the_age(
    fresh_dir, tmp_path, monkeypatch
):
    summary = tmp_path / "summary.md"
    summary.write_text("earlier content\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    _write(fresh_dir, "TN", _checks(TN_LAST_GOOD, ok=False))
    assert _main(fresh_dir) == 1
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("earlier content\n## Freshness watchdog\n")
    assert "1 of 4 live states stuck; checked 2026-11-07 13:40Z." in text
    assert "| State | Last good read | Age | Allowed | Result |" in text
    assert (
        "| TN Tennessee | 2026-10-15 13:31Z (automated) | 23.0 days | 7 days | "
        "STUCK: older than allowed |"
    ) in text
    assert (
        "| MI Michigan | 2026-11-07 09:40Z (automated) | 0.2 days | 7 days | fresh |"
    ) in text


def test_the_summary_flag_wins_over_the_environment_and_no_summary_is_written_otherwise(
    fresh_dir, tmp_path, monkeypatch
):
    from_env = tmp_path / "env.md"
    given = tmp_path / "given.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(from_env))
    assert _main(fresh_dir, "--summary", str(given)) == 0
    assert given.exists()
    assert not from_env.exists()
    monkeypatch.delenv("GITHUB_STEP_SUMMARY")
    assert _main(fresh_dir) == 0
    assert not from_env.exists()


def test_the_summary_says_none_on_record_rather_than_a_blank_or_a_dash(fresh_dir):
    (fresh_dir / "tn.json").unlink()
    readings = freshness.check(fresh_dir, _live_sources(), now=NOW)
    text = freshness.summary_markdown(readings, NOW)
    assert (
        "| TN Tennessee | none on record | none | 7 days | "
        "STUCK: no history file at tn.json |"
    ) in text
    assert "| TN Tennessee |  |" not in text
    assert "| - |" not in text


# ---- the workflow and the Makefile


def _jobs(text: str) -> dict[str, str]:
    """The workflow's jobs by name, each with its full YAML block."""
    body = text[text.index("\njobs:\n") + len("\njobs:") :]
    jobs: dict[str, str] = {}
    for block in re.split(r"\n(?=  [a-z-]+:\n)", body):
        m = re.match(r"\n?  ([a-z-]+):\n", block)
        if m:
            jobs[m.group(1)] = block
    return jobs


@pytest.fixture(scope="module")
def jobs() -> dict[str, str]:
    return _jobs(WORKFLOW.read_text(encoding="utf-8"))


def test_the_publish_workflow_runs_the_watchdog_as_its_own_job_after_the_build(jobs):
    assert list(jobs) == ["build", "deploy", "freshness", "alert-on-failure"]
    job = jobs["freshness"]
    assert "    needs: build\n" in job
    assert "    if: ${{ !cancelled() }}\n" in job
    assert "ref: main" in job
    assert "persist-credentials: false" in job
    assert "run: make freshness" in job
    assert "permissions:\n      contents: read" in job


def test_the_watchdog_blocks_neither_the_data_commit_nor_the_deploy(jobs):
    assert "freshness" not in jobs["build"]
    assert "    needs: build\n" in jobs["deploy"]
    assert "freshness" not in jobs["deploy"]
    needs = re.search(r"needs: \[(.*?)\]", jobs["alert-on-failure"])
    assert needs is not None
    assert [n.strip() for n in needs.group(1).split(",")] == ["build", "deploy"]


def test_the_shape_check_rejects_a_deploy_that_waits_on_the_watchdog():
    text = WORKFLOW.read_text(encoding="utf-8")
    sabotaged = text.replace(
        "  deploy:\n    needs: build\n", "  deploy:\n    needs: [build, freshness]\n"
    )
    assert sabotaged != text
    assert "freshness" in _jobs(sabotaged)["deploy"]


def test_the_watchdog_job_pins_the_same_actions_as_the_build_job(jobs):
    for action in re.findall(r"uses: (\S+@[0-9a-f]{40})", jobs["freshness"]):
        assert action in jobs["build"]
    assert len(re.findall(r"uses: ", jobs["freshness"])) == 2


def test_the_makefile_has_a_freshness_target_that_verify_does_not_run():
    text = MAKEFILE.read_text(encoding="utf-8")
    assert (
        "\nfreshness:\n\tcd $(PIPELINE) && $(UV_RUN) python -m cfpa.freshness\n" in text
    )
    verify = re.search(r"^verify: (.+)$", text, re.MULTILINE)
    assert verify is not None
    assert "freshness" not in verify.group(1).split()
    phony = re.search(r"^\.PHONY: (.+)$", text, re.MULTILINE)
    assert phony is not None
    assert "freshness" in phony.group(1).split()
