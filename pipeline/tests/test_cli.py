import datetime as dt
import json
from pathlib import Path

from cfpa import cli

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"


def _kwargs(tmp_path: Path) -> dict:
    return dict(
        fixture_path=str(FRESH),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        species_aliases_path=tmp_path / "species_aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=tmp_path / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )


def test_first_run_reports_every_name_unmatched(tmp_path: Path, capsys):
    cli.run(**_kwargs(tmp_path))
    out = capsys.readouterr().out
    assert "names matched: 0" in out
    assert "UNMATCHED cdfw-" in out


def test_second_run_matches_the_names_the_first_run_learned(tmp_path: Path, capsys):
    kwargs = _kwargs(tmp_path)
    cli.run(**kwargs)
    capsys.readouterr()
    cli.run(**kwargs)
    out = capsys.readouterr().out
    assert "unmatched: 0" in out


def test_rerun_on_identical_data_does_not_grow_history(tmp_path: Path):
    kwargs = _kwargs(tmp_path)
    cli.run(**kwargs)
    first = json.loads((tmp_path / "history.json").read_text())
    cli.run(**kwargs)
    second = json.loads((tmp_path / "history.json").read_text())
    assert len(first["plants"]) == len(second["plants"])


def test_aliases_file_is_committed_shape(tmp_path: Path):
    cli.run(**_kwargs(tmp_path))
    data = json.loads((tmp_path / "aliases.json").read_text())
    assert data["schema"] == "cfpa-aliases-v1"
    assert data["waters"]
    ids = [w["cdfw_stock_id"] for w in data["waters"]]
    assert ids == sorted(ids)  # deterministic, diff-friendly ordering


def test_species_alias_normalizes_an_inconsistent_spelling_end_to_end(tmp_path: Path):
    """The scenario this whole layer exists for: CDFW spells one row's
    species inconsistently ('Trout (Rainbow)' instead of 'Trout'). With a
    curated species_aliases.json entry, that row must fold into the same
    history/species identity as every other 'Trout' row -- not fork into a
    spurious second species."""
    variant_html = FRESH.read_text(encoding="utf-8").replace(
        "<td>\n                            Trout\n                        </td>",
        "<td>\n                            Trout (Rainbow)\n                        </td>",
        1,  # exactly one row gets the inconsistent spelling
    )
    variant_fixture = tmp_path / "schedule-variant-spelling.html"
    variant_fixture.write_text(variant_html, encoding="utf-8")

    species_aliases_path = tmp_path / "species_aliases.json"
    species_aliases_path.write_text(
        json.dumps(
            {
                "schema": "cfpa-species-aliases-v1",
                "species": [
                    {
                        "canonical_name": "Trout",
                        "slug": "trout",
                        "aliases": ["Trout", "Trout (Rainbow)"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    kwargs = _kwargs(tmp_path)
    kwargs["fixture_path"] = str(variant_fixture)
    kwargs["species_aliases_path"] = species_aliases_path
    snap = cli.run(**kwargs)

    # the inconsistent spelling normalized away -- only the two real species
    # remain, no spurious "Trout (Rainbow)" category
    assert snap["species"] == ["Catfish", "Trout"]
    history = json.loads((tmp_path / "history.json").read_text())
    species_in_history = {p["species"] for p in history["plants"]}
    assert species_in_history == {"Catfish", "Trout"}


def test_species_without_curated_alias_passes_through_unchanged(tmp_path: Path):
    """No curated species_aliases.json entry exists for real data today --
    confirm the default (empty) table changes nothing about a normal run."""
    snap = cli.run(**_kwargs(tmp_path))
    assert snap["species"] == ["Catfish", "Trout"]


def test_main_cli_exits_nonzero_and_prints_reason_on_stale_fixture(
    tmp_path: Path, capsys
):
    stale = FIXTURES / "schedule-stale-2025-cache.html"
    code = cli.main(
        [
            "--fixture",
            str(stale),
            "--history",
            str(tmp_path / "history.json"),
            "--aliases",
            str(tmp_path / "aliases.json"),
            "--schema",
            str(SCHEMA_PATH),
            "--site-out",
            str(tmp_path / "site"),
            "--run-today",
            "2026-09-13",
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "refused" in err
    assert not (tmp_path / "site").exists()


def test_main_cli_succeeds_on_fresh_fixture(tmp_path: Path, capsys):
    code = cli.main(
        [
            "--fixture",
            str(FRESH),
            "--history",
            str(tmp_path / "history.json"),
            "--aliases",
            str(tmp_path / "aliases.json"),
            "--schema",
            str(SCHEMA_PATH),
            "--site-out",
            str(tmp_path / "site"),
            "--run-today",
            "2026-09-13",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "coverage:" in out
    assert (tmp_path / "site" / "snapshot" / "v1.json").exists()


MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"


def test_midweek_run_after_a_sunday_run_updates_history_without_false_removals(
    tmp_path: Path, capsys
):
    """Two real CDFW responses, run in the order the scheduled job would:
    the 2026-09-13 (Sunday) page, then the 2026-09-17 (Thursday) page --
    trimmed to the same waters plus every plant the later page added.

    Pins both bugs that kept history from accumulating:
    - the Thursday run is accepted (it was refused as "5 day(s) stale");
    - the three week-of-2025-09-14 plants the Thursday page no longer shows
      (aged off the rolling window by the day) stay 'listed' -- they must not
      become permanent false "removed" records.
    """
    kwargs = _kwargs(tmp_path)
    cli.run(**kwargs)
    first = json.loads((tmp_path / "history.json").read_text())

    kwargs.update(
        fixture_path=str(MIDWEEK),
        fixture_fetched_at=dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 18),  # the UTC date, as publish.yml sees it
    )
    snap = cli.run(**kwargs)
    second = json.loads((tmp_path / "history.json").read_text())

    before = {
        (p["cdfw_stock_id"], p["week_start"], p["species"]): p for p in first["plants"]
    }
    after = {
        (p["cdfw_stock_id"], p["week_start"], p["species"]): p for p in second["plants"]
    }
    assert set(before) <= set(after)  # append-only
    added = set(after) - set(before)
    assert len(added) == 29  # plants CDFW listed between the two fetches
    assert {k[1] for k in added} == {"2026-09-13", "2026-09-20"}

    aged_off = [k for k in before if k[1] == "2025-09-14"]
    assert len(aged_off) == 3
    assert all(after[k]["status"] == "listed" for k in aged_off)
    assert [k for k, p in after.items() if p["status"] == "removed"] == []

    assert snap["source_week"]["label"] == "week of 2026-09-13"


def test_a_run_that_fails_schema_validation_writes_no_history_or_aliases(
    tmp_path: Path, monkeypatch
):
    """cli.run's contract: a schema violation writes nothing new. History
    and aliases used to be saved *before* the snapshot was built and
    validated, so a failure there left them written anyway."""
    import jsonschema

    from cfpa import snapshot as snapshot_mod

    kwargs = _kwargs(tmp_path)
    cli.run(**kwargs)
    history_before = (tmp_path / "history.json").read_bytes()
    aliases_before = (tmp_path / "aliases.json").read_bytes()

    def refuse(*_args, **_kwargs):
        raise jsonschema.ValidationError("simulated schema violation")

    monkeypatch.setattr(snapshot_mod, "validate_snapshot", refuse)
    kwargs.update(
        fixture_path=str(MIDWEEK),
        fixture_fetched_at=dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 18),
    )
    try:
        cli.run(**kwargs)
    except jsonschema.ValidationError:
        pass
    else:  # pragma: no cover - the sabotage must actually apply
        raise AssertionError("the simulated schema violation did not fire")

    assert (tmp_path / "history.json").read_bytes() == history_before
    assert (tmp_path / "aliases.json").read_bytes() == aliases_before


def test_a_water_whose_plants_all_aged_off_is_placed_from_cdfws_own_picker():
    """cdfw-500491 / cdfw-500492 were planted only the week of 2025-09-14;
    by 2026-09-17 they had no table row, and the run crashed on them. The
    same page's water picker still names their county."""
    from cfpa import parse
    from cfpa import snapshot as snapshot_mod

    html = MIDWEEK.read_text(encoding="utf-8")
    picker = snapshot_mod.counties_from_water_picker(
        parse.parse_select_options(html, "Params_StockingWaterID")
    )
    assert picker[500491] == ["Plumas"]
    assert picker[500492] == ["Plumas"]
    assert 500491 not in {r.cdfw_stock_id for r in parse.parse_schedule_table(html)}
    # Multi-county labels split the same way the table's Counties cell does.
    assert all(len(v) >= 1 for v in picker.values())
    assert any(len(v) > 1 for v in picker.values())
