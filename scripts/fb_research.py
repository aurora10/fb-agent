#!/usr/bin/env python3
"""Turn what the trade is arguing about into concerns the topic planner can use.

Usage: fb_research.py [--days N] [--limit N] [--threads N] [--comments N] [--source-cap N]
       fb_research.py --check          # do the credentials still work? no spend

Why this exists
---------------
78% of the first 50 published posts were triggered by a rule, a deadline or a calendar
date, so they read like notices. The angle that is actually interesting is whatever the
trade is arguing about this month — but a rumour is not a fact, and a wrong regulatory
claim is a liability. So this step deliberately produces no claims. It produces
CONCERNS: what people worry about, in their own terms, with a link to where they said
it, plus the fact that would have to be checked before any of it could be published.

    community discourse chooses the TOPIC
    verified sources supply the FACT
    a rumour is never published as content

Sources live in data/reddit.txt (per site). One line per source:

    Construction                          the whole subreddit
    belgium | aannem?er|bouw|verbouw      only posts matching this regex

The regex column exists because general country subreddits are mostly noise: r/belgium
TOP 100 matched 3 posts, and Reddit's own search is unreliable (a Russian query returns
zero; "bouw" matches the surname "De Bouw"). Whole-trade subreddits need no filter.

Writes data/concerns.json (planner input) and data/concerns.txt (human-readable brief).
"""
import argparse, datetime, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, REPO, ask, client, data_file, fb_cmd
from fb_reddit import Reddit, RedditError

MIN_COMMENTS = 3       # a post nobody replied to is not a shared concern
BODY_CHARS = 600       # per post
COMMENT_CHARS = 300    # per comment
MAX_CONCERNS = 12

SYSTEM = """\
You are a research assistant for a social media team. You are given a sample of what \
people in a trade are currently saying to each other in online forums.

Your job is NOT to summarise news and NOT to produce claims. It is to extract CONCERNS: \
the specific things these people worry about, argue about, complain about, disagree on, \
or are unsure about — especially matters of opinion, frustration, rumour or contested \
experience rather than settled fact.

Rules:
- A concern is a worry in the words a person would use, not a summary of a thread.
- Prefer tensions and disagreements: what people fear is changing, what they think \
others get wrong, what burned or surprised them, what they keep asking each other.
- Never state anything as fact. If a concern rests on a factual claim, put that claim in \
"fact_needed" as a question that must be answered before anything is published.
- Ignore moderator announcements, job ads, memes, and self-promotion.
- Do not invent. If the sample contains no real concerns, return an empty list.
- Every concern must cite at least one URL that appears in the sample, copied exactly.
- Aim for 5-10 concerns when the sample supports it. Two or three is an honest answer for a
  thin sample; across forty posts and two hundred comments it usually means the obvious ones
  were taken and nobody looked harder.
- Write in the language this Page publishes in. Name the audience segment in "who".

JSON only:
{"concerns": [{"concern": "...", "who": "...", "why_it_matters": "...",
               "heard": ["short paraphrase or quote", "..."],
               "links": ["https://www.reddit.com/..."],
               "fact_needed": "..."}]}"""

# Without this, a third of the extraction was DIY-homeowner worry on a Page that sells to
# general contractors: the forums are full of consumers even in "trade" subreddits, and
# relevance has to be scoped by who actually reads this Page. Comes from the site's own
# context.txt and persona.txt, so a new site needs no code change.
AUDIENCE = """

WHO READS THIS PAGE
{context}

Voice of the Page: {persona}

Keep only concerns this audience would recognise as THEIR OWN problem.
- If the audience is a BUSINESS selling to other businesses, a consumer or DIY-homeowner
  worry is background noise: drop it, unless it changes how professionals get hired,
  judged, paid or held responsible.
- If the audience is WORKERS, keep their worries (pay, conditions, paperwork, being
  treated fairly) and drop the contractor's operational worries.
- If a concern cannot be tied to this audience in one sentence, leave it out. Concerns
  about a different subject, a different country or a different industry are noise even
  when they are interesting: a short accurate brief beats a long noisy one.
- Write every concern in the SAME language as the Page voice above, even when the forum
  posts are in another language: translate. Never mix two languages in one brief — a
  Ukrainian/Russian/Dutch blend is unreadable and the writer inherits it.{language}"""


# ------------------------------------------------------------------ sources
def configured():
    """Sites that actually have research sources.

    Read off disk rather than hardcoded, so this answer stays true as sources are added or
    removed. Today it says crewnetusa, and that is deliberate: the Reddit step is set up
    for the US Page only.
    """
    out = ["root"] if (REPO / "data" / "reddit.txt").exists() else []
    out += [d.parent.parent.name for d in sorted((REPO / "sites").glob("*/data/reddit.txt"))]
    return out


