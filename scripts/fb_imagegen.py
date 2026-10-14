#!/usr/bin/env python3
"""Image generation for the pipeline — OpenAI GPT Image or Pollinations.

Provider comes from IMAGE_PROVIDER (`openai` by default, or `pollinations`).
Pollinations is free and needs no key; GPT Image costs per image, so
OPENAI_IMAGE_QUALITY is the main cost lever (low / medium / high / xhigh / max).

Kept in one module so fb_images.py and fb_regen_image.py cannot drift apart on which
provider, model or size they use.
"""
import base64, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fb_llm import client

DEFAULT_OPENAI_MODEL = "gpt-image-2"
VALID_SIZES = ("1024x1024", "1024x1536", "1536x1024")
VALID_QUALITY = ("low", "medium", "high", "xhigh", "max", "auto")
POLLINATIONS = "https://image.pollinations.ai/prompt/{}?width=1024&height=1024&nologo=true"


def provider():
    return (os.environ.get("IMAGE_PROVIDER") or "openai").strip().lower()


def image_model():
    return os.environ.get("OPENAI_IMAGE_MODEL") or DEFAULT_OPENAI_MODEL


def image_size():
    return os.environ.get("OPENAI_IMAGE_SIZE") or "1024x1024"


def image_quality():
    return os.environ.get("OPENAI_IMAGE_QUALITY") or "medium"


def image_format():
    return os.environ.get("OPENAI_IMAGE_FORMAT") or "jpeg"


def describe():
    """One line for the user, so it is obvious what is being spent."""
    if provider() == "pollinations":
        return "pollinations (free)"
    return f"{image_model()} @ {image_size()} quality={image_quality()} ({image_format()})"


def generate(prompt, log=print):
    """Image bytes, or None. Returns None without retrying when the model refuses."""
    if provider() == "pollinations":
        return _pollinations(prompt, log)
    return _openai(prompt, log)


def _openai(prompt, log):
    cl = client()
    size, quality = image_size(), image_quality()
    if size not in VALID_SIZES:
        log(f"[!!] OPENAI_IMAGE_SIZE={size!r} is not one of {VALID_SIZES}; using 1024x1024")
        size = "1024x1024"
    if quality not in VALID_QUALITY:
        log(f"[!!] OPENAI_IMAGE_QUALITY={quality!r} is not one of {VALID_QUALITY}; using medium")
        quality = "medium"

    for attempt in range(3):
        try:
            r = cl.images.generate(
                model=image_model(), prompt=prompt, n=1,
                size=size, quality=quality, output_format=image_format(),
            )
        except Exception as e:
            msg = str(e)
            # A refusal is deterministic — retrying just burns time and money.
            if any(k in msg.lower() for k in ("content_policy", "safety", "moderation",
                                              "rejected", "blocked")):
                log(f"[BLOCKED] the model refused this prompt — reword it and retry\n"
                    f"          {msg[:200]}")
                return None
            log(f"[retry {attempt + 1}] {type(e).__name__}: {msg[:160]}")
            time.sleep(5)
            continue

        d = r.data[0] if r.data else None
        b64 = getattr(d, "b64_json", None)
        if b64:
            return base64.b64decode(b64)
        url = getattr(d, "url", None)
        if url:
            return urllib.request.urlopen(url, timeout=60).read()
        log(f"[retry {attempt + 1}] response carried neither b64_json nor url")
        time.sleep(5)
    return None


def _pollinations(prompt, log):
    url = POLLINATIONS.format(urllib.parse.quote(prompt[:300]))
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fb-agent/1.0"})
            data = urllib.request.urlopen(req, timeout=120).read()
        except Exception as e:
            log(f"[retry {attempt + 1}] {e}")
            time.sleep(8)
            continue
        if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff":
            return data
        log(f"[retry {attempt + 1}] response was not an image ({len(data)} bytes)")
        time.sleep(8)
    return None
