#!/usr/bin/env python3
"""Regenerate (or just reword) the image prompt for one draft.

Usage: fb_regen_image.py NN "new prompt text"     regenerate with a new prompt
       fb_regen_image.py NN                        regenerate with the stored prompt
       fb_regen_image.py NN "new prompt" --edit-only
                                                   only update draft_NN.json, no image
NN is the draft number (e.g. 3 or 03).
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent
IMAGES = BASE / "images"
POLLINATIONS = "https://image.pollinations.ai/prompt/{}?width=1024&height=1024&nologo=true"


def fetch(prompt):
    """Pollinations → image bytes, or None after real network retries.

    The directory is created by the caller before this runs, so a missing-folder error
    can no longer masquerade as a flaky image service.
    """
    url = POLLINATIONS.format(urllib.parse.quote(prompt[:300]))
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fb-agent/1.0"})
            data = urllib.request.urlopen(req, timeout=120).read()
        except Exception as e:                       # network: worth retrying
            print(f"[retry {attempt + 1}] {e}")
            time.sleep(8)
            continue
        if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
            return data
        print(f"[retry {attempt + 1}] response was not an image ({len(data)} bytes)")
        time.sleep(8)
    return None


def main(argv):
    if not argv:
        sys.exit(__doc__)
    try:
        num = f"{int(argv[0]):02d}"
    except ValueError:
        sys.exit(f"error: {argv[0]!r} is not a draft number (try: fb_regen_image.py 03)")

    edit_only = "--edit-only" in argv
    prompt_args = [a for a in argv[1:] if a != "--edit-only"]

    f = BASE / "drafts" / f"draft_{num}.json"
    if not f.exists():
        sys.exit(f"error: {f} does not exist — run fb_plan.py first, or check the number")

    d = json.loads(f.read_text())
    # Joined with a space, not "": `NN gevel renovatie` used to silently become "gevelrenovatie".
    prompt = " ".join(prompt_args).strip() or d.get("image_prompt", "")
    if not prompt:
        sys.exit(f"error: draft_{num}.json has no image_prompt and none was given")

    d["image_prompt"] = prompt
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2))

    if edit_only:
        print(f"[ok] draft_{num}.json prompt updated (no image generated)")
        return

    IMAGES.mkdir(parents=True, exist_ok=True)
    img = IMAGES / f"{num}.png"

    data = fetch(prompt)
    if data is None:
        sys.exit("[FAIL] could not fetch an image from Pollinations — try again shortly. "
                 f"draft_{num}.json already holds the new prompt, so re-run with no prompt arg.")

    # Keep one previous version, not one per attempt.
    if img.exists():
        backup = IMAGES / f"{num}.old.png"
        backup.unlink(missing_ok=True)
        img.rename(backup)
    img.write_bytes(data)
    print(f"[ok] {img.name} ({len(data) // 1024} KB) — rerun fb_preview.py")


if __name__ == "__main__":
    main(sys.argv[1:])
