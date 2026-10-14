# fb-agent

Planner-based Facebook posting pipeline for constructief-bouw.be.
No Meta Graph API needed — scheduling happens via Meta Business Suite Planner bulk upload.

## Flow

```bash
cd /opt/data/fb-agent

# 1. Generate drafts (DeepSeek; key in /opt/data/.env as DEEPSEEK_API_KEY)
.venv/bin/python scripts/fb_plan.py "topic 1" "topic 2"
#    or: list topics, one per line, in data/topics.txt

# 2. Generate images (Pollinations, free, no key) -> images/NN.png
.venv/bin/python scripts/fb_images.py

# 3. Preview gallery -> previews/index.html (open in browser)
.venv/bin/python scripts/fb_preview.py

# 4. Approve the good ones
./approve 1 3 4

# 5. Export bulk-upload CSV (start date, every N days at 10:00)
.venv/bin/python scripts/fb_export_csv.py 2026-11-01 2
#    -> done/planner_upload_2026-11-01.csv

# 6. Upload in browser: business.facebook.com -> Planner -> Create -> Bulk upload
#    attach images/NN.png when prompted for media
```

## Layout

- `data/context.txt` — business context injected into every prompt (edit freely)
- `drafts/`, `approved/`, `done/` — post lifecycle (JSON)
- `images/` — generated images, numbered to match posts
- `scripts/verify_d01.sh` — offline pipeline check (`bash scripts/verify_d01.sh`)

## Notes

- Pollinations rate-limits ~1 image/min; the script retries, batches just take time.
- To use real candidate photos instead of AI: place them as `images/NN.png` before exporting.
- Monthly routine ≈ 15 min: plan ~10 topics → review gallery → approve → export → upload.
