from pathlib import Path

from cfpa import species_aliases


def test_load_missing_file_is_empty_table():
    table = species_aliases.SpeciesAliasTable.load(Path("/does/not/exist.json"))
    assert table.entries == []


def test_clean_species_normalizes_to_itself_when_no_alias_curated():
    """Today's real data ('Trout', 'Catfish') has no curated entries at all
    -- every observed name must just pass through unchanged."""
    table = species_aliases.SpeciesAliasTable(entries=[])
    assert table.normalize("Trout") == "Trout"
    assert table.normalize("Catfish") == "Catfish"


def test_whitespace_is_always_collapsed_even_with_no_curated_entry():
    table = species_aliases.SpeciesAliasTable(entries=[])
    assert table.normalize("  Trout  ") == "Trout"
    assert table.normalize("Rainbow\tTrout") == "Rainbow Trout"


def test_curated_alias_normalizes_an_inconsistent_spelling():
    """The mechanism this module exists for: feed a synthetic future CDFW
    inconsistency ('Trout - Rainbow' alongside 'Rainbow Trout') through a
    hand-curated entry and confirm both spellings resolve to one canonical
    species -- proving the table works even though real data doesn't need
    it yet."""
    table = species_aliases.SpeciesAliasTable(
        entries=[
            species_aliases.SpeciesAlias(
                canonical_name="Rainbow Trout",
                slug="rainbow-trout",
                aliases=["Rainbow Trout", "Trout - Rainbow", "RAINBOW TROUT"],
            )
        ]
    )
    assert table.normalize("Rainbow Trout") == "Rainbow Trout"
    assert table.normalize("Trout - Rainbow") == "Rainbow Trout"
    assert table.normalize("RAINBOW TROUT") == "Rainbow Trout"
    # an uncurated, unrelated species is untouched
    assert table.normalize("Catfish") == "Catfish"


def test_uncurated_spelling_variant_is_not_silently_merged():
    """Without a curated alias, two different strings stay two different
    species -- normalize() never guesses a merge on its own (mirrors
    AliasTable: only a human decides two spellings mean the same thing)."""
    table = species_aliases.SpeciesAliasTable(entries=[])
    assert table.normalize("Rainbow Trout") != table.normalize("Trout - Rainbow")


def test_save_and_load_round_trip(tmp_path: Path):
    table = species_aliases.SpeciesAliasTable(
        entries=[
            species_aliases.SpeciesAlias(
                canonical_name="Rainbow Trout",
                slug="rainbow-trout",
                aliases=["Rainbow Trout", "Trout - Rainbow"],
            )
        ]
    )
    path = tmp_path / "species_aliases.json"
    table.save(path)

    loaded = species_aliases.SpeciesAliasTable.load(path)
    assert loaded.normalize("Trout - Rainbow") == "Rainbow Trout"


def test_slugify_handles_punctuation():
    assert species_aliases.slugify("Rainbow Trout") == "rainbow-trout"
    assert species_aliases.slugify("Trout - Rainbow") == "trout-rainbow"


def test_real_committed_alias_file_loads_and_is_empty_today():
    """The committed pipeline/data/species_aliases.json is the defensive,
    empty-by-default table this module ships with -- real CDFW data has
    never needed a curated entry."""
    path = Path(__file__).parent.parent / "data" / "species_aliases.json"
    table = species_aliases.SpeciesAliasTable.load(path)
    assert table.entries == []
    assert table.normalize("Trout") == "Trout"
    assert table.normalize("Catfish") == "Catfish"
