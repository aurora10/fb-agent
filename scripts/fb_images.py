#!/usr/bin/env python3
"""Generate images for drafts via Pollinations (free, no key). -> images/NN.png"""
import json, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent

def main():
    (BASE / "images").mkdir(parents=True, exist_ok=True)
    for f in sorted((BASE / "drafts").glob("draft_*.json")):
        d = json.loads(f.read_text())
        num = f.stem.split("_")[1]
        img = BASE / "images" / f"{num}.png"
        if img.exists():
            continue
        prompt = urllib.parse.quote(d["image_prompt"][:300])
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "fb-agent/1.0"})
                data = urllib.request.urlopen(req, timeout=120).read()
                if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
                    img.write_bytes(data)
                    print(f"[ok] {img.name} ({len(data)//1024} KB)")
                    break
            except Exception as e:
                print(f"[retry {attempt+1}] {num}: {e}")
                time.sleep(5)
        else:
            print(f"[FAIL] image {num}")

if __name__ == "__main__":
    main()
