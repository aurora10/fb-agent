#!/usr/bin/env python3
"""Shared OpenAI helpers for the fb-agent scripts.

Lives in one place because fb_plan.py and fb_content_plan.py need to agree on the model
default and on how model output is parsed — they silently diverged when that logic was
duplicated.
"""
import json, os, re, sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI, BadRequestError

BASE = Path(__file__).parent.parent
ENV_PATH = BASE / ".env"
DEFAULT_MODEL = "gpt-5.4-mini"          # override with OPENAI_MODEL in .env

load_dotenv(ENV_PATH)


def client():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit(f"error: OPENAI_API_KEY is not set — add it to {ENV_PATH}\n"
                 f"       (see .env.example; get a key at https://platform.openai.com/api-keys)")
    return OpenAI(timeout=120)


def model():
    return os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL


def data_file(name):
    """Contents of data/<name>, or '' when it does not exist."""
    p = BASE / "data" / name
    return p.read_text() if p.exists() else ""


def parse_json(content):
    """Models sometimes wrap JSON in ``` fences or add prose around it."""
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content).strip()
    try:
        return json.loads(content)
    except ValueError:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            sys.exit(f"error: model did not return JSON:\n{content[:400]}")
        return json.loads(m.group(0))


def ask(cl, system, user):
    """One JSON-mode completion, falling back to plain completion for models without it."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        r = cl.chat.completions.create(model=model(), messages=msgs,
                                       response_format={"type": "json_object"})
    except BadRequestError:
        # Not every model supports JSON mode; retry and parse leniently instead.
        r = cl.chat.completions.create(model=model(), messages=msgs)
    return parse_json(r.choices[0].message.content)


def show_models():
    """Chat models this key can actually use — nobody should have to guess an id."""
    cl = client()
    names = sorted(m.id for m in cl.models.list().data
                   if m.id.startswith(("gpt-", "o")) and not any(
                       k in m.id for k in ("audio", "image", "realtime", "transcribe",
                                           "tts", "codex", "search", "moderation", "live")))
    print(f"chat models available to this key (current default: {model()}):\n")
    for n in names:
        print(f"  {n}")
    print("\nChange it in .env with:  OPENAI_MODEL=<one of the above>\n"
          "For this task a 'mini' tier is usually the right tradeoff.")