def sources():
    """data/reddit.txt -> [(sub, compiled regex or None, the original line)]."""
    p = BASE / "data" / "reddit.txt"
    if not p.exists():
        have = configured()
        sys.exit(
            f"error: the research step is not set up for this site ({p} is missing).\n"
            f"       Reddit sources are configured per site. Configured right now: "
            f"{', '.join(have) if have else 'none'}.\n"
            "       To add this Page, create that file with one source per line:\n"
            "         Construction                       (a whole trade subreddit)\n"
            "         Contractor | crew|sub|bid|insurance   (a general sub, filtered)\n"
            "       Lines starting with # are comments."
        )
    out, seen_subs = [], {}
    for n, raw in enumerate(p.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        sub, _, pat = line.partition("|")
        sub, pat = sub.strip(), pat.strip()
        if not sub:
            sys.exit(f"error: {p}:{n}: no subreddit before the '|' — line: {raw!r}")
        try:
            rx = re.compile(pat, re.I) if pat else None
        except re.error as e:
            sys.exit(f"error: {p}:{n}: bad regex {pat!r} ({e})")
        # A post is only ever sent to the model once, so listing a subreddit bare above a
        # filtered line makes the filtered line look broken ("100 listed, 0 usable").
        # That silent no-op is worse than a loud note.
        if sub.lower() in seen_subs:
            print(f"[..] note: r/{sub} appears twice in {p.name} (lines "
                  f"{seen_subs[sub.lower()]} and {n}). A post is used once, so the later "
                  "line only adds posts the earlier one skipped.", file=sys.stderr)
        seen_subs.setdefault(sub.lower(), n)
        out.append((sub, rx, line))
    if not out:
        sys.exit(f"error: {p} contains no usable source lines")
    return out


def window_for(days):
    return ("day" if days <= 1 else "week" if days <= 7 else
            "month" if days <= 31 else "year" if days <= 365 else "all")


def lang_rule():
    """Optional data/language.txt, e.g. "Russian". Empty when the site does not pin it.

    The Page's persona does state its language ("Простой русский"), but that lost to the
    source: with a Ukrainian post in the sample, the Russian Page's brief came back
    Ukrainian. Deriving a language from prose is a job for a model; declaring it is a job
    for a file. When the file exists the brief is deterministic.
    """
    lang = data_file("language.txt").strip()
    return f" The language is pinned for this site: write in {lang}." if lang else ""


# ------------------------------------------------------------------- gather
def gather(r, srcs, days, per_sub, limit, threads, n_comments, report, source_cap=0):
    """Fetch and rank discourse. Returns (corpus text, stats, per-source report)."""
    seen, posts = set(), []
    for sub, rx, line in srcs:
        got = r.listing(sub, window=window_for(days), limit=per_sub)
        kept = 0
        for p in got:
            if p.get("stickied") or p.get("id") in seen:
                continue
            body = p.get("selftext") or ""
            if rx and not rx.search((p.get("title") or "") + " " + body):
                continue
            if (p.get("num_comments") or 0) < MIN_COMMENTS:
                continue
            seen.add(p["id"])
            posts.append({"sub": p.get("subreddit") or sub, "id": p["id"],
                          "title": (p.get("title") or "").strip(),
                          "body": " ".join(body.split())[:BODY_CHARS],
                          "score": p.get("score") or 0,
                          "comments": p.get("num_comments") or 0,
                          "url": "https://www.reddit.com" + (p.get("permalink") or "")})
            kept += 1
        report.append((sub, len(got), kept, "" if got else "unreadable or empty"))

    # Discussion volume is the signal, not score: a shared worry is one people reply to.
    posts.sort(key=lambda p: (-p["comments"], -p["score"]))

    # One busy subreddit would otherwise fill every slot — on CrewNetUSA the corpus came
    # out half roofing/plumbing because comment count alone decides the ranking. Cap each
    # source so the brief reflects the whole trade, not its noisiest corner.
    if source_cap <= 0:
        source_cap = max(3, limit // max(1, len(srcs)))
    counts, capped = {}, []
    for p in posts:
        if counts.get(p["sub"], 0) < source_cap:
            counts[p["sub"]] = counts.get(p["sub"], 0) + 1
            capped.append(p)
    posts = capped[:limit]

    stats = {"posts": len(posts), "comments": 0, "cap": source_cap}
    parts = [f"Sample of forum discussion, last {days} day(s)."]
    for i, p in enumerate(posts):
        block = [f"\n### {p['sub']} | {p['comments']} comments | score {p['score']}",
                 f"TITLE: {p['title']}", f"URL: {p['url']}"]
        if p["body"]:
            block.append(f"BODY: {p['body']}")
        # Comments are the expensive part, so only the busiest threads get them.
        if i < threads:
            cs = r.comments(p["id"], limit=n_comments)
            if cs:
                stats["comments"] += len(cs)
                block.append("COMMENTS:\n" + "\n".join(
                    f"- {c['body'][:COMMENT_CHARS]}" for c in cs))
        parts.append("\n".join(block))
    return "\n".join(parts), stats, report


# ------------------------------------------------------------------- render
def render_txt(data):
    """The human-readable brief. Header must scream that this is not publishable."""
    d = data["generated"][:10]
    lines = [
        "=" * 78,
        f"RESEARCH BRIEF — {d}",
        "=" * 78,
        "NOT FOR PUBLICATION. These are things people are saying in forums, not verified",
        "facts. A post may be BUILT on a concern; it may never restate one as a claim.",
        "Anything under 'verify before use' must be checked before it appears in a post.",
        "",
        f"Sources : {', '.join(data['sources'])}",
        f"Sampled : {data['sampled']['posts']} posts, {data['sampled']['comments']} comments,"
        f" last {data['window_days']} day(s)",
        "",
    ]
    if not data["concerns"]:
        lines.append("No concerns found. The sample was too thin or too off-topic.")
        lines.append("Do not fall back on invented worries — widen data/reddit.txt instead.")
        return "\n".join(lines) + "\n"

    for i, c in enumerate(data["concerns"], 1):
        lines.append(f"{i}. {c['concern']}")
        if c.get("who"):
            lines.append(f"   Who            : {c['who']}")
        if c.get("why_it_matters"):
            lines.append(f"   Why it matters : {c['why_it_matters']}")
        for h in c.get("heard", [])[:3]:
            lines.append(f"   Heard          : {h}")
        for l in c.get("links", [])[:2]:
            lines.append(f"   Source         : {l}")
        if c.get("fact_needed"):
            lines.append(f"   Verify before use: {c['fact_needed']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def clean(raw):
    """Keep only well-formed concerns — one bad entry must not poison the brief."""
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        text = (c.get("concern") or "").strip()
        links = [l for l in (c.get("links") or []) if isinstance(l, str)
                 and l.startswith("https://")]
        if not text or not links:
            continue
        out.append({
            "concern": text,
            "who": (c.get("who") or "").strip(),
            "why_it_matters": (c.get("why_it_matters") or "").strip(),
            "heard": [h.strip() for h in (c.get("heard") or []) if isinstance(h, str) and h.strip()],
            "links": links,
            "fact_needed": (c.get("fact_needed") or "").strip(),
        })
    return out[:MAX_CONCERNS]


# --------------------------------------------------------------------- main
def main(argv):
    ap = argparse.ArgumentParser(prog="fb_research.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30, help="look-back window (default 30)")
    ap.add_argument("--limit", type=int, default=30, help="max posts sent to the model (30)")
    ap.add_argument("--per-sub", type=int, default=100, help="listing size per source (100)")
    ap.add_argument("--threads", type=int, default=10, help="threads to read comments from (10)")
    ap.add_argument("--comments", type=int, default=15, help="comments per thread (15)")
    ap.add_argument("--source-cap", type=int, default=0,
                    help="max posts per source in the corpus (0 = auto, limit/sources)")
    ap.add_argument("--check", action="store_true", help="verify credentials and sources only")
    a = ap.parse_args(argv)

    srcs = sources()
    r = Reddit()
    report = []

    if a.check:
        try:
            info = r.check()
        except RedditError as e:
            sys.exit(f"[!!] {e}")
        print(f"[ok] credentials work (app-only token, no user context: {info['user'] or 'none'})")
        for sub, rx, line in srcs:
            got = r.listing(sub, window="month", limit=5)
            flag = "[ok]" if got else "[!!]"
            filt = f"  filter: {rx.pattern}" if rx else ""
            print(f"{flag} r/{sub:<20} {len(got):>2} post(s) sampled{filt}")
        return 0

    corpus, stats, report = gather(r, srcs, a.days, a.per_sub, a.limit,
                                   a.threads, a.comments, report, a.source_cap)
    for sub, seen_n, kept, note in report:
        print(f"[ok] r/{sub:<20} {seen_n:>3} listed, {kept:>3} usable"
              + (f"  ({note})" if note else ""))
    print(f"[ok] corpus: {stats['posts']} posts, {stats['comments']} comments "
          f"(max {stats['cap']}/source, {r.calls} API call(s))")

    if not stats["posts"]:
        print("[..] nothing to analyse — no concerns written, no spend."
              "\n     Widen data/reddit.txt or the --days window.")
        return 0

    system = SYSTEM + AUDIENCE.format(
        context=(data_file("context.txt").strip()[:1200] or "(not described)"),
        persona=(data_file("persona.txt").strip()[:400] or "(not described)"),
        language=lang_rule(),
    )
    data = ask(client(), system, corpus + "\n\nExtract the concerns as JSON.")
    concerns = clean(data.get("concerns"))
    out = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "window_days": a.days,
        "sources": [f"r/{sub}" for sub, _, _ in srcs],
        "sampled": stats,
        "concerns": concerns,
    }

    (BASE / "data").mkdir(exist_ok=True)
    (BASE / "data" / "concerns.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    (BASE / "data" / "concerns.txt").write_text(render_txt(out))

    if not concerns:
        print("[..] no concerns found in this sample. data/concerns.txt records that, "
              "so the planner will ignore it rather than inherit stale worries.")
        return 0

    print(f"[ok] {len(concerns)} concern(s) -> data/concerns.txt (read it before planning)")
    for c in concerns:
        print(f"       - {c['concern'][:96]}")
    print(f"\nNext: {fb_cmd('topics')}   (the planner reads data/concerns.json)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except RedditError as e:
        sys.exit(f"[!!] {e}")
