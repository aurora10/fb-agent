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
from fb_llm import BASE, ask, client, data_file, history_block, show_models

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


def plan(topics):
    cl = client()
    (BASE / "drafts").mkdir(parents=True, exist_ok=True)
    system = (
        "Je schrijft Facebook-posts voor Constructief (constructief-bouw.be), "
        "een Belgische tussenpersoon die voor gecontroleerde Oost-Europese bouwteams legt voor aannemers. "
        "Toon: professioneel, direct, Vlaams Nederlands. Max 120 woorden. "
        "Eindig met 1 call-to-action (contact/website) + 3-5 hashtags. "
        f"Context: {CTX[:2000]}\n\n"
        + history_block()
    )
    for i, topic in enumerate(topics, start=next_number()):
        out = BASE / "drafts" / f"draft_{i:02d}.json"
        if out.exists():
            sys.exit(f"error: {out.name} already exists — refusing to overwrite it.\n"
                     f"       this should not happen with max+1 numbering; check drafts/ "
                     f"for a numbering clash")
        data = ask(cl, system, (
            f"Schrijf een Facebook-post over dit onderwerp: {topic}\n\n"
            "Geef OOK een image_prompt in het Engels voor een foto-realistische illustratie "
            "(bouwwerf, team aan het werk, geen logos/tekst in beeld, geen gezichten frontaal).\n\n"
            "JSON antwoord: {\"post\": \"...\", \"image_prompt\": \"...\"}"
        ))
        if "post" not in data:
            sys.exit(f"error: model returned no 'post' key for topic {topic!r}")
        data["topic"] = topic
        data["status"] = "draft"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[ok] {out.name}: {topic}")


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
            sys.exit("error: data/topics.txt is empty — run fb_content_plan.py first")

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
        plan(taken)

        # Only shrink the queue after drafting succeeded; a crash mid-run must not lose topics.
        TOPICS.write_text("".join(t + "\n" for t in queued[len(taken):]))
        remaining = len(queued) - len(taken)
        print(f"[ok] data/topics.txt: {remaining} topic(s) left in the queue")
        if remaining:
            print(f"     next batch: fb_plan.py --limit {min(BATCH_HINT, remaining)}")
