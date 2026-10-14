#!/usr/bin/env python3
"""Regenerate (or just reword) the image prompt for one draft.

Usage: fb_regen_image.py NN "new prompt text"     regenerate with a new prompt
       fb_regen_image.py NN                        regenerate with the stored prompt
       fb_regen_image.py NN "new prompt" --edit-only
                                                   only update draft_NN.json, no image
       fb_regen_image.py NN --revert               swap back to the previous prompt
NN is the draft number (e.g. 3 or 03).

The prompt that was replaced is kept in draft_NN.json as `image_prompt_prev`, so a typo
is reversible — --revert swaps the two and can be run again to swap back.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_imagegen import describe, generate

BASE = Path(__file__).parent.parent
IMAGES = BASE / "images"
FLAGS = ("--edit-only", "--revert")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    try:
        num = f"{int(argv[0]):02d}"
    except ValueError:
        sys.exit(f"error: {argv[0]!r} is not a draft number (try: fb_regen_image.py 03)")

    edit_only = "--edit-only" in argv
    revert = "--revert" in argv
    prompt_args = [a for a in argv[1:] if a not in FLAGS]

    if revert and prompt_args:
        sys.exit("error: --revert restores the previous prompt, so don't pass a new one "
                 "(use --edit-only to set one)")

    f = BASE / "drafts" / f"draft_{num}.json"
    if not f.exists():
        sys.exit(f"error: {f} does not exist — run fb_plan.py first, or check the number")

    d = json.loads(f.read_text())
    old = d.get("image_prompt", "")

    if revert:
        prev = d.get("image_prompt_prev")
        if not prev:
            sys.exit(f"error: draft_{num}.json has no image_prompt_prev — nothing to restore.\n"
                     f"       it is written the first time a prompt is replaced")
        d["image_prompt"], d["image_prompt_prev"] = prev, old
        f.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        print(f"[ok] draft_{num}.json: prompt swapped back to the previous one (no image)")
        print(f"     run --revert again to swap them back")
        return

    # Joined with a space, not "": `NN gevel renovatie` used to silently become "gevelrenovatie".
    prompt = " ".join(prompt_args).strip() or old
    if not prompt:
        sys.exit(f"error: draft_{num}.json has no image_prompt and none was given")

    if prompt != old and old:
        d["image_prompt_prev"] = old        # one step of undo
    d["image_prompt"] = prompt
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2))

    if edit_only:
        print(f"[ok] draft_{num}.json prompt updated (no image generated)")
        if prompt != old and old:
            print(f"     previous prompt kept — undo with: fb_regen_image.py {num} --revert")
        return

    IMAGES.mkdir(parents=True, exist_ok=True)
    img = IMAGES / f"{num}.png"

    print(f"rendering with {describe()}")
    data = generate(prompt)
    if data is None:
        sys.exit(f"[FAIL] no image produced. draft_{num}.json already holds the new prompt, "
                 f"so re-run with no prompt argument to try again.")

    # Keep one previous version, not one per attempt.
    if img.exists():
        backup = IMAGES / f"{num}.old.png"
        backup.unlink(missing_ok=True)
        img.rename(backup)
    img.write_bytes(data)
    print(f"[ok] {img.name} ({len(data) // 1024} KB) — rerun fb_preview.py")


if __name__ == "__main__":
    main(sys.argv[1:])
