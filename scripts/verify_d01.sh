#!/usr/bin/env bash
# D01: verify fb-agent pipeline (no network writes, no API spend)
set -e
cd "$(dirname "$0")/.."
V=.venv/bin/python

echo "-- scripts compile"
$V -m py_compile scripts/fb_plan.py scripts/fb_images.py scripts/fb_preview.py scripts/fb_export_csv.py

echo "-- plan dry-run scaffold"
T=$(mktemp -d); cp -r scripts data "$T/"
mkdir -p "$T"/{drafts,approved,done,images,previews}
echo "Testonderwerp: testweek voor aannemers" > "$T/data/topics.txt"
(cd "$T" && /opt/data/fb-agent/.venv/bin/python scripts/fb_preview.py | grep -q index.html || true)

echo "-- preview renders with 0 drafts"
[ -f "$T/previews/index.html" ] && grep -q "FB previews" "$T/previews/index.html"

echo "-- export guard: nothing approved exits cleanly"
(cd "$T" && /opt/data/fb-agent/.venv/bin/python scripts/fb_export_csv.py 2030-01-01 2 | grep -q "nothing approved")

echo "-- dirs exist"
for d in drafts approved done images previews data scripts; do [ -d "$d" ]; done

rm -rf "$T"
echo "== D01 PASS =="
