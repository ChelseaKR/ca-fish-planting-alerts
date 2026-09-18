#!/usr/bin/env bash
# Accessibility and performance gates over the built site: CI-CD-STANDARD
# §1 stages 6 (a11y) and 7 (perf). The same script runs locally and in
# .github/workflows/site-checks.yml.
#
#   1. Build the site from the committed fixture: offline, and nothing is
#      written inside the checkout.
#   2. Serve it on a free local port.
#   3. axe-core on every page, which covers A11Y-01 and the A11Y-09 reflow
#      check (axe.mjs).
#   4. pa11y-ci with the axe runner, WCAG2AA, on every page (A11Y-03).
#   5. Lighthouse CI on four representative pages (home, about, a water
#      page, a county page), run three times each:
#      accessibility >= 0.90 (A11Y-02); performance >= 0.90, script and
#      Core Web Vitals lab budgets (PERF-02, OBS-23/25, TBT as the lab
#      stand-in for INP). Then the >10% regression check against
#      perf/baseline.json (PERF-03).
#
# Google Analytics is blocked in every browser this script starts. The
# pages carry the production GA4 tag, and a CI run must not send page views
# to the real property. The script budget in perf/lighthouserc.json is
# therefore first-party only, and it is sized so that first-party script
# plus gtag.js stays under PERFORMANCE-STANDARD's 204,800 B. See
# perf/README.md.
#
# Setup, once: (cd tools/site-checks && npm ci && npx puppeteer browsers install chrome)
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
tools="$root/tools/site-checks"
work="$(mktemp -d)"
server_pid=""
cleanup() {
  if [ -n "$server_pid" ]; then kill "$server_pid" 2>/dev/null || true; fi
  rm -rf "$work"
}
trap cleanup EXIT

echo "== the checkers' own dependencies (SEC-12/13 applied to this toolchain)"
# package.json overrides @puppeteer/browsers and tmp past their HIGH
# advisories (perf/README.md). This keeps it that way: a lockfile that
# brings a fixed HIGH or CRITICAL back fails here.
(cd "$tools" && npm audit --audit-level=high --no-fund)

echo "== build the site from the fixture"
# Served under the same path prefix as production (the default base URL's
# path, /ca-fish-planting-alerts/). 404.html links its stylesheet by that
# absolute path because GitHub Pages serves it at any missing URL, so a site
# served from / would test an unstyled 404 page that nobody ever sees.
prefix="$(cd "$root/pipeline" && uv run --frozen python -c \
  'from urllib.parse import urlsplit; from cfpa.cli import DEFAULT_BASE_URL; print(urlsplit(DEFAULT_BASE_URL).path.strip("/"))')"
site="$work/root/$prefix"
mkdir -p "$site"
(cd "$root/pipeline" && uv run --frozen cfpa \
  --fixture tests/fixtures/schedule-fresh-2026-09-13.html \
  --fixture-fetched-at 2026-09-13T12:00:00Z \
  --run-today 2026-09-13 \
  --history "$work/history.json" \
  --aliases "$work/aliases.json" \
  --site-out "$site")

# Every page, relative to the site root: "about/index.html" becomes
# "about/", the home page "./", and 404.html stays as it is.
pages_file="$work/pages.txt"
(cd "$site" && find . -name '*.html' | LC_ALL=C sort) \
  | sed -e 's#^\./##' -e 's#index\.html$##' -e 's#^$#./#' > "$pages_file"
page_count="$(wc -l < "$pages_file" | tr -d ' ')"
if [ "$page_count" -lt 10 ]; then
  echo "site-checks: only $page_count page(s) built; refusing to pass a near-empty site" >&2
  exit 1
fi
echo "   $page_count pages"

port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
base="http://127.0.0.1:$port/$prefix/"
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$work/root" > "$work/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 50); do
  if curl -fsS -o /dev/null "$base" 2>/dev/null; then break; fi
  sleep 0.2
done
curl -fsS -o /dev/null "$base"

cd "$tools"
chrome="$(node -e 'Promise.resolve(require("puppeteer").executablePath()).then((p) => console.log(p))')"
if [ ! -x "$chrome" ]; then
  echo "site-checks: no Chrome at $chrome; run: (cd tools/site-checks && npx puppeteer browsers install chrome)" >&2
  exit 1
fi

echo "== axe-core (A11Y-01, A11Y-09)"
xargs node axe.mjs "$base" < "$pages_file"

echo "== pa11y-ci, axe runner, WCAG2AA (A11Y-03)"
python3 - "$base" "$pages_file" "$chrome" > "$work/pa11yci.json" <<'PY'
import json, sys
base, pages_file, chrome = sys.argv[1:4]
urls = [base + line.strip().removeprefix("./") for line in open(pages_file, encoding="utf-8") if line.strip()]
print(json.dumps({
    "defaults": {
        "standard": "WCAG2AA",
        "runners": ["axe"],
        "level": "error",
        "timeout": 60000,
        "chromeLaunchConfig": {
            "executablePath": chrome,
            "args": [
                "--no-sandbox",
                "--host-resolver-rules=MAP *.googletagmanager.com ~NOTFOUND, "
                "MAP *.google-analytics.com ~NOTFOUND",
            ],
        },
    },
    "urls": urls,
}))
PY
npx --no-install pa11y-ci --config "$work/pa11yci.json"

echo "== Lighthouse CI (A11Y-02, PERF-02, OBS-23/25)"
water="$(grep -m1 '^water/' "$pages_file")"
county="$(grep -m1 '^county/[^/]*/$' "$pages_file")"
mkdir -p "$work/lhci"
(cd "$work/lhci" && CHROME_PATH="$chrome" npx --prefix "$tools" --no-install lhci collect \
  --config="$root/perf/lighthouserc.json" \
  --url="$base" --url="${base}about/" --url="$base$water" --url="$base$county")
(cd "$work/lhci" && npx --prefix "$tools" --no-install lhci assert --config="$root/perf/lighthouserc.json")

echo "== baseline regression (PERF-03)"
(cd "$root" && python3 scripts/perf_baseline.py --self-test)
(cd "$root" && python3 scripts/perf_baseline.py "$work/lhci/.lighthouseci")

echo "site-checks: all gates passed"
