"""Massachusetts while ArcGIS Hub's copy is stale (DECISIONS 0063, 0071).

Measured live on 2026-11-14: Hub still answered ``cacheStatus`` "stale" for
the file it built 2026-10-13 02:35 UTC (150 rows), and its metadata for the
layer said 155 records, last edited 2026-10-13 17:06:39 UTC. From then the
freshness job was red on every run, with nothing new upstream to read.

0071: on a stale answer the reader also reads Hub's metadata (once, after
the Crawl-delay) and the failed check keeps what it said. The freshness job
calls such a state "waiting", not stuck, while the agency's last edit is
older than the allowance too, and the pages say why the read fails in the
words Chelsea approved. Every negative control asserts its sabotage changed
the input before it asserts the outcome.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from cfpa import freshness, site, site_states, snapshot_v2
from cfpa.states import SOURCES, ma
from cfpa.states import run as srun
from cfpa.states.base import (
    USER_AGENT_TEMPLATE,
    FetchedBody,
    StaleCopyError,
    StateFetchError,
    no_sleep,
)
from cfpa.states.store import (
    StateHistory,
    merge,
    record_failure,
    record_unchanged,
    records_in_last_good_read,
)

from .test_display_fixes import BASE, _text, _v1

REPO = Path(__file__).resolve().parents[2]
V2_SCHEMA = REPO / "schema" / "snapshot.v2.json"
STATE_FIXTURES = Path(__file__).parent / "fixtures" / "states"
# pipeline/data/states/ma.json as committed by the run of 2026-11-14 17:25
# UTC (b301f57): a stale-flag failure, written before 0071 existed.
COMMITTED_MA = STATE_FIXTURES / "history-ma-2026-11-14-stale-check.json"
UA = USER_AGENT_TEMPLATE.format(version="0.1.0")
HUB_ROBOTS = "User-agent: *\nCrawl-delay: 60\nDisallow: /sites/\n"
STALE_STATUS = {
    "message": "Download is available at the result url.",
    "status": "Completed",
    "cacheStatus": "stale",
    "resultUrl": (
        "https://hub.arcgis.com/api/v3/datasets/e27aa5ec1ef74659aac1ef12b39510f1_0"
        "/downloads/data?format=csv&spatialRefId=2249&where=1%3D1"
    ),
}
# Hub's answer for /api/v3/datasets/<id>_0 on 2026-11-14 17:31 UTC, cut to
# the attributes this reads plus one it must not (the item's own date).
HUB_METADATA = {
    "data": {
        "id": "e27aa5ec1ef74659aac1ef12b39510f1_0",
        "type": "dataset",
        "attributes": {
            "recordCount": 155,
            "modified": 1791911199165,
            "modifiedProvenance": "layer.editingInfo.lastEditDate",
            "itemModified": 1776176953000,
        },
    }
}
LAYER_EDIT = dt.datetime(2026, 10, 13, 17, 6, 39, tzinfo=dt.UTC)  # to the second
ATTEMPT = dt.datetime(2026, 11, 14, 17, 25, 22, tzinfo=dt.UTC)
NOW = dt.datetime(2026, 11, 14, 17, 30, tzinfo=dt.UTC)
GENERATED = ATTEMPT
APPROVED = (
    "MassWildlife last changed its stocking report on Tue, 13 Oct 2026. The copy "
    "Trout Truck can read is older than that change and has 150 of the report's "
    "155 entries, so some stockings may be missing here. ArcGIS Hub, the service "
    "it is read through, has not rebuilt that copy since."
)
WAITING_LINE = (
    "MA (Massachusetts): waiting: last good read 2026-11-07 13:22Z (automated), "
    "7.2 days ago, allowed 7 days; Hub's file is stale, and MassWildlife has not "
    "edited its layer since 2026-10-13 17:06Z (32.0 days ago); red again as soon "
    "as it does"
)


def _mock_hub(metadata: httpx.Response) -> dict[str, respx.Route]:
    respx.get("https://hub.arcgis.com/robots.txt").respond(
        200, text=HUB_ROBOTS, headers={"content-type": "text/plain"}
    )
    return {
        "status": respx.get(url__startswith=ma.DOWNLOAD_URL).respond(
            200, json=STALE_STATUS
        ),
        "metadata": respx.get(ma.METADATA_URL).mock(return_value=metadata),
        "csv": respx.get(url__startswith=STALE_STATUS["resultUrl"].split("?")[0]),
        "layer_host": respx.get(url__startswith="https://services1.arcgis.com/"),
    }


# ---- the reader


@respx.mock
def test_a_stale_answer_reads_hubs_metadata_once_after_the_crawl_delay():
    routes = _mock_hub(httpx.Response(200, json=HUB_METADATA))
    slept: list[float] = []
    with httpx.Client() as client, pytest.raises(StaleCopyError) as caught:
        ma.fetch(client, UA, slept.append)
    err = caught.value
    assert isinstance(err, StateFetchError)  # still a failed check
    assert err.source_last_edit_at == LAYER_EDIT
    assert err.source_record_count == 155
    assert "stale" in str(err)
    assert "last edited 2026-10-13 17:06 UTC, with 155 records" in str(err)
    assert routes["status"].call_count == 1
    assert routes["metadata"].call_count == 1
    sent = routes["metadata"].calls.last.request.headers["user-agent"]
    assert sent == UA
    assert slept == [61.0]  # the Crawl-delay, plus a second, before it
    assert not routes["csv"].called  # the stale file is still never read
    assert not routes["layer_host"].called


def _attrs(**changes: Any) -> dict[str, Any]:
    doc = copy.deepcopy(HUB_METADATA)
    doc["data"]["attributes"].update(changes)
    return doc


@pytest.mark.parametrize(
    ("response", "edited", "count"),
    [
        (httpx.Response(500, text="oops"), None, None),
        (httpx.Response(200, text="<html>not json</html>"), None, None),
        (httpx.Response(200, json={"data": {}}), None, None),
        # The item's date is not the layer's edit: never used in its place.
        (
            httpx.Response(200, json=_attrs(modifiedProvenance="item.modified")),
            None,
            155,
        ),
        (httpx.Response(200, json=_attrs(modified="yesterday")), None, 155),
        (httpx.Response(200, json=_attrs(recordCount=-1)), LAYER_EDIT, None),
        (httpx.Response(200, json=_attrs(recordCount=True)), LAYER_EDIT, None),
    ],
    ids=[
        "http-500",
        "not-json",
        "no-attributes",
        "item-date",
        "bad-millis",
        "negative-count",
        "bool-count",
    ],
)
@respx.mock
def test_what_hub_s_metadata_does_not_say_is_unknown_never_a_guess(
    response, edited, count
):
    _mock_hub(response)
    with httpx.Client() as client, pytest.raises(StaleCopyError) as caught:
        ma.fetch(client, UA, no_sleep)
    assert caught.value.source_last_edit_at == edited
    assert caught.value.source_record_count == count
    if edited is None:
        assert "last edited (unknown)" in str(caught.value)


# ---- the history file


def _states_dir(tmp_path: Path) -> Path:
    states = tmp_path / "states"
    states.mkdir()
    shutil.copy(COMMITTED_MA, states / "ma.json")
    return states


@respx.mock
def _stale_run(tmp_path: Path, metadata: httpx.Response) -> tuple[Path, StateHistory]:
    states = _states_dir(tmp_path)
    _mock_hub(metadata)
    with httpx.Client() as client:
        runs = srun.run_states(
            states_dir=states,
            fetch_codes=["MA"],
            user_agent=UA,
            now=ATTEMPT,
            client=client,
            sleep=no_sleep,
        )
    srun.write(runs)
    run = next(r for r in runs if r.source.code == "MA")
    assert run.outcome == "failed"
    return states, run.history


def test_the_failed_check_keeps_what_hub_said_with_that_attempt(tmp_path: Path):
    before = json.loads(COMMITTED_MA.read_text("utf-8"))
    states, history = _stale_run(tmp_path, httpx.Response(200, json=HUB_METADATA))
    saved = json.loads((states / "ma.json").read_text("utf-8"))
    assert saved["records"] == before["records"]  # no data changed
    checks = saved["checks"]
    assert checks["last_attempt_ok"] is False
    assert checks["last_success_at"] == "2026-11-07T13:22:11Z"
    assert checks["last_attempt_at"] == "2026-11-14T17:25:22Z"
    assert checks["stale_copy"] == {
        "checked_at": "2026-11-14T17:25:22Z",
        "source_last_edit_at": "2026-10-13T17:06:39Z",
        "source_record_count": 155,
        "copy_record_count": 150,
    }
    # It reads back as it was written.
    again = StateHistory.load(states / "ma.json", "MA")
    assert again.checks.stale_copy == history.checks.stale_copy


def test_an_unreadable_metadata_answer_is_kept_as_unknown(tmp_path: Path):
    states, _ = _stale_run(tmp_path, httpx.Response(503))
    stale = json.loads((states / "ma.json").read_text("utf-8"))["checks"]["stale_copy"]
    assert stale["source_last_edit_at"] is None
    assert stale["source_record_count"] is None
    assert stale["copy_record_count"] == 150


def test_copy_record_count_is_what_the_last_good_read_saw():
    history = StateHistory.load(COMMITTED_MA, "MA")
    assert records_in_last_good_read(history) == 150
    # Negative control: one record seen only on an earlier read is not counted.
    older = dataclasses.replace(
        history.records[0],
        last_observed_at=history.records[0].first_observed_at,
    )
    assert older.last_observed_at != history.checks.last_success_at
    fewer = dataclasses.replace(history, records=[older, *history.records[1:]])
    assert records_in_last_good_read(fewer) == 149


def _with_stale(history: StateHistory) -> StateHistory:
    return record_failure(
        history,
        attempted_at=ATTEMPT,
        error="stale",
        source_last_edit_at=LAYER_EDIT,
        source_record_count=155,
        stale_copy=True,
    )


def test_any_other_outcome_clears_the_stale_copy():
    stale = _with_stale(StateHistory.load(COMMITTED_MA, "MA"))
    assert stale.checks.stale_copy is not None
    later = ATTEMPT + dt.timedelta(hours=12)
    other_failure = record_failure(stale, attempted_at=later, error="robots 503")
    assert other_failure.checks.stale_copy is None
    assert record_unchanged(stale, checked_at=later).checks.stale_copy is None
    feed = ma.parse(
        [
            FetchedBody(
                url="file://ma.csv",
                text=(STATE_FIXTURES / "ma.csv").read_text("utf-8"),
                fetched_at=later,
                last_modified=None,
            )
        ]
    )
    good = merge(stale, feed, ma.SOURCE, as_of=later.date())
    assert good.checks.stale_copy is None
    assert "stale_copy" not in good.checks.to_json()


# ---- the snapshot and the pages


@pytest.fixture(scope="module")
def stale_site(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    tmp = tmp_path_factory.mktemp("ma-stale")
    history = _with_stale(StateHistory.load(COMMITTED_MA, "MA"))
    v1 = _v1(tmp)
    v2 = snapshot_v2.build_snapshot_v2(
        v1, [(SOURCES["MA"], history)], generated_at=GENERATED
    )
    snapshot_v2.validate_snapshot_v2(v2, V2_SCHEMA)
    out = tmp / "site"
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    return out, v2


def _ma(v2: dict) -> dict:
    return next(s for s in v2["states"] if s["code"] == "MA")


def _a_water_page(out: Path) -> str:
    page = sorted((out / "ma" / "water").glob("*/index.html"))[0]
    return _text(page.read_text("utf-8"))


def test_the_snapshot_carries_hubs_facts_and_validates(stale_site):
    _, v2 = stale_site
    checks = _ma(v2)["checks"]
    assert checks["last_attempt_ok"] is False
    assert checks["stale_copy"] == {
        "source_last_edit_at": "2026-10-13T17:06:39Z",
        "source_record_count": 155,
        "copy_record_count": 150,
    }


def test_the_hub_and_water_pages_say_why_in_the_approved_words(stale_site):
    out, _ = stale_site
    hub = _text((out / "ma" / "index.html").read_text("utf-8"))
    water = _a_water_page(out)
    for text in (hub, water):
        assert APPROVED in text
        assert "The check on" not in text
    # Hub's file time is no longer called MassWildlife's change.
    assert "last changed the file" not in hub
    assert "MassWildlife's data was last read 2026-11-07 13:22 UTC." in hub


def test_negative_control_without_the_facts_the_pages_keep_the_plain_line(
    tmp_path: Path,
):
    history = StateHistory.load(COMMITTED_MA, "MA")
    assert history.checks.stale_copy is None  # the file as written before 0071
    v1 = _v1(tmp_path)
    v2 = snapshot_v2.build_snapshot_v2(
        v1, [(SOURCES["MA"], history)], generated_at=GENERATED
    )
    assert "stale_copy" not in _ma(v2)["checks"]
    out = tmp_path / "site"
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    hub = _text((out / "ma" / "index.html").read_text("utf-8"))
    assert "MassWildlife last changed its stocking report" not in hub
    assert "The check on 2026-11-14 17:25 UTC failed" in hub
    assert "MassWildlife last changed the file Tue, 13 Oct 2026" in hub


def _state(**stale: Any) -> dict[str, Any]:
    facts = {
        "source_last_edit_at": "2026-10-13T17:06:39Z",
        "source_record_count": 155,
        "copy_record_count": 150,
    }
    facts.update(stale)
    return {
        "code": "MA",
        "agency": {"short_name": "MassWildlife"},
        "checks": {"last_attempt_ok": False, "stale_copy": facts},
    }


def test_the_sentence_is_the_approved_one_when_every_number_was_measured():
    assert site_states.stale_copy_sentence(_state()) == APPROVED


@pytest.mark.parametrize(
    "change",
    [
        {"source_last_edit_at": None},
        {"source_record_count": None},
        {"copy_record_count": 155},  # not fewer: "missing" would be untrue
        {"copy_record_count": 160},
    ],
    ids=["edit-unknown", "count-unknown", "same-count", "more-in-copy"],
)
def test_no_sentence_unless_it_would_be_true(change):
    assert site_states.stale_copy_sentence(_state(**change)) == ""


def test_no_sentence_once_a_check_succeeds():
    state = _state()
    state["checks"]["last_attempt_ok"] = True
    assert site_states.stale_copy_sentence(state) == ""


# ---- the freshness watchdog


def _checks(**changes: Any) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "last_attempt_at": "2026-11-14T17:25:22Z",
        "last_success_at": "2026-11-07T13:22:11Z",
        "last_attempt_ok": False,
        "last_error": "Hub marked its copy of MassWildlife's layer stale",
        "content_sha256": "0" * 64,
        "last_modified": "Tue, 13 Oct 2026 02:35:42 GMT",
        "stale_copy": {
            "checked_at": "2026-11-14T17:25:22Z",
            "source_last_edit_at": "2026-10-13T17:06:39Z",
            "source_record_count": 155,
            "copy_record_count": 150,
        },
    }
    checks.update(changes)
    return checks


def _write(states_dir: Path, checks: dict[str, Any]) -> Path:
    path = states_dir / "ma.json"
    doc = {
        "schema": "cfpa-state-history-v1",
        "state": "MA",
        "checks": checks,
        "waters": [],
        "aliases": {},
        "records": [],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def ma_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    states = tmp_path / "states"
    states.mkdir()
    _write(states, _checks())
    return states


def _run(states_dir: Path, *extra: str) -> int:
    return freshness.main(
        [
            "--states-dir",
            str(states_dir),
            "--states",
            "MA",
            "--now",
            "2026-11-14T17:30:00Z",
            *extra,
        ]
    )


def test_massachusetts_as_measured_on_2026_11_14_is_waiting_and_the_job_passes(
    ma_dir, capsys, monkeypatch
):
    """Fails on the code before 0071: this exact file was red."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert _run(ma_dir) == 0
    out = capsys.readouterr().out
    assert WAITING_LINE in out
    assert f"::warning title=Massachusetts is waiting::{WAITING_LINE}" in out
    assert "::error" not in out
    assert (
        "freshness: no live state stuck (0 fresh, 1 waiting); checked 2026-11-14 17:30Z"
        in out
    )


