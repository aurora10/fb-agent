#!/usr/bin/env python3
"""Render drafts (with existing images) into previews/index.html gallery + per-post text."""
import html, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE   # honours SITE / sites/<name>

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
  <details class="prompt"><summary>image_prompt</summary><pre class="ip">{html.escape(d.get('image_prompt',''))}</pre></details>
  <pre>{html.escape(d['post'])}</pre>
  <div class="cmd">goedkeuren: <code>./approve {num}</code> · beeld opnieuw: <code>fb_regen_image.py {num} "..."</code></div>
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
.prompt{{font-size:11px;color:#555;margin:6px 0}}
.prompt .ip{{white-space:pre-wrap;background:#f6f6f8;padding:6px;border-radius:4px;font-size:11px}}
</style>{''.join(cards)}""")
    print(f"[ok] previews/index.html ({len(cards)} cards) — open in browser")

if __name__ == "__main__":
    main()
