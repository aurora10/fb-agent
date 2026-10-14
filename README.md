# fb-agent

Facebook content pipeline for **constructief-bouw.be** — intent-focused posts that speak
to Belgian/Dutch general contractors who need reliable subcontractor teams.

Scheduling happens in **Meta Business Suite Planner** (bulk upload) — no Meta API needed.

## Content strategy

Posts are generated around buyer-intent topics, not generic construction fluff:

- **Problem-aware**: staffing shortages, unreliable subs, deadline risk, A1/Limosa compliance
- **Solution-aware**: how subcontracting with vetted teams works, testweek, pricing model
- **Proof**: how screening works, what "payment on result" means in practice
- **Trades**: gevel, renovatie, dak, beton — pain points per trade

Business context injected into every prompt lives in `data/context.txt` —
edit it as your positioning evolves. Topics go in `data/topics.txt` (one per line)
or are passed directly on the command line.

## Setup (once)

```bash
git clone https://github.com/aurora10/fb-agent.git
cd fb-agent
uv venv .venv && uv pip install --python .venv/bin/python openai python-dotenv
```

Keys: text generation uses DeepSeek — set `DEEPSEEK_API_KEY` in a local `.env`
or export it in your shell. Images use Pollinations (free, no key).

## Monthly routine (~15 min)

```bash
# 1. Draft posts (NL, with your USPs) + image prompts
.venv/bin/python scripts/fb_plan.py "topic 1" "topic 2" "topic 3"
#    or: write topics into data/topics.txt and run without arguments

# 2. Generate images -> images/NN.png (rate-limited ~1/min, retries built in)
.venv/bin/python scripts/fb_images.py

# 3. Review the preview gallery: previews/index.html (open in browser)
.venv/bin/python scripts/fb_preview.py

# 4. Approve the posts you want published
./approve 1 3 4

# 5. Export bulk-upload CSV (start date, every N days at 10:00)
.venv/bin/python scripts/fb_export_csv.py 2026-11-01 2

# 6. Upload: business.facebook.com -> Planner -> Create -> Bulk upload
#    CSV from done/, attach the numbered images/ when prompted
```

Approved posts move `drafts/ -> approved/ -> done/` so numbering never collides.

## Custom images

If you prefer your own site/project photos over AI ones for a given post,
save them as `images/NN.png` matching the post number and skip/finish
`fb_images.py` afterwards (it won't overwrite existing files).

## Verify

`bash scripts/verify_d01.sh` — offline pipeline check (no API calls).
