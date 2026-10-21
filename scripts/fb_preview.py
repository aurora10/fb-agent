#!/usr/bin/env python3
"""Render drafts (with existing images) into previews/index.html gallery + per-post text."""
import html, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, REPO, fb_cmd   # honours SITE / sites/<name>

def main():
    (BASE / "previews").mkdir(parents=True, exist_ok=True)
    cards = []
    for f in sorted((BASE / "drafts").glob("draft_*.json")):
        d = json.loads(f.read_text())
        num = f.stem.split("_")[1]
        img = (BASE / "images" / f"{num}.png")
        img_html = f'<img src="../images/{num}.png">' if img.exists() else "<div class='noimg'>no image yet</div>"
        cards.append(f"""
<div class="card">
  <div class="num">draft_{num} — {html.escape(d.get('topic',''))}</div>
  {img_html}
  <details class="prompt"><summary>image_prompt</summary><pre class="ip">{html.escape(d.get('image_prompt',''))}</pre></details>
  <pre>{html.escape(d['post'])}</pre>
  <div class="tools">tools (not part of the post): <code>{fb_cmd('approve', num)}</code> · <code>{fb_cmd('regen', num, 'NEW PROMPT')}</code></div>
</div>""")
    (BASE / "previews/index.html").write_text(f"""<!doctype html><meta charset=utf-8><title>FB previews</title>
<style>
body{{font-family:system-ui;background:#f0f2f5;margin:0;padding:20px;display:flex;flex-wrap:wrap;gap:20px}}
.card{{background:#fff;border-radius:8px;width:420px;padding:12px;box-shadow:0 1px 3px #0002}}
.num{{font-size:12px;color:#65676b;margin-bottom:8px}}
img{{width:100%;border-radius:6px}}
.noimg{{background:#ddd;height:200px;display:flex;align-items:center;justify-content:center;color:#888}}
pre{{white-space:pre-wrap;font-family:inherit;font-size:14px}}
/* chrome, clearly apart from the post body it sits under */
.tools{{border-top:1px solid #e4e6eb;margin-top:10px;padding-top:8px;font-size:11px;color:#8a8d91}}
.tools code{{background:#f0f2f5;padding:1px 4px;border-radius:3px;color:#1877f2;font-size:11px}}
.prompt{{font-size:11px;color:#555;margin:6px 0}}
.prompt .ip{{white-space:pre-wrap;background:#f6f6f8;padding:6px;border-radius:4px;font-size:11px}}
</style>{''.join(cards)}""")
    with_img = sum(1 for c in cards if "<img " in c)
    out = BASE / "previews" / "index.html"
    try:
        rel = out.relative_to(REPO)
    except ValueError:
        rel = out
    # Print the path from the repo root: "previews/index.html" alone silently opens the
    # ROOT site's gallery, which is a different (often empty) file.
    print(f"[ok] {rel} ({len(cards)} cards, {with_img} with an image)")
    print(f"     open {rel}")

    if not cards:
        # An empty gallery after scheduling is normal, but reads like a failure. The file is
        # still written, so a previously-good gallery cannot linger as stale content.
        scheduled = len(list((BASE / "done").glob("post_*.json")))
        print("[..] no drafts to review — drafts/ is empty.")
        if scheduled:
            print(f"     {scheduled} post(s) are in done/, i.e. already scheduled. To see the queue:")
            print(f"       {fb_cmd('list')}")
            print(f"       {fb_cmd('preview')}")
    elif not with_img:
        print(f"[..] no images yet. After `{fb_cmd('images')}`, re-run this to embed them — "
              "the gallery is a snapshot taken when it runs.")

if __name__ == "__main__":
    main()
