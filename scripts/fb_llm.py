#!/usr/bin/env python3
"""Shared helpers for the fb-agent scripts: site roots, env, OpenAI, post assembly.

This module is the single place that decides WHERE a run reads and writes. Everything
site-specific (Page identity, copy, topics, queue) lives under the active site root;
everything shared (the API keys, the visual style) does not.

Layout:
    repo/.env                 shared: OPENAI_API_KEY, FB_APP_ID/SECRET, SITE=
    repo/scripts/             shared, site-agnostic code — never edited per site
    repo/shared/              shared assets, e.g. image_style.txt
    repo/sites/<name>/        one site: .env, data/, drafts/, images/, done/ ...
    repo/ (SITE unset)        the repo root itself is the site — the original layout

Select a site with SITE in the shared .env, or per command:
    SITE=crewnetusa .venv/bin/python scripts/fb_plan.py
"""
import json, os, re, sys
from pathlib import Path
from dotenv import dotenv_values, load_dotenv
from openai import OpenAI, BadRequestError

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "shared"
DEFAULT_MODEL = "gpt-5.4-mini"          # override with OPENAI_MODEL in .env


def _site_name():
    """Real environment wins, then the shared .env, else '' (= the repo root is the site)."""
    if os.environ.get("SITE", "").strip():
        return os.environ["SITE"].strip()
    try:
        return (dotenv_values(REPO / ".env").get("SITE") or "").strip()
    except Exception:
        return ""


SITE = _site_name()
BASE = (REPO / "sites" / SITE) if SITE else REPO
ENV_PATH = BASE / ".env"

# Site .env first, so its Page identity can never be clobbered by the shared one.
# Rule that makes this safe: no key appears in both files — shared holds API keys,
# the site holds FB_PAGE_ID / FB_PAGE_TOKEN only.
load_dotenv(ENV_PATH)
load_dotenv(REPO / ".env")


def client():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit(f"error: OPENAI_API_KEY is not set — add it to {REPO / '.env'}\n"
                 f"       (see .env.example; get a key at https://platform.openai.com/api-keys)")
    return OpenAI(timeout=120)


def model():
    return os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL


def data_file(name):
    """Site data/<name>, falling back to shared/<name>, else ''.

    The fallback is what lets image_style.txt stay shared while context.txt, topics.txt,
    seeds.txt, past_posts.txt and cta.txt are per site. A site overrides a shared asset
    simply by having its own copy.
    """
    for p in (BASE / "data" / name, SHARED / name):
        if p.exists():
            return p.read_text()
    return ""


# --------------------------------------------------------------- post assembly
# The call-to-action is fixed, not model-written. Left to the model it drifted: across one
# batch, 5 posts used the /nl/werkgevers link and 8 used the bare domain, while 29 of the
# 50 published posts use the full link. Edit data/cta.txt to change it everywhere.

CTA_FILE = "cta.txt"


def cta():
    return data_file(CTA_FILE).strip()


def strip_tags(text):
    """Drop a trailing hashtag run, in case a model appends one anyway."""
    return re.sub(r"(\s*#[\w\u00c0-\u024f]+)+\s*$", "", (text or "").strip()).strip()


def compose_post(body, hashtags=()):
    """body -> CTA -> hashtags, matching the Page's existing convention."""
    body = (body or "").strip()
    tags = " ".join(h if h.startswith("#") else f"#{h}"
                    for h in (t.strip() for t in hashtags) if h)
    parts = [p for p in (body, cta(), tags) if p]
    return "\n\n".join(parts[:2]) + (f"\n{tags}" if len(parts) > 2 else "")


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


# --------------------------------------------------------------- post history
# Voice and dedup want different amounts of history, so they get different slices.
# A handful of full posts is enough to match the tone; avoiding a repeated angle needs
# every angle, but only the hook of each — full bodies would not fit and are not needed.

VOICE_POSTS = 10        # recent posts sent in full
HOOK_CHARS = 90         # per-post opener used as the angle digest
MAX_HOOKS = 400         # bound the prompt if history ever grows large


def past_posts():
    """data/past_posts.txt as a list, newest first (see `fb_api.py past-posts`)."""
    return [l.strip() for l in data_file("past_posts.txt").splitlines() if l.strip()]


def history_block(also_avoid=()):
    """Prompt text describing what is already published, and what is already queued.

    Replaces the old `PAST[:4000]`, which kept 9% of history — about 3 posts out of 50.
    """
    posts = past_posts()
    parts = []

    if posts:
        recent = posts[:VOICE_POSTS]
        parts.append("Recente posts (volledige tekst, om toon en stijl te volgen):\n"
                     + "\n".join(f"- {t}" for t in recent))

        hooks = posts[:MAX_HOOKS]
        note = "" if len(posts) <= MAX_HOOKS else f" (oudste {len(posts) - MAX_HOOKS} weggelaten)"
        parts.append(
            f"Alle {len(hooks)} eerder gepubliceerde invalshoeken{note} — kom hier niet op "
            "terug, ook niet met andere woorden:\n"
            + "\n".join(f"- {t[:HOOK_CHARS].rstrip()}" for t in hooks)
        )
    else:
        parts.append("(No post history loaded. If this Page has published posts, run "
                     "`fb_api.py past-posts` to load them. If it is a new Page, there is "
                     "nothing to avoid yet.)")

    if also_avoid:
        parts.append("Al gepland maar nog niet gepubliceerd (ook vermijden):\n"
                     + "\n".join(f"- {t}" for t in also_avoid))
    return "\n\n".join(parts)
