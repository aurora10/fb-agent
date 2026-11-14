# fb-agent

Facebook content pipeline for **constructief-bouw.be** — intent-focused posts for
Belgian/Dutch general contractors who need reliable subcontractor teams.

The agent writes the posts, generates the images, and **schedules them straight to the
Facebook Page** through the Meta Graph API. No manual uploading.

```
topics  ->  fb_plan.py   ->  drafts/draft_NN.json
            fb_images.py ->  images/NN.png
            (you review) ->  ./approve NN
            fb_api.py    ->  scheduled on the Page, every 2nd day at 19:05
```

---

# Part 1 — One-time setup

Do these once. After this, you only ever repeat Part 2.

## Step 1 — Install

```bash
git clone https://github.com/aurora10/fb-agent.git
cd fb-agent
uv venv .venv && uv pip install --python .venv/bin/python openai python-dotenv
```

## Step 2 — Add your keys

```bash
cp .env.example .env
```

Open `.env` and fill in the OpenAI block:

| Key | Default | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | <https://platform.openai.com/api-keys> |
| `OPENAI_MODEL` | `gpt-5.4-mini` | text generation |
| `IMAGE_PROVIDER` | `openai` | or `pollinations` (free, no key) |
| `OPENAI_IMAGE_MODEL` | `gpt-image-2` | also `gpt-image-1.5`, `gpt-image-2.5-flare` |
| `OPENAI_IMAGE_SIZE` | `1024x1024` | or `1024x1536`, `1536x1024` |
| `OPENAI_IMAGE_QUALITY` | `medium` | **the main cost lever** |
| `OPENAI_IMAGE_FORMAT` | `jpeg` | or `png`, `webp` |

Not sure which text model your key can use?

```bash
./fb root plan --models
```

**Image cost is per image, so test with one before rendering a batch.** Expect roughly
40–60 seconds per image at `gpt-image-2`/`medium`, so a 13-draft batch is ~10 minutes —
about the same wall-clock as the free Pollinations provider, but it bills. Drop
`OPENAI_IMAGE_QUALITY` to `low` if you want it cheaper, or set `IMAGE_PROVIDER=pollinations`
to go back to free.

## Step 3 — Connect the Facebook Page

This is the part that trips everyone up, so it has its own guide:
**follow `docs/meta-api-setup.md` start to finish.** It covers app creation, the
permission that is hidden by default, going Live, and the token exchange.

The two things that catch people:

- **`pages_manage_posts` is not visible by default.** You must open
  *Customize use case* and click **Add** next to it.
- **An unpublished app's posts are visible only to you.** Publish the app, or your posts
  silently reach nobody.

When you have `FB_APP_ID` and `FB_APP_SECRET` in `.env`:

```bash
./fb root token    # 1x: mints a Page token that never expires
./fb root check    # verify
```

`check` should end in `ok`, with `expires : never` and `CREATE_CONTENT` in the tasks list.
If it does, setup is done for good — the token does not expire.

## Step 4 — Sync your post history

Without this, the model writes blind: it has no idea what you have already published, so it
repeats angles you covered months ago.

```bash
./fb root past-posts          # whole history
./fb root past-posts --limit 60
```

Reads `/{page-id}/posts` and writes `data/past_posts.txt`, newest first. Each run replaces
the file, so **re-run it before planning a batch** to pick up whatever has published since.

How it reaches the model — two different slices, because voice and dedup need different
things:

| Purpose | What is sent | Size at 50 posts |
| --- | --- | --- |
| Tone and style | the **10 newest** posts in full | ~10k chars |
| Avoiding repeats | a **90-character hook from every** post | ~4.5k chars |

That covers the whole history for about 4k tokens. The earlier version sent `[:4000]`
characters, which at 50 posts meant **3 posts and 9% of the history** — the mechanism was
effectively switched off.

If you would rather import from a spreadsheet, `scripts/import_past_posts.py <export.csv>`
still works; the API route is just less work.

## Running a second Page

One Meta app serves every Page you administer, and one codebase serves every Page you post
to. Only the *data* differs per Page — never the code.

```bash
cp .env.example .env
# .env is SHARED: OPENAI_API_KEY, FB_APP_ID, FB_APP_SECRET, SITE=
```

