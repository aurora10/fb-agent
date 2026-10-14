#!/usr/bin/env python3
"""Export approved posts to Meta Business Suite Planner bulk-upload CSV -> done/.
Planner bulk format (comma CSV): Date,Time,Content,Link,Image filename
Run: ./scripts/fb_export_csv.py 2026-10-16 2      (start date, every N days, 10:00)
"""
import csv, json, sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).parent.parent

def main():
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() + timedelta(days=1)
    step = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    posts = sorted((BASE / "approved").glob("post_*.json"))
    if not posts:
        print("nothing approved"); return
    out = BASE / "done" / f"planner_upload_{start.isoformat()}.csv"
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        for i, f in enumerate(posts):
            d = date.fromordinal(start.toordinal() + i * step)
            dta = json.loads(f.read_text())
            num = f.stem.split("_")[1]
            img = f"{num}.png" if (BASE / "images" / f"{num}.png").exists() else ""
            w.writerow([d.isoformat(), "10:00", dta["post"], "https://constructief-bouw.be", img])
            f.rename(BASE / "done" / f.name)
            print(f"[ok] {d} 10:00  post_{num}")
    print(f"\n==> upload {out} in Meta Business Suite > Planner > Create > Bulk upload")
    print(f"==> and upload the images from {BASE / 'images'} alongside")

if __name__ == "__main__":
    main()
