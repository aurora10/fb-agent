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

---

# Part 2 — Creating and scheduling posts

This is the routine. About 15 minutes, and it produces ~2 weeks of scheduled posts.

## Step 1 — Decide your topics

Either pass them inline:

```bash
.venv/bin/python scripts/fb_plan.py "testweek voor aannemers" "A1/Limosa documenten"
```

…or edit `data/topics.txt` (one topic per line) and run it with no arguments:

```bash
.venv/bin/python scripts/fb_plan.py
```

Topics work best when they name a **specific contractor problem**. Compare:

- ❌ *"Onze diensten"* — nobody searches for this
- ✅ *"A1- en Limosa-documenten: zo vermijdt u boetes op de werf"*

Your positioning is injected into every prompt from `data/context.txt` — edit that file as
your offer evolves, and every future post follows it.

Output: `drafts/draft_NN.json`, each with a `post` and an `image_prompt`.
The planner also reads `data/past_posts.txt` and avoids repeating old angles.

## Step 2 — Generate the images

```bash
.venv/bin/python scripts/fb_images.py
```

Creates `images/NN.png` to match each draft. Rate-limited to about one per minute with
retries built in, so expect it to take a few minutes. It won't overwrite existing files.

## Step 3 — Review everything in one screen

```bash
.venv/bin/python scripts/fb_preview.py
open previews/index.html
```

A gallery of every draft: text, image, and topic side by side. This is where you decide
what actually goes out.

## Step 4 — Approve what you want published

```bash
./approve 1 3 4        # approve drafts 1, 3 and 4
```

Moves those to `approved/`. Anything you skip stays in `drafts/` and is never published.

## Step 5 — Preview the schedule (nothing is sent)

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

## Step 6 — Schedule them for real

```bash
.venv/bin/python scripts/fb_api.py schedule --start 2026-11-01
```

Each post goes out every 2nd day at **19:05 local time**, with its image attached, then
moves from `approved/` to `done/` so it can't be scheduled twice.

Two rules the script enforces:

- **Keep within 30 days.** That is Meta's real limit, so at 2-day spacing a run schedules
  ~14 posts. The script refuses anything further out rather than failing silently at
  Meta's end.
- **Times use your machine's timezone**, so the local clock stays at 19:05 across daylight
  saving changes.

## Step 7 — Confirm what's queued

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
| `fb_api.py cancel POST_ID` | delete a post |
| `fb_api.py schedule --start DATE [--every N] [--at HH:MM] [--dry-run]` | schedule `approved/` |
| `fb_plan.py TOPIC...` | generate drafts (+ `--models`) |
| `fb_images.py` | generate images |
| `fb_preview.py` | build the review gallery |
| `./approve NN...` | move drafts to `approved/` |
| `fb_export_csv.py` | fallback: Business Suite bulk-upload CSV |
| `import_past_posts.py` | seed `data/past_posts.txt` to avoid repeating topics |

## Files

| Path | What |
| --- | --- |
| `data/context.txt` | your positioning, injected into every prompt |
| `data/topics.txt` | topic queue (one per line) |
| `data/past_posts.txt` | previously published posts, used to avoid repeats |
| `drafts/` → `approved/` → `done/` | post lifecycle |
| `done/scheduled_posts.json` | local ledger of scheduled post ids |
| `.env` | keys and tokens (gitignored, chmod 600) |

**Everything generated is gitignored** — `drafts/`, `approved/`, `images/`, `previews/` and
`done/` are all excluded, so your post copy, published images and tokens stay off GitHub.
The consequence: **a fresh clone has none of those directories.** Every script creates the
one it needs, so just run the Part 2 steps in order. Only `data/` and `scripts/` are
tracked.

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