Each Page gets a site directory:

```
sites/
  constructief/
    .env       <- FB_PAGE_ID, FB_PAGE_TOKEN only
    data/      <- persona.txt, context.txt, topics.txt, seeds.txt, cta.txt, past_posts.txt
    drafts/ approved/ done/ images/ previews/
  crewnetusa/
    .env       <- FB_PAGE_ID=1357946317402134 + its own token
    data/      <- English persona, context, CTA
    drafts/ approved/ done/ images/ previews/
```

Which steps are actually configured, per Page:

| Page | `data/reddit.txt` | research step |
| --- | --- | --- |
| Constructief (`root`) | — | no — seeds only |
| `rabota` | — | no — seeds only, and Reddit has no audience for that Page anyway |
| `crewnetusa` | yes | yes — `research` then `topics --from-research` |

That file is the switch. Without it `research` refuses and names the Pages that do have
sources, so nothing silently runs against a source list nobody chose.

### The `./fb` shorthand

Rather than typing a site and a script path every time, there is a dispatcher:

```bash
./fb sites                                   # list the sites that exist
./fb crewnetusa check
./fb crewnetusa research                     # what the trade is arguing about
./fb crewnetusa topics --from-research
./fb crewnetusa plan --limit 14
./fb crewnetusa gallery
./fb crewnetusa images 1 2 3
./fb crewnetusa schedule --dry-run --start 2026-10-16
./fb root list                               # root = the repo root (Constructief)
./fb root verify
```

`./fb <site> <command>` is equivalent to `SITE=<site> .venv/bin/python scripts/<script>`,
and it refuses an unknown site name instead of silently creating one. `./fb` with no
arguments lists every command; `./fb root run fb_api.py list` reaches any script directly.

**The site is always explicit**, deliberately: a wrong site publishes to the wrong Page.

The long form still works and is what the rest of this document spells out:

Select one with a single variable:

```bash
./fb crewnetusa plan --limit 14
```

That is ordinary shell syntax: the variable applies to that one command and is not
remembered. Two consequences worth knowing:

- **It does not carry across `&&`.** `SITE=x cmd1 && cmd2` gives `cmd2` no SITE. Repeat the
  prefix, or use one of the options below.
- **`SITE=` (empty) means the repo root**, i.e. Constructief. That is the escape hatch.

To avoid repeating it, either set it for your terminal session:

```bash
export SITE=crewnetusa     # every later command in this window; `unset SITE` to undo
```

…or make it the default in the shared `.env`:

```
SITE=crewnetusa
```

Both are convenient and both are easy to forget when you switch back — a stray `SITE`
would point Constructief's queue at the other Page. `fb_api.py check` names the Page, and
every `schedule` run now prints its target first:

```
[..] site: crewnetusa   page: 1357946317402134
```

**Rules that keep this safe:**

- **No key appears in two `.env` files.** The shared file holds API keys; each site holds only
  its own `FB_PAGE_ID` / `FB_PAGE_TOKEN`. That removes any precedence ambiguity.
- **`shared/` is for assets all sites use** — currently `image_style.txt`. A site overrides a
  shared asset simply by having its own copy in `data/`.
- **`SITE` unset means the repo root *is* the site** — the original single-Page layout, byte
  for byte. Nothing breaks if you never use this.

The site `.env` also sets the cadence:

```
POST_TZ=America/New_York   # the AUDIENCE's timezone, not yours
POST_AT=19:05
POST_EVERY=2
```

`POST_TZ` matters more than it looks. `--at 19:05` is a wall clock in the **readers'**
timezone, so without it a 19:05 slot aimed at US contractors would actually publish at
13:05 New York time from a European machine. An IANA zone is used rather than an hour
offset because Belgium and the US change clocks on different dates, so a fixed offset
would drift twice a year:

```
POST_TZ=America/New_York, --at 19:05
  2026-10-30 -> NY 19:05 EDT = 00:05 Brussels
  2026-11-03 -> NY 19:05 EST = 01:05 Brussels
```

Leave `POST_TZ` unset to use the machine's own timezone, as before.

Getting the second Page's token — same app, no new one:

```bash
./fb crewnetusa token 1357946317402134
./fb crewnetusa check
```

