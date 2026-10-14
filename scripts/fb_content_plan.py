#!/usr/bin/env python3
"""Generate an intent-focused topic plan (deduped against past posts).
Usage: fb_content_plan.py SEED [SEED ...]   e.g. "gevelrenovatie" "personeelstekort"
Appends suggestions to data/topics.txt (deduped); you can delete lines there anytime.
"""
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

BASE = Path(__file__).parent.parent
load_dotenv(BASE / ".env")
DEFAULT_MODEL = "gpt-4o-mini"

CTX = (BASE / "data/context.txt").read_text() if (BASE / "data/context.txt").exists() else ""
PAST = (BASE / "data/past_posts.txt").read_text() if (BASE / "data/past_posts.txt").exists() else ""

def main():
    seeds = sys.argv[1:] or [l.strip() for l in (BASE / "data/seeds.txt").read_text().splitlines() if l.strip()]
    cl = OpenAI(timeout=120)
    new = []
    for seed in seeds:
        r = cl.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Je bent contentstrateeg voor Constructief (constructief-bouw.be). "
                    "Maak 10 Facebook-post-onderwerpen over het seed-thema voor aannemers in BE/NL. "
                    "Mix: probleem-bewust (werkvoorraad, deadlines, personeelstekort, A1/Limosa), "
                    "oplossing-bewust (testweek, screening, betaling op resultaat), bewijs, trade-specifiek (gevel/renovatie/dak/beton). "
                    "Max 15 woorden per onderwerp. Nederlandstalig.\n\n"
                    f"Context: {CTX[:1500]}\n"
                    f"Deze onderwerpen staan AL op de pagina, niet herhalen:\n{PAST[:3000] if PAST else '(geen)'}"
                )},
                {"role": "user", "content": f"Seed-thema: {seed}\nJSON: {{\"topics\": [\"...\", ...]}}"},
            ],
        )
        topics = json.loads(r.choices[0].message.content)["topics"]
        new += topics
        print(f"[ok] {seed}: {len(topics)} onderwerpen")

    tf = BASE / "data/topics.txt"
    existing = {l.strip().lower() for l in tf.read_text().splitlines()} if tf.exists() else set()
    add = [t for t in new if t.strip() and t.strip().lower() not in existing]
    if add:
        with tf.open("a") as fh:
            fh.write("".join(t + "\n" for t in add))
        print(f"[ok] data/topics.txt += {len(add)} nieuwe (totaal {len(existing) + len(add)})")
    else:
        print("[..] geen nieuwe unieke onderwerpen")

if __name__ == "__main__":
    main()
