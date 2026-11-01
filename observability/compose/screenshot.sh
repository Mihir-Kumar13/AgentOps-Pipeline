#!/usr/bin/env bash
# Capture a Grafana page with headless Chrome (uses a throwaway profile).
# Usage: observability/compose/screenshot.sh <url> <out.png> [width] [height]
set -euo pipefail
url=$1 out=$2 width=${3:-1600} height=${4:-1400}
profile=$(mktemp -d)
trap 'rm -r "$profile"' EXIT
"${CHROME:-google-chrome}" --headless=new --disable-gpu --hide-scrollbars \
  --user-data-dir="$profile" --window-size="$width,$height" \
  --virtual-time-budget=25000 --screenshot="$out" "$url" 2>/dev/null
echo "saved $out"