Each site gets its own token. Page tokens are per Page, so the two are different strings
even though they come from one app — `check` confirms which Page a site is pointed at,
which is the thing to verify before scheduling anything.

**No new app, and no App Review.** Page tokens are per Page, but the app is not — the app you
already have reaches every Page you administer.

---

# Part 2 — Creating and scheduling posts

This is the routine. About 15 minutes, and it produces ~2 weeks of scheduled posts.

Every command below is written as `./fb root …`, where `root` is the repo root — the first
Page. **For another Page, swap that word:** `./fb crewnetusa plan --limit 14`.

### The whole flow at a glance

```bash
./fb root check                      # 0. right Page? token alive?
./fb root past-posts                 #    load what you have published
./fb root topics "gevelrenovatie" "dakrenovatie"    # 1. topics -> data/topics.txt
#                                    #    (edit that file: delete what you don't want)
./fb root plan --limit 14            # 2. write posts + image prompts -> drafts/
./fb root gallery                    # 3. review copy AND prompts  <- before images
./fb root images                     # 4. render images
./fb root gallery                    # 5. review the images
./fb root check-dupes                # 6. do any two posts make the same point?  <- gate
./fb root approve 1 2 3 4 5          # 7. approve what goes out
./fb root schedule --dry-run --start 2026-11-01   # 8. see the plan, send nothing
./fb root schedule --start 2026-11-01             # 9. schedule it
./fb root list                       # 10. confirm the queue
./fb root preview                    # 11. as Facebook will render them
```

`gallery` and `preview` print the exact file to open. For a secondary Page that is
`sites/<name>/previews/…` — opening `previews/index.html` gives you the **first** Page's
gallery, which is a different and often empty file.

`./fb` with no arguments lists every command, and `./fb sites` lists the Pages you can post
to. The long form — `SITE=<site> .venv/bin/python scripts/<script>` — still works and is
what the tooling actually runs.

The order matters: **review the posts and their image prompts before generating any
images.** Prompts are shown in the gallery even for drafts that have no image yet, so
fixing a prompt costs seconds instead of a regeneration.

## Step 1 — Build the topic plan

First make sure the model knows what you have already published:

```bash
./fb root past-posts
```

### CrewNetUSA only — start from what contractors are arguing about

Topics generated from seeds alone tend to restate your selling point in ten rewordings.
CrewNetUSA has one extra step before planning that reads what US general contractors are
actually worrying about this month, so the worry becomes the subject of the post and the
service becomes the answer.

```bash
./fb crewnetusa research                  # read r/Construction etc. -> data/concerns.txt
open sites/crewnetusa/data/concerns.txt   # READ IT: delete what you disagree with
./fb crewnetusa topics --from-research    # one seed per concern
```

`research` writes a dated brief of **concerns**, not facts — each with a link to where it
was said and a `verify before use` line. A brief older than 7 days is ignored rather than
recycled, because a three-week-old worry is not current. `./fb crewnetusa research --check`
proves the Reddit credentials still work without spending anything on a model.

**This step is CrewNetUSA only.** Constructief and rabota have no `data/reddit.txt`, and
`./fb root research` refuses with an explanation instead of guessing at sources. Layout,
measured per-subreddit yield and the terms to respect:
[`docs/reddit-research.md`](docs/reddit-research.md).

Then let the agent propose the topics:

```bash
./fb root topics "gevelrenovatie" "personeelstekort" "testweek"
# or run with no arguments to use the seeds in data/seeds.txt
./fb root topics
```

Generates ~10 intent-focused topics per seed — problem-aware (deadline risk, A1/Limosa
fines, subs no-show), solution-aware (testweek, screening, pay-on-result), proof, and
trade-specific (gevel/renovatie/dak/beton). Appends to `data/topics.txt`.

Re-running is safe but not idempotent. The model rewords rather than repeats, so the script
runs a second pass that compares its output against what's already queued and drops the
near-duplicates (typically 6 of 10 when you reuse a seed). A few reworded angles still get
through — **always skim `data/topics.txt` and delete what you don't want.** One topic per
line; this file is the queue everything downstream reads.

Topics work best when they name a **specific contractor problem**:

- ❌ *"Onze diensten"* — nobody searches for this
- ✅ *"A1- en Limosa-documenten: zo vermijdt u boetes op de werf"*

