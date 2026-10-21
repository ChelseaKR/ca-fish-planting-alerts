"""The unchanged-source warning (cfpa.source_log)."""

import datetime as dt
import json
from pathlib import Path

import pytest

from cfpa import cli, source_log

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
PUBLISH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish.yml"

A = "a" * 64
B = "b" * 64
DAY0 = dt.date(2026, 10, 1)


def _log(*pairs: tuple[int, str]) -> source_log.SourceLog:
    log = source_log.SourceLog(runs=[])
    for offset, sha in pairs:
        log.record(DAY0 + dt.timedelta(days=offset), sha)
    return log


def test_the_threshold_clears_a_normal_week_and_catches_a_missed_rollover():
    # The page's stated week rolls every Sunday, so a normal streak is at most
    # 7 days (8 around the boundary the freshness check tolerates).
    assert 8 < source_log.STALE_SOURCE_DAYS <= 14


def test_a_new_hash_resets_the_count():
    log = _log(*[(i, A) for i in range(9)], (9, B))
    assert log.unchanged_days() == 0


def test_the_count_is_the_span_of_the_newest_unbroken_streak():
    log = _log((0, B), *[(i, A) for i in range(1, 8)])
    assert log.unchanged_days() == 6


def test_an_empty_log_is_zero_days():
    assert _log().unchanged_days() == 0


def test_a_hash_that_comes_back_does_not_join_an_older_streak():
    log = _log((0, A), (1, B), (2, A), (3, A))
    assert log.unchanged_days() == 1


def test_a_second_run_on_one_date_replaces_the_first():
    log = _log((0, A), (0, B))
    assert log.runs == [(DAY0, B)]


def test_the_log_stays_small():
    log = _log(*[(i, A if i % 2 else B) for i in range(source_log.MAX_ENTRIES + 20)])
    assert len(log.runs) == source_log.MAX_ENTRIES


def test_a_normal_week_does_not_warn(capsys):
    days = _log(*[(i, A) for i in range(8)]).unchanged_days()
    assert days == 7
    assert source_log.print_report(days) is False
    captured = capsys.readouterr()
    assert "unchanged for 7 days" in captured.out
    assert "WARNING" not in captured.err


def test_the_threshold_day_warns_on_stderr_and_in_github_actions(capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    days = _log(*[(i, A) for i in range(source_log.STALE_SOURCE_DAYS + 1)])
    assert source_log.print_report(days.unchanged_days()) is True
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert f"unchanged for {source_log.STALE_SOURCE_DAYS} days" in captured.out
    assert "::warning title=CDFW schedule page unchanged::" in captured.out


def test_a_round_trip_through_the_file(tmp_path: Path):
    path = tmp_path / "source_log.json"
    _log((0, A), (1, B)).save(path)
    assert source_log.SourceLog.load(path).runs == [
        (DAY0, A),
        (DAY0 + dt.timedelta(1), B),
    ]
    assert json.loads(path.read_text())["schema"] == source_log.SCHEMA


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"schema": "other", "runs": []}',
        '{"schema": "cfpa-source-log-v1", "runs": [{"date": "2026-10-01", "content_sha256": "xyz"}]}',
    ],
)
def test_a_malformed_file_is_a_source_log_error(tmp_path: Path, text: str):
    path = tmp_path / "source_log.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(source_log.SourceLogError):
        source_log.SourceLog.load(path)


def _run_kwargs(tmp_path: Path, day: dt.date) -> dict:
    # A fixture run on `day`: the fixture's stated week is 2026-09-13, so the
    # freshness check is satisfied through run_today, and fetched_at carries
    # the date the log records.
    return dict(
        fixture_path=str(FRESH),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        species_aliases_path=tmp_path / "species_aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=tmp_path / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime.combine(day, dt.time(12), tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
        source_log_path=tmp_path / "source_log.json",
    )


