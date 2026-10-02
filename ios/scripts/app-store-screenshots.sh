#!/usr/bin/env bash
# Regenerate the App Store screenshots in docs/app-store/screenshots/ from the
# snapshot bundled with the app (real pipeline output, never a fixture).
#
#   ios/scripts/app-store-screenshots.sh [SIMULATOR_UDID]
#   SCREENSHOT_CLASS=6.5 ios/scripts/app-store-screenshots.sh
#
# SCREENSHOT_CLASS picks the App Store display class:
#   6.9 (default)  iPhone 17 Pro Max, 1320x2868, into docs/app-store/screenshots/
#   6.5            iPhone 11 Pro Max, 1242x2688, into docs/app-store/screenshots/6.5-inch/
# App Store Connect requires only the 6.9" set for an iPhone-only app and
# scales it down for smaller iPhones; the 6.5" set is optional, for when the
# scaled shots look wrong (docs/APP-STORE.md, Screenshots).
#
# With no UDID it creates (once) and reuses a simulator named
# "Trout Truck screenshots <class>". It overrides the status bar, deletes
# the app so the run starts from a fresh install, picks the region and
# waters from the bundled snapshot, runs AppStoreScreenshotsUITests, and
# fails unless all five PNGs come back at the class's exact pixel size.
#
# Refresh the bundled snapshot first (ios/scripts/sync-bundled-snapshot.sh).
# The app refreshes on launch and shows the live week, so the picks must come
# from a recent bundle; the script refuses one more than 7 days old unless
# ALLOW_STALE_SNAPSHOT=1.
set -euo pipefail

ios_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_dir="$(cd "$ios_dir/.." && pwd)"
snapshot="$ios_dir/CAFishPlanting/Resources/snapshot.json"
screenshot_class="${SCREENSHOT_CLASS:-6.9}"
case "$screenshot_class" in
  6.9)
    out_dir="$repo_dir/docs/app-store/screenshots"
    device_name="Trout Truck screenshots"
    device_type="com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro-Max"
    expected_size="1320x2868"
    ;;
  6.5)
    out_dir="$repo_dir/docs/app-store/screenshots/6.5-inch"
    device_name="Trout Truck screenshots 6.5"
    device_type="com.apple.CoreSimulator.SimDeviceType.iPhone-11-Pro-Max"
    expected_size="1242x2688"
    ;;
  *)
    echo "SCREENSHOT_CLASS must be 6.9 or 6.5, not '$screenshot_class'" >&2
    exit 2
    ;;
esac
bundle_id="com.chelseakr.cafishplanting"
shots=(01-this-week 02-water-history 03-favorites 04-notifications 05-about)

udid="${1:-}"
if [[ -z "$udid" ]]; then
  udid="$(xcrun simctl list devices available -j | python3 -c '
import json, sys
name = sys.argv[1]
for devices in json.load(sys.stdin)["devices"].values():
    for d in devices:
        if d["name"] == name:
            print(d["udid"]); raise SystemExit
' "$device_name")"
  if [[ -z "$udid" ]]; then
    runtime="$(xcrun simctl list runtimes -j | python3 -c '
import json, sys
ios = [r for r in json.load(sys.stdin)["runtimes"] if r["platform"] == "iOS" and r["isAvailable"]]
print(max(ios, key=lambda r: [int(p) for p in r["version"].split(".")])["identifier"])
')"
    udid="$(xcrun simctl create "$device_name" "$device_type" "$runtime")"
  fi
fi
echo "simulator: $udid"

xcrun simctl boot "$udid" 2>/dev/null || true
xcrun simctl bootstatus "$udid" -b >/dev/null
xcrun simctl status_bar "$udid" override --time "9:41" \
  --dataNetwork wifi --wifiMode active --wifiBars 3 \
  --cellularMode active --cellularBars 4 \
  --batteryState discharging --batteryLevel 100
xcrun simctl uninstall "$udid" "$bundle_id" 2>/dev/null || true

