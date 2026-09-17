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
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.timezone.utc),
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


def test_main_cli_exits_nonzero_and_prints_reason_on_stale_fixture(tmp_path: Path, capsys):
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
