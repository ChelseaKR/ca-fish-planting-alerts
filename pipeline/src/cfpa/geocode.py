"""Offline geocoder: CDFW water -> one point, from public-domain federal data.

Run by hand, never by the daily pipeline (``cfpa-geocode --help``). Inputs,
all downloaded once and read locally (docs/LICENSES-AND-ATTRIBUTION.md has
the terms, quoted, and the dates they were read):

- USGS GNIS Domestic Names for California (names, feature classes, county of
  each feature's primary point, the primary point itself);
- USGS National Hydrography Dataset (NHD) for California, GeoPackage
  (waterbody polygons and stream flowlines, each tagged with its GNIS id);
- Census TIGER/Line counties (only to test which county a point is in).

Rules (the point is to never guess):

1. A water is matched on its CDFW name or an alias, plus its county. A few
   mechanical name variants are tried only when the plain names find
   nothing: CDFW's "Blue Lake Upper" is GNIS's "Upper Blue Lake", "Kern River
   South Fork" is "South Fork Kern River", "Lake Isabella" is "Isabella Lake".
   Each match records which variant found it.
2. ``exact``: exactly one GNIS feature of a fitting class has that name in
   that county. ``ambiguous``: several do; none is picked and every candidate
   is listed. ``none``: no feature, or the CDFW name names a reach of a
   stream ("Section 2", "Lower", "below Tinnemaha"), which no federal dataset
   locates.
3. A lake's point is the interior point of its NHD polygon farthest from the
   shore (``kind: waterbody``); with no NHD polygon, GNIS's own primary point
   (``kind: named_point``). A stream's point is a vertex of its NHD flowlines,
   central to its course inside the listed county (``kind: stream_point``),
   and readers must call it approximate.
4. The owner settles ambiguous or wrong matches in
   ``pipeline/data/water_location_overrides.json``; an override names the GNIS
   feature (or none), who decided, when, and why.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from . import geo

Kind = Literal["lake", "stream", "canal", "unknown"]
Status = Literal["exact", "ambiguous", "none", "owner_resolved", "owner_none"]

LOCATIONS_SCHEMA = "cfpa-water-locations-v1"
OVERRIDES_SCHEMA = "cfpa-water-location-overrides-v1"

CLASSES: dict[Kind, frozenset[str]] = {
    "lake": frozenset({"Lake", "Reservoir"}),
    "stream": frozenset({"Stream"}),
    "canal": frozenset({"Canal"}),
    "unknown": frozenset({"Lake", "Reservoir", "Stream", "Canal"}),
}
LINEAR = CLASSES["stream"] | CLASSES["canal"]

POSITION = frozenset({"upper", "lower", "middle", "north", "south", "east", "west"})
REACH_WORDS = frozenset({"upper", "lower", "middle"})
LAKE_WORDS = frozenset(
    {"lake", "lakes", "reservoir", "pond", "ponds", "lagoon", "forebay", "afterbay"}
)
STREAM_WORDS = frozenset({"creek", "river", "stream", "fork", "branch"})
CANAL_WORDS = frozenset({"canal", "ditch"})

SOURCE_NHD = "USGS National Hydrography Dataset"
SOURCE_GNIS = "USGS Geographic Names Information System"


def normalize(name: str) -> str:
    """Case, quotes, periods and punctuation folded; '#' kept ("Fork #2")."""
    s = name.casefold().replace("&", " and ")
    s = re.sub("[\"'\u2019.]", "", s)
    s = re.sub(r"[^a-z0-9#]+", " ", s)
    return " ".join(s.split())


@dataclasses.dataclass(frozen=True, slots=True)
class GnisFeature:
    feature_id: int
    name: str
    feature_class: str
    county: str
    lat: float | None
    lon: float | None

    def to_json(self) -> dict[str, Any]:
        return {
            "gnis_feature_id": self.feature_id,
            "name": self.name,
            "class": self.feature_class,
            "county": self.county,
            "gnis_point": None
            if self.lat is None or self.lon is None
            else {"lat": round(self.lat, 5), "lon": round(self.lon, 5)},
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Water:
    stock_id: int
    name: str
    aliases: tuple[str, ...]
    counties: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Override:
    stock_id: int
    gnis_feature_id: int | None
    resolved_by: str
    resolved_on: str
    note: str


class Geometry(Protocol):
    """Where geometry comes from; the real one reads NHD + TIGER files."""

    def waterbodies(self, gnis_id: int) -> list[geo.Polygon]: ...

    def flowlines(self, gnis_id: int) -> list[geo.Ring]: ...

    def in_counties(self, pt: geo.Point, counties: Sequence[str]) -> bool: ...


# --- reading inputs -----------------------------------------------------------


def _float_or_none(s: str) -> float | None:
    try:
        v = float(s)
    except ValueError:
        return None
    return None if v == 0 else v


def read_gnis(path: Path) -> list[GnisFeature]:
    """GNIS Domestic Names, pipe-delimited, BOM-prefixed (GNIS file format)."""
    out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter="|"):
            out.append(
                GnisFeature(
                    feature_id=int(row["feature_id"]),
                    name=row["feature_name"],
                    feature_class=row["feature_class"],
                    county=row["county_name"],
                    lat=_float_or_none(row["prim_lat_dec"]),
                    lon=_float_or_none(row["prim_long_dec"]),
                )
            )
    return out


def waters_from_snapshot(snapshot: Mapping[str, Any]) -> list[Water]:
    return [
        Water(
            stock_id=int(w["cdfw_stock_id"]),
            name=str(w["name"]),
            aliases=tuple(str(a) for a in w["aliases"]),
            counties=tuple(str(c) for c in w["counties"]),
        )
        for w in snapshot["waters"]
    ]


def read_overrides(path: Path) -> dict[int, Override]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != OVERRIDES_SCHEMA:
        raise ValueError(f"{path}: schema is not {OVERRIDES_SCHEMA}")
    out: dict[int, Override] = {}
    for o in data["overrides"]:
        for key in ("resolved_by", "resolved_on", "note"):
            if not str(o.get(key, "")).strip():
                raise ValueError(f"override for {o.get('cdfw_stock_id')}: no {key}")
        dt.date.fromisoformat(o["resolved_on"])
        sid = int(o["cdfw_stock_id"])
        if sid in out:
            raise ValueError(f"two overrides for cdfw-{sid}")
        gid = o["gnis_feature_id"]
        out[sid] = Override(
            sid,
            None if gid is None else int(gid),
            o["resolved_by"],
            o["resolved_on"],
            o["note"],
        )
    return out


# --- names --------------------------------------------------------------------


def _base(name: str) -> str:
    return re.split(r"[(,]", name, maxsplit=1)[0].strip()


def water_kind(name: str) -> Kind:
    """Lake, stream or canal, from the head word of the name's base part."""
    words = normalize(_base(name)).split()
    while words and (words[-1] in POSITION or re.fullmatch(r"#\d+", words[-1])):
        words.pop()
    if not words:
        return "unknown"
    if words[0] in {"lake", "reservoir"} or words[-1] in LAKE_WORDS:
        return "lake"
    if words[-1] in CANAL_WORDS:
        return "canal"
    if words[-1] in STREAM_WORDS:
        return "stream"
    return "unknown"


