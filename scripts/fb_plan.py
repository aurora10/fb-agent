#!/usr/bin/env python3
"""Generate N FB post drafts (text + image prompt) from topics.
Usage: fb-plan TOPIC [TOPIC ...]   or reads data/topics.txt (one per line)
Writes drafts/draft_NN.json
"""
import json, os, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

BASE = Path(__file__).parent.parent
load_dotenv("/opt/data/.env")
client = OpenAI(base_url="https://api.deepseek.com/v1", api_key=os.environ["DEEPSEEK_API_KEY"], timeout=120)

CTX = (BASE / "data/context.txt").read_text() if (BASE / "data/context.txt").exists() else ""
PAST = (BASE / "data/past_posts.txt").read_text() if (BASE / "data/past_posts.txt").exists() else ""

def plan(topics):
    n_existing = len(list((BASE / "drafts").glob("draft_*.json"))) + len(list((BASE / "approved").glob("post_*.json"))) + len(list((BASE / "done").glob("post_*.json")))
    for i, topic in enumerate(topics, start=n_existing + 1):
        r = client.chat.completions.create(model="deepseek-flash",
            messages=[
                {"role": "system", "content": (
                    "Je schrijft Facebook-posts voor Constructief (constructief-bouw.be), "
                    "een Belgische tussenpersoon die voor gecontroleerde Oost-Europese bouwteams legt voor aannemers. "
                    "Toon: professioneel, direct, Vlaams Nederlands. Max 120 woorden. "
                    "Eindig met 1 call-to-action (contact/website) + 3-5 hashtags. "
                    f"Context: {CTX[:2000]}\n"
                    f"Eerdere posts op de pagina (niet herhalen, ook geen bijna-dubbele invalshoeken):\n"
                    f"{PAST[:4000] if PAST else '(geen)'}"
                )},
                {"role": "user", "content": (
                    f"Schrijf een Facebook-post over dit onderwerp: {topic}\n\n"
                    "Geef OOK een image_prompt in het Engels voor een foto-realistische illustratie "
                    "(bouwwerf, team aan het werk, geen logos/tekst in beeld, geen gezichten frontaal).\n\n"
                    "JSON antwoord: {\"post\": \"...\", \"image_prompt\": \"...\"}"
                )},
            ],
            response_format={"type": "json_object"},
        )
        data = json.loads(r.choices[0].message.content)
        data["topic"] = topic
        data["status"] = "draft"
        out = BASE / "drafts" / f"draft_{i:02d}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[ok] {out.name}: {topic}")

if __name__ == "__main__":
    topics = sys.argv[1:] or [l.strip() for l in (BASE / "data/topics.txt").read_text().splitlines() if l.strip()]
    plan(topics)
