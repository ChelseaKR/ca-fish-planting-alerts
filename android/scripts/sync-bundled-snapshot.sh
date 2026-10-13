#!/usr/bin/env bash
# Replace the snapshot bundled with the Android app with the live v2 one the
# site publishes (every state, docs/DECISIONS.md 0025), after checking it
# against schema/snapshot.v2.json. Run it just before a release build, so a
# fresh install opens on the current week.
#
# The iOS app bundles the same v2 file through ios/scripts/; the Android
# app keeps its own copy so each build controls when its file changes.
#
#   android/scripts/sync-bundled-snapshot.sh
set -euo pipefail

android_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$android_dir/.." && pwd)"
url="https://chelseakr.github.io/ca-fish-planting-alerts/snapshot/v2.json"
bundled="$android_dir/app/src/main/assets/snapshot.json"
download="$(mktemp "${TMPDIR:-/tmp}/trout-truck-android-snapshot.XXXXXX")"
trap 'rm -f "$download"' EXIT

curl --fail --silent --show-error --location --output "$download" "$url"
uv run --quiet --project "$repo_dir/pipeline" python - "$download" "$repo_dir/schema/snapshot.v2.json" "$bundled" <<'PY'
import json, os, sys
import jsonschema
live_path, schema_path, bundled_path = sys.argv[1:4]
live, schema = (json.load(open(p)) for p in (live_path, schema_path))
jsonschema.validate(instance=live, schema=schema)
if live.get("schema_version") != 2:
    sys.exit(f"live snapshot has schema_version {live.get('schema_version')}, not 2")
if os.path.exists(bundled_path):
    bundled = json.load(open(bundled_path))
    if live["generated_at"] < bundled["generated_at"]:
        sys.exit(f"live snapshot {live['generated_at']} is older than the bundled {bundled['generated_at']}")
    codes = ", ".join(s["code"] for s in bundled.get("states", [{"code": "CA"}]))
    print(f"bundled: {bundled['generated_at']} ({codes})")
print(f"live:    {live['generated_at']} ({', '.join(s['code'] for s in live['states'])})")
PY
cp "$download" "$bundled"
chmod 644 "$bundled"
echo "updated android/app/src/main/assets/snapshot.json"
