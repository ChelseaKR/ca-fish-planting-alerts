#!/usr/bin/env bash
# The web push test's numbers (DECISIONS 0069): the live subscription count
# and the service's totals, read from the service's own /counts route with
# the sender token from SSM. Run as the trouttruck AWS account (for example
# `_agent-tools/aws-as-trouttruck.sh` or an AWS profile) from the repository
# root, so `gh` can read the PUSH_API_URL variable; or set PUSH_API_URL.
#
# The 60-day read (0069) puts these next to GA4: subscribes per 100 engaged
# sessions = subscribes / engaged sessions on California and Tennessee water
# pages x 100, for the same 60 days.
set -euo pipefail

prefix="${PUSH_SSM_PREFIX:-/trout-truck/web-push}"
api="${PUSH_API_URL:-}"
if [ -z "$api" ]; then
  api="$(gh variable get PUSH_API_URL 2>/dev/null || true)"
fi
if [ -z "$api" ]; then
  echo "set PUSH_API_URL to the function URL, or run from the repository checkout where gh can read the variable" >&2
  exit 2
fi

token="$(aws ssm get-parameter --with-decryption --name "$prefix/sender-token" --query Parameter.Value --output text)"
# The token goes to curl through a file, never on the command line.
umask 077
header="$(mktemp)"
trap 'rm -f "$header"' EXIT
printf 'Authorization: Bearer %s\n' "$token" > "$header"

curl -fsS --proto '=https' --max-time 30 -H @"$header" "${api%/}/counts" \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("live subscriptions:", d.get("live_subscriptions", "unknown"))
print("of those, on the Apple push service (iPhone, iPad or a Mac):", d.get("live_apple", "unknown"))
counters = d.get("counters", {})
if not counters:
    print("no totals yet: nothing has been subscribed or sent")
for k in sorted(counters):
    print(f"{k}: {counters[k]}")
'
