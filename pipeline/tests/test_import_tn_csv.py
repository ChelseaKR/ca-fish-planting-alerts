"""Tennessee by hand: TWRA's downloadable CSV (DECISIONS 0061).

The fixture ``tn-twra-download-sample.csv`` is 12 real rows of the file
Chelsea downloaded from TWRA's page on 2026-11-07 (header, quoting and the
trailing blank line as TWRA writes them): exact days, "TBD" months in both
date columns, week-of Sundays, a month-letters-only tailwater, and TWRA's
spelling "Caroll". (The real file's four non-Sunday "week of" rows are
skipped by the reader's own share cap, which a 12-row file cannot show.)
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import html
import json
import os
import shutil
from pathlib import Path

import pytest

from cfpa import import_tn_csv, site, snapshot_v2
from cfpa.import_tn_csv import ImportRefused, import_csv, read_rows
from cfpa.states import SOURCES, tn
from cfpa.states.base import FetchedBody
from cfpa.states.run import run_states
from cfpa.states.store import StateHistory, merge, record_unchanged

from .test_display_fixes import BASE, COMMITTED_TN, _description, _text, _v1

SAMPLE = Path(__file__).parent / "fixtures" / "states" / "tn-twra-download-sample.csv"
HEADER = '"REGION","COUNTY","LOCATION","TYPE","STOCKING DAY","STOCKING WEEK","STOCKING MONTHS","SPECIES"'
DOWNLOADED = dt.datetime(2026, 11, 7, 19, 23, 44, tzinfo=dt.UTC)  # 11:23 PT
IMPORTED = dt.datetime(2026, 11, 7, 20, 0, tzinfo=dt.UTC)
# The next morning's scheduled run, which tn.gov still refuses.
NEXT_RUN = dt.datetime(2026, 11, 8, 13, 21, tzinfo=dt.UTC)
DOE = "tn/water/doe-river-carter-county/index.html"
# In the 2026-10-21 history, not in the sample: its last date is past, so
# the imported file has nothing later for it.
STONY = "tn/water/stony-creek-carter-county/index.html"


def _states_dir(tmp_path: Path) -> Path:
    d = tmp_path / "states"
    d.mkdir()
    shutil.copy(COMMITTED_TN, d / "tn.json")
    return d


def _import(states: Path, csv_path: Path = SAMPLE) -> StateHistory:
    result = import_csv(
        csv_path,
        states_dir=states,
        downloaded_at=DOWNLOADED,
        now=IMPORTED,
        min_rows=5,
    )
    result.history.save(result.path)
    return StateHistory.load(states / "tn.json", "TN")


# ---- reading the file


def test_the_sample_reads_like_the_reader_reads_twras_json():
    """The CSV's rows go through the JSON reader's own parse_rows, and give
    exactly what the same rows give as the JSON the page loads."""
    rows = read_rows(SAMPLE.read_bytes())
    assert len(rows) == 12
    from_csv = tn.parse_rows(
        rows, fetched_at=DOWNLOADED, content_sha256="0" * 64, last_modified=None
    )
    body = FetchedBody(
        url="file://tn.json",
        text=json.dumps({"data": rows}),
        fetched_at=DOWNLOADED,
        last_modified=None,
    )
    from_json = tn.parse([body])
    assert from_csv.records == from_json.records
    assert from_csv.waters == from_json.waters
    assert from_csv.skipped == from_json.skipped == 0
    labels = {(r.water_id, r.period.label) for r in from_csv.records}
    assert ("tn-caroll-mckenzie-city-park", "2026-12-09") in labels
    assert ("tn-caroll-mckenzie-city-park", "December 2027") in labels  # TBD day
    assert (
        "tn-dickson-acorn-lake-montgomery-bell-sp",
        "December 2027",
    ) in labels  # TBD in the week column is a month, never a week
    assert ("tn-carter-doe-river", "week of 2027-02-28") in labels
    normandy = from_csv.waters["tn-coffee-bedford-normandy-tw-duck-river"]
    assert normandy.months_note == "J, F, M, A, N, D"  # verbatim, no dates
    assert len(from_csv.records) == 11


def _with_header(header: str) -> bytes:
    body = SAMPLE.read_text("utf-8").split("\n", 1)[1]
    return (header + "\n" + body).encode("utf-8")


@pytest.mark.parametrize(
    "drifted",
    [
        HEADER.replace("STOCKING DAY", "STOCKING DATE"),
        HEADER.replace('"REGION","COUNTY"', '"COUNTY","REGION"'),
        HEADER + ',"NOTES"',
        HEADER.replace(',"TYPE"', ""),
        HEADER.lower(),
    ],
    ids=["renamed", "reordered", "extra", "missing", "lowercase"],
)
def test_negative_control_a_drifted_header_is_refused(drifted: str):
    assert drifted != HEADER  # the drift applied
    with pytest.raises(ImportRefused, match="header"):
        read_rows(_with_header(drifted))


def test_the_unchanged_header_passes_the_same_check():
    """The control for the drift test: the same rebuild with TWRA's header."""
    assert len(read_rows(_with_header(HEADER))) == 12


