"""The ``make verify`` smoke run reads the committed alias table.

An empty temporary table made the smoke coverage line print "names matched
0/37 seen" by construction (``AliasTable.apply`` counts a pair as matched only
when the table already held it). Seeding the table from the committed
``data/aliases.json`` makes the line a real reading: the fixture's names
against the names the pipeline has already learned.
"""

import contextlib
import datetime as dt
import io
import re
from pathlib import Path

from cfpa import cli

PIPELINE = Path(__file__).resolve().parents[1]
MAKEFILE = PIPELINE.parent / "Makefile"
COMMITTED_ALIASES = PIPELINE / "data" / "aliases.json"
FIXTURE = Path(__file__).parent / "fixtures" / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = PIPELINE.parent / "schema" / "snapshot.v1.json"

SEED_RE = re.compile(
    r"^\tcp \$\(PIPELINE\)/data/aliases\.json \$\(TMP\)/smoke/aliases\.json$",
    re.MULTILINE,
)


def _smoke_recipe(makefile_text: str) -> str:
    start = makefile_text.index("\nsmoke:\n")
    end = makefile_text.index("\n\n", start + 1)
    return makefile_text[start:end]


def _seeds_from_committed_aliases(makefile_text: str) -> bool:
    recipe = _smoke_recipe(makefile_text)
    seed = SEED_RE.search(recipe)
    run = recipe.find("$(UV_RUN) cfpa")
    return seed is not None and run != -1 and seed.start() < run


def _smoke_run(aliases_path: Path, tmp_path: Path) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.run(
            fixture_path=str(FIXTURE),
            history_path=tmp_path / "history.json",
            aliases_path=aliases_path,
            schema_path=SCHEMA_PATH,
            site_out=tmp_path / "site",
            base_url="https://example.invalid/ca-fish-planting-alerts",
            fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
            run_today=dt.date(2026, 9, 13),
            states_dir=None,
        )
    return buf.getvalue()


def test_the_smoke_target_seeds_its_alias_table_before_the_run():
    assert _seeds_from_committed_aliases(MAKEFILE.read_text(encoding="utf-8"))


def test_the_seed_check_rejects_a_smoke_target_without_the_seed():
    text = MAKEFILE.read_text(encoding="utf-8")
    sabotaged = SEED_RE.sub("\t@true", text)
    # Negative control: the sabotage must have changed the file, or a pass
    # below would prove nothing.
    assert sabotaged != text
    assert not _seeds_from_committed_aliases(sabotaged)


def test_the_fixture_matches_every_name_against_the_committed_aliases(tmp_path):
    seeded = tmp_path / "aliases.json"
    seeded.write_bytes(COMMITTED_ALIASES.read_bytes())
    out = _smoke_run(seeded, tmp_path)
    assert "unmatched: 0" in out
    seen = re.search(r"names seen: (\d+)  names matched: (\d+)", out)
    assert seen is not None
    assert seen.group(1) == seen.group(2)
    assert int(seen.group(1)) > 0


def test_an_empty_alias_table_reads_zero_matched(tmp_path):
    """The reading the smoke target used to print, kept as the control that
    shows the seeded run above is not passing by accident."""
    empty = tmp_path / "aliases.json"
    assert not empty.exists()
    out = _smoke_run(empty, tmp_path)
    assert "names matched: 0" in out
    assert "UNMATCHED cdfw-" in out
