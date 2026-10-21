#!/usr/bin/env python3
"""Report near-duplicate posts before they reach a live Page.

Usage: fb_check_dupes.py [--threshold 0.5] [NN ...]

Two checks, because both failure modes are silent otherwise:
  1. within the queue  — two posts in drafts/approved/done that say the same thing,
     which is how a pair can end up publishing two days apart;
  2. against history   — a post that substantially repeats something already published.

Similarity is the overlap coefficient (shared words / smaller word set), so a short post
that is wholly contained in a longer one scores high. Words shorter than 4 characters are
ignored, which drops most stopwords in Russian, Dutch and English without a word list.

Exits 1 when anything is flagged. Threshold is a judgement call, not a truth: it costs
nothing to look at a false positive, and a duplicate on a Page costs credibility.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, ask, client, cta, fb_cmd, strip_tags

FOLDERS = ("drafts", "approved", "done")
DEFAULT_THRESHOLD = 0.5
WORD = re.compile(r"[а-яёa-z0-9]{4,}", re.I)


def core(text):
    """The post with its hashtag trail and the site's fixed CTA removed.

    Every post on a site ends with the same CTA and often overlapping hashtags, so
    comparing raw text inflates every pair: two unrelated posts pick up eight or so shared
    tokens for free. Compare only what the author actually varied.
    """
    t = strip_tags(text or "")
    c = cta()
    if c:
        t = t.replace(c, " ")
    return t


def tokens(text):
    return set(WORD.findall(core(text).lower()))


def overlap(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def load_ledger():
    """post start-of-text -> scheduled epoch, so a queued post can be shown with its date."""
    p = BASE / "done" / "scheduled_posts.json"
    if not p.exists():
        return {}
    try:
        rows = json.loads(p.read_text())
    except ValueError:
        return {}
    return {(r.get("text") or "")[:100]: r.get("scheduled") for r in rows}


def load_posts():
    ledger = load_ledger()
    out = []
    for folder in FOLDERS:
        for f in sorted((BASE / folder).glob("*.json")):
            if not re.fullmatch(r"(post|draft)_\d+", f.stem):
                continue
            try:
                d = json.loads(f.read_text())
            except ValueError:
                continue
            body = d.get("post", "")
            if not body.strip():
                continue
            num = f.stem.split("_")[1]
            when = ledger.get(body[:100]) if folder == "done" else None
            out.append({"num": num, "label": f"{f.stem}", "folder": folder,
                        "when": when, "body": body, "tok": tokens(body),
                        "topic": d.get("topic", "")})
    return out


def load_history():
    p = BASE / "data" / "past_posts.txt"
    if not p.exists():
        return []
    return [{"label": "published", "body": t.strip(), "tok": tokens(t)}
            for t in p.read_text().splitlines() if t.strip()]


def fmt_when(ts):
    if not ts:
        return "not scheduled"
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def main(argv):
    threshold = DEFAULT_THRESHOLD
    if "--threshold" in argv:
        i = argv.index("--threshold")
        try:
            threshold = float(argv[i + 1])
        except (IndexError, ValueError):
            sys.exit("error: --threshold needs a number between 0 and 1, e.g. 0.6")
        del argv[i:i + 2]
    only = {f"{int(a):02d}" for a in argv if a.isdigit()}

    posts = [p for p in load_posts() if not only or p["num"] in only]
    history = load_history()
    if not posts:
        print("nothing to check — no posts with text in drafts/, approved/ or done/")
        return 0

    flagged = 0

    print(f"within the queue ({len(posts)} post(s), threshold {threshold:.0%}):")
    pair_found = False
    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            a, b = posts[i], posts[j]
            s = overlap(a["tok"], b["tok"])
            if s >= threshold:
                pair_found = True
                flagged += 1
                print(f"  {s:.0%}  {a['label']} ({fmt_when(a['when'])})"
                      f"  <->  {b['label']} ({fmt_when(b['when'])})")
                print(f"        A: {a['body'][:86]}")
                print(f"        B: {b['body'][:86]}")
    if not pair_found:
        print("  none")

    print()
    print(f"against published history ({len(history)} post(s)):")
    hist_found = False
    for a in posts:
        worst, best = 0.0, ""
        for h in history:
            s = overlap(a["tok"], h["tok"])
            if s > worst:
                worst, best = s, h["body"]
        if worst >= threshold:
            hist_found = True
            flagged += 1
            print(f"  {worst:.0%}  {a['label']} ({fmt_when(a['when'])})")
            print(f"        post     : {a['body'][:86]}")
            print(f"        published: {best[:86]}")
    if not hist_found:
        print("  none")

    # Word overlap cannot see a paraphrase, and paraphrase is exactly what an LLM produces:
    # two posts explaining the same thing in different words score ~33%, under any useful
    # threshold. Ask the model instead — it is one call per batch.
    if len(posts) > 1 and "--lexical-only" not in argv:
        print()
        print("semantic check (same point, different wording):")
        sem = semantic(posts, threshold)
        flagged += sem
        if not sem:
            print("  none")

    print()
    if flagged:
        print(f"{flagged} finding(s). Cancel with: {fb_cmd('cancel', '<post-id>')}")
        print(f"see the queue with: {fb_cmd('list')}")
        return 1
    print("no near-duplicates found")
    return 0


def semantic(posts, threshold):
    """One call: which pairs would read as repetitive to a human?"""
    listing = "\n\n".join(
        f"[{i}] {p['body'][:600]}" for i, p in enumerate(posts, 1))
    try:
        data = ask(client(), (
            "You review batches of social media posts for one Page and spot pairs that make "
            "the SAME POINT — the kind a reader would notice as repetitive. Wording may "
            "differ completely. Do NOT flag posts that merely share a topic area but say "
            "something different. Reply with JSON only."
        ), (
            f"{listing}\n\n"
            "Return every pair that says the same thing. Use the bracket numbers.\n"
            'JSON: {"duplicates": [{"a": 1, "b": 2, "why": "one line"}]}'
        ))
    except SystemExit:
        print("  skipped — the model could not be reached")
        return 0

    pairs = data.get("duplicates") if isinstance(data, dict) else None
    if not pairs:
        return 0
    n = 0
    for d in pairs:
        try:
            a, b = posts[int(d["a"]) - 1], posts[int(d["b"]) - 1]
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        n += 1
        print(f"  {a['label']} ({fmt_when(a['when'])})"
              f"  <->  {b['label']} ({fmt_when(b['when'])})")
        print(f"        {str(d.get('why', ''))[:100]}")
    return n


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
