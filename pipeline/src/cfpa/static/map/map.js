// Trout Truck map: loads nothing until someone asks for a map.
//
// Each [data-map] section starts as a summary and a "Show map" button; the
// list or table on the page is the map's full text alternative. Pressing the
// button loads MapLibre, the basemap style and the California tiles, all from
// this site (map/vendor, map/california.pmtiles). No other host is contacted.
//
// Only waters with a confident location are in map/waters.json; a stream's
// point is drawn as a ring and called approximate.

const section = (el) => ({
  root: new URL(el.dataset.root || "./", document.baseURI),
  mode: el.dataset.map, // "home" or "water"
  focus: el.dataset.focus || "",
});

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`could not load ${src}`));
    document.head.append(s);
  });
}

function loadCss(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = href;
  document.head.append(l);
}

let libs;
function loadLibs(root) {
  const v = (f) => new URL(`map/vendor/${f}`, root).href;
  libs ??= (async () => {
    loadCss(v("maplibre-gl.css"));
    const [gl] = await Promise.all([
      import(v("maplibre-gl.mjs")),
      loadScript(v("pmtiles.js")),
      loadScript(v("basemaps.js")),
    ]);
    const protocol = new window.pmtiles.Protocol();
    gl.addProtocol("pmtiles", protocol.tile);
    return gl;
  })();
  return libs;
}

const dark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;
const still = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function style(root) {
  const flavor = dark() ? "dark" : "light";
  return {
    version: 8,
    glyphs: new URL("map/fonts/{fontstack}/{range}.pbf", root)
      .href.replace("%7Bfontstack%7D", "{fontstack}")
      .replace("%7Brange%7D", "{range}"),
    sprite: new URL(`map/sprites/${flavor}`, root).href,
    sources: {
      protomaps: {
        type: "vector",
        url: `pmtiles://${new URL("map/california.pmtiles", root).href}`,
        attribution:
          '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>, ' +
          '<a href="https://protomaps.com">Protomaps</a>, water locations: U.S. Geological Survey',
      },
    },
    layers: window.basemaps.layers(
      "protomaps",
      window.basemaps.namedFlavor(flavor),
      { lang: "en" },
    ),
  };
}

const css = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function addWaters(map, data, mode) {
  const accent = css("--link") || "#0b5d3b";
  const muted = css("--muted") || "#45564c";
  const bg = css("--bg") || "#ffffff";
  map.addSource("waters", {
    type: "geojson",
    data,
    cluster: mode === "home",
    clusterRadius: 40,
    clusterMaxZoom: 9,
  });
  map.addLayer({
    id: "clusters",
    type: "circle",
    source: "waters",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": muted,
      "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 30, 22],
      "circle-stroke-color": bg,
      "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "cluster-count",
    type: "symbol",
    source: "waters",
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["Noto Sans Medium"],
      "text-size": 13,
    },
    paint: { "text-color": bg },
  });
  // On a water's own page its pin is the accent color, like this week's.
  const week = mode === "water" ? true : ["==", ["get", "this_week"], true];
  const approx = ["==", ["get", "kind"], "stream_point"];
  map.addLayer({
    id: "waters",
    type: "circle",
    source: "waters",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-radius": ["case", week, 8, 6],
      // A stream's point is approximate: drawn as a ring, not a dot.
      "circle-color": ["case", approx, bg, week, accent, muted],
      "circle-stroke-color": ["case", week, accent, muted],
      "circle-stroke-width": ["case", approx, 3, 2],
    },
  });
}

function popupContent(p, root) {
  const div = document.createElement("div");
  const line = (child) => {
    const para = document.createElement("p");
    para.append(child);
    div.append(para);
  };
  const a = document.createElement("a");
  a.href = new URL(p.url, root).href;
  a.textContent = p.name;
  line(a);
  line(`${p.county} County`);
  if (p.this_week) line("Scheduled this week");
  if (p.kind === "stream_point") line("Approximate: somewhere on the stream");
  return div;
}

async function show(el, button) {
  const s = section(el);
  const status = el.querySelector("[data-map-status]");
  button.disabled = true;
  status.textContent = "Loading the map…";
  try {
    const [gl, data] = await Promise.all([
      loadLibs(s.root),
      fetch(new URL("map/waters.json", s.root)).then((r) => {
        if (!r.ok) throw new Error(`waters.json ${r.status}`);
        return r.json();
      }),
    ]);
    if (s.focus) {
      data.features = data.features.filter((f) => f.properties.id === s.focus);
    }
    const box = el.querySelector("[data-map-canvas]");
    box.hidden = false;
    const only = data.features.length === 1 ? data.features[0] : null;
    const map = new gl.Map({
      container: box,
      style: style(s.root),
      bounds: only ? undefined : [-124.48, 32.53, -114.13, 42.01],
      center: only ? only.geometry.coordinates : undefined,
      zoom: only ? 10 : undefined,
      maxBounds: [-127, 31, -111, 44],
      attributionControl: { compact: true },
      fadeDuration: still() ? 0 : 300,
    });
    map.addControl(new gl.NavigationControl({ showCompass: false }));
    map.on("load", () => {
      addWaters(map, data, s.mode);
      status.textContent = "Map loaded. Use the arrow keys to pan and + or − to zoom.";
    });
    map.on("click", "clusters", async (e) => {
      const f = e.features[0];
      const zoom = await map
        .getSource("waters")
        .getClusterExpansionZoom(f.properties.cluster_id);
      map.easeTo({ center: f.geometry.coordinates, zoom, animate: !still() });
    });
    map.on("click", "waters", (e) => {
      const f = e.features[0];
      new gl.Popup({ maxWidth: "16rem" })
        .setLngLat(f.geometry.coordinates)
        .setDOMContent(popupContent(f.properties, s.root))
        .addTo(map);
    });
    for (const id of ["clusters", "waters"]) {
      map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
    }
    button.hidden = true;
  } catch (err) {
    button.disabled = false;
    status.textContent =
      "The map could not load in this browser. Every water is still listed on this page.";
    console.error(err);
  }
}

for (const el of document.querySelectorAll("[data-map]")) {
  const button = el.querySelector("[data-map-show]");
  if (!button) continue;
  button.hidden = false;
  button.addEventListener("click", () => show(el, button));
}