def test_a_byte_order_mark_is_not_drift():
    assert len(read_rows(b"\xef\xbb\xbf" + SAMPLE.read_bytes())) == 12


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (
            HEADER + '\n"1","Caroll","McKenzie City Park","Winter","12/9/2026",""\n',
            "fields",
        ),
        (
            HEADER
            + '\n\n"1","Caroll","McKenzie City Park","Winter","12/9/2026","","","Rainbow Trout"\n',
            "fields",
        ),
        ("", "empty"),
        ("\n\n", "empty"),
    ],
    ids=["short-row", "interior-blank", "empty", "blank-only"],
)
def test_malformed_files_are_refused(data: str, match: str):
    with pytest.raises(ImportRefused, match=match):
        read_rows(data.encode("utf-8"))


def test_a_file_that_is_not_utf8_is_refused():
    with pytest.raises(ImportRefused, match="UTF-8"):
        read_rows(b"\xff\xfe" + "x".encode("utf-16-le"))


def test_a_file_too_small_to_be_the_schedule_is_refused(tmp_path: Path):
    """The real floor (tn.SOURCE.min_rows): a truncated download is never
    read as "nothing scheduled"."""
    states = _states_dir(tmp_path)
    with pytest.raises(ImportRefused, match="fewer than 100"):
        import_csv(SAMPLE, states_dir=states, downloaded_at=DOWNLOADED, now=IMPORTED)


# ---- provenance


def test_import_writes_the_files_provenance_and_keeps_the_automated_check(
    tmp_path: Path,
):
    before = StateHistory.load(COMMITTED_TN, "TN")
    h = _import(_states_dir(tmp_path))
    c = h.checks
    assert c.read_method == "manual"
    assert c.manual_file is not None
    assert c.manual_file.source == "TWRA's downloadable CSV"
    assert c.manual_file.source_url == tn.PAGE_URL
    assert c.manual_file.file_name == SAMPLE.name
    assert c.manual_file.rows == 12
    assert c.manual_file.downloaded_at == DOWNLOADED
    assert c.manual_file.imported_at == IMPORTED
    assert c.last_success_at == DOWNLOADED
    # The automated read's own fields are untouched: the import is not a
    # check of tn.gov.
    assert c.last_attempt_at == before.checks.last_attempt_at
    assert c.last_attempt_ok is False
    assert c.last_error == before.checks.last_error
    # The last automated file's validators do not describe this file.
    assert c.last_modified is None and c.etag is None
    by_key = {r.key(): r for r in h.records}
    doe = by_key[("tn-carter-doe-river", "2027-02-28", "week", "Rainbow Trout")]
    assert doe.status == "listed" and doe.first_observed_at == DOWNLOADED
    # Caroll's "TBD 12/2026" became 12/9/2026: the month reads removed.
    month = by_key[
        ("tn-caroll-mckenzie-city-park", "2026-12-01", "month", "Rainbow Trout")
    ]
    assert month.status == "removed"
    # Nothing on file was dropped (save() asserts it too).
    assert {r.key() for r in before.records} <= set(by_key)


def test_a_later_failed_automated_run_keeps_the_import_and_its_label(tmp_path: Path):
    states = _states_dir(tmp_path)
    imported = _import(states)
    empty = tmp_path / "no-fixtures"
    empty.mkdir()
    runs = run_states(
        states_dir=states,
        fetch_codes=["TN"],
        user_agent="test",
        now=NEXT_RUN,
        fixtures_dir=empty,  # no TN body: the fetch fails, as tn.gov's 403 does
    )
    tn_run = next(r for r in runs if r.source.code == "TN")
    assert tn_run.outcome == "failed"
    tn_run.history.save(tn_run.path)
    after = StateHistory.load(states / "tn.json", "TN")
    assert after.records == imported.records
    assert after.checks.manual_file == imported.checks.manual_file
    assert after.checks.last_success_at == DOWNLOADED
    assert after.checks.last_attempt_at == NEXT_RUN
    assert after.checks.last_attempt_ok is False


