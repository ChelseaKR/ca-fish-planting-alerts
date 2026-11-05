"""Every water on a real week's schedule has a location or is listed as
unknown, and an unknown one is shown as unknown, never as a distance.

The sample is CDFW's California schedule for the week of 2026-11-01 (the 20
waters on trouttruck.com that week, which matched CDFW's own table 20 of 20).
Before the 2026-11-05 overrides, 15 of them had no location, so "Closest to
me" left out every Los Angeles, Orange and Ventura park lake on it.

Every negative control asserts that its sabotage changed the input before it
asserts that the check caught it.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, locations, site

DATA = Path(__file__).resolve().parents[1] / "data"
FIXTURES = Path(__file__).parent / "fixtures"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
REPO_ROOT = Path(__file__).resolve().parents[2]

# CDFW stock id -> name, for the week of 2026-11-01.
SAMPLE_WEEK_2026_11_01: dict[int, str] = {
    4250: "Modesto Reservoir",
    4320: "Lake Del Valle",
    7115: "Hansen Dam Lake",
    7342: "Echo Park Lake",
    7406: "Laguna Lake",
    7410: "La Mirada Lake",
    7422: "Alondra Park Lake",
    7449: "Eisenhower Park Lake",
    7466: "El Dorado Park Lakes",
    13306: "Donner Lake",
    19260: "Bass Lake",
    27430: "Belvedere Lake",
    27431: "Cerritos Lake",
    27434: "Downey Wilderness Park Lake",
    27435: "Hollenbeck Park Lake",
    27436: "Kenneth Hahn Lake",
    27437: "Lincoln Park Lake",
    27440: "Rancho Simi Park Lake",
    27441: "Santa Fe Reservoir",
    500770: "Kings River, Below Pine Flat Dam",
}
# Explicitly unknown, and why. A stream reach has no location: no source
# marks where CDFW's reaches start and end (cfpa.geocode rule 2).
KNOWN_UNKNOWN: dict[int, str] = {500770: "a reach of a stream"}
NOT_PLACED = frozenset({"ambiguous", "none", "owner_none"})


def _problems(doc: dict[str, Any]) -> list[str]:
    by = {w["cdfw_stock_id"]: w for w in doc["waters"]}
    placed = locations.PLACED
    found = []
    for sid, name in SAMPLE_WEEK_2026_11_01.items():
        w = by.get(sid)
        if w is None:
            found.append(f"{sid} {name}: not in water_locations.json")
            continue
        if w["name"] != name:
            found.append(f"{sid}: named {w['name']!r}, not {name!r}")
        if sid in KNOWN_UNKNOWN:
            if w["status"] not in NOT_PLACED or w["location"] is not None:
                found.append(f"{sid} {name}: listed unknown but placed")
            if not (w.get("reason") or "").strip():
                found.append(f"{sid} {name}: unknown with no reason")
        elif w["status"] not in placed or w["location"] is None:
            found.append(f"{sid} {name}: no location and not listed as unknown")
    return found


def _committed() -> dict[str, Any]:
    return json.loads((DATA / "water_locations.json").read_text(encoding="utf-8"))


def test_every_water_on_the_sample_week_is_placed_or_listed_unknown() -> None:
    assert len(SAMPLE_WEEK_2026_11_01) == 20
    assert _problems(_committed()) == []
    placed = set(SAMPLE_WEEK_2026_11_01) - set(KNOWN_UNKNOWN)
    assert len(placed) == 19


def test_negative_control_an_unplaced_water_is_caught() -> None:
    doc = _committed()
    sabotaged = copy.deepcopy(doc)
    w = next(w for w in sabotaged["waters"] if w["cdfw_stock_id"] == 7342)
    w.update(status="none", location=None, reason="no GNIS feature")
    assert sabotaged != doc  # the sabotage applied
    assert _problems(sabotaged) == [
        "7342 Echo Park Lake: no location and not listed as unknown"
    ]


def test_negative_control_a_placed_unknown_is_caught() -> None:
    doc = _committed()
    sabotaged = copy.deepcopy(doc)
    w = next(w for w in sabotaged["waters"] if w["cdfw_stock_id"] == 500770)
    w.update(status="exact", location={"lat": 36.8, "lon": -119.4})
    assert sabotaged != doc
    assert _problems(sabotaged) == [
        "500770 Kings River, Below Pine Flat Dam: listed unknown but placed"
    ]


def test_cdfw_points_cite_their_source_and_sit_in_southern_california() -> None:
    doc = _committed()
    cited = [
        w
        for w in doc["waters"]
        if w["status"] == "owner_resolved" and w["override"].get("point")
    ]
    assert {w["cdfw_stock_id"] for w in cited} == set(SAMPLE_WEEK_2026_11_01) - {
        4250,
        4320,
        7406,
        13306,
        19260,
        500770,
    }
    for w in cited:
        point = w["override"]["point"]
        assert point["source"].startswith(site.CDFW_POINT_SOURCE_PREFIX)
        assert point["source_url"].startswith("https://hub.arcgis.com/datasets/")
        assert (
            point["source_feature_id"] == f"ds2897 StockingWaterID {w['cdfw_stock_id']}"
        )
        # Los Angeles, Orange and Ventura counties, generously.
        assert 33.4 <= point["lat"] <= 34.9 and -119.5 <= point["lon"] <= -117.4


# ---- on the site: a CDFW point is labeled as one; unknown stays unknown


def _locations_with_a_cdfw_point(root: Path) -> tuple[Path, int]:
    """The committed file, with one fixture lake's point swapped for a CDFW
    point, so the build exercises the label (the fixture weeks predate the
    park lakes' overrides)."""
    doc = _committed()
    fixture = MIDWEEK.read_text(encoding="utf-8")
    w = next(
        w
        for w in doc["waters"]
        if w["status"] == "exact"
        and w["location"]["kind"] == "waterbody"
        and f'stockid={w["cdfw_stock_id"]}"' in fixture
    )
    w["location"] = {
        **w["location"],
        "source": "California Department of Fish and Wildlife, Planting Location (BIOS ds2897)",
        "kind": "named_point",
        "source_feature_id": f"ds2897 StockingWaterID {w['cdfw_stock_id']}",
    }
    path = root / "water_locations.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path, w["cdfw_stock_id"]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("closest-sample")
    shutil.copy(cli.DEFAULT_ALIASES_PATH, root / "aliases.json")
    locs, sid = _locations_with_a_cdfw_point(root)
    snap = cli.run(
        fixture_path=str(MIDWEEK),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=REPO_ROOT / "schema" / "snapshot.v1.json",
        site_out=root / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 18),
        locations_path=locs,
    )
    return root / "site", snap, sid, locations.load_locations(locs)


