#!/usr/bin/env python3
"""Regenerate the image for one draft with a new prompt.
Usage: fb_regen_image.py 03 "nieuwe prompt tekst"     (03 = draft number)
Empty prompt → reuse the prompt already stored in draft_03.json.
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    num = f"{int(sys.argv[1]):02d}"
    f = BASE / "drafts" / f"draft_{num}.json"
    d = json.loads(f.read_text())
    prompt = "".join(sys.argv[2:]).strip() or d["image_prompt"]
    d["image_prompt"] = prompt
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2))

    img = BASE / "images" / f"{num}.png"
    if img.exists():
        img.rename(img.with_suffix(f".old_{int(time.time())}.png"))
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:300])}?width=1024&height=1024&nologo=true"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fb-agent/1.0"})
            data = urllib.request.urlopen(req, timeout=120).read()
            if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
                img.write_bytes(data)
                print(f"[ok] {img.name} ({len(data)//1024} KB) — rerun fb_preview.py")
                return
        except Exception as e:
            print(f"[retry {attempt+1}] {e}")
            time.sleep(8)
    print("[FAIL] image still not generated — try again in a minute")

if __name__ == "__main__":
    main()
