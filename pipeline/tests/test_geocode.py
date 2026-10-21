"""The offline geocoder: names, matching rules, geometry, files, output.

Every input is built here, in the formats the real files ship in (GNIS
pipe-delimited text, an NHD-shaped GeoPackage table, a TIGER-shaped polygon
shapefile), so the end-to-end test runs the same code as a real run.

Negative controls: an ambiguous name is never placed, a same-name feature in
another county is never used, a stream reach is never placed, and a stream
whose channel never enters the listed county is never placed.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import struct
from pathlib import Path

import pytest

from cfpa import cli, geo, geocode, locations
from cfpa.geocode_report import render_report

DATA = Path(__file__).resolve().parents[1] / "data"
REPO = Path(__file__).resolve().parents[2]

# --- builders for the three input formats -------------------------------------


def wkb_polygon(*rings: list[tuple[float, float]]) -> bytes:
    out = struct.pack("<BII", 1, 3, len(rings))
    for ring in rings:
        out += struct.pack("<I", len(ring))
        for x, y in ring:
            out += struct.pack("<dd", x, y)
    return out


def wkb_line(pts: list[tuple[float, float]], z: bool = False) -> bytes:
    out = struct.pack("<BII", 1, 1002 if z else 2, len(pts))
    for x, y in pts:
        out += struct.pack("<ddd", x, y, 0.0) if z else struct.pack("<dd", x, y)
    return out


def wkb_multi(kind: int, parts: list[bytes]) -> bytes:
    return struct.pack("<BII", 1, kind, len(parts)) + b"".join(parts)


def gpkg(wkb: bytes, envelope: int = 0) -> bytes:
    flags = (envelope << 1) | 1
    env = b"\0" * {0: 0, 1: 32, 2: 48}[envelope]
    return b"GP\x00" + bytes([flags]) + struct.pack("<i", 4269) + env + wkb


def write_shapefile(
    shp: Path, rows: list[tuple[dict[str, str], list[list[tuple[float, float]]]]]
) -> None:
    records = b""
    for n, (_, rings) in enumerate(rows, start=1):
        pts = [p for r in rings for p in r]
        parts, k = [], 0
        for r in rings:
            parts.append(k)
            k += len(r)
        content = struct.pack("<i4d", 5, 0, 0, 0, 0)
        content += struct.pack("<ii", len(rings), len(pts))
        content += struct.pack(f"<{len(parts)}i", *parts)
        content += b"".join(struct.pack("<dd", *p) for p in pts)
        records += struct.pack(">ii", n, len(content) // 2) + content
    shp.write_bytes(b"\0" * 100 + records)
    fields = [("STATEFP", 2), ("NAME", 20)]
    hlen = 32 + 32 * len(fields) + 1
    rlen = 1 + sum(w for _, w in fields)
    head = struct.pack("<B3xIHH20x", 3, len(rows), hlen, rlen)
    for name, width in fields:
        head += name.encode().ljust(11, b"\0") + b"C" + b"\0" * 4
        head += bytes([width]) + b"\0" * 15
    head += b"\x0d"
    body = b"".join(
        b" " + b"".join(a[f].encode().ljust(w) for f, w in fields) for a, _ in rows
    )
    shp.with_suffix(".dbf").write_bytes(head + body)


def square(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


GNIS_HEADER = (
    "feature_id|feature_name|feature_class|state_name|state_numeric|county_name|"
    "county_numeric|map_name|date_created|date_edited|bgn_type|bgn_authority|"
    "bgn_date|prim_lat_dms|prim_long_dms|prim_lat_dec|prim_long_dec|"
    "source_lat_dms|source_long_dms|source_lat_dec|source_long_dec"
)


def gnis_row(fid: int, name: str, cls: str, county: str, lat: float, lon: float) -> str:
    cells = [str(fid), name, cls, "California", "06", county]
    cells += [""] * 9 + [str(lat), str(lon)] + [""] * 4
    return "|".join(cells)


# A C-shaped reservoir: its vertex average falls in the open bite, on land.
CRESCENT = [
    (-119.90, 38.40),
    (-119.70, 38.40),
    (-119.70, 38.44),
    (-119.86, 38.44),
    (-119.86, 38.56),
    (-119.70, 38.56),
    (-119.70, 38.60),
    (-119.90, 38.60),
    (-119.90, 38.40),
]
# Alpha County: lon -120..-119; Beta County: lon -119..-118; both lat 38..39.
TROUT_CREEK = [(-119.5, 38.5), (-119.2, 38.5), (-118.8, 38.5), (-118.5, 38.6)]

FEATURES = [
    (1, "Crescent Lake", "Reservoir", "Alpha", 38.5, -119.8),
    (2, "Pine Flat Lake", "Reservoir", "Alpha", 38.2, -119.3),
    (3, "Twin Lake", "Lake", "Alpha", 38.3, -119.6),
    (4, "Twin Lake", "Lake", "Alpha", 38.7, -119.4),
    (5, "Lone Lake", "Lake", "Alpha", 38.8, -119.7),
    (6, "Trout Creek", "Stream", "Alpha", 38.5, -119.5),
    (7, "Mill Creek", "Stream", "Alpha", 38.1, -118.5),
    (8, "Crescent Lake", "Summit", "Alpha", 38.9, -119.1),
    (9, "Gone Lake", "Lake", "Alpha", 0, 0),
]
WATERS = [
    (101, "Crescent Lake", [], ["Alpha"]),
    (102, "Pine Flat Reservoir", [], ["Alpha"]),
    (103, "Twin Lake", [], ["Alpha"]),
    (104, "Lone Lake", [], ["Beta"]),
    (105, "Trout Creek", [], ["Beta"]),
    (106, "Trout Creek, Section 2", [], ["Beta"]),
    (107, "Mill Creek", [], ["Alpha"]),
    (108, "Twin Lake, Upper Meadow", [], ["Alpha"]),
    (109, "Gone Lake", [], ["Alpha"]),
]


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Path]:
    gnis = tmp_path / "gnis.txt"
    gnis.write_text(
        "﻿" + "\r\n".join([GNIS_HEADER, *(gnis_row(*f) for f in FEATURES)]) + "\r\n",
        encoding="utf-8",
    )
    nhd = tmp_path / "nhd.gpkg"
    db = sqlite3.connect(nhd)
    db.execute("CREATE TABLE NHDWaterbody (gnis_id TEXT, SHAPE BLOB)")
    db.execute("CREATE TABLE NHDFlowline (gnis_id TEXT, SHAPE BLOB)")
    small = square(-119.9, 38.0, -119.89, 38.01)
    db.executemany(
        "INSERT INTO NHDWaterbody VALUES (?, ?)",
        [
            ("00000001", gpkg(wkb_multi(6, [wkb_polygon(CRESCENT)]), envelope=1)),
            ("00000001", gpkg(wkb_polygon(small))),  # a smaller piece: ignored
            ("00000099", gpkg(wkb_polygon(small))),  # nobody asked for 99
            ("00000003", None),
        ],
    )
    db.executemany(
        "INSERT INTO NHDFlowline VALUES (?, ?)",
        [
            ("00000006", gpkg(wkb_multi(1005, [wkb_line(TROUT_CREEK, z=True)]))),
            ("00000007", gpkg(wkb_line([(-118.6, 38.1), (-118.4, 38.2)]))),
        ],
    )
    db.commit()
    db.close()
    shp = tmp_path / "counties.shp"
    write_shapefile(
        shp,
        [
            ({"STATEFP": "06", "NAME": "Alpha"}, [square(-120, 38, -119, 39)]),
            (
                {"STATEFP": "06", "NAME": "Beta"},
                [square(-117.5, 38, -117.4, 38.1), square(-119, 38, -118, 39)],
            ),
            ({"STATEFP": "32", "NAME": "Alpha"}, [square(-118, 38, -117, 39)]),
        ],
    )
    snapshot = tmp_path / "v1.json"
    snapshot.write_text(
        json.dumps(
            {
                "waters": [
                    {"cdfw_stock_id": i, "name": n, "aliases": a, "counties": c}
                    for i, n, a, c in WATERS
                ]
            }
        ),
        encoding="utf-8",
    )
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps({"schema": geocode.OVERRIDES_SCHEMA, "overrides": []}),
        encoding="utf-8",
    )
    return {
        "gnis": gnis,
        "nhd": nhd,
        "counties": shp,
        "snapshot": snapshot,
        "overrides": overrides,
    }


def run_cli(inputs: dict[str, Path], tmp_path: Path) -> dict[str, dict]:
    out, report = tmp_path / "locations.json", tmp_path / "report.md"
    argv = [f"--{k}={v}" for k, v in inputs.items()]
    argv += [f"--out={out}", f"--report={report}"]
    argv += [f"--{k}=2026-10-12" for k in ("generated-on", "terms-read-on")]
    argv += ["--downloaded-on=2026-10-12"]
    assert geocode.main(argv) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["_report"] = report.read_text(encoding="utf-8")
    return doc


def by_id(doc: dict) -> dict[int, dict]:
    return {w["cdfw_stock_id"]: w for w in doc["waters"]}


# --- end to end -------------------------------------------------------------------


def test_end_to_end_statuses(inputs, tmp_path):
    doc = run_cli(inputs, tmp_path)
    w = by_id(doc)
    assert {k: v["status"] for k, v in w.items()} == {
        101: "exact",
        102: "exact",
        103: "ambiguous",
        104: "none",
        105: "exact",
        106: "none",
        107: "none",
        108: "ambiguous",
        109: "none",
    }
    assert doc["counts"] == {
        "exact": 3,
        "owner_resolved": 0,
        "ambiguous": 2,
        "none": 4,
        "owner_none": 0,
    }
    assert doc["schema"] == geocode.LOCATIONS_SCHEMA
    assert all(i["terms_read_on"] == "2026-10-12" for i in doc["inputs"])


def test_lake_gets_a_point_inside_its_largest_polygon(inputs, tmp_path):
    loc = by_id(run_cli(inputs, tmp_path))[101]["location"]
    assert loc["kind"] == "waterbody"
    assert loc["source"] == geocode.SOURCE_NHD
    assert loc["source_feature_id"] == "1"
    pt = (loc["lon"], loc["lat"])
    assert geo.contains(geo.Polygon((CRESCENT,)), pt)
    # The vertex average lies in the bite of the C, on land: never used.
    mx = sum(p[0] for p in CRESCENT) / len(CRESCENT)
    my = sum(p[1] for p in CRESCENT) / len(CRESCENT)
    assert not geo.contains(geo.Polygon((CRESCENT,)), (mx, my))


def test_lake_without_polygon_uses_gnis_point_through_a_variant(inputs, tmp_path):
    w = by_id(run_cli(inputs, tmp_path))[102]
    assert w["matched_name"] == "Pine Flat Lake"
    assert w["method"] == "lake word swapped"
    assert w["location"] == {
        "lat": 38.2,
        "lon": -119.3,
        "source": geocode.SOURCE_GNIS,
        "kind": "named_point",
        "source_feature_id": "2",
    }


def test_negative_control_ambiguous_is_never_placed(inputs, tmp_path):
    w = by_id(run_cli(inputs, tmp_path))[103]
    assert w["location"] is None
    assert [c["gnis_feature_id"] for c in w["candidates"]] == [3, 4]
    assert all(c["would_be"]["kind"] == "named_point" for c in w["candidates"])
    # A locality after the comma is dropped only to look the name up; both
    # Twin Lakes still match, so it stays ambiguous rather than guessed.
    assert by_id(run_cli(inputs, tmp_path))[108]["status"] == "ambiguous"


def test_negative_control_same_name_in_another_county_is_not_used(inputs, tmp_path):
    w = by_id(run_cli(inputs, tmp_path))[104]
    assert w["location"] is None
    assert w["reason"] == "no GNIS feature with this name in the listed county"
    assert [n["gnis_feature_id"] for n in w["near_misses"]] == [5]


def test_stream_point_is_on_the_channel_inside_the_listed_county(inputs, tmp_path):
    loc = by_id(run_cli(inputs, tmp_path))[105]["location"]
    assert loc["kind"] == "stream_point"
    assert (loc["lon"], loc["lat"]) in [(round(x, 5), y) for x, y in TROUT_CREEK]
    assert -119 <= loc["lon"] <= -118


def test_negative_control_stream_reach_is_never_placed(inputs, tmp_path):
    w = by_id(run_cli(inputs, tmp_path))[106]
    assert w["location"] is None
    assert "reach" in w["reason"]
    assert w["candidates"] == []


def test_negative_control_stream_outside_the_county_is_not_a_candidate(
    inputs, tmp_path
):
    w = by_id(run_cli(inputs, tmp_path))[107]
    assert w["status"] == "none"
    assert w["candidates"] == []


def test_feature_with_no_point_and_no_polygon_is_none(inputs, tmp_path):
    w = by_id(run_cli(inputs, tmp_path))[109]
    assert w["status"] == "none"
    assert w["location"] is None
    assert w["reason"] == "GNIS has no point and NHD no polygon for this feature"


def test_report_lists_every_ambiguous_candidate(inputs, tmp_path):
    report = run_cli(inputs, tmp_path)["_report"]
    assert "## Ambiguous: pick one, or none (2)" in report
    assert "GNIS 3 Twin Lake (Lake, Alpha County" in report
    assert "GNIS 4 Twin Lake (Lake, Alpha County" in report
    assert "## No match (4)" in report
    assert "elsewhere: GNIS 5 Lone Lake" in report
    assert '"Pine Flat Lake" (lake word swapped)' in report
    assert "## Owner overrides (0)" in report
    assert "| total | 9 |" in report


def test_overrides_resolve_and_refuse(inputs, tmp_path):
    entries = [
        {
            "cdfw_stock_id": 103,
            "gnis_feature_id": 4,
            "resolved_by": "Chelsea",
            "resolved_on": "2026-10-12",
            "note": "the one by the campground",
        },
        {
            "cdfw_stock_id": 108,
            "gnis_feature_id": None,
            "resolved_by": "Chelsea",
            "resolved_on": "2026-10-12",
            "note": "a meadow pond GNIS does not name",
        },
    ]
    inputs["overrides"].write_text(
        json.dumps({"schema": geocode.OVERRIDES_SCHEMA, "overrides": entries}),
        encoding="utf-8",
    )
    doc = run_cli(inputs, tmp_path)
    w = by_id(doc)
    assert w[103]["status"] == "owner_resolved"
    assert w[103]["location"]["source_feature_id"] == "4"
    assert w[103]["override"]["resolved_by"] == "Chelsea"
    assert w[108]["status"] == "owner_none"
    assert w[108]["location"] is None
    assert "the one by the campground" in doc["_report"]


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"gnis_feature_id": 12345}, "not found"),
        ({"gnis_feature_id": 7}, "do not enter"),
    ],
)
def test_bad_override_is_an_error(inputs, tmp_path, entry, message):
    o = {
        "cdfw_stock_id": 107,
        "resolved_by": "Chelsea",
        "resolved_on": "2026-10-12",
        "note": "n",
        **entry,
    }
    inputs["overrides"].write_text(
        json.dumps({"schema": geocode.OVERRIDES_SCHEMA, "overrides": [o]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=message):
        run_cli(inputs, tmp_path)


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"schema": "x", "overrides": []}, "schema"),
        (
            {
                "schema": geocode.OVERRIDES_SCHEMA,
                "overrides": [{"cdfw_stock_id": 1, "gnis_feature_id": 1}],
            },
            "no resolved_by",
        ),
        (
            {
                "schema": geocode.OVERRIDES_SCHEMA,
                "overrides": [
                    {
                        "cdfw_stock_id": 1,
                        "gnis_feature_id": 1,
                        "resolved_by": "a",
                        "resolved_on": "2026-10-12",
                        "note": "n",
                    }
                ]
                * 2,
            },
            "two overrides",
        ),
    ],
)
def test_override_file_is_checked(tmp_path, doc, message):
    p = tmp_path / "o.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        geocode.read_overrides(p)


def test_unknown_county_is_an_error(inputs, tmp_path):
    geom = geocode.FileGeometry(inputs["nhd"], inputs["counties"], "06")
    with pytest.raises(ValueError, match="not in the TIGER/Line file"):
        geom.in_counties((-119.5, 38.5), ["Gamma"])
    # Beta's first ring is a far-off island; the bounding box covers both.
    assert geom.in_counties((-118.5, 38.5), ["Beta"])
    assert geom.in_counties((-117.45, 38.05), ["Beta"])
    assert not geom.in_counties((-117.5, 38.5), ["Alpha"])  # Nevada's Alpha


# --- names --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Crowley Lake", "lake"),
        ("Lake Isabella", "lake"),
        ("Blue Lake Upper", "lake"),
        ("Kern River South Fork", "stream"),
        ("Lyons Canal", "canal"),
        ("Broodfish Waters", "unknown"),
        ("Upper", "unknown"),
        ("Trinity Lake (Clair Engle Lake)", "lake"),
    ],
)
def test_water_kind(name, kind):
    assert geocode.water_kind(name) == kind


def test_normalize_folds_punctuation_but_keeps_number_sign():
    assert geocode.normalize("St. Mary's  Lake") == "st marys lake"
    assert geocode.normalize("Fork #2 & Pond") == "fork #2 and pond"


def _plan(name: str, *aliases: str) -> geocode.NamePlan:
    return geocode.name_plan(geocode.Water(1, name, aliases, ("Alpha",)))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Blue Lake Upper", ("Upper Blue Lake", "reordered")),
        ("Salmon Lake, Upper", ("Upper Salmon Lake", "reordered")),
        ("Kern River South Fork", ("South Fork Kern River", "reordered")),
        ("Bishop Creek, Middle Fork", ("Middle Fork Bishop Creek", "reordered")),
        ("Lake Isabella", ("Isabella Lake", "lake word swapped")),
        ("Lake Isabella", ("Isabella Reservoir", "lake word swapped")),
        ("Pine Flat Reservoir", ("Pine Flat Lake", "lake word swapped")),
        ("Pine Flat Reservoir", ("Lake Pine Flat", "lake word swapped")),
        ("Twin Lakes, Mammoth", ("Twin Lakes", "locality dropped")),
    ],
)
def test_derived_names(name, expected):
    assert expected in _plan(name).derived


def test_parenthetical_names_are_tried_literally():
    plan = _plan("Trinity Lake (Clair Engle Lake)")
    assert ("Trinity Lake", "parenthetical") in plan.literal
    assert ("Clair Engle Lake", "parenthetical") in plan.literal
    assert plan.reach is None


def test_aliases_come_before_variants():
    plan = _plan("Lake Isabella", "Isabella Reservoir", "Lake Isabella")
    assert plan.literal == (
        ("Lake Isabella", "name"),
        ("Isabella Reservoir", "alias"),
    )


@pytest.mark.parametrize(
    ("name", "reach"),
    [
        ("Owens River, Section 2", "Section 2"),
        ("Bishop Creek, Intake II", "Intake II"),
        ("Kings River (below Pine Flat)", "below Pine Flat"),
        ("Lower Owens River", "lower"),
        ("Fish Creek #2", "#2"),
        ("Kern River South Fork", None),
        ("Granite Creek (West Fork)", None),
        ("Middle Fork Feather River", None),
        ("Lower Blue Lake", None),
    ],
)
def test_stream_reaches_are_detected(name, reach):
    assert _plan(name).reach == reach


def test_reorder_and_swap_helpers_decline_what_they_do_not_fit():
    assert geocode._reorder_trailing("Lake", geocode.POSITION) is None
    assert geocode._reorder_fork("Owens River") is None
    assert geocode._swap_lake_word("Owens River") == []
    assert geocode._split_paren("Owens River") == ("Owens River", None)


def test_waters_from_snapshot_and_gnis_reader(inputs):
    waters = geocode.waters_from_snapshot(
        json.loads(inputs["snapshot"].read_text(encoding="utf-8"))
    )
    assert waters[0] == geocode.Water(101, "Crescent Lake", (), ("Alpha",))
    feats = geocode.read_gnis(inputs["gnis"])
    assert feats[0].name == "Crescent Lake"
    gone = next(f for f in feats if f.feature_id == 9)
    assert (gone.lat, gone.lon) == (None, None)
    assert gone.to_json()["gnis_point"] is None
    assert geocode._float_or_none("") is None


# --- geometry -------------------------------------------------------------------


def test_wkb_handles_points_ewkb_z_and_big_endian():
    assert geo.parse_wkb(struct.pack("<BIdd", 1, 1, 1.0, 2.0)) == ([], [[(1.0, 2.0)]])
    ewkb = struct.pack("<BI", 1, 0x80000002) + struct.pack("<I3d", 1, 1, 2, 3)
    assert geo.parse_wkb(ewkb) == ([], [[(1.0, 2.0)]])
    big = struct.pack(">BII2d", 0, 2, 1, 5.0, 6.0)
    assert geo.parse_wkb(big)[1] == [[(5.0, 6.0)]]


@pytest.mark.parametrize(
    ("blob", "message"),
    [
        (struct.pack("<BI", 1, 7), "unsupported WKB geometry type 7"),
        (struct.pack("<BI", 1, 5002), "dimension"),
        (struct.pack("<BII", 1, 2, 3), "ends early"),
    ],
)
def test_wkb_errors(blob, message):
    with pytest.raises(geo.GeometryError, match=message):
        geo.parse_wkb(blob)


def test_gpkg_header_errors():
    with pytest.raises(geo.GeometryError, match="not a GeoPackage"):
        geo.gpkg_to_wkb(b"XX")
    with pytest.raises(geo.GeometryError, match="envelope"):
        geo.gpkg_to_wkb(b"GP\x00" + bytes([7 << 1]) + b"\0" * 8)


def test_contains_excludes_holes():
    poly = geo.Polygon((square(0, 0, 10, 10), square(4, 4, 6, 6)))
    assert geo.contains(poly, (1, 1))
    assert not geo.contains(poly, (5, 5))
    assert not geo.contains(poly, (11, 5))
    assert geo.polygon_area(poly) < geo.ring_area(square(0, 0, 10, 10))
    assert geo.ring_area([(0, 0), (1, 1)]) == 0.0


def test_pole_avoids_holes_and_degenerate_polygons_fail():
    poly = geo.Polygon((square(0, 0, 10, 10), square(3, 3, 7, 7)))
    pt = geo.pole_of_inaccessibility(poly)
    assert geo.contains(poly, pt)
    assert geo.pole_of_inaccessibility(geo.Polygon(([(1, 1), (1, 1)],))) == (1, 1)
    with pytest.raises(geo.GeometryError, match="no interior point"):
        geo.pole_of_inaccessibility(
            geo.Polygon(([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],) * 2)
        )


def test_nearest_vertex_needs_vertices():
    with pytest.raises(geo.GeometryError, match="no vertices"):
        geo.nearest_vertex_to_center([])


def test_shapefile_errors(tmp_path):
    shp = tmp_path / "x.shp"
    write_shapefile(shp, [({"STATEFP": "06", "NAME": "A"}, [square(0, 0, 1, 1)])])
    null_rec = struct.pack(">ii", 2, 2) + struct.pack("<i", 0)
    shp.write_bytes(shp.read_bytes() + null_rec)
    with pytest.raises(geo.GeometryError, match="2 shapes, 1 rows"):
        geo.read_shapefile(shp)
    pt_rec = struct.pack(">ii", 1, 10) + struct.pack("<i2d", 1, 0, 0)
    shp.write_bytes(b"\0" * 100 + pt_rec)
    with pytest.raises(geo.GeometryError, match="not a polygon"):
        geo.read_shapefile(shp)


def test_null_shape_is_read_as_none(tmp_path):
    shp = tmp_path / "x.shp"
    write_shapefile(shp, [({"STATEFP": "06", "NAME": "A"}, [square(0, 0, 1, 1)])])
    shp.write_bytes(b"\0" * 100 + struct.pack(">ii", 1, 2) + struct.pack("<i", 0))
    assert geo.read_shapefile(shp) == [({"STATEFP": "06", "NAME": "A"}, None)]


# --- locations (what the snapshot reads) --------------------------------------------


def test_locations_round_trip(inputs, tmp_path):
    run_cli(inputs, tmp_path)
    locs = locations.load_locations(tmp_path / "locations.json")
    assert sorted(locs) == [101, 102, 105]
    loc = locations.location_for(locs, 102)
    assert loc is not None
    assert set(loc) == set(locations.LOCATION_KEYS)
    loc["lat"] = 0  # a copy: the loaded table is not changed
    assert locs[102]["lat"] == 38.2
    assert locations.location_for(locs, 103) is None


def _doc(**water: object) -> dict:
    base = {
        "cdfw_stock_id": 1,
        "status": "exact",
        "location": {
            "lat": 38.0,
            "lon": -120.0,
            "source": "x",
            "kind": "waterbody",
            "source_feature_id": "1",
        },
    }
    return {"schema": geocode.LOCATIONS_SCHEMA, "waters": [{**base, **water}]}


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        ({"schema": "nope", "waters": []}, "schema"),
        (_doc(status="ambiguous"), "ambiguous with a point"),
        (_doc(location={"lat": 1}), "location must have"),
        (
            _doc(
                location={
                    "lat": 47.6,
                    "lon": -122.3,
                    "source": "x",
                    "kind": "waterbody",
                    "source_feature_id": "1",
                }
            ),
            "not in California",
        ),
        (
            _doc(
                location={
                    "lat": 38.0,
                    "lon": -120.0,
                    "source": "x",
                    "kind": "guess",
                    "source_feature_id": "1",
                }
            ),
            "unknown kind",
        ),
    ],
)
def test_locations_refuses_bad_files(tmp_path, doc, message):
    p = tmp_path / "l.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        locations.load_locations(p)


def test_committed_locations_file_is_consistent():
    path = DATA / "water_locations.json"
    locs = locations.load_locations(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    statuses = [w["status"] for w in doc["waters"]]
    assert doc["counts"] == {s: statuses.count(s) for s in geocode.STATUS_ORDER}
    assert len(locs) == doc["counts"]["exact"] + doc["counts"]["owner_resolved"]
    ids = [w["cdfw_stock_id"] for w in doc["waters"]]
    assert len(ids) == len(set(ids))
    for w in doc["waters"]:
        if w["status"] == "ambiguous":
            assert len(w["candidates"]) > 1
            assert w["location"] is None
    overrides = geocode.read_overrides(DATA / "water_location_overrides.json")
    assert set(overrides) <= set(ids)
    # The report rendered from the committed file is what MATCH-REPORT.md shows.
    assert render_report(doc).startswith("# Water locations: match report")


def test_snapshot_v1_still_has_no_locations(tmp_path):
    """v1 is read by installed 1.0 builds: its location stays null."""
    snap = cli.run(
        fixture_path=str(
            Path(__file__).parent / "fixtures" / "schedule-fresh-2026-09-13.html"
        ),
        history_path=tmp_path / "history.json",
        aliases_path=tmp_path / "aliases.json",
        schema_path=REPO / "schema" / "snapshot.v1.json",
        site_out=tmp_path / "site",
        base_url="https://example.invalid/ca-fish-planting-alerts",
        fixture_fetched_at=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 13),
    )
    assert snap["waters"]
    assert all(w["location"] is None for w in snap["waters"])


class _NoFlowlines:
    """A Geometry where one stream has a mapped channel and its namesake has
    none, as GNIS 264220 and 267078 (North Fork Willow Creek, Madera) did."""

    def waterbodies(self, gnis_id: int) -> list[geo.Polygon]:
        return []

    def flowlines(self, gnis_id: int) -> list[geo.Ring]:
        return [[(-119.5, 37.3), (-119.4, 37.4)]] if gnis_id == 1 else []

    def in_counties(self, pt: geo.Point, counties) -> bool:
        return True


def test_a_second_same_name_stream_without_flowlines_still_counts():
    water = geocode.Water(7, "Willow Creek North Fork", (), ("Madera",))
    with_lines = geocode.GnisFeature(
        1, "North Fork Willow Creek", "Stream", "Madera", 34.3, -119.5
    )
    without = geocode.GnisFeature(
        2, "North Fork Willow Creek", "Stream", "Madera", 37.2, -119.4
    )
    elsewhere = geocode.GnisFeature(
        3, "North Fork Willow Creek", "Stream", "Fresno", 36.0, -119.0
    )
    geom = _NoFlowlines()
    alone = geocode.Gazetteer.build([with_lines, elsewhere])
    assert geocode.match_water(water, alone, geom)["status"] == "exact"
    both = geocode.Gazetteer.build([with_lines, without, elsewhere])
    result = geocode.match_water(water, both, geom)
    # Negative control: the second feature is what changed the answer, and the
    # one in another county (with no channel to test) is still left out.
    assert [c["gnis_feature_id"] for c in result["candidates"]] == [1, 2]
    assert result["status"] == "ambiguous"
    assert result["location"] is None
