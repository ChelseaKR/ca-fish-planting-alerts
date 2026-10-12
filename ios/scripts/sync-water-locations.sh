#!/usr/bin/env bash
# Rebuild the app's bundled water locations from the pipeline's committed
# geocoder output (DECISIONS 0024, 0025). Run it after `cfpa-geocode`
# changes pipeline/data/water_locations.json; pipeline/tests/test_site_map.py
# fails while the two disagree.
#
#   ios/scripts/sync-water-locations.sh
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$ios_dir/.." && pwd)"
out="$ios_dir/CAFishPlanting/Resources/water-locations.json"

uv run --quiet --frozen --project "$repo_dir/pipeline" python - \
  "$repo_dir/pipeline/data/water_locations.json" "$out" <<'PY'
import json, sys
from pathlib import Path
from cfpa.locations import app_table
table = app_table(Path(sys.argv[1]))
Path(sys.argv[2]).write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
print(f"{len(table['locations'])} waters with a location")
PY
echo "updated ios/CAFishPlanting/Resources/water-locations.json"