## Step 2 — Write the posts and image prompts

Work in batches of about **14**, because that is what one scheduling window holds (29 days
at 2-day spacing). `fb_content_plan.py` happily queue 90 topics, but generating them all at
once means 90 drafts, 90 rate-limited images and an unusable review gallery:

```bash
./fb root plan --limit 14
```

`data/topics.txt` acts as a queue: the topics used are removed once they have been drafted,
so the next run continues where this one stopped. The queue is only trimmed **after**
drafting succeeds, so a crash or a Ctrl-C never loses topics. Each run prints what is left
and suggests the next command.

If you queue more than ~14 and forget `--limit`, it warns and gives you 8 seconds to stop
before spending anything.

Other forms:

```bash
./fb root plan                  # everything queued, no batching
./fb root plan "topic one" "topic two"   # inline; queue untouched
```

Writes `drafts/draft_NN.json`, each with a `post` and an `image_prompt`. Your positioning is
injected from `data/context.txt`, and the history from Part 1 Step 4 keeps it off angles you
have already published.

## Step 3 — Review, and fix the image prompts

```bash
./fb root gallery
open previews/index.html
```

A gallery of every draft: text, topic, and the **image_prompt** (collapsed — click ▸ to
expand). No images exist yet, which is the point: this is where you judge the prompts.

### Scene vs style — the important split

Drafts describe only the **scene**: objects, people, materials, composition. The **visual
style** lives in `data/image_style.txt` and is appended to every prompt at generation time.
Edit that file to restyle everything at once — no code change, and no need to regenerate
drafts.

```
<scene from the draft>

VISUAL STYLE — PREMIUM ISOMETRIC 3D EDITORIAL ILLUSTRATION
...
```

Scene comes first on purpose: providers with a prompt limit (Pollinations truncates at 300
characters) lose the style rather than the content.

### The call-to-action is fixed too

Every post ends with the text in `data/cta.txt`, inserted between the body and the hashtags:

```
<body text>

Plaats uw aanvraag bij ons:
👉 https://constructief-bouw.be/nl/werkgevers
#hashtags
```

It is **not** model-written. Left to the model it drifted: within one batch 5 posts used
`/nl/werkgevers` and 8 used the bare domain, while 29 of the 50 published posts use the full
link. `fb_plan.py` now asks for the body and the hashtags separately and assembles the post
itself, so the CTA is identical everywhere and changing it is an edit to that file.

**This means a draft prompt must not contradict the style.** `fb_plan.py` is instructed to
write scene-only, but drafts written before `data/image_style.txt` existed say
"photorealistic, documentary style" — which fights it. Fix existing drafts with:

```bash
./fb root restyle-prompts            # every draft
./fb root restyle-prompts 5 6 11     # or selected ones
```

It rewrites only `image_prompt` (never the post text) and keeps the old value in
`image_prompt_prev`, so `fb_regen_image.py NN --revert` undoes it.

To reword one scene by hand without generating anything:

```bash
./fb root regen 03 "brick facade renovation site in Flanders, scaffolding, no text, no logos" --edit-only
```

`--edit-only` only updates `draft_03.json`. Without it, the same command also generates the
image, so you can go straight from "this prompt is wrong" to seeing the result.

## Step 4 — Generate the images

To try **one** post before committing to the batch — or any subset:

```bash
./fb root images 4          # just draft 4
./fb root images 4 7 12     # a few
./fb root images            # every draft still missing an image
```

It prints which provider and model it is about to use, so you always know what is being
spent:

```
generating 1 image(s) with gpt-image-2 @ 1024x1024 quality=medium (jpeg)
[ok] 04.png (175 KB)
```

Expect roughly 40–60 seconds per image with `gpt-image-2`, so a full 14-draft batch takes
about 10 minutes. It never overwrites, so prompts you already reworded in Step 3 are left
alone, and an already-generated image makes it a no-op rather than a re-render. A prompt the
image model refuses is reported as `[BLOCKED]` and **not** retried — reword it instead.

Redo a single image at any time, with a new prompt or the stored one:

```bash
./fb root regen 03
./fb root regen 03 "different angle, wider shot"
./fb root regen 03 --revert     # undo a bad prompt
```

