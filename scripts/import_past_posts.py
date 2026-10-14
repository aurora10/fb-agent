#!/usr/bin/env python3
"""Import a past-posts export (Meta Business Suite: Content -> Export, or any CSV
with post text) into data/past_posts.txt (one snippet per line) used by fb_plan.py.
Usage: .venv/bin/python scripts/import_past_posts.py <export.csv>
Accepts common column names: content/text/message/description (case-insensitive).
"""
import csv, sys
from pathlib import Path

BASE = Path(__file__).parent.parent

def main():
    src = Path(sys.argv[1])
    out = BASE / "data/past_posts.txt"
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
    if not rows:
        sys.exit("empty or unreadable CSV")
    key = next((k for k in rows[0] if k and k.strip().lower()
                in ("content", "text", "message", "description", "post")), None)
    if not key:
        sys.exit(f"no text column found; columns: {list(rows[0])}")
    texts = []
    for r in rows:
        t = (r.get(key) or "").strip().replace("\n", " ")
        if t:
            texts.append(t)
    out.write_text("\n".join(texts) + "\n")
    print(f"[ok] {out}: {len(texts)} past posts imported")

if __name__ == "__main__":
    main()
