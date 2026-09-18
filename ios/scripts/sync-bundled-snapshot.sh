#!/usr/bin/env bash
# Replace the snapshot bundled with the app with the live one the site
# publishes, after checking it against schema/snapshot.v1.json. Run it just
# before archiving, so a fresh install opens on the current week.
#
#   ios/scripts/sync-bundled-snapshot.sh
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$ios_dir/.." && pwd)"
url="https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json"
bundled="$ios_dir/CAFishPlanting/Resources/snapshot.json"
download="$(mktemp "${TMPDIR:-/tmp}/trout-truck-snapshot.XXXXXX")"

curl --fail --silent --show-error --location --output "$download" "$url"
uv run --quiet --project "$repo_dir/pipeline" python - "$download" "$repo_dir/schema/snapshot.v1.json" "$bundled" <<'PY'
import json, sys
import jsonschema
live, schema, bundled = (json.load(open(p)) for p in sys.argv[1:4])
jsonschema.validate(instance=live, schema=schema)
if live["generated_at"] < bundled["generated_at"]:
    sys.exit(f"live snapshot {live['generated_at']} is older than the bundled {bundled['generated_at']}")
print(f"bundled: {bundled['generated_at']} ({bundled['source_week']['label']}, {len(bundled['this_week'])} this week)")
print(f"live:    {live['generated_at']} ({live['source_week']['label']}, {len(live['this_week'])} this week)")
PY
cp "$download" "$bundled"
rm -f "$download"
echo "updated ios/CAFishPlanting/Resources/snapshot.json"