Then rerun `fb_preview.py` to see the result. The previous image is kept as
`images/03.old.png`, and the previous *prompt* is kept in the JSON as `image_prompt_prev` —
so `--revert` swaps the two back (run it again to swap forward). Useful because a typo in
a prompt is otherwise unrecoverable.

## Step 5 — Approve what you want published

```bash
./approve 1 3 4        # approve drafts 1, 3 and 4
```

Moves those to `approved/`. Anything you skip stays in `drafts/` and is never published.

### Step 6 in detail — what the repetition gate catches

An LLM asked for ten post topics on one narrow offer will produce ten variations of the same
point, and nothing else in the pipeline notices. Run this first:

```bash
./fb root check-dupes
```

Two passes: word overlap (catches near-copies) and one model call that asks whether any two
posts make the *same argument* — which is what a paraphrase hides from any word count. The
first pair it caught scored only 33% word overlap, so the lexical check alone would miss it.

Exits 1 when it finds anything, so it can gate a scripted run. `--lexical-only` skips the
model call.

**This is a gate, not a formality.** The first runs on real batches found 15 pairs across 13
Constructief posts, 22 across 14 CrewNetUSA posts and 4 across 11 Russian posts. Each pair
publishes two days apart, so a reader sees the same argument twice in a week.

Two levers reduce it, and they are not equally strong:

- **`data/planner.txt` demands angle variety** — a different trade, objection and kind of
  proof per topic, and no more than two topics resting on one selling point. Measured on a
  single seed: the same six posts went from **6 duplicate pairs to 3**.
- **Diverse seeds matter more.** One narrow seed ("insurance checks") yields ten posts about
  insurance checks however the planner is worded. Seed with different problems, trades or
  audiences instead of ten variations on one theme.

Use the gate for what the planner cannot fix: read what it flags, keep the better post of
each pair, and let the rest go.

## Step 6 — Preview the schedule (nothing is sent)

```bash
./fb root schedule --dry-run --start 2026-11-01
```

Prints exactly what would be scheduled and when:

```
[dry ] 2026-11-01 19:05  post_01  +01.png
[dry ] 2026-11-03 19:05  post_03  +03.png
[dry ] 2026-11-05 19:05  post_04  (text only)

--dry-run: nothing sent, nothing moved
```

Needs no token, touches nothing. Always look before you send.

## Step 7 — Schedule them for real

```bash
./fb root schedule --start 2026-11-01
```

Each post goes out every 2nd day at **19:05 local time**, with its image attached, then
moves from `approved/` to `done/` so it can't be scheduled twice.

Two rules the script enforces:

- **Keep within 29 days.** Measured against this Page: **+29.00 days is accepted, +29.01 is
  rejected** with `(#100) The specified scheduled publish time is invalid`. Meta's docs claim
  30 days (Pages API guide) and 75 days (Page Feed reference) — both wrong in practice. At
  2-day spacing that means **14 posts per run** starting tomorrow at 19:05 — 15 if you start
  today, or 15 if you post at 10:00. The script refuses anything past the limit and tells you
  how many actually fit, so you can split a batch rather than lose it mid-run.
- **Times use your machine's timezone**, so the local clock stays at 19:05 across daylight
  saving changes.

## Step 8 — Confirm what's queued

```bash
./fb root list
```

```
scheduled (tracked locally in done/scheduled_posts.json, verified against the API):
  SCHEDULED 2026-11-01 19:05 1262992640226921_...  Waarom een 14-daagse testweek...
  SCHEDULED 2026-11-03 19:05 1262992640226921_...  A1- en Limosa-documenten...

recent published (times shown in your local timezone):
  2026-10-08 18:31 1262992640226921_...  Slecht weer en najaarsstormen...
```

Check the Page in a **private window while logged out** at least once. If your posts are
visible to you but not to anyone else, the app is not published — see Part 1 Step 3.

## Step 9 — See them as Facebook will render them

**Meta Business Suite does not list API-scheduled posts.** They only appear there once they
publish, and no API edge lists them either — so the ledger and this preview are your queue
view. Render the real thing from Facebook's own data:

```bash
./fb root preview            # everything in the ledger
./fb root preview 1262992640226921_...   # one post
open previews/scheduled.html
```

