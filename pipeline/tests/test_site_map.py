"""The site's maps (DECISIONS 0026).

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


def _v2(out: Path) -> dict:
    v2: dict = json.loads((out / "snapshot" / "v2.json").read_text(encoding="utf-8"))
    return v2


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
    v2 = _v2(out)
    status = {
        w["cdfw_stock_id"]: w["status"]
        for w in json.loads(
            (DATA / "water_locations.json").read_text(encoding="utf-8")
        )["waters"]
    }
    by_id = {w["id"]: w for w in v2["waters"]}
    stock = {w["id"]: w["cdfw_stock_id"] for w in snap["waters"]}
    assert feats, "the fixture week should place some waters"
    for f in feats:
        w = by_id[f["properties"]["id"]]
        loc = w["location"]
        assert loc is not None
        assert f["geometry"]["coordinates"] == [loc["lon"], loc["lat"]]
        assert f["properties"]["kind"] == loc["kind"]
        assert f["properties"]["state"] == w["state"]
        assert f["properties"]["url"] == w["site_path"].lstrip("/")
        # A California pin is an exact or owner-resolved match, nothing else.
        if w["state"] == "CA":
            assert status[stock[w["id"]]] in locations.PLACED
    on_map = {f["properties"]["id"] for f in feats}
    assert on_map == {w["id"] for w in v2["waters"] if w["location"] is not None}
    # Negative control: the fixture has waters with no location, and none of
    # them is on the map.
    unplaced = {w["id"] for w in v2["waters"] if w["location"] is None}
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
    out, _ = built
    v2 = _v2(out)
    html = (out / "index.html").read_text(encoding="utf-8")
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    feats = _features(out)
    for st in v2["states"]:
        total = sum(1 for w in v2["waters"] if w["state"] == st["code"])
        placed = sum(1 for f in feats if f["properties"]["state"] == st["code"])
        assert f"{st['name']}: {placed} of {total} waters have a map location" in text
    this_week = {e["water_id"] for e in v2["this_week"]}
    assert all(
        f["properties"]["this_week"] == (f["properties"]["id"] in this_week)
        for f in feats
    )
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


def _rebuild(built, tmp_path, v2: dict) -> Path:
    _, snap = built
    site_out = tmp_path / "site"
    site.build_site(
        snap,
        site_out,
        base_url="https://example.invalid/x",
        snapshot_v2=v2,
        maps=True,
    )
    return site_out


def test_this_week_waters_are_counted_and_highlighted(built, tmp_path):
    """The fixture week has nothing scheduled, so put one placed water in
    this week and check the home sentence and the map flag."""
    v2 = _v2(built[0])
    w = next(w for w in v2["waters"] if w["location"] is not None)
    v2["this_week"] = [{"water_id": w["id"], "species": "Trout"}]
    out = _rebuild(built, tmp_path, v2)
    flagged = [
        f["properties"]["id"] for f in _features(out) if f["properties"]["this_week"]
    ]
    assert flagged == [w["id"]]
    text = " ".join(re.sub(r"<[^>]+>", " ", (out / "index.html").read_text()).split())
    assert "This week, 1 of the 1 scheduled or stocked waters are on the map." in text


def test_a_located_water_in_another_state_is_pinned(built, tmp_path):
    """State-aware: any state's water with a location gets a pin, labeled
    with its state and its own page; one without stays off."""
    v2 = _v2(built[0])
    v2["states"].append({**v2["states"][0], "code": "TN", "name": "Tennessee"})
    base = next(w for w in v2["waters"] if w["location"] is not None)
    tn = {
        **base,
        "id": "tn-test-lake",
        "state": "TN",
        "site_path": "/tn/water/test-lake/",
        # Inside the tiles on purpose; the next test covers outside.
        "location": dict(base["location"]),
    }
    v2["waters"].append(tn)
    v2["waters"].append({**tn, "id": "tn-no-location", "location": None})
    out = _rebuild(built, tmp_path, v2)
    props = {f["properties"]["id"]: f["properties"] for f in _features(out)}
    assert props["tn-test-lake"]["state"] == "TN"
    assert props["tn-test-lake"]["url"] == "tn/water/test-lake/"
    assert "tn-no-location" not in props
    text = " ".join(re.sub(r"<[^>]+>", " ", (out / "index.html").read_text()).split())
    assert "Tennessee: 1 of 2 waters have a map location" in text


def test_a_pin_outside_the_tiles_fails_the_build(built, tmp_path):
    v2 = _v2(built[0])
    w = next(w for w in v2["waters"] if w["location"] is not None)
    w["location"] = {**w["location"], "lat": 36.16, "lon": -86.78}  # Nashville
    with pytest.raises(site.MapCoverageError, match="outside the map tiles"):
        _rebuild(built, tmp_path, v2)


def test_maps_need_snapshot_v2(built, tmp_path):
    with pytest.raises(ValueError, match="maps need snapshot_v2"):
        site.build_site(
            built[1], tmp_path / "s", base_url="https://example.invalid/x", maps=True
        )


def test_a_state_with_no_locations_says_so(built, tmp_path):
    v2 = _v2(built[0])
    v2["states"].append({**v2["states"][0], "code": "TN", "name": "Tennessee"})
    base = v2["waters"][0]
    v2["waters"].append(
        {
            **base,
            "id": "tn-nowhere",
            "state": "TN",
            "site_path": "/tn/water/nowhere/",
            "location": None,
        }
    )
    out = _rebuild(built, tmp_path, v2)
    text = " ".join(re.sub(r"<[^>]+>", " ", (out / "index.html").read_text()).split())
    assert (
        "Tennessee: 0 of 1 waters have a map location (none yet: no location "
        "source for this state)" in text
    )
