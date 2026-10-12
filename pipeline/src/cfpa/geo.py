"""Small pure-Python geometry for the offline geocoder (``cfpa.geocode``).

Nothing here touches the network or the daily run. It reads the two file
formats the public-domain inputs ship in -- GeoPackage geometry blobs (USGS
NHD) and ESRI shapefiles (Census TIGER/Line counties) -- and does the three
operations the geocoder needs: point-in-polygon, a point inside a polygon
(the pole of inaccessibility, so a crescent-shaped reservoir never gets a pin
on dry land the way a centroid can), and a point on a line.

Coordinates stay in the inputs' own datum, NAD83 (EPSG:4269), which differs
from WGS84 by about one to two meters in California: far below what a map pin
can show, so no transformation is done.
"""

from __future__ import annotations

import heapq
import math
import struct
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

Point = tuple[float, float]  # (lon, lat)
Ring = list[Point]


@dataclass(frozen=True, slots=True)
class Polygon:
    """One polygon: an outer ring and zero or more holes, (lon, lat) pairs."""

    rings: tuple[Ring, ...]


class GeometryError(ValueError):
    """A geometry blob or file is not in the shape this module reads."""


# --- WKB / GeoPackage -------------------------------------------------------

_POINT, _LINESTRING, _POLYGON, _MULTILINESTRING, _MULTIPOLYGON = 1, 2, 3, 5, 6


def _wkb_type(raw: int) -> tuple[int, int]:
    """(base type, extra ordinates per point) for ISO and EWKB type codes."""
    extra = 0
    if raw & 0x80000000:
        extra += 1
    if raw & 0x40000000:
        extra += 1
    raw &= 0x0FFFFFFF
    base, dims = raw % 1000, raw // 1000
    extra += {0: 0, 1: 1, 2: 1, 3: 2}.get(dims, -1)
    if extra < 0 or extra > 2:
        raise GeometryError(f"unsupported WKB dimension code {raw}")
    return base, extra


class _Reader:
    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.pos = offset

    def take(self, fmt: str) -> tuple[float | int, ...]:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise GeometryError("geometry blob ends early")
        out = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return out


def _read_points(r: _Reader, order: str, extra: int) -> Ring:
    (n,) = r.take(order + "I")
    pts: Ring = []
    fmt = order + "d" * (2 + extra)
    for _ in range(int(n)):
        vals = r.take(fmt)
        pts.append((float(vals[0]), float(vals[1])))
    return pts


def _read_geometry(r: _Reader) -> tuple[int, list[Polygon], list[Ring]]:
    (bo,) = r.take("B")
    order = "<" if bo == 1 else ">"
    (raw,) = r.take(order + "I")
    base, extra = _wkb_type(int(raw))
    polygons: list[Polygon] = []
    lines: list[Ring] = []
    if base == _POINT:
        vals = r.take(order + "d" * (2 + extra))
        lines.append([(float(vals[0]), float(vals[1]))])
    elif base == _LINESTRING:
        lines.append(_read_points(r, order, extra))
    elif base == _POLYGON:
        (nrings,) = r.take(order + "I")
        rings = tuple(_read_points(r, order, extra) for _ in range(int(nrings)))
        polygons.append(Polygon(rings))
    elif base in (_MULTILINESTRING, _MULTIPOLYGON):
        (nparts,) = r.take(order + "I")
        for _ in range(int(nparts)):
            _, p, ln = _read_geometry(r)
            polygons.extend(p)
            lines.extend(ln)
    else:
        raise GeometryError(f"unsupported WKB geometry type {base}")
    return base, polygons, lines


def parse_wkb(data: bytes) -> tuple[list[Polygon], list[Ring]]:
    """Polygons and lines in a WKB geometry (ISO or EWKB, 2D/Z/M/ZM)."""
    _, polygons, lines = _read_geometry(_Reader(data))
    return polygons, lines


