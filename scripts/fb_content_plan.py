#!/usr/bin/env python3
"""Generate an intent-focused topic plan (deduped against past posts and existing topics).

Usage: fb_content_plan.py SEED [SEED ...]   e.g. "gevelrenovatie" "personeelstekort"
       fb_content_plan.py                   uses data/seeds.txt (one seed per line)
       fb_content_plan.py --from-research   seeds ARE the concerns from data/concerns.json
       fb_content_plan.py --per-seed 3 ...  topics per seed (default 10, or 3 from research)

Appends new topics to data/topics.txt; delete lines there you don't want before fb_plan.py.

--from-research is the mode that actually makes research count. Leaving the concerns as
background did not work: the site's planner brief is all selling points, so the model kept
restating the USP and the brief became decoration. Making each concern the SEED forces the
worry to be the subject of the post.
"""
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import (BASE, CONCERN_TTL_DAYS, ask, client, concerns, concerns_block,
                    data_file, fb_cmd, history_block)

PER_SEED = 10
RESEARCH_PER_SEED = 3      # a concern is already specific; 10 angles on one is padding
PLANNER = data_file("planner.txt")     # strategist brief; per site
CTX = data_file("context.txt")


def norm(t):
    """Compare topics on words alone: the model rewords the same idea every run.

    \\w, not a-z0-9: the Russian Page's topics are Cyrillic, and the old pattern reduced
    every one of them to "" — which the caller reads as falsy and drops. That made
    `topics` a silent no-op for that site. Accented Dutch was mangled the same way.
    """
    return re.sub(r"[^\w ]+", " ", t.lower(), flags=re.UNICODE).strip()


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


def research_seeds():
    """Turn the freshest concerns into seeds, refusing a stale brief.

    Stale is refused rather than warned about here, because a topic built on a worry from
    three weeks ago is exactly the failure this whole step exists to avoid.
    """
    items, age = concerns()
    if not items:
        # "Run research first" is circular on a Page with no research sources: that command
        # refuses too. Say which situation this actually is.
        if (BASE / "data" / "reddit.txt").exists():
            hint = f"Run `{fb_cmd('research')}` first, or drop --from-research."
        else:
            hint = ("This Page has no research setup (no data/reddit.txt), so "
                    "--from-research cannot work here.\n"
                    "       Plan from seeds instead, or see docs/reddit-research.md.")
        sys.exit(f"error: no research brief at {BASE / 'data' / 'concerns.json'}\n"
                 f"       {hint}")
    if age is not None and age > CONCERN_TTL_DAYS:
        sys.exit(f"error: the research brief is {age} days old (limit {CONCERN_TTL_DAYS}).\n"
                 f"       Refresh it with `{fb_cmd('research')}`, or drop --from-research.")
    return [c["concern"].strip() for c in items]


def main(argv):
    ap = argparse.ArgumentParser(prog="fb_content_plan.py", add_help=False,
                                 description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seeds", nargs="*", help="seed themes (default: data/seeds.txt)")
    ap.add_argument("--from-research", action="store_true",
                    help="use the concerns from data/concerns.json as the seeds")
    ap.add_argument("--per-seed", type=int, default=0,
                    help=f"topics per seed (default {PER_SEED}, or {RESEARCH_PER_SEED} "
                         "with --from-research)")
    if any(x in ("-h", "--help") for x in argv):
        print(__doc__)
        return 0
    a = ap.parse_args(argv)

    if a.from_research and a.seeds:
        sys.exit("error: --from-research builds its seeds from data/concerns.json, so it "
                 "does not take seeds as arguments.\n"
                 f"       Use one or the other; `{fb_cmd('research')}` explains the brief.")

    if a.from_research:
        seed_list = research_seeds()
        per_seed = a.per_seed or RESEARCH_PER_SEED
        label = "concern"
    else:
        seed_list = seeds(a.seeds)      # validate inputs before demanding credentials
        per_seed = a.per_seed or PER_SEED
        label = "seed"

    tf = BASE / "data" / "topics.txt"
    queued = [l.strip() for l in tf.read_text().splitlines() if l.strip()] if tf.exists() else []

    cl = client()
    # history_block() carries the published history AND the queued topics, so the model
    # knows what to avoid rather than relying on post-hoc filtering.
    # Brief and output language come from data/planner.txt so a second site needs no code change.
    # concerns_block() is empty unless a research brief exists and is still fresh. In
    # --from-research mode its list would only repeat the seeds, so keep the no-facts rule
    # and drop the list.
    brief = concerns_block(include_list=not a.from_research)
    head = (
        (PLANNER.replace("{n}", str(per_seed)) or
         f"Propose {per_seed} social post topics about the seed theme.") + "\n\n"
        f"Context: {CTX[:1500]}\n\n"
    )
    tail = ("\n\n" + brief if brief else "")

    # Say out loud which way the research influenced this run: silence here is how a
    # three-week-old worry quietly becomes a "current" topic.
    items, age = concerns()
    if a.from_research:
        print(f"[ok] research brief: {len(seed_list)} concern(s) from {age}d ago "
              f"-> one seed each")
    elif items and brief:
        print(f"[ok] research brief: {len(items)} concern(s) from {age}d ago — angles only")
    elif items:
        print(f"[..] research brief is {age}d old, ignoring it. "
              f"Refresh with `{fb_cmd('research')}`.")
    else:
        print(f"[..] no research brief — topics come from seeds alone "
              f"(`{fb_cmd('research')}` adds what the trade is arguing about)")

    proposed = []
    for seed in seed_list:
        # Each seed is planned blind to the ones before it unless they are fed back, and
        # the result was visible: 8 of 20 topics all reached for drywall. Passing this
        # run's own proposals in as "avoid" costs nothing and keeps the trades spread out.
        system = head + history_block(also_avoid=queued + proposed) + tail
        data = ask(cl, system, f"{label.capitalize()} theme: {seed}\n"
                               f"JSON: {{\"topics\": [\"...\", ...]}}")
        topics = [t.strip() for t in (data.get("topics") or [])
                  if isinstance(t, str) and t.strip()]
        if not topics:
            print(f"[..] {seed[:60]}: model returned no topics")
            continue
        proposed += topics
        print(f"[ok] {seed[:60]}: {len(topics)} topic(s)")

    # A prompt instruction alone does not stop paraphrases: re-running the same seed produced
    # "Personeelstekort op het dak" alongside an existing "Personeel tekort op het dak?".
    # Comparing two lists is a much easier task than generating while avoiding a list, so
    # filter in a second, focused pass.
    if queued and proposed:
        keep = ask(cl, (
            "You filter duplicate content topics. Reply with JSON only."
        ), (
            "Already planned topics:\n"
            + "\n".join(f"- {t}" for t in queued[-150:])
            + "\n\nNew candidates:\n"
            + "\n".join(f"- {t}" for t in proposed)
            + "\n\nDrop every candidate that means the same as an already-planned topic "
              "(even when the wording differs), and any candidate that duplicates an earlier "
              "one. Keep the original wording of what you retain.\n"
              'JSON: {"keep": ["...", ...]}'
        )).get("keep")
        if isinstance(keep, list) and all(isinstance(k, str) for k in keep):
            dropped = len(proposed) - len(keep)
            if dropped > 0:
                print(f"[ok] filter: dropped {dropped} near-duplicate topic(s)")
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
        print(f"[ok] data/topics.txt += {len(add)} new (total {len(queued) + len(add)})"
              + (f" — {dupes} duplicate(s) skipped" if dupes else ""))
    else:
        print("[..] no new unique topics" + (f" ({dupes} duplicate(s))" if dupes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