def test_a_later_good_automated_read_clears_the_manual_label(tmp_path: Path):
    imported = _import(_states_dir(tmp_path))
    rows = read_rows(SAMPLE.read_bytes())
    feed = tn.parse_rows(
        rows, fetched_at=NEXT_RUN, content_sha256="1" * 64, last_modified=None
    )
    merged = merge(imported, feed, tn.SOURCE, as_of=NEXT_RUN.date())
    assert merged.checks.manual_file is None
    assert merged.checks.read_method == "automated"
    assert merged.checks.last_success_at == NEXT_RUN


def test_an_older_or_repeated_file_is_refused(tmp_path: Path):
    states = _states_dir(tmp_path)
    with pytest.raises(ImportRefused, match="not after"):
        import_csv(
            SAMPLE,
            states_dir=states,
            downloaded_at=dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
            now=IMPORTED,
            min_rows=5,
        )
    _import(states)
    with pytest.raises(ImportRefused, match="already loaded"):
        import_csv(
            SAMPLE,
            states_dir=states,
            downloaded_at=DOWNLOADED + dt.timedelta(days=1),
            now=IMPORTED + dt.timedelta(days=1),
            min_rows=5,
        )


def test_a_download_time_in_the_future_is_refused(tmp_path: Path):
    with pytest.raises(ImportRefused, match="future"):
        import_csv(
            SAMPLE,
            states_dir=_states_dir(tmp_path),
            downloaded_at=IMPORTED + dt.timedelta(hours=1),
            now=IMPORTED,
            min_rows=5,
        )


def test_a_missing_states_dir_is_refused(tmp_path: Path):
    with pytest.raises(ImportRefused, match="does not exist"):
        import_csv(
            SAMPLE,
            states_dir=tmp_path,
            downloaded_at=DOWNLOADED,
            now=IMPORTED,
            min_rows=5,
        )


def test_downloaded_at_forms(tmp_path: Path):
    parse = import_tn_csv.parse_downloaded_at
    assert parse("2026-11-07T11:23:44-08:00", SAMPLE) == DOWNLOADED
    assert parse("2026-11-07T19:23:44Z", SAMPLE) == DOWNLOADED
    # A date alone: noon in Tennessee (Central time).
    assert parse("2026-11-07", SAMPLE) == dt.datetime(2026, 11, 7, 18, tzinfo=dt.UTC)
    with pytest.raises(ImportRefused, match="offset"):
        parse("2026-11-07T11:23", SAMPLE)
    with pytest.raises(ImportRefused, match="not a date"):
        parse("yesterday", SAMPLE)
    f = tmp_path / "x.csv"
    f.write_text("x")
    stamp = DOWNLOADED.timestamp()
    os.utime(f, (stamp, stamp))
    assert parse(None, f) == DOWNLOADED


def test_cli_writes_on_success_and_nothing_on_drift(tmp_path: Path, capsys):
    states = _states_dir(tmp_path)
    original = (states / "tn.json").read_bytes()
    drifted = tmp_path / "drifted.csv"
    drifted.write_bytes(_with_header(HEADER.replace("SPECIES", "FISH")))
    code = import_tn_csv.main(
        [str(drifted), "--states-dir", str(states), "--downloaded-at", "2026-11-07"]
    )
    assert code == 1
    assert "refused, nothing written" in capsys.readouterr().err
    assert (states / "tn.json").read_bytes() == original
    # The real floor refuses the 12-row sample too, through the CLI.
    assert (
        import_tn_csv.main(
            [str(SAMPLE), "--states-dir", str(states), "--downloaded-at", "2026-11-07"]
        )
        == 1
    )
    assert (states / "tn.json").read_bytes() == original


