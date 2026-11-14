# Research: what contractors are arguing about (CrewNetUSA)

> **Scope: `sites/crewnetusa/` only.** Constructief and rabota have no `data/reddit.txt`,
> so `./fb root research` and `./fb rabota research` refuse with an explanation. That file
> is the switch — see [Enabling it for another Page](#enabling-it-for-another-page).

The research step exists because of a measured problem, not a hunch. Of the first 50 posts
Constructief published, 39 (78%) were triggered by a rule, a deadline or a calendar date.
They read like notices. When the same pipeline was pointed at a selling point instead, it
produced ten rewordings of that selling point — which is where the duplicate rates came from.

The missing ingredient was not more data. It was **what people actually worry about**.

---

## The one rule

```
community discourse chooses the TOPIC
verified sources          supply the FACT
a rumour is never published as content
```

The brief is not a fact sheet and must never be treated as one. A post may be *built on* a
concern — "why does this keep happening to us" — but every hard claim in that post (a
figure, a fine, a date, a rule) still has to come from `data/context.txt` or from a source
you can point at. That is why every concern carries a `verify before use` line.

Wrong regulatory content is a liability, not a weak post. If the fact is missing, the post
asks a question or reports someone's experience. It does not assert.

---

## Credentials

One Reddit app serves the account, so the keys live in the **shared** `.env`, not per site:

```bash
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=macos:fb-agent:1.0 (by /u/yourname)   # optional, but Reddit asks for it
```

Check them at any time, with no model spend:

```bash
./fb crewnetusa research --check
```

That prints the token result plus a per-source reachability line, and is the fastest way to
answer "did Reddit break, or did my app get revoked?".

**Access model.** These are app-only (`client_credentials`) credentials: read access with
no user context, 1000 requests per 10 minutes. Nothing here posts, votes, moderates or
identifies as a user — `scripts/fb_reddit.py` only reads.

Reddit closed self-service app creation in late 2025 (the dashboard now shows the
Responsible Builder Policy and stops). An app that already exists keeps working; a new one
needs approval. Treat these keys as inventory you cannot simply replace.

---

## What was measured, and why it shaped the design

Reddit's search endpoint is much less useful than it looks. Measured on the live API:

| Query | Result |
| --- | --- |
| `r/belgium` → `bouw` | "Jolan **De Bouw**" (a surname), "1 euro per dag" |
| `r/Ukraine` → `работа Европа` | **0 results** |
| `r/Belarus` → `работа` | **0 results** |

So `research` does not search. It reads `/top` listings and filters **locally**, which is
predictable. Sources live in `data/reddit.txt`, one per line:

```
Construction                          the whole subreddit — trade subs need no filter
Contractor | crew|sub|bid|insurance   a general sub, filtered to what matters
```

`--source-cap` exists because comment count decides the ranking, so one noisy sub filled
every slot: the first CrewNetUSA corpus came out half roofing/plumbing. The cap spreads the
brief across trades, and the planner feeds its own proposals back into each subsequent seed
for the same reason — otherwise 8 of 20 topics all reached for drywall.

**One source per subreddit.** A post is sent to the model once, so an unfiltered line above
a filtered line for the same sub makes the second look broken ("100 listed, 0 usable"). The
tool now says so out loud instead of failing silently.

---

## Why only the US Page

Measured relevance on the top 100 posts of a month, which is the whole argument:

| Source | Relevant | Verdict |
| --- | --- | --- |
| `r/Construction`, `r/Contractor`, `r/ConstructionManagers`, `r/GeneralContractor`, `r/SkilledTrades`, `r/Concrete`, `r/Roofing`, `r/HVAC`, `r/electricians`, `r/Plumbing`, `r/Carpentry` | 90–100/100 | enabled |
| `r/Klussers` (NL) | 36/100 | would work, but it is a DIY/homeowner sub |
| `r/belgium` | 3/100 | mostly politics without a filter |
| `r/Netherlands` | 0/100 | dropped |
| `r/Ukraine`, `r/Belarus`, `r/AskARussian` | 0–2/100 | no Russian-language construction community exists |

`rabota` targets Ukrainian, Belarusian and Baltic construction workers. Reddit has nothing
for that audience, and loosening the filter to `Европа` or `работа` pulls in posts about the
Estonian border and university coursework — not the concerns of a worker choosing a Belgian
employer. Its real sources are Telegram and VK, which this client cannot read; that needs
its own connector, not a wider filter. So it is not enabled, and the tool says so rather
than filling the brief with invented worries.

Constructief is a business-to-business Page in Dutch and Belgian Dutch, and the one
plausible source (`r/Klussers`) is a homeowners' DIY sub. It stays on seeds only.

---

## Daily workflow

```bash
./fb crewnetusa past-posts                   # once: what is already published
./fb crewnetusa research                     # read the trade -> data/concerns.txt
open sites/crewnetusa/data/concerns.txt      # READ IT. Delete what you disagree with.
./fb crewnetusa topics --from-research       # one seed per concern
./fb crewnetusa plan --limit 6
./fb crewnetusa gallery && ./fb crewnetusa images
./fb crewnetusa approve 01 02 03
./fb crewnetusa schedule --dry-run --start 2026-11-16
```

`--from-research` is the mode that makes this count. Leaving the concerns as *background*
did not work: the site's `planner.txt` is all selling points and won the argument, so the
model kept restating the selling points and the brief became decoration. Making each concern
a **seed** forces the worry to be the subject and the offer to be the resolution.

Compare, on the same Page:

```
without research   Still bidding blind? Screening helps small GCs avoid Craigslist flakes.
with research      Stop arguing over paint ridges — define cosmetic vs defect before
                   crews mobilize.
```

`./fb crewnetusa topics` *without* the flag still injects a fresh brief as angles, and pairs
it with your own seeds — the lighter option when you already know the theme.

### Language

The brief must be in the Page's language, and the source posts are not always that.
`data/language.txt` pins it deterministically:

```
American English (contractor-to-contractor)
```

Optional. Without it the brief follows the Page's voice, which is fine when the sources
already match. It exists because the source language can win: on a Page whose sources were
partly Ukrainian, a Russian-language brief came back Ukrainian, and that leaked onward into
the topics as a mixed-language batch.

### Freshness

A brief older than **7 days** is ignored, not recycled. `topics --from-research` refuses it
outright and tells you to re-run `research`. This is enforced in `fb_llm.concerns_block()`
and covered by the offline suite with a literal 45-day fixture — an earlier version of that
test referenced the very constant it was checking, so raising the limit to 999 still passed.

Breaking news is worthless three weeks later. The brief carries its own date for the same
reason.

---

## Tunables

| Flag | Default | Use |
| --- | --- | --- |
| `--days N` | 30 | look-back window |
| `--limit N` | 30 | posts sent to the model |
| `--threads N` | 10 | how many threads get their comments read |
| `--comments N` | 15 | comments per thread |
| `--source-cap N` | auto | max posts per source; auto = `limit / sources` |
| `--per-seed N` | 3 | topics per concern in `--from-research` mode |

Cost: one research run is ~20 cheap Reddit calls plus **one** model call.

---

## Enabling it for another Page

Two files, no code changes:

```bash
# 1. the switch: without this file the step refuses to run
cat > sites/<name>/data/reddit.txt <<'EOF'
Construction
Contractor | crew|sub|bid|insurance
EOF

# 2. optional, and worth it when sources and Page differ in language
echo 'Dutch (Nederlands, «u» form)' > sites/<name>/data/language.txt
```

Then check it resolves before spending anything:

```bash
./fb <name> research --check
```

Do the check first. It costs nothing, and a source list that returns 0 posts is a source
list that will produce an empty brief.

---

## Terms and good manners

- **Read-only.** The client has no write path. Do not add one for engagement-farming.
- **Rate limit** is 1000 requests/10 min and the client backs off on 429/5xx. A normal run
  uses ~20 calls. Do not run it in a loop.
- **Do not reproduce comment text** in posts. The brief paraphrases and links; that is the
  point. Quoting a Reddit comment into a client's Facebook feed is both bad practice and,
  under Reddit's terms, a licensing question you do not want.
- **Attribute nothing you cannot source.** If the fact is not in your own context, the post
  asks rather than asserts.
- The content is other people's words. Using it to understand a market is normal research;
  republishing it is not.

---

## Troubleshooting

| Symptom | Meaning |
| --- | --- |
| `the research step is not set up for this site` | no `data/reddit.txt` for that Page — see [Enabling it](#enabling-it-for-another-page) |
| `Reddit rejected these credentials (HTTP 401)` | wrong id/secret, or the app was deleted |
| `--check` shows `[!!] r/x 0 post(s)` | sub is private/banned/renamed — fix `data/reddit.txt` |
| `no concerns found in this sample` | sample too thin or off-topic; widen sources or `--days` |
| `research brief is N days old, ignoring it` | re-run `research` before planning |
| `100 listed, 0 usable` | the filter matched nothing — check the regex, or drop it |
| Only one trade appears in the topics | `--source-cap` is being overridden; drop the flag to use auto |