@dataclasses.dataclass(frozen=True, slots=True)
class NamePlan:
    """Names to try, in two tiers, or the reach that makes a match impossible."""

    literal: tuple[tuple[str, str], ...]  # (name, method)
    derived: tuple[tuple[str, str], ...]
    reach: str | None


_PAREN_RE = re.compile(r"^(?P<pre>.*?)\s*\((?P<inside>[^)]*)\)\s*(?P<post>.*)$")
_FORK_RE = re.compile(r"(\S+\s+)?(fork|branch)", re.I)
_REACH_RE = re.compile(
    r"\b(section|below|above|intake|camp|bar|falls|ll|ii|iii|iv)\b|#\s*\d+", re.I
)


def _split_paren(name: str) -> tuple[str, str | None]:
    m = _PAREN_RE.match(name)
    if not m:
        return name, None
    outside = " ".join(f"{m['pre']} {m['post']}".split())
    return outside, m["inside"].strip()


def _reorder_trailing(name: str, words: frozenset[str]) -> str | None:
    """'Blue Lake Upper' -> 'Upper Blue Lake' when the tail is in ``words``."""
    parts = name.split()
    tail: list[str] = []
    while len(parts) > 1 and parts[-1].casefold() in words:
        tail.insert(0, parts.pop())
    return " ".join([*tail, *parts]) if tail else None


