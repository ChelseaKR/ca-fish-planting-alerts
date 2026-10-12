# Map assets: sources, versions, licenses

Everything here is served from this site. Nothing on a map page loads from
another host.

| File | From | Version | License |
|---|---|---|---|
| `vendor/maplibre-gl.mjs`, `vendor/maplibre-gl-shared.mjs`, `vendor/maplibre-gl-worker.mjs`, `vendor/maplibre-gl.css` | npm `maplibre-gl` | 6.11.2 | BSD-3-Clause (`maplibre-gl.txt`) |
| `vendor/pmtiles.js` | npm `pmtiles` | 4.5.0 | BSD-3-Clause (`pmtiles.txt`) |
| `vendor/basemaps.js` | npm `@protomaps/basemaps` | 5.7.2 | BSD-3-Clause code, CC0 visual design (`protomaps-basemaps.md`) |
| `california.pmtiles` | Protomaps basemap daily build `20261012.pmtiles` (basemap v4.15.2), cut with `pmtiles extract --bbox=-124.48,32.53,-114.13,42.01 --maxzoom=10` (go-pmtiles 1.31.2) | 2026-10-12 | Map data: OpenStreetMap contributors, ODbL 1.0, as a Produced Work: attribution "© OpenStreetMap contributors" is shown on every map. Also Natural Earth (public domain). |
| `fonts/Noto Sans {Regular,Medium,Italic}/{0-255,256-511,8192-8447}.pbf` | github.com/protomaps/basemaps-assets at 028c18f | 2026-10-12 | SIL Open Font License 1.1 (`noto-sans-OFL.txt`) |
| `sprites/{light,dark}{,@2x}.{json,png}` | github.com/protomaps/basemaps-assets `sprites/v4` at 028c18f | 2026-10-12 | Derived from MIT-licensed tangrams/icons (`tangrams-icons-MIT.md`) |

Vendor files are byte for byte what the npm tarballs hold (sha256 in
`pipeline/tests/test_site_map.py`). Their `sourceMappingURL` comments point
at `.map` files that are not shipped; a browser asks for them only when its
developer tools are open.

Only three Latin glyph ranges are shipped. A label with a character outside
them is drawn without that character rather than fetched from elsewhere.
