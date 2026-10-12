"""The site's maps (DECISIONS 0025).

Only waters with a confident location (``exact`` or owner-resolved, through
``cfpa.locations``) are on a map; a stream's point is marked approximate;
everything a map loads comes from this site; and a water with no location
says so instead of getting a pin.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pytest

from cfpa import cli, locations, site

FIXTURES = Path(__file__).parent / "fixtures"
FRESH = FIXTURES / "schedule-fresh-2026-09-13.html"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "snapshot.v1.json"
DATA = Path(__file__).resolve().parents[1] / "data"
MAP = site.MAP_STATIC_DIR

# Byte for byte the npm tarballs (map/licenses/README.md has the versions).
VENDOR_SHA256 = {
    "basemaps.js": "551864f01da1bfe3005e99987197f22f56d0c35f9a10fa1727a889e2434af16d",
    "maplibre-gl-shared.mjs": "76b5f55bdee928c65d592684aaff2b913d50b6b17b0ec6334e88b09b6aa47960",
    "maplibre-gl-worker.mjs": "01ad197aa7f4cec258a890febd71b7515e96309881b036a7095befc01a45296e",
    "maplibre-gl.css": "d8617d8421930e3fc6185365400e788c374c1a5d9fbe87999998c0bc14a202d3",
    "maplibre-gl.mjs": "3f55566295583644617fe17d008a36c580414b8c71dd2e1fcff1309de6fdee5d",
    "pmtiles.js": "caf981bc46f6327ee7e65d5dc964d89d38a69f60edca2bd4c5c890c21b554c6c",
}
PMTILES_SHA256 = "99b3fe69392a16df6b443b065ac6c372b8044fd9730cf310d313df95eff018fd"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    root = tmp_path_factory.mktemp("maps")
    out = root / "site"
    snap = cli.run(
        fixture_path=str(FRESH),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    return out, snap


def _features(out: Path) -> list[dict]:
    doc = json.loads((out / "map" / "waters.json").read_text(encoding="utf-8"))
    assert doc["type"] == "FeatureCollection"
    feats: list[dict] = doc["features"]
    return feats


def test_vendor_files_are_the_pinned_releases():
    for name, digest in VENDOR_SHA256.items():
        assert _sha(MAP / "vendor" / name) == digest, name
    assert _sha(MAP / "california.pmtiles") == PMTILES_SHA256
    assert sorted(p.name for p in (MAP / "vendor").iterdir()) == sorted(VENDOR_SHA256)
    for lic in ("maplibre-gl.txt", "pmtiles.txt", "noto-sans-OFL.txt"):
        assert (MAP / "licenses" / lic).read_text(encoding="utf-8").strip()


def test_only_confidently_placed_waters_are_on_the_map(built):
    out, snap = built
    feats = _features(out)
    placed = locations.load_locations(DATA / "water_locations.json")
    status = {
        w["cdfw_stock_id"]: w["status"]
        for w in json.loads(
            (DATA / "water_locations.json").read_text(encoding="utf-8")
        )["waters"]
    }
    by_id = {w["id"]: w for w in snap["waters"]}
    assert feats, "the fixture week should place some waters"
    for f in feats:
        w = by_id[f["properties"]["id"]]
        assert status[w["cdfw_stock_id"]] in locations.PLACED
        loc = placed[w["cdfw_stock_id"]]
        assert f["geometry"]["coordinates"] == [loc["lon"], loc["lat"]]
        assert f["properties"]["kind"] == loc["kind"]
        assert f["properties"]["url"] == f"water/{w['slug']}/"
    on_map = {f["properties"]["id"] for f in feats}
    expected = {w["id"] for w in snap["waters"] if w["cdfw_stock_id"] in placed}
    assert on_map == expected
    # Negative control: the fixture has waters the geocoder could not place,
    # and none of them is on the map.
    unplaced = {w["id"] for w in snap["waters"] if w["cdfw_stock_id"] not in placed}
    assert unplaced
    assert not unplaced & on_map


def test_water_page_with_a_location(built):
    out, _ = built
    f = next(f for f in _features(out) if f["properties"]["kind"] == "waterbody")
    html = (out / f["properties"]["url"] / "index.html").read_text(encoding="utf-8")
    assert '<script type="module" src="../../map/map.js"></script>' in html
    assert 'data-map="water"' in html
    assert f'data-focus="{f["properties"]["id"]}"' in html
    assert "https://maps.apple.com/?ll=" in html
    assert "Directions in Apple Maps" in html
    assert "approximate" not in html.split('id="location-heading"')[1][:600]


def test_stream_points_are_called_approximate(built):
    out, _ = built
    streams = [f for f in _features(out) if f["properties"]["kind"] == "stream_point"]
    if not streams:
        pytest.skip("no stream in the fixture week has a location")
    html = (out / streams[0]["properties"]["url"] / "index.html").read_text(
        encoding="utf-8"
    )
    assert "It is approximate" in html
    assert "(approximate point)" in html


def test_water_page_without_a_location_says_so_and_loads_no_script(built):
    out, snap = built
    on_map = {f["properties"]["id"] for f in _features(out)}
    w = next(w for w in snap["waters"] if w["id"] not in on_map)
    html = (out / "water" / w["slug"] / "index.html").read_text(encoding="utf-8")
    assert "No map location." in html
    assert "map.js" not in html
    assert "maps.apple.com" not in html
    assert "data-map=" not in html


def test_home_map_summary_counts_are_true(built):
    out, snap = built
    html = (out / "index.html").read_text(encoding="utf-8")
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    feats = _features(out)
    this_week = {e["water_id"] for e in snap["this_week"]}
    week_placed = sum(1 for f in feats if f["properties"]["id"] in this_week)
    assert all(
        f["properties"]["this_week"] == (f["properties"]["id"] in this_week)
        for f in feats
    )
    placed = f"{len(feats)} of all {len(snap['waters'])} waters have a map location"
    if this_week:
        assert (
            f"{placed}, including {week_placed} of the {len(this_week)} "
            "scheduled this week." in text
        )
    else:
        assert f"{placed}. A water is placed only" in text
    assert '<script type="module" src="./map/map.js"></script>' in html


# map.js may name another host only as a link in the attribution text.
ALLOWED_LINKS = {"https://www.openstreetmap.org/copyright", "https://protomaps.com"}


def test_map_js_contacts_no_other_host():
    js = (MAP / "map.js").read_text(encoding="utf-8")
    assert set(re.findall(r"https?://[^\s\"'<>`]+", js)) <= ALLOWED_LINKS
    # Every fetch, import and asset URL is built from the site root.
    for call in re.findall(r"(?:fetch|import|loadScript|loadCss)\(([^)]*)\)", js):
        assert "http" not in call, call
    assert "pmtiles://${new URL(" in js
    assert "innerHTML" not in js and "setHTML" not in js


def test_negative_control_link_check_catches_a_cdn():
    sabotaged = 'import("https://unpkg.com/maplibre-gl.mjs")'
    assert not set(re.findall(r"https?://[^\s\"'<>`]+", sabotaged)) <= ALLOWED_LINKS


def test_this_week_waters_are_counted_and_highlighted(built, tmp_path):
    """The fixture week has nothing scheduled, so schedule one placed water
    in the current week and check the home sentence and the map flag."""
    _, snap = built
    snap = json.loads(json.dumps(snap))
    placed = locations.load_locations(DATA / "water_locations.json")
    w = next(w for w in snap["waters"] if w["cdfw_stock_id"] in placed and w["plants"])
    plant = json.loads(json.dumps(w["plants"][-1]))
    plant["week"] = dict(snap["source_week"])
    plant["status"] = "listed"
    w["plants"].append(plant)
    snap["this_week"] = [{"water_id": w["id"], "species": plant["species"]}]
    out = tmp_path / "site"
    site.build_site(snap, out, base_url="https://example.invalid/x", locations=placed)
    feats = _features(out)
    flagged = [f["properties"]["id"] for f in feats if f["properties"]["this_week"]]
    assert flagged == [w["id"]]
    html = (out / "index.html").read_text(encoding="utf-8")
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "including 1 of the 1 scheduled this week." in text


def test_ios_bundled_locations_match_the_pipeline():
    """ios/scripts/sync-water-locations.sh output, committed: no drift."""
    bundled = (
        Path(__file__).resolve().parents[2]
        / "ios"
        / "CAFishPlanting"
        / "Resources"
        / "water-locations.json"
    )
    expected = locations.app_table(DATA / "water_locations.json")
    assert json.loads(bundled.read_text(encoding="utf-8")) == expected
    statuses = {
        f"cdfw-{w['cdfw_stock_id']}": w["status"]
        for w in json.loads(
            (DATA / "water_locations.json").read_text(encoding="utf-8")
        )["waters"]
    }
    # Negative control: ambiguous and unmatched waters exist, and none is in it.
    unplaced = {i for i, s in statuses.items() if s not in locations.PLACED}
    assert unplaced
    assert not unplaced & set(expected["locations"])
