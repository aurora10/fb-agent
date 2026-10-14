#!/usr/bin/env python3
"""Rewrite drafts' image_prompt into a scene-only description.

Usage: fb_restyle_prompts.py [NN ...]     default: every draft in drafts/

Why: the house style lives in data/image_style.txt and is appended at generation time.
Prompts written before that file existed describe rendering too ("photorealistic",
"cinematic", "documentary style") and contradict it. This regenerates just the scene
description — the post text is never touched.

The replaced prompt is kept as `image_prompt_prev`, so
`fb_regen_image.py NN --revert` undoes it.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, ask, client

STYLE_SNIPPET = 400     # how much of the style file to show the model as context


def targets(argv):
    if not argv:
        return sorted((BASE / "drafts").glob("draft_*.json"))
    out = []
    for a in argv:
        if not a.isdigit():
            sys.exit(f"error: {a!r} is not a draft number (try: fb_restyle_prompts.py 5 6)")
        f = BASE / "drafts" / f"draft_{int(a):02d}.json"
        if not f.exists():
            sys.exit(f"error: {f} does not exist")
        out.append(f)
    return out


def main(argv):
    files = targets(argv)
    if not files:
        sys.exit("error: no drafts found — run fb_plan.py first")

    cl = client()
    from fb_imagegen import style
    sty = style()

    system = (
        "You write image scene descriptions. Write ONLY in ENGLISH, whatever language the "
        "post is in.\n\n"
        "Describe only WHAT is visible: objects, people, materials, actions and composition. "
        "Do NOT describe style, lighting, colours, camera angle or rendering — those come "
        "from a fixed house style prompt.\n"
        "Banned words and anything like them: photorealistic, photo-realistic, cinematic, "
        "documentary, 3D render, hyperrealistic, dramatic lighting, glossy, ultra detailed, "
        "8k, octane, unreal engine.\n"
        "1 to 3 sentences. No text or logos in frame, no front-facing faces.\n\n"
        f"The fixed house style your description must fit with (do not restate it):\n"
        f"{sty[:STYLE_SNIPPET]}"
    )

    changed = 0
    for f in files:
        d = json.loads(f.read_text())
        num = f.stem.split("_")[1]
        old = d.get("image_prompt", "")
        data = ask(cl, system, (
            f"Post topic: {d.get('topic', '')}\n"
            f"Post text: {d.get('post', '')[:700]}\n\n"
            "Describe the scene for this post's image. Reply in ENGLISH only.\n"
            "JSON: {\"image_prompt\": \"...\"}"
        ))
        new = (data.get("image_prompt") or "").strip()
        if not new:
            print(f"[..] {f.name}: model returned no image_prompt — left unchanged")
            continue
        if new == old:
            print(f"[..] {f.name}: already scene-only")
            continue
        if old:
            d["image_prompt_prev"] = old
        d["image_prompt"] = new
        f.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        changed += 1
        print(f"[ok] {f.name}: {new[:76]}")

    print(f"\nrewrote {changed} of {len(files)} prompt(s)")
    if changed:
        print("undo one with: fb_regen_image.py NN --revert")


if __name__ == "__main__":
    main(sys.argv[1:])
