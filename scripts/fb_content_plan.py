#!/usr/bin/env python3
"""Generate an intent-focused topic plan (deduped against past posts and existing topics).

Usage: fb_content_plan.py SEED [SEED ...]   e.g. "gevelrenovatie" "personeelstekort"
       fb_content_plan.py                   uses data/seeds.txt (one seed per line)
Appends new topics to data/topics.txt; delete lines there you don't want before fb_plan.py.
"""
import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, ask, client, data_file, history_block

PER_SEED = 10
PLANNER = data_file("planner.txt")     # strategist brief; per site
CTX = data_file("context.txt")


def norm(t):
    """Compare topics on words alone: the model rewords the same idea every run."""
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower()).strip()


def seeds(args):
    if args:
        return args
    p = BASE / "data" / "seeds.txt"
    if not p.exists():
        sys.exit(f"error: no seeds given and {p} does not exist\n"
                 f"       pass seeds as arguments, e.g. fb_content_plan.py \"gevelrenovatie\"\n"
                 f"       or create that file with one seed theme per line")
    lines = [l.strip() for l in p.read_text().splitlines()
             if l.strip() and not l.startswith("#")]
    if not lines:
        sys.exit(f"error: {p} contains no usable seed lines")
    return lines


def main(args):
    seed_list = seeds(args)      # validate inputs before demanding credentials

    tf = BASE / "data" / "topics.txt"
    queued = [l.strip() for l in tf.read_text().splitlines() if l.strip()] if tf.exists() else []

    cl = client()
    # history_block() carries the published history AND the queued topics, so the model
    # knows what to avoid rather than relying on post-hoc filtering.
    # Brief and output language come from data/planner.txt so a second site needs no code change.
    system = (
        (PLANNER.replace("{n}", str(PER_SEED)) or
         f"Propose {PER_SEED} social post topics about the seed theme.") + "\n\n"
        f"Context: {CTX[:1500]}\n\n"
        + history_block(also_avoid=queued)
    )

    proposed = []
    for seed in seed_list:
        data = ask(cl, system, f"Seed theme: {seed}\nJSON: {{\"topics\": [\"...\", ...]}}")
        topics = [t.strip() for t in (data.get("topics") or [])
                  if isinstance(t, str) and t.strip()]
        if not topics:
            print(f"[..] {seed}: model returned no topics")
            continue
        proposed += topics
        print(f"[ok] {seed}: {len(topics)} onderwerpen")

    # A prompt instruction alone does not stop paraphrases: re-running the same seed produced
    # "Personeelstekort op het dak" alongside an existing "Personeel tekort op het dak?".
    # Comparing two lists is a much easier task than generating while avoiding a list, so
    # filter in a second, focused pass.
    if queued and proposed:
        keep = ask(cl, (
            "Je filtert dubbele content-onderwerpen. Antwoord alleen met JSON."
        ), (
            "Bestaande onderwerpen (already planned):\n"
            + "\n".join(f"- {t}" for t in queued[-150:])
            + "\n\nNieuwe kandidaten:\n"
            + "\n".join(f"- {t}" for t in proposed)
            + "\n\nVerwijder elke kandidaat die inhoudelijk hetzelfde is als een bestaand "
              "onderwerp (ook als de woorden verschillen), en elke kandidaat die dubbel is "
              "met een eerdere kandidaat. Behoud de originele formulering.\n"
              'JSON: {"keep": ["...", ...]}'
        )).get("keep")
        if isinstance(keep, list) and all(isinstance(k, str) for k in keep):
            dropped = len(proposed) - len(keep)
            if dropped > 0:
                print(f"[ok] filter: {dropped} bijna-dubbele onderwerpen verwijderd")
            proposed = [k.strip() for k in keep if k.strip()]

    # Backstop for literal repeats the filter may have let through.
    existing = {norm(t) for t in queued}
    add, seen = [], set()
    for t in proposed:
        key = norm(t)
        if key and key not in existing and key not in seen:
            seen.add(key)
            add.append(t)

    dupes = len(proposed) - len(add)
    if add:
        with tf.open("a") as fh:
            fh.write("".join(t + "\n" for t in add))
        print(f"[ok] data/topics.txt += {len(add)} nieuwe (totaal {len(queued) + len(add)})"
              + (f" — {dupes} duplicaten overgeslagen" if dupes else ""))
    else:
        print("[..] geen nieuwe unieke onderwerpen" + (f" ({dupes} duplicaten)" if dupes else ""))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
    else:
        main(args)
