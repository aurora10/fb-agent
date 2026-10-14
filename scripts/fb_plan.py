#!/usr/bin/env python3
"""Generate FB post drafts (text + image prompt) from topics.

Usage: fb_plan.py TOPIC [TOPIC ...]   or reads data/topics.txt (one per line)
       fb_plan.py --models            list chat models your OpenAI key can use
Writes drafts/draft_NN.json
"""
import json, os, re, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI, BadRequestError

BASE = Path(__file__).parent.parent
ENV_PATH = BASE / ".env"
DEFAULT_MODEL = "gpt-5.4-mini"        # override with OPENAI_MODEL in .env

# Keys come from the .env beside the repo.
load_dotenv(ENV_PATH)

CTX = (BASE / "data/context.txt").read_text() if (BASE / "data/context.txt").exists() else ""
PAST = (BASE / "data/past_posts.txt").read_text() if (BASE / "data/past_posts.txt").exists() else ""


def client():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit(f"error: OPENAI_API_KEY is not set — add it to {ENV_PATH}\n"
                 f"       (see .env.example; get a key at https://platform.openai.com/api-keys)")
    return OpenAI(timeout=120)


def model():
    return os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL


def parse_json(content):
    """Models sometimes wrap JSON in ``` fences or add prose."""
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content).strip()
    try:
        return json.loads(content)
    except ValueError:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            raise SystemExit(f"error: model did not return JSON:\n{content[:400]}")
        return json.loads(m.group(0))


def ask(cl, system, user):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        r = cl.chat.completions.create(model=model(), messages=msgs,
                                       response_format={"type": "json_object"})
    except BadRequestError:
        # Not every model supports JSON mode; retry and parse leniently instead.
        r = cl.chat.completions.create(model=model(), messages=msgs)
    return parse_json(r.choices[0].message.content)


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
        data["topic"] = topic
        data["status"] = "draft"
        out = BASE / "drafts" / f"draft_{i:02d}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"[ok] {out.name}: {topic}")


def show_models():
    cl = client()
    names = sorted(m.id for m in cl.models.list().data
                   if m.id.startswith(("gpt-", "o")) and not any(
                       k in m.id for k in ("audio", "image", "realtime", "transcribe",
                                           "tts", "codex", "search", "moderation", "live")))
    print(f"chat models available to this key (current default: {model()}):\n")
    for n in names:
        print(f"  {n}")
    print(f"\nChange it in .env with:  OPENAI_MODEL=<one of the above>\n"
          f"For this task a 'mini' tier is usually the right tradeoff.")


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