_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def gpkg_to_wkb(blob: bytes) -> bytes:
    """Strip the GeoPackage binary header (GPKG spec 2.1.3) off a geometry."""
    if len(blob) < 8 or blob[:2] != b"GP":
        raise GeometryError("not a GeoPackage geometry blob")
    flags = blob[3]
    env = (flags >> 1) & 0b111
    if env not in _ENVELOPE_BYTES:
        raise GeometryError(f"bad GeoPackage envelope code {env}")
    return blob[8 + _ENVELOPE_BYTES[env] :]


def parse_gpkg(blob: bytes) -> tuple[list[Polygon], list[Ring]]:
    return parse_wkb(gpkg_to_wkb(blob))


# --- shapefile (polygons only) + dBase ---------------------------------------


def _dbf_records(path: Path) -> list[dict[str, str]]:
    data = path.read_bytes()
    nrec, hlen, rlen = struct.unpack_from("<IHH", data, 4)
    fields: list[tuple[str, int]] = []
    pos = 32
    while data[pos] != 0x0D:
        name = data[pos : pos + 11].split(b"\0", 1)[0].decode("ascii")
        fields.append((name, data[pos + 16]))
        pos += 32
    out = []
    for i in range(nrec):
        rec = data[hlen + i * rlen : hlen + (i + 1) * rlen]
        off = 1  # deletion flag
        row = {}
        for name, length in fields:
            row[name] = rec[off : off + length].decode("utf-8", "replace").strip()
            off += length
        out.append(row)
    return out


def _shp_polygons(path: Path) -> Iterator[Polygon | None]:
    data = path.read_bytes()
    pos = 100
    while pos + 8 <= len(data):
        (_, clen) = struct.unpack_from(">ii", data, pos)
        content = data[pos + 8 : pos + 8 + clen * 2]
        pos += 8 + clen * 2
        (stype,) = struct.unpack_from("<i", content, 0)
        if stype == 0:
            yield None
            continue
        if stype not in (5, 15, 25):
            raise GeometryError(f"shapefile record type {stype} is not a polygon")
        nparts, npoints = struct.unpack_from("<ii", content, 36)
        parts = list(struct.unpack_from(f"<{nparts}i", content, 44))
        base = 44 + 4 * nparts
        coords = struct.unpack_from(f"<{2 * npoints}d", content, base)
        pts = [(coords[2 * k], coords[2 * k + 1]) for k in range(npoints)]
        bounds = [*parts, npoints]
        rings = tuple(pts[bounds[k] : bounds[k + 1]] for k in range(nparts))
        yield Polygon(rings)


def read_shapefile(shp: Path) -> list[tuple[dict[str, str], Polygon | None]]:
    """(attributes, polygon) per record of a polygon shapefile and its .dbf."""
    attrs = _dbf_records(shp.with_suffix(".dbf"))
    shapes = list(_shp_polygons(shp))
    if len(attrs) != len(shapes):
        raise GeometryError(f"{shp.name}: {len(shapes)} shapes, {len(attrs)} rows")
    return list(zip(attrs, shapes, strict=True))


# --- operations ---------------------------------------------------------------


BBox = tuple[float, float, float, float]  # min lon, min lat, max lon, max lat


