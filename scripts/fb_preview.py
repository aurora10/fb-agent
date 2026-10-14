#!/usr/bin/env python3
"""Render drafts (with existing images) into previews/index.html gallery + per-post text."""
import html, json
from pathlib import Path

BASE = Path(__file__).parent.parent

def main():
    (BASE / "previews").mkdir(parents=True, exist_ok=True)
    cards = []
    for f in sorted((BASE / "drafts").glob("draft_*.json")):
        d = json.loads(f.read_text())
        num = f.stem.split("_")[1]
        img = (BASE / "images" / f"{num}.png")
        img_html = f'<img src="../images/{num}.png">' if img.exists() else "<div class='noimg'>nog geen beeld</div>"
        cards.append(f"""
<div class="card">
  <div class="num">draft_{num} — {html.escape(d.get('topic',''))}</div>
  {img_html}
  <pre>{html.escape(d['post'])}</pre>
  <div class="cmd">goedkeuren: <code>./approve {num}</code></div>
</div>""")
    (BASE / "previews/index.html").write_text(f"""<!doctype html><meta charset=utf-8><title>FB previews</title>
<style>
body{{font-family:system-ui;background:#f0f2f5;margin:0;padding:20px;display:flex;flex-wrap:wrap;gap:20px}}
.card{{background:#fff;border-radius:8px;width:420px;padding:12px;box-shadow:0 1px 3px #0002}}
.num{{font-size:12px;color:#65676b;margin-bottom:8px}}
img{{width:100%;border-radius:6px}}
.noimg{{background:#ddd;height:200px;display:flex;align-items:center;justify-content:center;color:#888}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:14px}}
.cmd{{font-size:12px;color:#1877f2}}
</style>{''.join(cards)}""")
    print(f"[ok] previews/index.html ({len(cards)} cards) — open in browser")

if __name__ == "__main__":
    main()
