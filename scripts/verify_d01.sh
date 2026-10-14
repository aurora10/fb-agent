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

echo "-- scripts compile (every .py in scripts/, so new files can't be forgotten)"
"$V" -m py_compile "$ROOT"/scripts/*.py

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

echo "-- schedule guard: refuses a window beyond 29 days (the measured limit)"
# Capture first, then grep: with `set -o pipefail` a non-zero producer fails the pipeline
# even when grep matches, which would silently turn this assertion into a no-op.
out="$(cd "$T" && "$V" scripts/fb_api.py schedule --dry-run --start 2030-01-01 2>&1 || true)"
if grep -q "29-day" <<<"$out" && grep -q "post(s) fit" <<<"$out"; then
  echo "   ok: refused, and reported how many fit"
else
  echo "   !! 29-day guard did not fire correctly; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_plan --help works without a key"
(cd "$T" && env -u OPENAI_API_KEY "$V" scripts/fb_plan.py --help) | grep -q "Usage"

echo "-- fb_content_plan: clear error when there are no seeds and no seeds.txt"
rm -f "$T/data/seeds.txt"
out="$(cd "$T" && "$V" scripts/fb_content_plan.py 2>&1 || true)"
if grep -q "no seeds given" <<<"$out"; then
  echo "   ok: explained instead of a traceback"
else
  echo "   !! expected a clear no-seeds error; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi
(cd "$T" && "$V" scripts/fb_content_plan.py --help) | grep -q "Usage"

echo "-- fb_regen_image: creates images/ in a fresh clone (offline, network stubbed)"
printf '{"post":"t","image_prompt":"orig","topic":"t","status":"draft"}\n' > "$T/drafts/draft_01.json"
out="$("$V" -c "
import importlib.util, sys, urllib.request
from pathlib import Path
T = Path('$T')
class R:
    def read(self): return b'\xff\xd8\xff' + b'0' * 2000
urllib.request.urlopen = lambda req, timeout=0: R()      # keep this offline
spec = importlib.util.spec_from_file_location('r', str(T / 'scripts' / 'fb_regen_image.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.main(['01', 'stub test'])
print('IMAGES_DIR=' + str((T / 'images').is_dir()))
print('IMAGE_FILE=' + str((T / 'images' / '01.png').is_file()))
" 2>&1)"
if grep -q "IMAGES_DIR=True" <<<"$out" && grep -q "IMAGE_FILE=True" <<<"$out"; then
  echo "   ok: images/ created and image written"
else
  echo "   !! regen did not create images/; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_regen_image: prompt args join with spaces, not concatenated"
(cd "$T" && "$V" scripts/fb_regen_image.py 01 gevel renovatie --edit-only) >/dev/null
if "$V" -c "
import json,sys
sys.exit(0 if json.load(open('$T/drafts/draft_01.json'))['image_prompt']=='gevel renovatie' else 1)
"; then
  echo "   ok: 'gevel renovatie' preserved"
else
  echo "   !! multi-arg prompt was mangled"; exit 1
fi

echo "-- fb_plan: a failed run must not consume the topic queue"
printf 'Topic one\nTopic two\nTopic three\n' > "$T/data/topics.txt"
before="$(grep -c . "$T/data/topics.txt")"
(cd "$T" && "$V" scripts/fb_plan.py --limit 1) >/dev/null 2>&1 || true
after="$(grep -c . "$T/data/topics.txt")"
if [ "$before" = "$after" ]; then
  echo "   ok: $after topics still queued after the failure"
else
  echo "   !! queue went from $before to $after topics on a failed run"; exit 1
fi

echo "-- fb_plan: --limit validates its argument"
out="$(cd "$T" && "$V" scripts/fb_plan.py --limit abc 2>&1 || true)"
if grep -q "needs a number" <<<"$out"; then
  echo "   ok: rejected a non-numeric limit"
else
  echo "   !! --limit accepted junk; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_images: renders only the requested drafts (offline, network stubbed)"
printf '{"post":"t","image_prompt":"p2","topic":"t","status":"draft"}\n' > "$T/drafts/draft_02.json"
rm -f "$T/images"/*.png
out="$("$V" - "$T" <<'PY'
import importlib.util, sys, urllib.request
from pathlib import Path
T = Path(sys.argv[1])
class R:
    def read(self): return b'\xff\xd8\xff' + b'0' * 2000
urllib.request.urlopen = lambda req, timeout=0: R()
spec = importlib.util.spec_from_file_location('i', str(T / 'scripts' / 'fb_images.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.main(['1'])                      # ask for draft 1 only
print('ONE=' + str((T / 'images' / '01.png').is_file()))
print('TWO=' + str((T / 'images' / '02.png').is_file()))
PY
)"
if grep -q "ONE=True" <<<"$out" && grep -q "TWO=False" <<<"$out"; then
  echo "   ok: generated 1, left 2 alone"
else
  echo "   !! draft selection leaks; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_plan: numbers new drafts from max+1, so pruning cannot cause an overwrite"
rm -f "$T"/drafts/draft_*.json
printf 'x\n' > "$T/drafts/draft_04.json"
printf 'x\n' > "$T/drafts/draft_07.json"
out="$(cd "$T" && "$V" - <<'PY'
import sys
sys.path.insert(0, "scripts")
import fb_plan
print("NEXT=" + str(fb_plan.next_number()))
PY
)"
if grep -q "NEXT=8" <<<"$out"; then
  echo "   ok: gaps skipped (04,07 -> next 08)"
else
  echo "   !! numbering would collide; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_regen_image: --revert restores the previous prompt (offline)"
printf '{"post":"t","image_prompt":"ORIGINAL PROMPT","topic":"t","status":"draft"}\n' > "$T/drafts/draft_01.json"
(cd "$T" && "$V" scripts/fb_regen_image.py 01 "typo oops" --edit-only) >/dev/null
(cd "$T" && "$V" scripts/fb_regen_image.py 01 --revert) >/dev/null
if "$V" -c "
import json, sys
d = json.load(open('$T/drafts/draft_01.json'))
sys.exit(0 if d['image_prompt'] == 'ORIGINAL PROMPT' else 1)
"; then
  echo "   ok: back to the original after a typo"
else
  echo "   !! --revert did not restore the prompt"; exit 1
fi

echo "-- fb_regen_image: --revert without a stored prompt fails clearly"
printf '{"post":"t","image_prompt":"p","topic":"t","status":"draft"}\n' > "$T/drafts/draft_02.json"
out="$(cd "$T" && "$V" scripts/fb_regen_image.py 02 --revert 2>&1 || true)"
if grep -q "nothing to restore" <<<"$out"; then
  echo "   ok: explained"
else
  echo "   !! unclear error; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- fb_api preview: no template placeholder survives rendering"
out="$(cd "$T" && "$V" - <<'PY'
import importlib.util, re
spec = importlib.util.spec_from_file_location("fb_api", "scripts/fb_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
card = m.CARD
for k in ("AVATAR", "PAGE", "WHEN", "MESSAGE", "IMAGE", "ID", "PERMALINK"):
    card = card.replace(f"__{k}__", "x")
page = m.PAGE_HTML.replace("__TITLE__", "t").replace("__CARDS__", card)
left = re.findall(r"__[A-Z_]+__", card + page)
print("LEFT=" + (",".join(left) if left else "none"))
# escaping must hold, and hashtags/domains get styled
assert "&lt;script&gt;" in m._linkify("<script>"), "escaping broken"
assert 'class="tag"' in m._linkify("einde #bouwsector"), "hashtags not styled"
assert 'class="tag"' in m._linkify("kijk op constructief-bouw.be"), "domain not styled"
print("SANITISE=ok")
PY
)"
if grep -q "LEFT=none" <<<"$out" && grep -q "SANITISE=ok" <<<"$out"; then
  echo "   ok: placeholders filled, escaping + link styling hold"
else
  echo "   !! preview template problem; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- history block: every published post contributes an angle hook"
# Own fixture: data/past_posts.txt is gitignored, so a fresh clone has none.
printf 'Fixture post one about gevelrenovatie.\nFixture post two about dakwerken.\nFixture post three about betonbouw.\n' > "$T/data/past_posts.txt"
out="$(cd "$T" && "$V" - <<'PY'
import sys
sys.path.insert(0, "scripts")
from fb_llm import history_block, past_posts
n = len(past_posts())
assert n == 3, f"expected the 3 fixture posts, got {n}"
b = history_block()
hooks = b.count("\n- ")
assert hooks >= n, f"only {hooks} hook lines for {n} posts"
print(f"HOOKS_OK {n}")
PY
)"
if grep -q "HOOKS_OK 3" <<<"$out"; then
  echo "   ok: all 3 fixture posts contributed"
else
  echo "   !! history block lost posts; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

echo "-- history block: says what to run when there is no history yet"
mv "$T/data/past_posts.txt" "$T/data/past_posts.bak"
out="$(cd "$T" && "$V" - <<'PY'
import sys
sys.path.insert(0, "scripts")
from fb_llm import history_block
print(history_block())
PY
)"
mv "$T/data/past_posts.bak" "$T/data/past_posts.txt"
if grep -q "past-posts" <<<"$out"; then
  echo "   ok: points at fb_api.py past-posts"
else
  echo "   !! no guidance when history is missing; got:"; echo "$out" | sed 's/^/      /'; exit 1
fi

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
