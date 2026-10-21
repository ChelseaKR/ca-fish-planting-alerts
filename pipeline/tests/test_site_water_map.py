"""Water locations on the site (DECISIONS 0024): the "View on map" link, the
coordinates and structured-data ``geo`` on a water page, the static file of
coordinates, and the home page's "closest to me" button.

Built from the schedule fixture with the repository's own alias table (as the
smoke build does), so the fixture's waters are the real ones and the committed
``water_locations.json`` places some of them. Every check reads the page with
the standard library's HTML parser, never a regex over tags.

Every negative control asserts that its sabotage changed the input before it
asserts that the check caught it; a sabotage that silently no-ops would
otherwise read as a pass.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cfpa import cli, locations, site

FIXTURES = Path(__file__).parent / "fixtures"
MIDWEEK = FIXTURES / "schedule-midweek-2026-09-17.html"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "snapshot.v1.json"
BASE_URL = "https://example.invalid/ca-fish-planting-alerts"
TEST_ID = "G-TEST12345"
CLOSEST_JS = site.TEMPLATES_DIR / site.CLOSEST_JS_FILE


def _build(
    root: Path, *, ga4: str | None = None, with_locations: bool = True
) -> tuple[Path, dict[str, Any]]:
    shutil.copy(cli.DEFAULT_ALIASES_PATH, root / "aliases.json")
    out = root / "site"
    kwargs: dict[str, Any] = {}
    if not with_locations:
        kwargs["locations_path"] = None
    snap = cli.run(
        fixture_path=str(MIDWEEK),
        history_path=root / "history.json",
        aliases_path=root / "aliases.json",
        schema_path=SCHEMA_PATH,
        site_out=out,
        base_url=BASE_URL,
        fixture_fetched_at=dt.datetime(2026, 9, 18, 3, 10, 18, tzinfo=dt.UTC),
        run_today=dt.date(2026, 9, 18),
        ga4_measurement_id=ga4,
        **kwargs,
    )
    return out, snap


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    return _build(tmp_path_factory.mktemp("map"))


@pytest.fixture(scope="module")
def built_ga(tmp_path_factory: pytest.TempPathFactory):
    return _build(tmp_path_factory.mktemp("map-ga"), ga4=TEST_ID)


@pytest.fixture(scope="module")
def built_no_locations(tmp_path_factory: pytest.TempPathFactory):
    return _build(tmp_path_factory.mktemp("map-none"), with_locations=False)


class _Page(HTMLParser):
    """Links, scripts, table rows and the pieces of the closest-to-me section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str | None]] = []
        self.scripts: list[dict[str, Any]] = []
        self.external_loads: list[tuple[str, str]] = []
        self.section: dict[str, str | None] | None = None
        self.button: dict[str, str | None] | None = None
        self.row_slugs: list[str | None] = []
        self.table_links: list[str | None] = []
        self.text: list[str] = []
        self._script: dict[str, Any] | None = None
        self._table = 0
        self._body = 0
        self._link: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "script":
            self._script = {"attrs": a, "text": ""}
            self.scripts.append(self._script)
        elif tag == "a":
            self._link = {**a, "_text": ""}
            self.links.append(self._link)
            if self._table:
                self.table_links.append(a.get("href"))
        elif tag in ("table", "tbody", "tr"):
            self._table_tag(tag, a)
        elif tag == "section" and a.get("id") == "closest":
            self.section = a
        elif tag == "button" and a.get("id") == "closest-button":
            self.button = a
        else:
            self._note_load(tag, a)

    def _table_tag(self, tag: str, a: dict[str, str | None]) -> None:
        if tag == "table":
            self._table += 1
        elif tag == "tbody":
            self._body += 1
        elif self._body:
            self.row_slugs.append(a.get("data-slug"))

    def _note_load(self, tag: str, a: dict[str, str | None]) -> None:
        """Anything the browser fetches by itself, if it is off-origin."""
        loads = tag in ("iframe", "img", "embed", "object", "source") or (
            tag == "link" and a.get("rel") in ("stylesheet", "preload", "prefetch")
        )
        if not loads:
            return
        for key in ("src", "href"):
            value = a.get(key) or ""
            if value.startswith(("http:", "https:", "//")):
                self.external_loads.append((tag, value))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._script = None
        elif tag == "a":
            self._link = None
        elif tag == "table":
            self._table -= 1
        elif tag == "tbody":
            self._body -= 1

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script["text"] += data
            return
        if self._link is not None:
            self._link["_text"] = (self._link["_text"] or "") + data
        self.text.append(data)

    @property
    def visible(self) -> str:
        return " ".join("".join(self.text).split())


