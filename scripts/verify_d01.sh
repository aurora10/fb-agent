#!/usr/bin/env bash
# D01: verify fb-agent pipeline (no network writes, no API spend)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
V="$ROOT/.venv/bin/python"
if [ ! -x "$V" ]; then
  echo "!! no venv at $V"
  echo "   run: uv venv .venv && uv pip install --python .venv/bin/python openai python-dotenv"
  exit 1
fi

echo "-- scripts compile"
"$V" -m py_compile \
  "$ROOT/scripts/fb_plan.py" "$ROOT/scripts/fb_images.py" "$ROOT/scripts/fb_preview.py" \
  "$ROOT/scripts/fb_export_csv.py" "$ROOT/scripts/fb_api.py" "$ROOT/scripts/import_past_posts.py"

echo "-- scaffold mirroring a FRESH CLONE"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cp -r "$ROOT/scripts" "$ROOT/data" "$ROOT/approve" "$T/"
# Deliberately create NO pipeline dirs: drafts/, approved/, images/, previews/ and done/
# are all gitignored, so a fresh clone has none of them and every step must cope.

echo "-- preview renders with 0 drafts"
(cd "$T" && "$V" scripts/fb_preview.py) | grep -q "previews/index.html"
grep -q "FB previews" "$T/previews/index.html"

echo "-- preview renders with 1 draft + approve hint"
mkdir -p "$T/drafts"          # fixture: fb_plan.py creates this itself when it writes a draft
printf '{"post":"testpost","image_prompt":"x","topic":"t","status":"draft"}\n' > "$T/drafts/draft_01.json"
(cd "$T" && "$V" scripts/fb_preview.py) | grep -q "(1 cards)"
grep -q "./approve 01" "$T/previews/index.html"

echo "-- export guard: nothing approved exits cleanly"
(cd "$T" && "$V" scripts/fb_export_csv.py 2030-01-01 2) | grep -q "nothing approved"

echo "-- schedule guard: nothing approved, and needs no token in --dry-run"
(cd "$T" && "$V" scripts/fb_api.py schedule --dry-run --start 2030-01-01) | grep -q "nothing in approved"

echo "-- approve creates approved/ when it does not exist (fresh-clone case)"
(cd "$T" && ./approve 1) | grep -q "approved post_01"
[ -f "$T/approved/post_01.json" ] || { echo "   !! post_01.json was not created"; exit 1; }

echo "-- schedule guard: refuses a window beyond 30 days"
# Capture first, then grep: with `set -o pipefail` a non-zero producer fails the pipeline
# even when grep matches, which would silently turn this assertion into a no-op.
out="$(cd "$T" && "$V" scripts/fb_api.py schedule --dry-run --start 2030-01-01 2>&1 || true)"
if grep -q "30-day" <<<"$out"; then
  echo "   ok: refused"
else
  echo "   !! 30-day guard did not fire; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_plan --help works without a key"
(cd "$T" && env -u OPENAI_API_KEY "$V" scripts/fb_plan.py --help) | grep -q "Usage"

echo "-- no stale absolute paths"
# --exclude self: this check's own pattern would otherwise match itself.
# --exclude-dir __pycache__: stale bytecode can hold strings the source no longer has.
if grep -rn "/opt/data" "$ROOT/scripts" "$ROOT/README.md" "$ROOT/docs" "$ROOT/approve" \
     --exclude=verify_d01.sh --exclude-dir=__pycache__ >/dev/null 2>&1; then
  echo "   !! /opt/data is still referenced:"
  grep -rn "/opt/data" "$ROOT/scripts" "$ROOT/README.md" "$ROOT/docs" "$ROOT/approve" \
    --exclude=verify_d01.sh --exclude-dir=__pycache__ | sed 's/^/      /'
  exit 1
fi
echo "   ok: none"

echo "== D01 PASS =="
