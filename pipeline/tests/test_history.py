import datetime as dt
from pathlib import Path

import pytest

from cfpa import history


def _rec(stock_id=1116, week_start="2026-09-13", status="listed", species="Trout",
         first="2026-09-13T12:00:00Z", last="2026-09-13T12:00:00Z"):
    ws = dt.date.fromisoformat(week_start)
    return history.PlantRecord(
        cdfw_stock_id=stock_id,
        week_start=ws,
        week_end=ws + dt.timedelta(days=6),
        species=species,
        status=status,
        first_observed_at=dt.datetime.fromisoformat(first.replace("Z", "+00:00")),
        last_observed_at=dt.datetime.fromisoformat(last.replace("Z", "+00:00")),
    )


def test_append_only_allows_pure_additions():
    old = [_rec()]
    new = [_rec(), _rec(week_start="2026-09-20")]
    history.assert_append_only(old, new)  # must not raise


def test_append_only_allows_status_transition_to_removed():
    old = [_rec(status="listed")]
    new = [_rec(status="removed", last="2026-09-14T00:00:00Z")]
    history.assert_append_only(old, new)  # must not raise


def test_append_only_rejects_a_dropped_record():
    old = [_rec(stock_id=1), _rec(stock_id=2)]
    new = [_rec(stock_id=1)]  # record for stock_id=2 silently dropped
    with pytest.raises(history.HistoryIntegrityError, match="missing from the new write"):
        history.assert_append_only(old, new)


def test_append_only_rejects_a_mutated_immutable_field():
    old = [_rec(stock_id=1, first="2026-09-13T12:00:00Z")]
    new = [_rec(stock_id=1, first="2020-01-01T00:00:00Z")]  # provenance rewritten
    with pytest.raises(history.HistoryIntegrityError, match="changed an immutable field"):
        history.assert_append_only(old, new)


def test_store_save_refuses_to_shrink_the_file_on_disk(tmp_path: Path):
    path = tmp_path / "history.json"
    history.HistoryStore(records=[_rec(stock_id=1), _rec(stock_id=2)]).save(path)
    before = path.read_bytes()

    shrunk = history.HistoryStore(records=[_rec(stock_id=1)])
    with pytest.raises(history.HistoryIntegrityError):
        shrunk.save(path)

    # the file on disk must be untouched by the failed write
    assert path.read_bytes() == before


def test_store_save_load_round_trip(tmp_path: Path):
    path = tmp_path / "history.json"
    recs = [_rec(stock_id=1), _rec(stock_id=2, week_start="2026-09-20")]
    history.HistoryStore(records=recs).save(path)
    loaded = history.HistoryStore.load(path)
    assert len(loaded.records) == 2
    assert {r.key() for r in loaded.records} == {r.key() for r in recs}


def test_merge_observations_marks_a_dropped_listed_plant_as_removed():
    existing = [_rec(stock_id=1, week_start="2026-09-13", status="listed")]
    merged = history.merge_observations(
        existing,
        observed_this_run=set(),  # this run's page did not show it
        parsed_rows={},
        page_window_start=dt.date(2025, 9, 13),
        page_window_end=dt.date(2026, 9, 27),  # week is inside the page's window
        fetched_at=dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc),
    )
    assert len(merged) == 1
    assert merged[0].status == "removed"


def test_merge_observations_leaves_out_of_window_history_alone():
    """A week that has aged off the page's rolling window disappearing from
    this run's rows is NOT a removal -- it's just old. Must stay 'listed'."""
    existing = [_rec(stock_id=1, week_start="2024-01-07", status="listed")]
    merged = history.merge_observations(
        existing,
        observed_this_run=set(),
        parsed_rows={},
        page_window_start=dt.date(2025, 9, 13),  # 2024-01-07 is before the window
        page_window_end=dt.date(2026, 9, 27),
        fetched_at=dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc),
    )
    assert merged[0].status == "listed"


def test_merge_observations_adds_a_new_listed_record():
    key = (1116, "2026-09-13", "Trout")
    merged = history.merge_observations(
        [],
        observed_this_run={key},
        parsed_rows={key: (1116, dt.date(2026, 9, 13), dt.date(2026, 9, 19), "Trout")},
        page_window_start=dt.date(2025, 9, 13),
        page_window_end=dt.date(2026, 9, 27),
        fetched_at=dt.datetime(2026, 9, 13, tzinfo=dt.timezone.utc),
    )
    assert len(merged) == 1
    assert merged[0].status == "listed"
    assert merged[0].first_observed_at == merged[0].last_observed_at
