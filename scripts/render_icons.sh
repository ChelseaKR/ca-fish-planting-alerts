#!/usr/bin/env bash
# Render the site's raster icons from the tab icon's own SVG.
#
# The tab icon is an SVG written inside every page (base.html.jinja), so a
# browser shows it with no request. Google Search shows a site icon only
# from a file it can crawl, in one of BMP, GIF, ICO, PNG, JPEG, PPM or TIFF,
# square, and it recommends a multiple of 48 px
# (developers.google.com/search/docs/appearance/favicon-in-search, read
# 2026-11-17). An inline SVG is neither a file nor one of those formats.
# This writes, into the templates directory:
#
#   icon-48.png, icon-96.png, icon-192.png   the <link rel="icon"> files
#   favicon.ico                              16, 32 and 48 px, for clients
#                                            that ask for /favicon.ico
#
# Every pixel comes from the SVG in base.html.jinja's inline icon link, read
# here and decoded; nothing is drawn. This is a developer tool, not part of
# the build: the outputs are committed, and the build copies them (site.py,
# _write_assets). Run it again, and commit the files, only when that icon
# changes. Needs rsvg-convert (brew install librsvg).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
templates="$root/pipeline/src/cfpa/templates"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

command -v rsvg-convert >/dev/null || {
  echo "rsvg-convert not found (brew install librsvg)" >&2
  exit 1
}

python3 - "$templates/base.html.jinja" "$work/mark.svg" <<'PY'
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

PREFIX = "data:image/svg+xml,"


class Icon(HTMLParser):
    href = None

    def handle_starttag(self, tag, attrs):
        got = dict(attrs)
        if tag == "link" and got.get("rel") == "icon" and (got.get("href") or "").startswith(PREFIX):
            self.href = got["href"]


parser = Icon()
parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8"))
if parser.href is None:
    sys.exit("base.html.jinja has no inline SVG icon link")
Path(sys.argv[2]).write_text(unquote(parser.href[len(PREFIX):]), encoding="utf-8")
PY

for size in 48 96 192; do
  rsvg-convert --width "$size" --height "$size" "$work/mark.svg" --output "$templates/icon-$size.png"
done
for size in 16 32 48; do
  rsvg-convert --width "$size" --height "$size" "$work/mark.svg" --output "$work/$size.png"
done

# An .ico file is a small directory followed by the images; each image may be
# a whole PNG file (every browser since Internet Explorer 11 reads that).
python3 - "$work" "$templates/favicon.ico" <<'PY'
import struct
import sys
from pathlib import Path

work, out = Path(sys.argv[1]), Path(sys.argv[2])
images = [(size, (work / f"{size}.png").read_bytes()) for size in (16, 32, 48)]
offset = 6 + 16 * len(images)
directory = struct.pack("<HHH", 0, 1, len(images))
for size, data in images:
    directory += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
out.write_bytes(directory + b"".join(data for _, data in images))
PY

ls -l "$templates"/icon-*.png "$templates/favicon.ico"