def test_ten_daily_runs_of_the_same_page_warn_and_still_succeed(tmp_path: Path, capsys):
    for i in range(source_log.STALE_SOURCE_DAYS + 1):
        snap = cli.run(**_run_kwargs(tmp_path, DAY0 + dt.timedelta(days=i)))
        out = capsys.readouterr()
        if i < source_log.STALE_SOURCE_DAYS:
            assert "WARNING CDFW's schedule page" not in out.err
        else:
            assert "WARNING CDFW's schedule page" in out.err
            assert f"unchanged for {i} days" in out.out
    # The run was not refused, and the snapshot contract is untouched.
    assert snap["coverage"]["rows_parsed"] > 0
    assert "source_unchanged_days" not in snap["coverage"]


def test_negative_control_a_changed_page_never_reaches_the_threshold(
    tmp_path: Path, capsys
):
    """Sabotage the page so each day's hash differs and the same ten-run loop
    stays quiet, so the warning above comes from the repeated hash."""
    import hashlib

    from cfpa import fetch as fetch_mod

    real_load = fetch_mod.load_fixture

    for i in range(source_log.STALE_SOURCE_DAYS + 1):
        page = real_load(str(FRESH), fetched_at=None)
        changed = hashlib.sha256(f"{page.content_sha256}-{i}".encode()).hexdigest()
        # The sabotage must have changed the hash, or this proves nothing.
        assert changed != page.content_sha256
        orig = fetch_mod.load_fixture

        def patched(path, *, fetched_at=None, _h=changed, _orig=orig):
            p = _orig(path, fetched_at=fetched_at)
            import dataclasses

            return dataclasses.replace(p, content_sha256=_h)

        fetch_mod.load_fixture = patched
        try:
            cli.run(**_run_kwargs(tmp_path, DAY0 + dt.timedelta(days=i)))
        finally:
            fetch_mod.load_fixture = orig
        out = capsys.readouterr()
        assert "WARNING CDFW's schedule page" not in out.err
        assert "unchanged for 0 days" in out.out


def test_an_unreadable_log_warns_and_does_not_fail_the_run(tmp_path: Path, capsys):
    kwargs = _run_kwargs(tmp_path, DAY0)
    kwargs["source_log_path"].write_text("not json", encoding="utf-8")
    snap = cli.run(**kwargs)
    err = capsys.readouterr().err
    assert snap["coverage"]["rows_parsed"] > 0
    assert "source log could not be updated" in err


def test_a_run_without_a_log_path_touches_no_log(tmp_path: Path):
    kwargs = _run_kwargs(tmp_path, DAY0)
    kwargs["source_log_path"] = None
    cli.run(**kwargs)
    assert not (tmp_path / "source_log.json").exists()


def _add_line(text: str) -> str:
    return next(
        line
        for line in text.splitlines()
        if line.strip().startswith("git add pipeline/")
    )


def test_the_publish_job_carries_the_log_as_an_artifact_and_never_commits_it():
    text = PUBLISH.read_text(encoding="utf-8")
    assert "name: source-log" in text
    assert "actions/upload-artifact@" in text
    assert '--source-log "$RUNNER_TEMP/source-log/source_log.json"' in text
    assert "source_log.json" not in _add_line(text)
    assert "uses: actions/cache" not in text  # CICD-24: no cache in a deploying job


def test_the_negative_control_for_the_workflow_check():
    text = PUBLISH.read_text(encoding="utf-8")
    sabotaged = text.replace(
        "git add pipeline/data/history.json",
        "git add pipeline/data/source_log.json pipeline/data/history.json",
    )
    assert sabotaged != text
    assert "source_log.json" in _add_line(sabotaged)


def test_a_cold_start_says_the_count_restarts(tmp_path: Path, capsys):
    cli.run(**_run_kwargs(tmp_path, DAY0))
    out = capsys.readouterr().out
    assert "source log was empty" in out
    assert "restarts at 0" in out
    cli.run(**_run_kwargs(tmp_path, DAY0 + dt.timedelta(days=1)))
    assert "source log was empty" not in capsys.readouterr().out
