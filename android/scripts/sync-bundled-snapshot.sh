#!/usr/bin/env bash
# Replace the snapshot bundled with the Android app with the live v1 one the
# site publishes, after checking it against schema/snapshot.v1.json. Run it
# just before a release build, so a fresh install opens on the current week.
#
# Android reads v1 (California only), which stays byte-compatible for
# installed builds (docs/DECISIONS.md 0025). The iOS app bundles v2, so the
# two apps keep separate files.
#
#   android/scripts/sync-bundled-snapshot.sh
set -euo pipefail

android_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$android_dir/.." && pwd)"
url="https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v1.json"
bundled="$android_dir/app/src/main/assets/snapshot.json"
download="$(mktemp "${TMPDIR:-/tmp}/trout-truck-android-snapshot.XXXXXX")"
trap 'rm -f "$download"' EXIT

curl --fail --silent --show-error --location --output "$download" "$url"
uv run --quiet --project "$repo_dir/pipeline" python - "$download" "$repo_dir/schema/snapshot.v1.json" "$bundled" <<'PY'
import json, os, sys
import jsonschema
live_path, schema_path, bundled_path = sys.argv[1:4]
live, schema = (json.load(open(p)) for p in (live_path, schema_path))
jsonschema.validate(instance=live, schema=schema)
if live.get("schema_version") != 1:
    sys.exit(f"live snapshot has schema_version {live.get('schema_version')}, not 1")
if os.path.exists(bundled_path):
    bundled = json.load(open(bundled_path))
    if live["generated_at"] < bundled["generated_at"]:
        sys.exit(f"live snapshot {live['generated_at']} is older than the bundled {bundled['generated_at']}")
    print(f"bundled: {bundled['generated_at']} ({bundled['source_week']['label']})")
print(f"live:    {live['generated_at']} ({live['source_week']['label']})")
PY
cp "$download" "$bundled"
chmod 644 "$bundled"
echo "updated android/app/src/main/assets/snapshot.json"