def test_cli_success_path(tmp_path: Path, capsys, monkeypatch):
    states = _states_dir(tmp_path)
    real = import_tn_csv.import_csv

    def small_floor(
        path: Path,
        *,
        states_dir: Path,
        downloaded_at: dt.datetime,
        now: dt.datetime,
        min_rows: int | None = None,
    ) -> import_tn_csv.ImportResult:
        return real(
            path,
            states_dir=states_dir,
            downloaded_at=downloaded_at,
            now=now,
            min_rows=5,
        )

    monkeypatch.setattr(import_tn_csv, "import_csv", small_floor)
    code = import_tn_csv.main(
        [
            str(SAMPLE),
            "--states-dir",
            str(states),
            "--downloaded-at",
            "2026-11-07T11:23:44-08:00",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "12 rows, 11 records, 6 waters, " in out
    assert "downloaded 2026-11-07" in out
    saved = json.loads((states / "tn.json").read_text("utf-8"))
    assert saved["checks"]["read_method"] == "manual"
    assert saved["checks"]["manual_file"]["downloaded_at"] == "2026-11-07T19:23:44Z"


# ---- what the site says


def _site(tmp_path: Path, history: StateHistory) -> tuple[Path, dict]:
    v1 = _v1(tmp_path)
    v2 = snapshot_v2.build_snapshot_v2(
        v1, [(SOURCES["TN"], history)], generated_at=NEXT_RUN
    )
    out = tmp_path / "site"
    site.build_site(v1, out, base_url=BASE, snapshot_v2=v2)
    return out, v2


def _after_failed_run(tmp_path: Path) -> StateHistory:
    states = _states_dir(tmp_path)
    _import(states)
    empty = tmp_path / "no-fixtures"
    empty.mkdir()
    runs = run_states(
        states_dir=states,
        fetch_codes=["TN"],
        user_agent="test",
        now=NEXT_RUN,
        fixtures_dir=empty,
    )
    return next(r for r in runs if r.source.code == "TN").history


MANUAL = "This data is from TWRA's published schedule file, downloaded 2026-11-07."


def test_pages_name_the_downloaded_file_and_its_date_not_failed_checks(
    tmp_path: Path,
):
    history = _after_failed_run(tmp_path)
    assert history.checks.last_attempt_ok is False  # the background run failed
    out, v2 = _site(tmp_path, history)
    state = next(s for s in v2["states"] if s["code"] == "TN")
    assert state["source"]["read_method"] == "manual"
    assert state["source"]["fetched_at"] == "2026-11-07T19:23:44Z"
    assert state["as_of"] == "2026-11-07"
    assert state["checks"]["last_attempt_ok"] is False  # the snapshot stays true

    doe_html = (out / DOE).read_text("utf-8")
    doe = _text(doe_html)
    assert "Next scheduled: week of 2027-02-28" in doe
    assert MANUAL in doe
    assert "automatic daily read of TWRA's website is not working" in doe
    assert "failed" not in doe
    assert "next scheduled week of 2027-02-28." in _description(doe_html)

    stale_html = (out / STONY).read_text("utf-8")
    stale = _text(stale_html)
    assert (
        "Nothing later was on TWRA's published schedule file, downloaded 2026-11-07."
        in stale
    )
    assert "schedule right now" not in stale
    assert "failed" not in stale
    desc = html.unescape(_description(stale_html))
    assert "in TWRA's schedule file downloaded 2026-11-07." in desc
    assert "nothing later listed" not in desc and "failed" not in desc

    hub = _text((out / "tn" / "index.html").read_text("utf-8"))
    assert MANUAL in hub
    assert "The latest check failed" not in hub
    assert "The check on" not in hub


def test_negative_control_the_same_history_without_the_label_says_checks_failed(
    tmp_path: Path,
):
    """Strip only manual_file: the pages fall back to the failed-check
    wording, so the test above is about the provenance, not the dates."""
    history = _after_failed_run(tmp_path)
    plain = dataclasses.replace(
        history, checks=dataclasses.replace(history.checks, manual_file=None)
    )
    assert plain.checks.read_method == "automated"  # the stripping landed
    out, v2 = _site(tmp_path, plain)
    assert (
        next(s for s in v2["states"] if s["code"] == "TN")["source"]["read_method"]
        == "automated"
    )
    stale = _text((out / STONY).read_text("utf-8"))
    assert MANUAL not in stale
    assert "The checks since then failed" in stale
    assert "The check on 2026-11-08 13:21 UTC failed" in stale


def test_a_304_after_an_import_never_moves_the_imported_datas_date(tmp_path: Path):
    """The import clears the validators, so a 304 should not come; if one
    does, it is about the old automated file, and the data keeps its
    download date and label."""
    imported = _import(_states_dir(tmp_path))
    after = record_unchanged(imported, checked_at=NEXT_RUN)
    assert after.checks.last_success_at == DOWNLOADED
    assert after.checks.manual_file == imported.checks.manual_file
    assert after.checks.last_attempt_at == NEXT_RUN
    assert after.checks.last_attempt_ok is True