def bbox(polygon: Polygon) -> BBox:
    """Bounds over every ring: a shapefile record can hold several outer
    rings (a county with islands), and any of them may hold the point."""
    xs = [p[0] for ring in polygon.rings for p in ring]
    ys = [p[1] for ring in polygon.rings for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def in_bbox(box: BBox, pt: Point) -> bool:
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def _ring_contains(ring: Sequence[Point], x: float, y: float) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(polygon: Polygon, pt: Point) -> bool:
    """Even-odd point-in-polygon over every ring (holes excluded)."""
    inside = False
    for ring in polygon.rings:
        if _ring_contains(ring, pt[0], pt[1]):
            inside = not inside
    return inside


def _scale(lat: float) -> float:
    # Degrees of longitude shrink with latitude; scale x so distances are
    # comparable in both axes over one lake.
    return math.cos(math.radians(lat))


def ring_area(ring: Sequence[Point]) -> float:
    """Planar shoelace area in degrees^2, longitude scaled by cos(latitude)."""
    if len(ring) < 3:
        return 0.0
    k = _scale(sum(p[1] for p in ring) / len(ring))
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        s += (x1 * k) * y2 - (x2 * k) * y1
    return abs(s) / 2.0


def polygon_area(polygon: Polygon) -> float:
    outer, *holes = polygon.rings
    return ring_area(outer) - sum(ring_area(h) for h in holes)


def _seg_dist_sq(px: float, py: float, a: Point, b: Point) -> float:
    x, y = a
    dx, dy = b[0] - x, b[1] - y
    if dx != 0 or dy != 0:
        t = ((px - x) * dx + (py - y) * dy) / (dx * dx + dy * dy)
        if t > 1:
            x, y = b
        elif t > 0:
            x += dx * t
            y += dy * t
    dx, dy = px - x, py - y
    return dx * dx + dy * dy


def _signed_distance(polygon: Polygon, x: float, y: float) -> float:
    """Distance from (x, y) to the polygon's edge; negative when outside."""
    best = math.inf
    for ring in polygon.rings:
        for a, b in zip(ring, [*ring[1:], ring[0]], strict=True):
            best = min(best, _seg_dist_sq(x, y, a, b))
    d = math.sqrt(best)
    return d if contains(polygon, (x, y)) else -d


def pole_of_inaccessibility(polygon: Polygon, precision: float = 1e-4) -> Point:
    """The interior point farthest from the polygon's edge (polylabel).

    The algorithm is Mapbox's polylabel (ISC licensed idea, written fresh
    here): a quadtree search over cells, best-first by the most distance a
    cell could still hold. Works in longitude scaled by cos(latitude) so a
    "farthest" point is farthest on the ground, not in raw degrees. Always
    returns a point inside the polygon.
    """
    outer = polygon.rings[0]
    lat0 = sum(p[1] for p in outer) / len(outer)
    k = _scale(lat0)
    scaled = Polygon(tuple([(x * k, y) for x, y in ring] for ring in polygon.rings))
    xs = [p[0] for p in scaled.rings[0]]
    ys = [p[1] for p in scaled.rings[0]]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    size = min(maxx - minx, maxy - miny)
    if size == 0:
        return outer[0]
    h = size / 2

    def cell(
        cx: float, cy: float, ch: float
    ) -> tuple[float, float, float, float, float]:
        d = _signed_distance(scaled, cx, cy)
        return (-(d + ch * math.sqrt(2)), d, cx, cy, ch)

    heap = [
        cell(x + h, y + h, h)
        for x in _steps(minx, maxx, size)
        for y in _steps(miny, maxy, size)
    ]
    heapq.heapify(heap)

    # Start from the vertex average and the bounding-box center, whichever is
    # better; both may be outside, which the search fixes.
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    best = cell(cx, cy, 0)
    bbox = cell(minx + (maxx - minx) / 2, miny + (maxy - miny) / 2, 0)
    if bbox[1] > best[1]:
        best = bbox

    while heap:
        c = heapq.heappop(heap)
        if c[1] > best[1]:
            best = c
        if -c[0] - best[1] <= precision:
            continue
        ch = c[4] / 2
        for dx in (-ch, ch):
            for dy in (-ch, ch):
                heapq.heappush(heap, cell(c[2] + dx, c[3] + dy, ch))

    if best[1] <= 0:
        raise GeometryError("no interior point found (degenerate polygon)")
    return (best[2] / k, best[3])


def _steps(start: float, stop: float, step: float) -> list[float]:
    out = []
    v = start
    while v < stop:
        out.append(v)
        v += step
    return out


def nearest_vertex_to_center(lines: Sequence[Sequence[Point]]) -> Point:
    """A vertex on the lines, the one nearest the mean of all their vertices.

    For a stream this is a point that is really on the mapped channel and
    central to the part of it that was passed in; never a point off the water.
    """
    pts = [p for line in lines for p in line]
    if not pts:
        raise GeometryError("no vertices")
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    k = _scale(my)
    return min(pts, key=lambda p: ((p[0] - mx) * k) ** 2 + (p[1] - my) ** 2)