The image in this preview is Facebook's `full_picture` — **the asset Facebook stored, already
cropped and re-encoded** (your 1024px file becomes 720×720). So you are judging what the feed
will actually serve, not your local file. It also shows the Page name, avatar, scheduled
badge, the message with hashtags and links styled, and the permalink.

That makes the intended loop: **schedule a batch with the first post a couple of days out,
preview the lot, and cancel anything you don't like** — cancelling works right up until a post
goes live. This is the closest thing to the Business Suite scheduled view that Meta provides
for API posts.

## Changing your mind

```bash
./fb root cancel 1262992640226921_...   # remove a scheduled post
```

Cancelling works until a post goes live. Once published, delete it in Meta Business Suite.

**Pruning a draft you don't want** (duplicate angle, weak text) is just deleting it, plus its
image so you don't leave an orphan:

```bash
rm drafts/draft_03.json images/03.png
```

Numbering gaps are fine. New drafts are numbered from **max+1**, not from a count, precisely
so that deleting drafts cannot make the next batch reuse a number that is still in use —
with count-based numbering, pruning 3 of 16 drafts made the next batch start at `draft_15`
and silently overwrite `draft_15`, `draft_16` and `draft_17`. `fb_plan.py` also refuses to
write over an existing draft rather than trusting the arithmetic.

---

# Reference

## Commands

