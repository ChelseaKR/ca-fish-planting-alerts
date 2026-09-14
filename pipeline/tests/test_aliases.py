from pathlib import Path

from cfpa import aliases


def test_new_water_is_unmatched_and_added():
    table = aliases.AliasTable(by_id={})
    report = aliases.apply_all(table, [(1116, "Lake Almanor")])
    assert report.names_seen == 1
    assert report.names_matched == 0
    assert report.unmatched == [(1116, "Lake Almanor")]
    assert table.by_id[1116].canonical_name == "Lake Almanor"
    assert table.by_id[1116].aliases == ["Lake Almanor"]
    assert table.by_id[1116].reviewed is False


def test_known_spelling_matches_on_a_later_run():
    table = aliases.AliasTable(by_id={})
    aliases.apply_all(table, [(1116, "Lake Almanor")])
    report2 = aliases.apply_all(table, [(1116, "Lake Almanor")])
    assert report2.names_matched == 1
    assert report2.unmatched == []


def test_new_spelling_of_a_known_id_is_reported_unmatched():
    table = aliases.AliasTable(by_id={})
    aliases.apply_all(table, [(1116, "Lake Almanor")])
    report2 = aliases.apply_all(table, [(1116, "Lake  Almanor ")])  # different whitespace
    assert report2.unmatched == [(1116, "Lake  Almanor ")]
    assert "Lake  Almanor " in table.by_id[1116].aliases
    assert table.by_id[1116].canonical_name == "Lake Almanor"  # canonical untouched


def test_same_name_different_ids_stay_distinct_waters():
    """'Silver Lake' is 3 different physical waters in CDFW's own data
    (different stock ids). The alias table must never merge them."""
    table = aliases.AliasTable(by_id={})
    aliases.apply_all(table, [(17432, "Silver Lake"), (10784, "Silver Lake"), (14582, "Silver Lake")])
    assert len(table.by_id) == 3
    slugs = {e.slug for e in table.by_id.values()}
    assert len(slugs) == 3, "same-named waters must get distinct slugs"


def test_unmatched_report_prints_every_new_pair(capsys):
    table = aliases.AliasTable(by_id={})
    report = aliases.apply_all(table, [(1, "A Lake"), (2, "B Lake")])
    report.print_report()
    out = capsys.readouterr().out
    assert "names seen: 2" in out
    assert "names matched: 0" in out
    assert "UNMATCHED cdfw-1: 'A Lake'" in out
    assert "UNMATCHED cdfw-2: 'B Lake'" in out


def test_save_and_load_round_trip(tmp_path: Path):
    table = aliases.AliasTable(by_id={})
    aliases.apply_all(table, [(1116, "Lake Almanor")])
    path = tmp_path / "aliases.json"
    table.save(path)

    loaded = aliases.AliasTable.load(path)
    assert loaded.by_id[1116].canonical_name == "Lake Almanor"
    assert loaded.by_id[1116].slug == "lake-almanor"


def test_load_missing_file_is_empty_table(tmp_path: Path):
    table = aliases.AliasTable.load(tmp_path / "does-not-exist.json")
    assert table.by_id == {}


def test_slugify_handles_punctuation():
    assert aliases.slugify("Owens River, below Tinnemaha") == "owens-river-below-tinnemaha"
    assert aliases.slugify("Blue Lake (Upper)") == "blue-lake-upper"
