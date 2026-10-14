#!/usr/bin/env python3
"""Generate images for drafts via Pollinations (free, no key). -> images/NN.png

Usage: fb_images.py            every draft that has no image yet
       fb_images.py 4 7 12     only those draft numbers (handy for a one-post test)
Existing images are never overwritten (use fb_regen_image.py to redo one).
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent
POLLINATIONS = "https://image.pollinations.ai/prompt/{}?width=1024&height=1024&nologo=true"


def wanted(argv):
    """Draft numbers to render, or None for 'all'."""
    if not argv:
        return None
    nums = set()
    for a in argv:
        if not a.isdigit():
            sys.exit(f"error: {a!r} is not a draft number (try: fb_images.py 4 7)")
        nums.add(f"{int(a):02d}")
    return nums


def render(num, prompt):
    img = BASE / "images" / f"{num}.png"
    url = POLLINATIONS.format(urllib.parse.quote(prompt[:300]))
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fb-agent/1.0"})
            data = urllib.request.urlopen(req, timeout=120).read()
            if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
                img.write_bytes(data)
                print(f"[ok] {img.name} ({len(data) // 1024} KB)")
                return True
        except Exception as e:
            print(f"[retry {attempt + 1}] {num}: {e}")
            time.sleep(5)
    print(f"[FAIL] image {num}")
    return False


def main(argv):
    only = wanted(argv)
    (BASE / "images").mkdir(parents=True, exist_ok=True)
    drafts = sorted((BASE / "drafts").glob("draft_*.json"))

    if only:
        have = {f.stem.split("_")[1] for f in drafts}
        missing = sorted(only - have)
        if missing:
            print(f"[..] no draft for: {', '.join(missing)} — skipping")

    todo, skipped = [], 0
    for f in drafts:
        num = f.stem.split("_")[1]
        if only and num not in only:
            continue
        if (BASE / "images" / f"{num}.png").exists():
            skipped += 1
            continue
        todo.append((num, json.loads(f.read_text())["image_prompt"]))

    if not todo:
        print("nothing to do — every selected draft already has an image"
              if skipped else "no matching drafts")
        return

    print(f"generating {len(todo)} image(s)"
          + (f", {skipped} already present" if skipped else "")
          + " — roughly one per minute")
    ok = sum(render(num, prompt) for num, prompt in todo)
    print(f"done: {ok}/{len(todo)}")


if __name__ == "__main__":
    main(sys.argv[1:])