def _reorder_fork(name: str) -> str | None:
    """'Kern River South Fork' -> 'South Fork Kern River'."""
    m = re.match(r"^(?P<stem>.+?)\s+(?P<fork>\S+\s+(?:Fork|Branch))$", name, re.I)
    if not m:
        return None
    return f"{m['fork']} {m['stem']}"


def _swap_lake_word(name: str) -> list[str]:
    """The other two ways a lake's name is written.

    'Lake Isabella' -> 'Isabella Lake', 'Isabella Reservoir';
    'Pine Flat Reservoir' -> 'Pine Flat Lake', 'Lake Pine Flat'. CDFW and
    GNIS often disagree on exactly this (GNIS: "Pine Flat Lake", "Tulloch
    Reservoir", "Lake Success"; CDFW: "Pine Flat Reservoir", "Tulloch Lake",
    "Success Reservoir").
    """
    m = re.match(r"^Lake\s+(.+)$", name, re.I)
    if m:
        return [f"{m[1]} Lake", f"{m[1]} Reservoir"]
    m = re.match(r"^(.+?)\s+(Lake|Reservoir)$", name, re.I)
    if m:
        other = "Reservoir" if m[2].casefold() == "lake" else "Lake"
        return [f"{m[1]} {other}", f"Lake {m[1]}"]
    return []


def _stream_reach(kind: Kind, name: str, qualifier: str | None) -> str | None:
    """The words that make a stream name a reach, or None."""
    if kind not in ("stream", "canal"):
        return None
    if qualifier is not None and not _FORK_RE.fullmatch(qualifier.strip()):
        return qualifier
    words = normalize(name).split()
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w in REACH_WORDS and nxt not in {"fork", "branch"}:
            return w
    m = _REACH_RE.search(f"{name} {qualifier or ''}")
    return m.group(0) if m else None


def name_plan(water: Water) -> NamePlan:
    """The names to look up for a water, most literal first."""
    kind = water_kind(water.name)
    literal: list[tuple[str, str]] = [(water.name, "name")]
    literal += [(a, "alias") for a in water.aliases if a != water.name]
    derived: list[tuple[str, str]] = []
    reach: str | None = None
    for full, _ in list(literal):
        outside, inside = _split_paren(full)
        if inside is not None:
            if water_kind(inside) != "unknown" and not _FORK_RE.fullmatch(inside):
                literal += [(outside, "parenthetical"), (inside, "parenthetical")]
                continue
            outside = f"{outside}, {inside}"
        stem, _, qualifier = (s.strip() for s in outside.partition(","))
        reach = reach or _stream_reach(kind, stem, qualifier or None)
        derived += _derive(stem, qualifier or None, kind)
    return NamePlan(tuple(_dedupe(literal)), tuple(_dedupe(derived)), reach)


def _derive(stem: str, qualifier: str | None, kind: Kind) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if qualifier is not None:
        if all(w.casefold() in POSITION for w in qualifier.split()) or (
            _FORK_RE.fullmatch(qualifier)
        ):
            out.append((f"{qualifier} {stem}", "reordered"))
        elif kind in ("lake", "unknown"):
            out.append((stem, "locality dropped"))
    for b in [stem] + [n for n, _ in out]:
        for alt in (_reorder_trailing(b, POSITION), _reorder_fork(b)):
            if alt:
                out.append((alt, "reordered"))
    for b in [stem] + [n for n, _ in out]:
        out += [(s, "lake word swapped") for s in _swap_lake_word(b)]
    return out


