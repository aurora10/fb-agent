#!/usr/bin/env python3
"""Replace the improvised call-to-action in existing posts with the pinned one.

Usage: fb_fix_cta.py [NN ...] [--dry-run]

Posts written before data/cta.txt existed end with a model-invented CTA — some with the
full https://constructief-bouw.be/nl/werkgevers link, some with the bare domain, each
worded differently. This rewrites just that trailing part.

Images are untouched: the picture is generated from `image_prompt`, and the CTA is not
part of it.

Always run --dry-run first. The old text is kept as `post_prev`, so a mistake is
recoverable, but text surgery on 13 posts deserves a read-through.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, cta

FOLDERS = ("drafts", "approved", "done")
TAG_RE = re.compile(r"((?:\s*#[\w\u00c0-\u024f]+)+)\s*$")
# Phrases that mark the closing call-to-action. Deliberately narrow: a false positive
# silently deletes a real sentence, so this errs towards leaving text alone.
CTA_HINT = re.compile(
    r"(https?://\S+|constructief-bouw\.be|contacteer ons|neem contact|plan een gesprek|"
    r"meer weten|ontdek hoe|bekijk onze|vraag het aan|bel ons|stuur een bericht)",
    re.I,
)


def locate(argv):
    nums = [a for a in argv if a.isdigit()]
    files = []
    for folder in FOLDERS:
        for f in sorted((BASE / folder).glob("*.json")):
            stem = f.stem
            if not re.fullmatch(r"(post|draft)_\d+", stem):
                continue
            num = stem.split("_")[1]
            if nums and num not in {f"{int(n):02d}" for n in nums}:
                continue
            files.append(f)
    return files


def split_tags(text):
    """(body without the hashtag trail, the trail)"""
    text = (text or "").strip()
    m = TAG_RE.search(text)
    if not m:
        return text, ""
    return text[:m.start()].strip(), m.group(1).strip()


def drop_trailing_cta(body):
    """Remove trailing sentences that look like a call-to-action."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", body) if p.strip()]
    while parts and CTA_HINT.search(parts[-1]):
        parts.pop()
    return " ".join(parts).strip()


def fix(text):
    body, tags = split_tags(text)
    stripped = drop_trailing_cta(body)
    if not stripped:
        return None, body, tags      # the whole post was a CTA; refuse to gut it
    new = f"{stripped}\n\n{cta()}" + (f"\n{tags}" if tags else "")
    return new, body, tags


def main(argv):
    dry = "--dry-run" in argv
    files = locate([a for a in argv if a != "--dry-run"])
    if not files:
        sys.exit("error: no post/draft JSON found (looked in drafts/, approved/, done/)")

    pinned = cta()
    if not pinned:
        sys.exit("error: data/cta.txt is empty — nothing to apply")

    changed = skipped = unchanged = 0
    for f in files:
        d = json.loads(f.read_text())
        old = d.get("post", "")
        new, body, tags = fix(old)

        if new is None:
            print(f"[!!] {f.name}: whole post looks like a CTA — left alone, check by hand")
            skipped += 1
            continue
        if pinned in body:
            print(f"[..] {f.name}: already uses the pinned CTA")
            unchanged += 1
            continue

        print(f"\n{'[dry]' if dry else '[ok ]'} {f.name}")
        print(f"   removed tail: ...{body[-95:]}")
        print(f"   added       : {pinned.splitlines()[-1]}")
        if dry:
            changed += 1
            continue

        d["post_prev"] = old          # recoverable
        d["post"] = new
        # untouched: image_prompt, hashtags, topic, status — the image is unaffected
        f.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        changed += 1

    print(f"\n{changed} changed" + (", " if skipped or unchanged else "")
          + (f"{unchanged} already correct, " if unchanged else "")
          + (f"{skipped} needing manual review" if skipped else "")
          + ("  (--dry-run: nothing written)" if dry else ""))
    if not dry and changed:
        print("images/ untouched — nothing to regenerate")
        print("to schedule these, move them back: mv done/post_NN.json approved/")


if __name__ == "__main__":
    main(sys.argv[1:])
