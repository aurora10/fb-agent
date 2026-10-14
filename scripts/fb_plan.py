#!/usr/bin/env python3
"""Generate FB post drafts (text + image prompt) from topics.

Usage: fb_plan.py TOPIC [TOPIC ...]   or reads data/topics.txt (one per line)
       fb_plan.py --models            list chat models your OpenAI key can use
Writes drafts/draft_NN.json
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import BASE, ask, client, data_file, show_models

CTX = data_file("context.txt")
PAST = data_file("past_posts.txt")


def plan(topics):
    cl = client()
    (BASE / "drafts").mkdir(parents=True, exist_ok=True)
    n_existing = (len(list((BASE / "drafts").glob("draft_*.json")))
                  + len(list((BASE / "approved").glob("post_*.json")))
                  + len(list((BASE / "done").glob("post_*.json"))))
    system = (
        "Je schrijft Facebook-posts voor Constructief (constructief-bouw.be), "
        "een Belgische tussenpersoon die voor gecontroleerde Oost-Europese bouwteams legt voor aannemers. "
        "Toon: professioneel, direct, Vlaams Nederlands. Max 120 woorden. "
        "Eindig met 1 call-to-action (contact/website) + 3-5 hashtags. "
        f"Context: {CTX[:2000]}\n"
        f"Eerdere posts op de pagina (niet herhalen, ook geen bijna-dubbele invalshoeken):\n"
        f"{PAST[:4000] if PAST else '(geen)'}"
    )
    for i, topic in enumerate(topics, start=n_existing + 1):
        data = ask(cl, system, (
            f"Schrijf een Facebook-post over dit onderwerp: {topic}\n\n"
            "Geef OOK een image_prompt in het Engels voor een foto-realistische illustratie "
            "(bouwwerf, team aan het werk, geen logos/tekst in beeld, geen gezichten frontaal).\n\n"
            "JSON antwoord: {\"post\": \"...\", \"image_prompt\": \"...\"}"
        ))
        if "post" not in data:
            sys.exit(f"error: model returned no 'post' key for topic {topic!r}")
        data["topic"] = topic
        data["status"] = "draft"
        out = BASE / "drafts" / f"draft_{i:02d}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[ok] {out.name}: {topic}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
    elif args and args[0] == "--models":
        show_models()
    else:
        topics = args
        if not topics:
            tf = BASE / "data/topics.txt"
            if not tf.exists():
                sys.exit(f"error: no topics given and {tf} does not exist — "
                         f"pass topics as arguments or create that file (one per line)")
            topics = [l.strip() for l in tf.read_text().splitlines() if l.strip()]
        if not topics:
            sys.exit("error: no topics to plan")
        plan(topics)
