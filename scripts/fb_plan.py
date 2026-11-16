#!/usr/bin/env python3
"""Generate FB post drafts (text + image prompt) from topics.

Usage: fb_plan.py TOPIC [TOPIC ...]        generate for topics given inline
       fb_plan.py                          take everything queued in data/topics.txt
       fb_plan.py --limit N                take the next N from the queue (they are
                                           removed from it once drafted)
       fb_plan.py --models                 list chat models your OpenAI key can use
Writes drafts/draft_NN.json
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import (BASE, ask, client, compose_post, data_file, fb_cmd, history_block,
                    show_models, strip_tags)

PERSONA = data_file("persona.txt")     # brand + language + tone; per site
CTX = data_file("context.txt")
TOPICS = BASE / "data" / "topics.txt"
BATCH_HINT = 14     # what one 29-day scheduling window holds at 2-day spacing


def existing_numbers():
    """Draft numbers already in use across drafts/, approved/ and done/."""
    nums = []
    for pat in ("draft_*.json", "post_*.json"):
        for folder in ("drafts", "approved", "done"):
            for p in (BASE / folder).glob(pat):
                stem = p.stem.split("_")[-1]
                if stem.isdigit():
                    nums.append(int(stem))
    return nums


def next_number():
    """max+1, NOT count+1.

    Counting breaks as soon as you delete a duplicate: 16 drafts minus 3 pruned gives a
    count that points back into the surviving range, so the next batch would silently
    overwrite draft_15, draft_16, draft_17.
    """
    return max(existing_numbers(), default=0) + 1


DRAFT_ASK = """Write a Facebook post about this topic: TOPIC

Also return an image_prompt describing ONLY THE SCENE: which objects, people, materials
and actions are visible, and the composition. The image_prompt MUST be written in ENGLISH
and only in ENGLISH — translate any trade terms rather than leaving words in the post's
language. Do NOT describe style, lighting, colours, camera angle or rendering — the visual
style comes from a separate fixed style prompt and must not be contradicted. Never use
'photorealistic', 'cinematic' or '3D render'. No logos or text in frame, no front-facing
faces.

Return 5 hashtags in the same language as the post, as a list, without the #.

JSON: {"post": "...", "hashtags": ["..."], "image_prompt": "..."}"""

REQUIRED = ("post", "image_prompt", "hashtags")


def hashtags_only(cl, post, attempts=2):
    """Ask for just the tag trail.

    Asking for the post, the scene and the tags in one JSON object is where the tags get
    dropped: the model spends its budget on prose and returns two of three keys. A lone
    question about hashtags is answered reliably, and it costs a fraction of a retry.
    """
    for _ in range(attempts):
        got = ask(cl, "You choose hashtags for a social media post. Reply with JSON only.",
                  f"Post:\n{post}\n\nReturn 5 hashtags in the same language as the post, "
                  'as a list, without the #.\nJSON: {"hashtags": ["...", "..."]}')
        tags = [t.strip().lstrip("#") for t in (got.get("hashtags") or [])
                if isinstance(t, str) and t.strip()]
        if tags:
            return tags[:5]
    return []


SCENE_ONLY = """Describe ONLY THE SCENE for an image to accompany this post: which objects,
people, materials and actions are visible, and the composition. Write in ENGLISH only.
Do NOT describe style, lighting, colours, camera angle or rendering — a fixed style prompt
is appended separately. Never write 'photorealistic', 'cinematic' or '3D render'. No logos
or text in frame, no front-facing faces.

Post:
POSTTEXT

