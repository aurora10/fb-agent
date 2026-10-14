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

| Key | Where to get it |
| --- | --- |
| `OPENAI_API_KEY` | <https://platform.openai.com/api-keys> |
| `OPENAI_MODEL` | optional; defaults to `gpt-5.4-mini` |

Not sure which model your key can use?

```bash
.venv/bin/python scripts/fb_plan.py --models
```

Then paste your favourite into `OPENAI_MODEL`. Images use Pollinations (free, no key).

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
.venv/bin/python scripts/fb_api.py token    # 1x: mints a Page token that never expires
.venv/bin/python scripts/fb_api.py check    # verify
```

`check` should end in `ok`, with `expires : never` and `CREATE_CONTENT` in the tasks list.
If it does, setup is done for good — the token does not expire.

## Step 4 — Sync your post history

Without this, the model writes blind: it has no idea what you have already published, so it
repeats angles you covered months ago.

```bash
.venv/bin/python scripts/fb_api.py past-posts          # whole history
.venv/bin/python scripts/fb_api.py past-posts --limit 60
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

---

# Part 2 — Creating and scheduling posts

This is the routine. About 15 minutes, and it produces ~2 weeks of scheduled posts.

The order matters: **review the posts and their image prompts before generating any
images.** Prompts are shown in the gallery even for drafts that have no image yet, so
fixing a prompt costs seconds instead of a regeneration.

## Step 1 — Build the topic plan

First make sure the model knows what you have already published:

```bash
.venv/bin/python scripts/fb_api.py past-posts
```

Then let the agent propose the topics:

```bash
.venv/bin/python scripts/fb_content_plan.py "gevelrenovatie" "personeelstekort" "testweek"
# or run with no arguments to use the seeds in data/seeds.txt
.venv/bin/python scripts/fb_content_plan.py
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
.venv/bin/python scripts/fb_plan.py --limit 14
```

`data/topics.txt` acts as a queue: the topics used are removed once they have been drafted,
so the next run continues where this one stopped. The queue is only trimmed **after**
drafting succeeds, so a crash or a Ctrl-C never loses topics. Each run prints what is left
and suggests the next command.

If you queue more than ~14 and forget `--limit`, it warns and gives you 8 seconds to stop
before spending anything.

Other forms:

```bash
.venv/bin/python scripts/fb_plan.py                  # everything queued, no batching
.venv/bin/python scripts/fb_plan.py "topic one" "topic two"   # inline; queue untouched
```

Writes `drafts/draft_NN.json`, each with a `post` and an `image_prompt`. Your positioning is
injected from `data/context.txt`, and the history from Part 1 Step 4 keeps it off angles you
have already published.

## Step 3 — Review, and fix the image prompts

```bash
.venv/bin/python scripts/fb_preview.py
open previews/index.html
```

A gallery of every draft: text, topic, and the **image_prompt** (collapsed — click ▸ to
expand). No images exist yet, which is the point: this is where you judge the prompts.

To reword one without generating anything yet:

```bash
.venv/bin/python scripts/fb_regen_image.py 03 "photorealistic brick facade renovation in Flanders, no text, no logos"
```

`--edit-only` only updates `draft_03.json`. Without it, the same command also generates the
image, so you can go straight from "this prompt is wrong" to seeing the result.

## Step 4 — Generate the images

To try **one** post before committing to the batch — or any subset:

```bash
.venv/bin/python scripts/fb_images.py 4          # just draft 4
.venv/bin/python scripts/fb_images.py 4 7 12     # a few
.venv/bin/python scripts/fb_images.py            # every draft still missing an image
```

Rate-limited to about one per minute with retries built in, so a full 14-draft batch takes
roughly 15 minutes. It never overwrites, so prompts you already reworded in Step 3 are left
alone, and an already-generated image makes it a no-op rather than a re-render.

Redo a single image at any time, with a new prompt or the stored one:

```bash
.venv/bin/python scripts/fb_regen_image.py 03
.venv/bin/python scripts/fb_regen_image.py 03 "different angle, wider shot"
```

Then rerun `fb_preview.py` to see the result. The previous version is kept as
`images/03.old.png`.

## Step 5 — Approve what you want published

```bash
./approve 1 3 4        # approve drafts 1, 3 and 4
```

Moves those to `approved/`. Anything you skip stays in `drafts/` and is never published.

## Step 6 — Preview the schedule (nothing is sent)

