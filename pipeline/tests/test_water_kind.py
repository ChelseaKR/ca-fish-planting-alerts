"""cfpa.water_kind: still or moving, from the agency's name (DECISIONS 0045)."""

from __future__ import annotations

import pytest

from cfpa.water_kind import water_kind


@pytest.mark.parametrize(
    ("name", "want"),
    [
        ("Collins Lake", "still"),
        ("Ralphine Lake", "still"),
        ("Lake Berryessa", "still"),
        ("Shadow Cliff Lake", "still"),
        ("Portal Forebay", "still"),
        ("Milan City Pond", "still"),
        ("Pine Creek Reservoir", "still"),
        ("Rock Creek Lake", "still"),
        ("Anderson River Park Pond", "still"),
        ("Bear River Reservoir Lower", "still"),
        ("Kings River, Below Pine Flat Dam", "moving"),
        ("Trinity River, above Clair Engle Lake", "moving"),
        ("Yuba River North Fork", "moving"),
        ("Little River", "moving"),
        ("Mossy Creek (New)", "moving"),
        ("Broodfish Waters", None),
        ("", None),
    ],
)
def test_water_kind(name: str, want: str | None) -> None:
    assert water_kind(name) == want


def test_a_word_inside_another_word_does_not_count() -> None:
    # "Lakeshore" and "Pondera" are not "lake" or "pond".
    assert water_kind("Lakeshore Park") is None
    assert water_kind("Pondera") is None