JSON: {"image_prompt": "..."}"""


def image_prompt_only(cl, post, attempts=2):
    """Ask for just the scene description, for the same reason as the hashtags.

    This was the field that actually blocked batches: five of fourteen topics produced no
    draft at all because image_prompt came back missing twice in a row, and an earlier
    batch had ten of fourteen incomplete. Asked on its own it is reliable.
    """
    for _ in range(attempts):
        got = ask(cl, "You write image scene descriptions. Reply with JSON only.",
                  SCENE_ONLY.replace("POSTTEXT", post))
        ip = str(got.get("image_prompt") or "").strip()
        if ip and ip.isascii():
            return ip
    print("[..] no English scene prompt after "
          f"{attempts} attempt(s); leaving image_prompt empty")
    return ""


def draft_payload(cl, system, topic, attempts=2):
    """Ask for a draft, then fill the two side fields separately if they are missing.

    Originally the whole payload was required up front, and the model kept returning two of
    three keys — ten of fourteen drafts in one batch came back incomplete, and `images`
    later died on the KeyError. Only the post is worth retrying a topic over. The scene
    prompt and the tags are companion fields that the model answers reliably when they are
    the only thing asked, and a draft with an empty image_prompt is still publishable
    (which matters when images are being reused rather than rendered).
    """
    why = ""
    for attempt in range(1, attempts + 1):
        prompt = DRAFT_ASK.replace("TOPIC", topic, 1)
        if attempt > 1:
            prompt += ("\n\nIMPORTANT: your previous answer was missing " + why +
                       ". Return ALL THREE keys as described.")
        data = ask(cl, system, prompt)
        if not str(data.get("post") or "").strip():
            why = "the post itself"
            print(f"[..] attempt {attempt}: model omitted the post")
            continue
        if not str(data.get("image_prompt") or "").strip():
            data["image_prompt"] = image_prompt_only(cl, data["post"])
        if not isinstance(data.get("hashtags"), list) or not data["hashtags"]:
            tags = hashtags_only(cl, data["post"])
            if tags:
                data["hashtags"] = tags
            else:
                print("[..] no hashtags produced; this post ends without a tag trail")
        return data
    print(f"[!!] skipped: no usable post for {topic!r} after {attempts} attempt(s).")
    return None


def plan(topics):
    """Draft each topic, skipping the ones the model will not fill in. Returns the skips.

    One stubborn topic must not take the other thirteen down with it: a batch is a batch,
    and a topic that fails twice is a topic to retry later, not a reason to stop.
    """
    cl = client()
    (BASE / "drafts").mkdir(parents=True, exist_ok=True)
    # The persona file carries the brand, the output language and the tone, so this module
    # stays language-neutral and a second site is a data change, not a fork.
    system = (
        (PERSONA or "You write social media posts.") + "\n\n"
        f"Context: {CTX[:2000]}\n\n"
        + history_block()
    )
    n = next_number()
    skipped = []
    for topic in topics:
        out = BASE / "drafts" / f"draft_{n:02d}.json"
        if out.exists():
            sys.exit(f"error: {out.name} already exists — refusing to overwrite it.\n"
                     f"       this should not happen with max+1 numbering; check drafts/ "
                     f"for a numbering clash")
        data = draft_payload(cl, system, topic)
        if data is None:
            skipped.append(topic)
            continue                      # the number is reused by the next good draft
        # The CTA is fixed (data/cta.txt), not model-written: left to the model it drifted
        # from the Page's own convention. Belt and braces in case the model still appends tags.
        body = strip_tags(data["post"])
        data["post"] = compose_post(body, data.get("hashtags") or [])
        data["topic"] = topic
        data["status"] = "draft"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[ok] {out.name}: {topic}")
        n += 1
    return skipped


def queued_topics():
    if not TOPICS.exists():
        sys.exit(f"error: {TOPICS} does not exist\n"
                 f"       pass topics as arguments, or run fb_content_plan.py first")
    return [l.strip() for l in TOPICS.read_text().splitlines() if l.strip()]


if __name__ == "__main__":
    args = sys.argv[1:]

    limit = None
    if "--limit" in args:
        i = args.index("--limit")
        try:
            limit = int(args[i + 1])
        except (IndexError, ValueError):
            sys.exit("error: --limit needs a number, e.g. --limit 14")
        if limit < 1:
            sys.exit("error: --limit must be at least 1")
        del args[i:i + 2]

    if args and args[0] in ("-h", "--help"):
        print(__doc__)
    elif args and args[0] == "--models":
        show_models()
    elif args:
        plan(args)                    # topics inline: the queue is left untouched
    else:
        queued = queued_topics()
        if not queued:
            sys.exit(f"error: data/topics.txt is empty — run {fb_cmd('topics')} first")

        if limit and limit < len(queued):
            print(f"[..] queue holds {len(queued)}; taking the first {limit}, "
                  f"leaving {len(queued) - limit} for later batches")
        elif not limit and len(queued) > BATCH_HINT:
            # One scheduling window is ~14 posts, so generating a 90-topic backlog in one
            # go means 90 drafts, 90 rate-limited images and an unusable review gallery.
            print(f"[!!] {len(queued)} topics queued, but one scheduling window holds about "
                  f"{BATCH_HINT}.\n"
                  f"     That would create {len(queued)} drafts and as many images.\n"
                  f"     Re-run as:  fb_plan.py --limit {BATCH_HINT}\n"
                  f"     Continuing with all of them in 8s — Ctrl-C to stop.")
            time.sleep(8)

        taken = queued[:limit] if limit else queued
        skipped = plan(taken)

        # Only shrink the queue after drafting succeeded; a crash mid-run must not lose topics.
        # Topics that produced no draft go back to the FRONT, so the retry is the next thing
        # that happens rather than something buried 86 lines down.
        TOPICS.write_text("".join(t + "\n" for t in skipped + queued[len(taken):]))
        made = len(taken) - len(skipped)
        remaining = len(queued) - len(taken) + len(skipped)
        print(f"[ok] drafted {made} of {len(taken)}; {remaining} topic(s) left in the queue")
        if skipped:
            print(f"[!!] {len(skipped)} topic(s) produced no draft and went back to the queue:")
            for t in skipped:
                print(f"     - {t}")
        if remaining:
            print(f"     next batch: {fb_cmd('plan', '--limit', min(BATCH_HINT, remaining))}")