def _visible(html: str) -> str:
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.text: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            self.skip += tag in ("script", "style")

        def handle_endtag(self, tag: str) -> None:
            self.skip -= tag in ("script", "style")

        def handle_data(self, data: str) -> None:
            if not self.skip:
                self.text.append(data)

    p = P()
    p.feed(html)
    return " ".join("".join(p.text).split())


def test_a_cdfw_point_is_credited_to_cdfw_and_never_called_inside_the_water(built):
    out, snap, sid, locs = built
    w = next(w for w in snap["waters"] if w["cdfw_stock_id"] == sid)
    html = (out / "water" / w["slug"] / "index.html").read_text(encoding="utf-8")
    text = _visible(html)
    loc = locs[sid]
    assert f"{loc['lat']}, {loc['lon']}, CDFW's own point for this water." in text
    assert "Source: California Department of Fish and Wildlife" in text
    assert "a point inside the water" not in text
    assert "GeoCoordinates" not in html  # no structured-data geo for it
    coords = json.loads((out / "assets" / site.COORDS_FILE).read_text("utf-8"))
    assert coords["waters"][w["slug"]] == [loc["lat"], loc["lon"], "c"]
    assert "ds2897" in coords["source"]


def test_an_unknown_location_is_shown_as_unknown_never_as_a_distance(built):
    out, snap, _, locs = built
    coords = json.loads((out / "assets" / site.COORDS_FILE).read_text("utf-8"))
    unplaced = [w for w in snap["waters"] if w["cdfw_stock_id"] not in locs]
    assert unplaced
    for w in unplaced:
        # No point in the file closest.js ranks by, so the script names it
        # under "no location on file" (test_site_water_map runs that).
        assert w["slug"] not in coords["waters"], w["slug"]
        text = _visible(
            (out / "water" / w["slug"] / "index.html").read_text(encoding="utf-8")
        )
        assert "Coordinates" not in text, w["slug"]
        assert " miles" not in text and " mile " not in text, w["slug"]