def _dedupe(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out = []
    for name, method in items:
        key = normalize(name)
        if key and key not in seen:
            seen.add(key)
            out.append((name, method))
    return out


# --- matching -------------------------------------------------------------------


@dataclasses.dataclass(slots=True)
class Gazetteer:
    by_name: dict[str, list[GnisFeature]]
    by_id: dict[int, GnisFeature]

    @classmethod
    def build(cls, features: Iterable[GnisFeature]) -> Gazetteer:
        by_name: dict[str, list[GnisFeature]] = defaultdict(list)
        by_id: dict[int, GnisFeature] = {}
        for f in features:
            by_name[normalize(f.name)].append(f)
            by_id[f.feature_id] = f
        return cls(dict(by_name), by_id)

    def named(self, names: Iterable[tuple[str, str]]) -> set[int]:
        return {
            f.feature_id for n, _ in names for f in self.by_name.get(normalize(n), [])
        }


def _fits(f: GnisFeature, kind: Kind) -> bool:
    return f.feature_class in CLASSES[kind]


def candidates_for(
    water: Water,
    names: Sequence[tuple[str, str]],
    gaz: Gazetteer,
    geom: Geometry,
) -> list[tuple[GnisFeature, str, str]]:
    """(feature, name used, method) for every fitting feature in the county."""
    kind = water_kind(water.name)
    out: list[tuple[GnisFeature, str, str]] = []
    seen: set[int] = set()
    for name, method in names:
        for f in gaz.by_name.get(normalize(name), []):
            if f.feature_id in seen or not _fits(f, kind):
                continue
            if _in_water_counties(f, water, geom):
                seen.add(f.feature_id)
                out.append((f, name, method))
    return out


def _in_water_counties(f: GnisFeature, water: Water, geom: Geometry) -> bool:
    if f.feature_class in LINEAR:
        # GNIS places a stream at its mouth; the planted water may be upstream
        # in another county, so test the mapped channel itself.
        lines = geom.flowlines(f.feature_id)
        if not lines:
            # No mapped channel to test, so the only evidence is GNIS's own
            # county. Dropping the feature here let a second same-name
            # stream in the county go uncounted (hand review 2026-10-20:
            # North Fork Willow Creek, Madera), so it stays a candidate and
            # ``locate`` then declines to place it.
            return f.county in water.counties
        return bool(_lines_in_counties(lines, water, geom))
    return f.county in water.counties


def _lines_in_counties(
    lines: Sequence[geo.Ring], water: Water, geom: Geometry
) -> list[geo.Ring]:
    """The runs of each line whose vertices fall inside the water's counties."""
    runs: list[geo.Ring] = []
    for line in lines:
        run: geo.Ring = []
        for p in line:
            if geom.in_counties(p, water.counties):
                run.append(p)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
    return runs


def locate(
    f: GnisFeature, water: Water, geom: Geometry
) -> tuple[dict[str, Any] | None, str | None]:
    """(location, None) or (None, reason) for one chosen GNIS feature."""
    if f.feature_class in LINEAR:
        runs = _lines_in_counties(geom.flowlines(f.feature_id), water, geom)
        if not runs:
            return None, "the stream's NHD flowlines do not enter the listed county"
        pt = geo.nearest_vertex_to_center(runs)
        return _loc(pt, SOURCE_NHD, "stream_point", f), None
    polys = geom.waterbodies(f.feature_id)
    if polys:
        largest = max(polys, key=geo.polygon_area)
        pt = geo.pole_of_inaccessibility(largest)
        kind, source = "waterbody", SOURCE_NHD
    elif f.lat is not None and f.lon is not None:
        pt = (f.lon, f.lat)
        kind, source = "named_point", SOURCE_GNIS
    else:
        return None, "GNIS has no point and NHD no polygon for this feature"
    if not geom.in_counties(pt, water.counties):
        return None, "the point falls outside the county CDFW lists"
    return _loc(pt, source, kind, f), None


def _loc(pt: geo.Point, source: str, kind: str, f: GnisFeature) -> dict[str, Any]:
    return {
        "lat": round(pt[1], 5),
        "lon": round(pt[0], 5),
        "source": source,
        "kind": kind,
        "source_feature_id": str(f.feature_id),
    }


def _near_misses(water: Water, plan: NamePlan, gaz: Gazetteer) -> list[dict[str, Any]]:
    """Same-name, fitting-class features anywhere in the file (at most 5)."""
    kind = water_kind(water.name)
    found = {
        f.feature_id: f
        for n, _ in (*plan.literal, *plan.derived)
        for f in gaz.by_name.get(normalize(n), [])
        if _fits(f, kind)
    }
    return [found[k].to_json() for k in sorted(found)][:5]


def match_water(
    water: Water,
    gaz: Gazetteer,
    geom: Geometry,
    override: Override | None = None,
) -> dict[str, Any]:
    """One water's result record."""
    plan = name_plan(water)
    rec: dict[str, Any] = {
        "cdfw_stock_id": water.stock_id,
        "name": water.name,
        "counties": list(water.counties),
        "kind": water_kind(water.name),
        "status": "none",
        "matched_name": None,
        "method": None,
        "location": None,
        "candidates": [],
        "near_misses": [],
        "reason": None,
    }
    if override is not None:
        return _apply_override(rec, water, override, gaz, geom)
    if plan.reach is not None:
        rec["reason"] = (
            f"names a reach of a stream ({plan.reach!r}); no federal dataset "
            "marks where CDFW's reaches start and end"
        )
        rec["near_misses"] = _near_misses(water, plan, gaz)
        return rec
    found = candidates_for(water, plan.literal, gaz, geom) or candidates_for(
        water, plan.derived, gaz, geom
    )
    if not found:
        rec["reason"] = "no GNIS feature with this name in the listed county"
        rec["near_misses"] = _near_misses(water, plan, gaz)
        return rec
    rec["candidates"] = [_candidate_json(f, water, geom) for f, _, _ in found]
    if len(found) > 1:
        rec["status"] = "ambiguous"
        rec["reason"] = f"{len(found)} GNIS features with this name in the county"
        return rec
    f, name, method = found[0]
    loc, reason = locate(f, water, geom)
    rec.update(matched_name=name, method=method, location=loc, reason=reason)
    rec["status"] = "exact" if loc is not None else "none"
    return rec


def _candidate_json(f: GnisFeature, water: Water, geom: Geometry) -> dict[str, Any]:
    c = f.to_json()
    loc, _ = locate(f, water, geom)
    c["would_be"] = loc
    return c


def _apply_override(
    rec: dict[str, Any],
    water: Water,
    o: Override,
    gaz: Gazetteer,
    geom: Geometry,
) -> dict[str, Any]:
    rec["override"] = {
        "gnis_feature_id": o.gnis_feature_id,
        "resolved_by": o.resolved_by,
        "resolved_on": o.resolved_on,
        "note": o.note,
    }
    if o.gnis_feature_id is None:
        rec["status"] = "owner_none"
        rec["reason"] = "owner: no location"
        return rec
    f = gaz.by_id.get(o.gnis_feature_id)
    if f is None:
        raise ValueError(
            f"override for cdfw-{water.stock_id}: GNIS {o.gnis_feature_id} not found"
        )
    loc, reason = locate(f, water, geom)
    if loc is None:
        raise ValueError(f"override for cdfw-{water.stock_id}: {reason}")
    rec.update(
        status="owner_resolved",
        matched_name=f.name,
        method="owner override",
        location=loc,
        candidates=[f.to_json()],
    )
    return rec


# --- real geometry --------------------------------------------------------------


class FileGeometry:
    """NHD GeoPackage + TIGER/Line counties, read once, cached in memory."""

    def __init__(self, nhd_gpkg: Path, counties_shp: Path, state_fips: str) -> None:
        self._db = sqlite3.connect(f"file:{nhd_gpkg}?mode=ro", uri=True)
        self._wb: dict[int, list[geo.Polygon]] = {}
        self._fl: dict[int, list[geo.Ring]] = {}
        self._counties: dict[str, list[tuple[geo.BBox, geo.Polygon]]] = defaultdict(
            list
        )
        for attrs, poly in geo.read_shapefile(counties_shp):
            if attrs.get("STATEFP") == state_fips and poly is not None:
                self._counties[attrs["NAME"]].append((geo.bbox(poly), poly))

    def prefetch(self, gnis_ids: Iterable[int]) -> None:
        """Load every needed geometry in one scan per NHD table (no index)."""
        keys = {f"{i:08d}": i for i in gnis_ids}
        wb: dict[int, list[geo.Polygon]] = defaultdict(list)
        fl: dict[int, list[geo.Ring]] = defaultdict(list)
        for gid, blob in self._db.execute(
            "SELECT gnis_id, SHAPE FROM NHDWaterbody WHERE gnis_id IS NOT NULL"
        ):
            if gid in keys and blob is not None:
                wb[keys[gid]].extend(geo.parse_gpkg(blob)[0])
        for gid, blob in self._db.execute(
            "SELECT gnis_id, SHAPE FROM NHDFlowline WHERE gnis_id IS NOT NULL"
        ):
            if gid in keys and blob is not None:
                fl[keys[gid]].extend(geo.parse_gpkg(blob)[1])
        self._wb, self._fl = dict(wb), dict(fl)

    def waterbodies(self, gnis_id: int) -> list[geo.Polygon]:
        return self._wb.get(gnis_id, [])

    def flowlines(self, gnis_id: int) -> list[geo.Ring]:
        return self._fl.get(gnis_id, [])

    def in_counties(self, pt: geo.Point, counties: Sequence[str]) -> bool:
        for c in counties:
            if c not in self._counties:
                raise ValueError(f"county {c!r} is not in the TIGER/Line file")
            for box, poly in self._counties[c]:
                if geo.in_bbox(box, pt) and geo.contains(poly, pt):
                    return True
        return False


# --- output -----------------------------------------------------------------------

USGS_TERMS_URL = (
    "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"
)
INPUTS = [
    {
        "name": "USGS GNIS Domestic Names, California (published 2026-09-29)",
        "url": "https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/DomesticNames_CA_Text.zip",
        "terms_url": USGS_TERMS_URL,
        "terms": "U.S. Public Domain; file metadata use constraints: None.",
    },
    {
        "name": "USGS National Hydrography Dataset (NHD), California, GeoPackage (published 2023-12-27)",
        "url": "https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHD/State/GPKG/NHD_H_California_State_GPKG.zip",
        "terms_url": USGS_TERMS_URL,
        "terms": "U.S. Public Domain; file metadata use constraints: None.",
    },
    {
        "name": "U.S. Census Bureau TIGER/Line Shapefiles 2024, Counties",
        "url": "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip",
        "terms_url": "https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/",
        "terms": "Not copyrighted; acknowledgement of the U.S. Census Bureau required.",
    },
]

STATUS_ORDER: tuple[Status, ...] = (
    "exact",
    "owner_resolved",
    "ambiguous",
    "none",
    "owner_none",
)


def build_document(
    results: list[dict[str, Any]], generated_on: dt.date, read_on: Mapping[str, str]
) -> dict[str, Any]:
    counts = {s: sum(1 for r in results if r["status"] == s) for s in STATUS_ORDER}
    return {
        "schema": LOCATIONS_SCHEMA,
        "generated_on": generated_on.isoformat(),
        "inputs": [{**i, **read_on} for i in INPUTS],
        "counts": counts,
        "waters": sorted(results, key=lambda r: r["cdfw_stock_id"]),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    waters = waters_from_snapshot(snapshot)
    gaz = Gazetteer.build(read_gnis(Path(args.gnis)))
    overrides = read_overrides(Path(args.overrides))
    geom = FileGeometry(Path(args.nhd), Path(args.counties), "06")
    wanted: set[int] = set()
    for w in waters:
        plan = name_plan(w)
        wanted |= gaz.named((*plan.literal, *plan.derived))
    wanted |= {o.gnis_feature_id for o in overrides.values() if o.gnis_feature_id}
    geom.prefetch(wanted)
    results = [match_water(w, gaz, geom, overrides.get(w.stock_id)) for w in waters]
    read_on = {"terms_read_on": args.terms_read_on, "downloaded_on": args.downloaded_on}
    return build_document(results, dt.date.fromisoformat(args.generated_on), read_on)


def main(argv: list[str] | None = None) -> int:
    from .geocode_report import render_report

    p = argparse.ArgumentParser(prog="cfpa-geocode", description=__doc__)
    p.add_argument("--snapshot", required=True, help="a published snapshot v1.json")
    p.add_argument("--gnis", required=True, help="DomesticNames_CA.txt")
    p.add_argument("--nhd", required=True, help="NHD_H_California_State_GPKG.gpkg")
    p.add_argument("--counties", required=True, help="tl_2024_us_county.shp")
    p.add_argument("--overrides", required=True)
    p.add_argument("--out", required=True, help="water_locations.json to write")
    p.add_argument("--report", required=True, help="Markdown match report to write")
    p.add_argument("--generated-on", required=True)
    p.add_argument("--terms-read-on", required=True)
    p.add_argument("--downloaded-on", required=True)
    args = p.parse_args(argv)
    doc = run(args)
    Path(args.out).write_text(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    Path(args.report).write_text(render_report(doc), encoding="utf-8")
    print("geocode: " + ", ".join(f"{k} {v}" for k, v in doc["counts"].items()))
    return 0