def test_the_runs_own_history_file_reads_as_waiting(tmp_path: Path):
    """End to end: the reader's failed check, as written, is what the
    watchdog reads."""
    states, _ = _stale_run(tmp_path, httpx.Response(200, json=HUB_METADATA))
    [reading] = freshness.check(states, {"MA": SOURCES["MA"]}, now=NOW)
    assert reading.fresh and reading.status == "waiting"
    assert freshness.line(reading) == WAITING_LINE


def test_the_summary_says_waiting_and_why(ma_dir, tmp_path):
    summary = tmp_path / "summary.md"
    assert _run(ma_dir, "--summary", str(summary)) == 0
    text = summary.read_text("utf-8")
    assert (
        "No live state stuck (0 fresh, 1 waiting); checked 2026-11-14 17:30Z." in text
    )
    assert (
        "| MA Massachusetts | 2026-11-07 13:22Z (automated) | 7.2 days | 7 days | "
        "waiting: Hub's file is stale, and MassWildlife has not edited its layer "
        "since 2026-10-13 17:06Z (32.0 days ago); red again as soon as it does |"
    ) in text


def _stale(**changes: Any) -> Callable[[dict], None]:
    def mutate(checks: dict) -> None:
        checks["stale_copy"].update(changes)

    return mutate


