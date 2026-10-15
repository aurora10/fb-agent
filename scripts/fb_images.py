#!/usr/bin/env python3
"""Generate images for drafts -> images/NN.png

Usage: fb_images.py            every draft that has no image yet
       fb_images.py 4 7 12     only those draft numbers (handy for a one-post test)
Existing images are never overwritten (use fb_regen_image.py to redo one).

Provider is IMAGE_PROVIDER in .env: `openai` (default, gpt-image-2) or `pollinations`.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_imagegen import describe, generate
from fb_llm import BASE   # honours SITE / sites/<name>


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
    data = generate(prompt)
    if data is None:
        print(f"[FAIL] image {num}")
        return False
    img.write_bytes(data)
    print(f"[ok] {img.name} ({len(data) // 1024} KB)")
    return True


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
          + f" with {describe()}")
    ok = sum(render(num, prompt) for num, prompt in todo)
    print(f"done: {ok}/{len(todo)}")
    if ok:
        # The gallery is a snapshot, so new images are invisible until this runs again.
        print("     run fb_preview.py to see them in the gallery")


if __name__ == "__main__":
    main(sys.argv[1:])