```bash
.venv/bin/python scripts/fb_api.py schedule --dry-run --start 2026-11-01
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
.venv/bin/python scripts/fb_api.py schedule --start 2026-11-01
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
.venv/bin/python scripts/fb_api.py list
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

## Changing your mind

```bash
.venv/bin/python scripts/fb_api.py cancel 1262992640226921_...   # remove a scheduled post
```

Cancelling works until a post goes live. Once published, delete it in Meta Business Suite.

---

# Reference

## Commands

| Command | Purpose |
| --- | --- |
| `fb_api.py check` | verify token + Page + tasks |
| `fb_api.py token [PAGE_ID]` | mint the non-expiring Page token (re-run to switch Pages) |
| `fb_api.py test-post [--now]` | create a test post; `--now` publishes immediately |
| `fb_api.py list` | what's scheduled, plus recent published posts |
| `fb_api.py past-posts [--limit N]` | sync published posts → `data/past_posts.txt` |
| `fb_api.py cancel POST_ID` | delete a post |
| `fb_api.py schedule --start DATE [--every N] [--at HH:MM] [--dry-run]` | schedule `approved/` |
| `fb_plan.py [TOPIC...] [--limit N]` | generate drafts; `--limit N` takes the next N from the queue |
| `fb_content_plan.py SEED...` | LLM-proposed topic list → `data/topics.txt` |
| `fb_images.py [NN...]` | generate images (all drafts, or just the numbers given) |
| `fb_regen_image.py NN ["new prompt"] [--edit-only]` | reword a prompt and/or redo one image |
| `fb_preview.py` | build the review gallery (shows image_prompt per draft) |
| `./approve NN...` | move drafts to `approved/` |
| `fb_export_csv.py` | fallback: Business Suite bulk-upload CSV |
| `import_past_posts.py` | fallback: import history from a CSV export instead of the API |
| `fb_llm.py` | shared OpenAI helpers — model default, JSON parsing, key guard. Imported by the two planning scripts; not run directly |

## Files

| Path | What |
| --- | --- |
| `data/context.txt` | your positioning, injected into every prompt |
| `data/topics.txt` | topic queue (one per line) — fed by you or `fb_content_plan.py` |
| `data/past_posts.txt` | published history, newest first — synced by `fb_api.py past-posts` (gitignored) |
| `data/seeds.txt` | seed themes for `fb_content_plan.py` (one per line, `#` comments) |
| `drafts/` → `approved/` → `done/` | post lifecycle |
| `done/scheduled_posts.json` | local ledger of scheduled post ids |
| `.env` | keys and tokens (gitignored, chmod 600) |

**Everything generated is gitignored** — `drafts/`, `approved/`, `images/`, `previews/`,
`done/` and `data/past_posts.txt` are all excluded, so your post copy, published history,
generated images and tokens stay off GitHub.

The consequence: **a fresh clone has none of those directories, and no post history.** Every
script creates the directory it needs, so just run Part 1 Step 4 and then the Part 2 steps in
order. Tracked under `data/` are only `context.txt`, `topics.txt` and `seeds.txt`.

## Gotchas

- **`.env` holds a Page token.** Gitignored and chmod 600. Never commit it.
- **The Page token never expires.** It dies only if you change your Facebook password,
  lose your Page role, or remove the app. On error code `190`, re-run `fb_api.py token`
  with a fresh short-lived token from the Graph API Explorer.
- **`GET /{page-id}/feed` is blocked** with Standard Access (error `#10`) even though the
  token has `pages_read_engagement` — that edge includes *other people's* posts. Use
  `/{page-id}/posts`. Meta's own docs get this wrong.
- **No API edge lists scheduled posts.** The tooling keeps a local ledger and verifies each
  id against the API, so don't delete `done/scheduled_posts.json`.
- **`images/NN.png` are actually JPEG data** (Pollinations returns JPEG). Harmless — the
  uploader sniffs real content instead of trusting the extension.
- **Rate limits are a non-issue** at this volume (~4800 × engaged users calls per day).

## Fallback: manual scheduling

If the API path is unavailable, `fb_export_csv.py` still produces a Business Suite
bulk-upload CSV:

```bash
.venv/bin/python scripts/fb_export_csv.py 2026-11-01 2
# then: business.facebook.com -> Planner -> Create -> Bulk upload
```

Unverified: Meta has renamed the Planner to "calendar view", and CSV bulk upload could not
be confirmed in current Meta documentation. Prefer the API.

## Verify

`bash scripts/verify_d01.sh` — offline pipeline check. No network writes, no API spend, no
key needed. Runs everything in a temp dir so your real `drafts/`, `approved/` and `done/`
are untouched. It also fails if a stale absolute path ever creeps back in.