def _top(**changes: Any) -> Callable[[dict], None]:
    def mutate(checks: dict) -> None:
        checks.update(changes)

    return mutate


@pytest.mark.parametrize(
    ("sabotage", "problem"),
    [
        (
            _stale(source_last_edit_at=None),
            "older than allowed; Hub's file is stale and MassWildlife's last edit "
            "to its layer could not be read",
        ),
        (
            _stale(source_last_edit_at="not a time"),
            "older than allowed; Hub's file is stale and MassWildlife's last edit "
            "to its layer could not be read",
        ),
        (
            # MassWildlife edited again: new data we cannot read.
            _stale(source_last_edit_at="2026-11-12T15:00:00Z"),
            "older than allowed; Hub's file is stale and MassWildlife edited its "
            "layer 2026-11-12 15:00Z, 2.1 days ago",
        ),
        # Facts from an earlier attempt say nothing about this one.
        (_stale(checked_at="2026-11-14T05:25:22Z"), "older than allowed"),
        # The latest attempt did not fail on the stale flag.
        (_top(last_attempt_ok=True), "older than allowed"),
        (_top(stale_copy=None), "older than allowed"),
    ],
    ids=[
        "edit-unknown",
        "edit-unparseable",
        "edited-within-allowance",
        "facts-from-an-earlier-attempt",
        "attempt-ok",
        "no-stale-copy",
    ],
)
def test_negative_controls_each_is_stuck_and_red(ma_dir, sabotage, problem):
    path = ma_dir / "ma.json"
    doc = json.loads(path.read_text("utf-8"))
    before = copy.deepcopy(doc["checks"])
    sabotage(doc["checks"])
    assert doc["checks"] != before  # the sabotage landed
    _write(ma_dir, doc["checks"])
    [reading] = freshness.check(ma_dir, {"MA": SOURCES["MA"]}, now=NOW)
    assert not reading.fresh and reading.status == "STUCK"
    assert reading.waiting is None
    assert reading.problem == problem
    assert _run(ma_dir) == 1


def test_waiting_never_rescues_a_state_that_is_not_old(ma_dir):
    """Inside the allowance the state is plainly fresh: waiting is only an
    answer to "older than allowed"."""
    _write(ma_dir, _checks(last_success_at="2026-11-12T13:22:11Z"))
    [reading] = freshness.check(ma_dir, {"MA": SOURCES["MA"]}, now=NOW)
    assert reading.status == "fresh"