# Region: the one with the most waters on this week's schedule. History
# water: the deepest history among this week's waters in any region, with a
# name short enough (18 characters) not to be cut off in the large title.
# Favorites: that water, then this week's deepest three in the region, then
# the deepest history not on this week's schedule. Names must be unique so
# the UI test's search lands on the right row.
picks="$(python3 - "$snapshot" <<'PY'
import collections, json, sys
s = json.load(open(sys.argv[1]))
# The app refreshes the snapshot on launch, so the screens show the live
# week. Picks made from an older bundled week then miss it (measured
# 2026-10-01: a 13-day-old bundle left one "This week" badge in five
# favorites). Refuse unless the bundle is recent; sync it first.
import datetime, os
generated = datetime.datetime.fromisoformat(s["generated_at"].replace("Z", "+00:00"))
age = datetime.datetime.now(datetime.timezone.utc) - generated
if age > datetime.timedelta(days=7) and os.environ.get("ALLOW_STALE_SNAPSHOT") != "1":
    sys.exit(f"the bundled snapshot is {age.days} days old; run ios/scripts/sync-bundled-snapshot.sh "
             "first (or set ALLOW_STALE_SNAPSHOT=1)")
this_week = {t["water_id"] for t in s["this_week"]}
if not this_week:
    sys.exit("the bundled snapshot has nothing scheduled this week; refresh it first")
names = collections.Counter(w["name"] for w in s["waters"])
waters = sorted((w for w in s["waters"] if names[w["name"]] == 1),
                key=lambda w: (-len(w["plants"]), w["name"]))
by_region = collections.Counter(w["region"] for w in waters if w["id"] in this_week)
region = max(by_region, key=lambda code: (by_region[code], code))
history = next(w for w in waters if w["id"] in this_week and len(w["name"]) <= 18)
in_region = [w for w in waters if w["id"] in this_week and w["region"] == region and w is not history][:3]
not_this_week = next(w for w in waters if w["id"] not in this_week)
region_name = next(r["name"] for r in s["regions"] if r["code"] == region)
print(region_name)
print(history["name"])
print("|".join(w["name"] for w in in_region + [not_this_week]))
print(s["generated_at"], s["source_week"]["label"])
PY
)"
region="$(sed -n 1p <<<"$picks")"
history_water="$(sed -n 2p <<<"$picks")"
favorites="$(sed -n 3p <<<"$picks")"
echo "snapshot: $(sed -n 4p <<<"$picks")"
echo "region: $region"
echo "history water: $history_water"
echo "favorites: $favorites"

work="$(mktemp -d "${TMPDIR:-/tmp}/trout-truck-screenshots.XXXXXX")"
TEST_RUNNER_TT_SCREENSHOTS=1 \
TEST_RUNNER_TT_OUTPUT_DIR="$work/png" \
TEST_RUNNER_TT_REGION="$region" \
TEST_RUNNER_TT_HISTORY_WATER="$history_water" \
TEST_RUNNER_TT_FAVORITES="$favorites" \
xcodebuild -project "$ios_dir/CAFishPlanting.xcodeproj" -scheme CAFishPlanting \
  -destination "platform=iOS Simulator,id=$udid" \
  -derivedDataPath "${DERIVED_DATA:-$work/DerivedData}" \
  -resultBundlePath "$work/screenshots.xcresult" \
  -only-testing:CAFishPlantingUITests/AppStoreScreenshotsUITests \
  test

mkdir -p "$out_dir"
for shot in "${shots[@]}"; do
  png="$work/png/$shot.png"
  [[ -f "$png" ]] || { echo "missing $shot.png (was the test skipped?)" >&2; exit 1; }
  size="$(sips -g pixelWidth -g pixelHeight "$png" | awk '/pixelWidth/ {w=$2} /pixelHeight/ {h=$2} END {print w "x" h}')"
  [[ "$size" == "$expected_size" ]] || { echo "$shot.png is $size, not $expected_size" >&2; exit 1; }
  cp "$png" "$out_dir/$shot.png"
  echo "wrote ${out_dir#"$repo_dir"/}/$shot.png ($size)"
done
xcrun simctl status_bar "$udid" clear