| Command | Purpose |
| --- | --- |
| `fb_api.py check` | verify token + Page + tasks |
| `fb_api.py token [PAGE_ID]` | mint the non-expiring Page token (re-run to switch Pages) |
| `fb_api.py test-post [--now]` | create a test post; `--now` publishes immediately |
| `fb_api.py list` | what's scheduled, plus recent published posts |
| `fb_api.py preview [POST_ID]` | render scheduled posts as Facebook will (uses FB's own image asset) |
| `fb_api.py past-posts [--limit N]` | sync published posts → `data/past_posts.txt` |
| `fb_api.py cancel POST_ID` | delete a post |
| `fb_api.py schedule --start DATE [--every N] [--at HH:MM] [--dry-run]` | schedule `approved/` |
| `fb_plan.py [TOPIC...] [--limit N]` | generate drafts; `--limit N` takes the next N from the queue |
| `fb_content_plan.py SEED... [--from-research] [--per-seed N]` | LLM-proposed topic list → `data/topics.txt`; `--from-research` uses the concerns as seeds |
| `fb_research.py [--days N] [--check]` | **CrewNetUSA only**: read forum discourse → concern brief (`data/concerns.txt`). `--check` verifies the Reddit credentials, no spend |
| `fb_images.py [NN...]` | generate images (all drafts, or just the numbers given) |
| `fb_restyle_prompts.py [NN...]` | rewrite draft prompts to scene-only (drops style wording) |
| `fb_fix_cta.py [NN...] [--dry-run]` | replace an improvised CTA in existing posts with the pinned one |
| `check-dupes [--threshold N] [--lexical-only]` | report posts that make the same point; exits 1 if any |
| `fb_imagegen.py` | shared provider layer for image generation — OpenAI GPT Image or Pollinations. Imported by the two scripts above; not run directly |
| `fb_regen_image.py NN ["prompt"] [--edit-only\|--revert]` | reword a prompt, redo one image, or undo |
| `fb_preview.py` | build the review gallery (shows image_prompt per draft) |
| `./approve NN...` | move drafts to `approved/` |
| `fb_export_csv.py` | fallback: Business Suite bulk-upload CSV |
| `import_past_posts.py` | fallback: import history from a CSV export instead of the API |
| `fb_llm.py` | shared OpenAI helpers — model default, JSON parsing, key guard. Imported by the two planning scripts; not run directly |

## Files

| Path | What |
| --- | --- |
| `data/persona.txt` | brand, output language and tone — the writer brief |
| `data/planner.txt` | the topic-strategist brief for `fb_content_plan.py`; it demands a different angle, trade and kind of proof per topic |
| `data/context.txt` | your positioning, injected into every post prompt |
| `shared/image_style.txt` | the house visual style, appended to every image prompt (shared by all sites) |
| `data/cta.txt` | the fixed call-to-action, appended to every post |
| `data/topics.txt` | topic queue (one per line) — fed by you or `fb_content_plan.py` |
| `data/past_posts.txt` | published history, newest first — synced by `fb_api.py past-posts` (gitignored) |
| `data/seeds.txt` | seed themes for `fb_content_plan.py` (one per line, `#` comments). **Vary them** — one narrow seed produces ten posts on that one theme |
| `data/reddit.txt` | research sources, one per line: `Construction` or `Contractor \| crew\|bid`. One line per subreddit. Only `sites/crewnetusa/` has this, which is what enables `research` there |
| `data/language.txt` | optional: pins the language the research brief is written in, so a foreign-language source post cannot drag the brief with it. Only the US Page needs one today |
| `data/concerns.json` / `.txt` | research output: what the audience worries about, dated and sourced (gitignored). The `.txt` is for reading, the `.json` for the planner |
| `drafts/` → `approved/` → `done/` | post lifecycle |
| `done/scheduled_posts.json` | local ledger of scheduled post ids |
| `.env` | keys and tokens (gitignored, chmod 600) |

**Everything generated is gitignored** — `drafts/`, `approved/`, `images/`, `previews/`,
`done/`, `data/past_posts.txt` and the research output (`data/concerns.*`) are all
excluded, so your post copy, published history, generated images, research briefs and
tokens stay off GitHub.

The consequence: **a fresh clone has none of those directories, and no post history.** Every
script creates the directory it needs, so just run Part 1 Step 4 and then the Part 2 steps in
order. Tracked under `data/` are only `context.txt`, `topics.txt` and `seeds.txt`.

## Gotchas

- **Reddit keys are inventory you cannot replace.** Reddit closed self-service app
  creation in late 2025, so `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` in `.env` are
  the only ones you will get without an approval process. The client is read-only and
  rate-limited to 1000 requests/10 min; `research` uses about 20 per run. Never
  reproduce comment text in a post — the brief paraphrases and links for a reason.
- **`.env` holds a Page token.** Gitignored and chmod 600. Never commit it.
- **The Page token never expires.** It dies only if you change your Facebook password,
  lose your Page role, or remove the app. On error code `190`, re-run `fb_api.py token`
  with a fresh short-lived token from the Graph API Explorer.
- **`GET /{page-id}/feed` is blocked** with Standard Access (error `#10`) even though the
  token has `pages_read_engagement` — that edge includes *other people's* posts. Use
  `/{page-id}/posts`. Meta's own docs get this wrong.
- **"API access blocked" (code 200) is usually KYC, not a ban.** If a call made with an *app*
  access token (`app_id|app_secret`) fails, the problem sits above the token — an unfinished
  identity check on the Facebook account. It presents exactly like an app restriction, so
  check identity verification before hunting the dashboard. Scheduled posts keep publishing
  through it, because Meta publishes them server-side. See `docs/meta-api-setup.md`.
- **No API edge lists scheduled posts.** The tooling keeps a local ledger and verifies each
  id against the API, so don't delete `done/scheduled_posts.json`.
- **`images/NN.png` are actually JPEG data** — `OPENAI_IMAGE_FORMAT=jpeg` by default, and
  Pollinations also returns JPEG. Harmless: the uploader sniffs real content instead of
  trusting the extension.
- **Facebook re-encodes your image anyway.** Upload a 1024×1024 file and the feed serves a
  720×720 version — `fb_api.py preview` shows that stored asset, which is what you should
  judge from.
- **Mixing providers is fine.** Old Pollinations images and new GPT Image ones coexist;
  nothing keys off the provider after the file is written.
- **Rate limits are a non-issue** at this volume (~4800 × engaged users calls per day).

## Fallback: manual scheduling

If the API path is unavailable, `fb_export_csv.py` still produces a Business Suite
bulk-upload CSV:

```bash
./fb root export-csv 2026-11-01 2
# then: business.facebook.com -> Planner -> Create -> Bulk upload
```

Unverified: Meta has renamed the Planner to "calendar view", and CSV bulk upload could not
be confirmed in current Meta documentation. Prefer the API.

## Verify

`bash scripts/verify_d01.sh` — offline pipeline check. No network writes, no API spend, no
key needed. Runs everything in a temp dir so your real `drafts/`, `approved/` and `done/`
are untouched. It also fails if a stale absolute path ever creeps back in.