def _page(out: Path, rel: str) -> _Page:
    p = _Page()
    p.feed((out / rel / "index.html").read_text(encoding="utf-8"))
    return p


def _all_pages(out: Path) -> dict[str, _Page]:
    pages = {}
    for f in sorted(out.rglob("*.html")):
        p = _Page()
        p.feed(f.read_text(encoding="utf-8"))
        pages[str(f.relative_to(out))] = p
    assert len(pages) > 10
    return pages


def _placed(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """slug -> the committed location, for each water on the site."""
    committed = locations.load_locations(cli.DEFAULT_LOCATIONS_PATH)
    return {
        w["slug"]: committed[w["cdfw_stock_id"]]
        for w in snap["waters"]
        if w["cdfw_stock_id"] in committed
    }


# ---- the file of coordinates


def test_fixture_places_some_waters_and_leaves_others_unplaced(built):
    _, snap = built
    placed = _placed(snap)
    kinds = {loc["kind"] for loc in placed.values()}
    assert 0 < len(placed) < len(snap["waters"])
    assert "stream_point" in kinds and kinds - {"stream_point"}


def test_coords_file_is_the_committed_locations_and_nothing_else(built):
    out, snap = built
    doc = json.loads((out / "assets" / site.COORDS_FILE).read_text(encoding="utf-8"))
    assert doc["schema"] == site.COORDS_SCHEMA
    assert "U.S. Geological Survey" in doc["source"]
    placed = _placed(snap)
    assert set(doc["waters"]) == set(placed)
    for slug, (lat, lon, kind) in doc["waters"].items():
        loc = placed[slug]
        assert (lat, lon) == (loc["lat"], loc["lon"]), slug
        assert kind == ("s" if loc["kind"] == "stream_point" else "w"), slug
        assert 32.0 <= lat <= 42.5 and -125.0 <= lon <= -114.0, slug
        assert (out / "water" / slug / "index.html").exists(), slug


def test_no_locations_means_no_script_no_file_no_section(built_no_locations):
    out, _ = built_no_locations
    assert not (out / "assets" / site.COORDS_FILE).exists()
    assert not (out / "assets" / site.CLOSEST_JS_FILE).exists()
    index = _page(out, ".")
    assert index.section is None and index.button is None
    assert all(not s["attrs"].get("src") for s in index.scripts)
    assert set(index.row_slugs) <= {None}
    for name, page in _all_pages(out).items():
        assert not any(
            (link["href"] or "").startswith(site.OSM_URL) for link in page.links
        ), name


# ---- the water page


def test_placed_water_has_a_map_link_and_coordinates_and_unplaced_has_neither(built):
    out, snap = built
    placed = _placed(snap)
    seen_placed = seen_unplaced = 0
    for w in snap["waters"]:
        page = _page(out, f"water/{w['slug']}")
        osm = [
            link for link in page.links if (link["href"] or "").startswith(site.OSM_URL)
        ]
        loc = placed.get(w["slug"])
        if loc is None:
            seen_unplaced += 1
            assert osm == [], w["name"]
            assert "Coordinates" not in page.visible, w["name"]
            continue
        seen_placed += 1
        assert len(osm) == 1, w["name"]
        link = osm[0]
        approximate = loc["kind"] == "stream_point"
        zoom = 12 if approximate else 14
        lat, lon = loc["lat"], loc["lon"]
        assert (
            link["href"]
            == f"{site.OSM_URL}?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"
        )
        assert link["_text"] == "View on map"
        assert set((link["rel"] or "").split()) == {"noopener", "noreferrer"}
        assert f"{lat}, {lon}" in page.visible
        assert (
            "approximate" in page.visible.split("Coordinates", 1)[1][:200]
        ) == approximate
        assert "U.S. Geological Survey" in page.visible
    assert seen_placed and seen_unplaced


def test_a_map_link_is_only_a_link(built):
    """No script, tile, iframe or image loads from a map service or anywhere
    else off-origin, on any page; the map service is reached by a click."""
    out, _ = built
    for name, page in _all_pages(out).items():
        assert page.external_loads == [], name
        for s in page.scripts:
            src = s["attrs"].get("src")
            assert not src or not src.startswith(("http:", "https:", "//")), name


def test_geo_only_for_a_point_inside_the_water_and_matching_the_page(built):
    out, snap = built
    placed = _placed(snap)
    with_geo = without_geo = 0
    for w in snap["waters"]:
        html = (out / "water" / w["slug"] / "index.html").read_text(encoding="utf-8")
        page = _page(out, f"water/{w['slug']}")
        ld = [
            s for s in page.scripts if s["attrs"].get("type") == "application/ld+json"
        ]
        assert len(ld) == 1
        water = next(
            n
            for n in json.loads(ld[0]["text"])["@graph"]
            if n["@type"] == "BodyOfWater"
        )
        loc = placed.get(w["slug"])
        if loc is None or loc["kind"] == "stream_point":
            without_geo += 1
            assert "geo" not in water, w["name"]
            continue
        with_geo += 1
        assert water["geo"] == {
            "@type": "GeoCoordinates",
            "latitude": loc["lat"],
            "longitude": loc["lon"],
        }
        assert f"{loc['lat']}, {loc['lon']}, a point inside the water" in page.visible
        assert html.count("GeoCoordinates") == 1
    assert with_geo and without_geo


def test_a_stream_point_is_labeled_approximate_and_given_no_geo(built):
    out, snap = built
    streams = [s for s, loc in _placed(snap).items() if loc["kind"] == "stream_point"]
    assert streams
    for slug in streams:
        page = _page(out, f"water/{slug}")
        assert "approximate: a point on the stream" in page.visible, slug
        assert "a point inside the water" not in page.visible, slug


# ---- the home page


def test_closest_section_is_hidden_without_script_and_the_lists_are_unchanged(
    built, built_no_locations
):
    out, _ = built
    plain, _ = built_no_locations
    index, baseline = _page(out, "."), _page(plain, ".")
    assert index.section is not None and index.button is not None
    assert (
        "hidden" in index.section
    )  # the section is not shown until the script shows it
    assert index.section["data-coords"] == f"assets/{site.COORDS_FILE}"
    assert index.button["type"] == "button"
    # With the section removed and its script ignored, the lists are the same
    # links in the same order, so a visitor without JavaScript sees what they
    # saw before.
    assert index.table_links == baseline.table_links
    assert index.table_links
    assert all(s for s in index.row_slugs)  # every row carries its slug for the script
    closest_text = "Closest to me"
    assert closest_text in index.visible and closest_text not in baseline.visible


def test_the_only_new_script_is_the_first_party_one_and_it_is_idle(built, built_ga):
    for out, expected_inline in ((built[0], 0), (built_ga[0], 1)):
        for name, page in _all_pages(out).items():
            kinds = []
            for s in page.scripts:
                a = s["attrs"]
                if a.get("type") == "application/ld+json":
                    continue
                kinds.append("src" if a.get("src") else "inline")
                if a.get("src"):
                    assert a == {
                        "src": f"assets/{site.CLOSEST_JS_FILE}",
                        "defer": None,
                    }, name
                    assert s["text"] == "", name
            if name == "index.html":
                assert kinds.count("src") == 1, name
            else:
                assert "src" not in kinds, name
            assert kinds.count("inline") == expected_inline, name


# ---- what closest.js is allowed to do (read as text, then executed below)

FORBIDDEN = (
    "XMLHttpRequest",
    "sendBeacon",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
    "new Image",
    "WebSocket",
    "eval(",
    "innerHTML",
    "watchPosition",
    "gtag",
    "dataLayer",
    "history.pushState",
    "location.href",
    "location.search",
)


def _script_problems(js: str) -> list[str]:
    problems = [f"uses {word}" for word in FORBIDDEN if word in js]
    if js.count("fetch(") != 1:
        problems.append("does not make exactly one fetch")
    if js.count("getCurrentPosition(") != 1:
        problems.append("does not ask for the position exactly once")
    click = js.find('button.addEventListener("click"')
    if click < 0 or js.find("getCurrentPosition(") < click:
        problems.append("asks for the position outside the click handler")
    return problems


def test_script_text_has_no_storage_beacon_or_second_request():
    js = CLOSEST_JS.read_text(encoding="utf-8")
    assert _script_problems(js) == []


def test_script_text_check_is_not_vacuous():
    js = CLOSEST_JS.read_text(encoding="utf-8")
    for needle, word in (
        (
            "var EARTH_RADIUS_MILES",
            'localStorage.setItem("p", 1); var EARTH_RADIUS_MILES',
        ),
        ("var EARTH_RADIUS_MILES", "navigator.sendBeacon(u); var EARTH_RADIUS_MILES"),
    ):
        sabotaged = js.replace(needle, word, 1)
        assert sabotaged != js  # the sabotage landed
        assert _script_problems(sabotaged)
    early = js.replace(
        'button.addEventListener("click"',
        'nav.geolocation.getCurrentPosition(onPosition, onFailure);\n  button.addEventListener("click"',
        1,
    )
    assert early != js  # the sabotage landed
    assert "asks for the position outside the click handler" in _script_problems(early)


def test_the_script_is_written_to_the_site_byte_for_byte(built):
    out, _ = built
    assert (
        out / "assets" / site.CLOSEST_JS_FILE
    ).read_bytes() == CLOSEST_JS.read_bytes()


# ---- executed under node, against a stub browser

_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync(process.argv[2], "utf8");
const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

class Node_ {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.hidden = false;
    this.disabled = false; this.className = ""; this.listeners = {}; this._text = null; }
  get firstChild() { return this.children[0] || null; }
  removeChild(ch) { this.children.splice(this.children.indexOf(ch), 1); }
  appendChild(ch) { this.children.push(ch); return ch; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text !== null ? this._text : this.children.map((x) => x.textContent).join(""); }
  querySelectorAll(sel) { return this.tag === "tr" && sel === "td" ? this.cells : []; }
  querySelector(sel) { return sel === "a" ? this.link || null : null; }
}
const text = (s) => { const n = new Node_("#text"); n._text = s; return n; };
function row(slug, name, href, county, species) {
  const tr = new Node_("tr"); tr.attrs["data-slug"] = slug;
  const a = new Node_("a"); a._text = name; a.attrs.href = href;
  const td0 = new Node_("td"); td0.link = a;
  const td1 = new Node_("td"); td1._text = county;
  const td2 = new Node_("td"); td2._text = species;
  tr.cells = [td0, td1, td2];
  return tr;
}
const els = {};
for (const id of ["closest", "closest-button", "closest-status", "closest-result"]) els[id] = new Node_("x");
els.closest.hidden = true;
els.closest.attrs["data-coords"] = c.coordsPath;
const rows = c.rows.map((r) => row(r[0], r[1], r[2], r[3], r[4]));
const log = { geolocation: 0, fetches: [], other: [] };
const document = {
  getElementById: (id) => (c.omitElements ? null : els[id] || null),
  querySelectorAll: (sel) => (sel === "tr[data-slug]" ? rows : []),
  createElement: (t) => new Node_(t),
  createTextNode: text,
};
let positionCallbacks = null;
const geolocation = c.noGeolocation ? undefined : {
  getCurrentPosition: (ok, fail, opts) => { log.geolocation++; positionCallbacks = { ok, fail, opts }; },
  watchPosition: () => { log.other.push("watchPosition"); },
};
const navigator = c.noNavigator ? undefined : { geolocation };
const window = { document, navigator };
if (!c.noFetch) window.fetch = (url, opts) => {
  log.fetches.push({ url, opts });
  return Promise.resolve({ ok: !c.fetchFails, status: c.fetchFails ? 500 : 200, json: () => Promise.resolve(c.coords) });
};
for (const name of ["XMLHttpRequest", "WebSocket", "Image"]) window[name] = function () { log.other.push(name); };
window.localStorage = { setItem() { log.other.push("localStorage"); }, getItem() { return null; } };
window.sessionStorage = window.localStorage;
document.cookie = "";
const context = { window, document, navigator, Math, Object, Array, Number, String, Promise, Error };
context.fetch = window.fetch;
const out = { states: [] };
const snap = (label) => out.states.push({
  label, hidden: els.closest.hidden, status: els["closest-status"].textContent,
  disabled: els["closest-button"].disabled,
  geolocation: log.geolocation, fetches: log.fetches.length,
});
vm.runInContext(code, vm.createContext(context));
snap("after load");
const click = els["closest-button"].listeners.click;
if (click) {
  snap("before click");
  click();
  snap("after click");
  (async () => {
    if (positionCallbacks) {
      if (c.denied) positionCallbacks.fail({ code: 1 });
      else if (c.unavailable) positionCallbacks.fail({ code: 2 });
      else positionCallbacks.ok({ coords: { latitude: c.origin[0], longitude: c.origin[1] } });
    }
    await new Promise((r) => setTimeout(r, 20));
    snap("after answer");
    finish();
  })();
} else finish();
function finish() {
  const list = els["closest-result"].children[0];
  out.items = list ? list.children.map((li) => li.textContent) : [];
  out.hrefs = list ? list.children.map((li) => li.children[0].attrs.href) : [];
  out.note = els["closest-result"].children.length > 1 ? els["closest-result"].children[1].textContent : null;
  out.fetches = log.fetches; out.other = log.other; out.geoOpts = positionCallbacks ? positionCallbacks.opts : null;
  process.stdout.write(JSON.stringify(out));
}
"""

# name, slug, href, county, species
ROWS = [
    ["far", "Far Lake", "water/far/", "Inyo", "trout"],
    ["near", "Near Lake", "water/near/", "Alameda", "trout"],
    ["stream", "Mid Creek", "water/stream/", "Contra Costa", "trout"],
    [
        "near",
        "Near Lake",
        "water/near/",
        "Alameda",
        "trout",
    ],  # a second region lists it
    ["nowhere", "Unplaced Pond", "water/nowhere/", "Kern", "catfish"],
]
ROWS = [[r[0], r[1], r[2], r[3], r[4]] for r in ROWS]
COORDS = {
    "schema": site.COORDS_SCHEMA,
    "waters": {
        "far": [36.5, -118.3, "w"],
        "near": [37.8, -122.2, "w"],
        "stream": [37.95, -122.0, "s"],
    },
}
ORIGIN = [37.77, -122.42]  # San Francisco


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("node is required in CI to execute closest.js")
        pytest.skip("node is not installed; closest.js is only string-checked")
    return node


def _run(tmp_path: Path, js: str, **case: Any) -> dict[str, Any]:
    node = _node()
    harness = tmp_path / "harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    script = tmp_path / "closest.js"
    script.write_text(js, encoding="utf-8")
    spec = tmp_path / "case.json"
    spec.write_text(
        json.dumps(
            {
                "coordsPath": f"assets/{site.COORDS_FILE}",
                "rows": ROWS,
                "coords": COORDS,
                "origin": ORIGIN,
                **case,
            }
        ),
        encoding="utf-8",
    )
    done = subprocess.run(
        [node, str(harness), str(script), str(spec)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    parsed: dict[str, Any] = json.loads(done.stdout)
    return parsed


def _states(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in result["states"]}


def test_nothing_is_asked_or_sent_until_the_button_is_pressed(tmp_path):
    js = CLOSEST_JS.read_text(encoding="utf-8")
    result = _run(tmp_path, js)
    states = _states(result)
    before = states["before click"]
    assert before["hidden"] is False  # the section is shown once the script runs
    assert (before["geolocation"], before["fetches"]) == (0, 0)
    after = states["after click"]
    assert (after["geolocation"], after["fetches"]) == (
        1,
        0,
    )  # asked; nothing fetched yet
    assert result["geoOpts"] == {"timeout": 20000}


def test_the_only_request_is_the_static_file_and_carries_no_location(tmp_path):
    js = CLOSEST_JS.read_text(encoding="utf-8")
    result = _run(tmp_path, js)
    assert result["other"] == []  # no XHR, socket, image, storage or watch
    assert result["fetches"] == [
        {"url": f"assets/{site.COORDS_FILE}", "opts": {"credentials": "omit"}}
    ]
    assert not any(str(n) in json.dumps(result["fetches"]) for n in ("37.77", "122.42"))


def test_sorted_nearest_first_deduplicated_and_unplaced_named_not_ranked(tmp_path):
    js = CLOSEST_JS.read_text(encoding="utf-8")
    result = _run(tmp_path, js)
    assert result["hrefs"] == ["water/near/", "water/stream/", "water/far/"]
    assert result["items"][0].startswith("Near Lake, Alameda County, trout: ")
    assert result["items"][1].endswith("(approximate)")  # the stream
    assert result["items"][2].startswith("Far Lake, Inyo County, trout: about ")
    assert all(
        "(approximate)" not in i for i in (result["items"][0], result["items"][2])
    )
    assert result["note"] == (
        "1 water on this week's schedule has no location on file and is not in "
        "this list. It is in the lists below."
    )
    final = _states(result)["after answer"]
    assert "Nothing about your location was sent." in final["status"]
    assert final["disabled"] is False


def test_denied_unavailable_and_failed_load_leave_the_list_alone(tmp_path):
    js = CLOSEST_JS.read_text(encoding="utf-8")
    denied = _run(tmp_path, js, denied=True)
    assert _states(denied)["after answer"]["status"] == (
        "Your browser did not share your location, so the list is unchanged."
    )
    assert denied["items"] == [] and denied["fetches"] == []
    unavailable = _run(tmp_path, js, unavailable=True)
    assert "could not be found" in _states(unavailable)["after answer"]["status"]
    failed = _run(tmp_path, js, fetchFails=True)
    assert "could not be loaded" in _states(failed)["after answer"]["status"]
    assert failed["items"] == []
    for r in (denied, unavailable, failed):
        assert _states(r)["after answer"]["disabled"] is False  # can try again


def test_a_browser_that_cannot_do_it_keeps_the_section_hidden(tmp_path):
    js = CLOSEST_JS.read_text(encoding="utf-8")
    for case in ({"noGeolocation": True}, {"noFetch": True}, {"noNavigator": True}):
        result = _run(tmp_path, js, **case)
        assert _states(result)["after load"]["hidden"] is True, case
        assert result["fetches"] == [], case
    missing = _run(tmp_path, js, omitElements=True)
    assert missing["states"][0]["geolocation"] == 0


def test_executed_check_catches_a_request_that_carries_the_location(tmp_path):
    """Negative control: the same harness flags a script that puts the
    position in the URL it fetches."""
    js = CLOSEST_JS.read_text(encoding="utf-8")
    needle = '.fetch(section.getAttribute("data-coords"), '
    assert needle in js
    sabotaged = js.replace(
        needle,
        '.fetch(section.getAttribute("data-coords") + "?" + origin.lat, ',
        1,
    )
    assert sabotaged != js  # the sabotage landed
    result = _run(tmp_path, sabotaged)
    assert "37.77" in json.dumps(result["fetches"])
    clean = _run(tmp_path, js)
    assert "37.77" not in json.dumps(clean["fetches"])


def test_executed_check_catches_a_request_made_before_the_click(tmp_path):
    js = CLOSEST_JS.read_text(encoding="utf-8")
    needle = "section.hidden = false;"
    assert needle in js
    sabotaged = js.replace(
        needle,
        needle + '\n  root.fetch(section.getAttribute("data-coords"));',
        1,
    )
    assert sabotaged != js  # the sabotage landed
    assert _states(_run(tmp_path, sabotaged))["before click"]["fetches"] == 1
    assert _states(_run(tmp_path, js))["before click"]["fetches"] == 0


def test_distance_is_great_circle_miles():
    node = _node()
    code = (
        f"const m = require({json.dumps(str(CLOSEST_JS))});"
        "process.stdout.write(JSON.stringify({"
        "sfLa: m.milesBetween(37.7749, -122.4194, 34.0522, -118.2437),"
        "zero: m.milesBetween(40, -120, 40, -120),"
        "under: m.milesLabel(0.4), one: m.milesLabel(1.2), many: m.milesLabel(12.6)}));"
    )
    done = subprocess.run(
        [node, "-e", code], capture_output=True, text=True, check=True, timeout=30
    )
    got = json.loads(done.stdout)
    assert 345 < got["sfLa"] < 349  # about 347 miles
    assert got["zero"] == 0
    assert (got["under"], got["one"], got["many"]) == (
        "under 1 mile",
        "about 1 mile",
        "about 13 miles",
    )


def test_about_page_states_the_true_count_and_credits_the_usgs(built):
    out, snap = built
    about = _page(out, "about").visible
    placed = _placed(snap)
    assert (
        f"{len(placed)} of {len(snap['waters'])} California waters have a location"
        in about
    )
    assert "Source of water locations: U.S. Geological Survey" in about
    assert "Geographic Names Information System" in about
    # Negative control: a different count is not in the page.
    wrong = (
        f"{len(placed) + 1} of {len(snap['waters'])} California waters have a location"
    )
    assert wrong not in about
