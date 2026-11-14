#!/usr/bin/env python3
"""Minimal read-only Reddit client: app-only OAuth, listings, comment bodies.

Reddit closed self-service app creation in late 2025, so new credentials are hard to
come by — but an existing "web app" still works for reading. client_credentials yields
a token with scope "*" and 1000 requests per 10 minutes, which covers listings and
comments. Nothing here posts, votes, or acts as a user; this is a read-only client.

Credentials are shared, not per site (one app serves every Page):
    REDDIT_CLIENT_ID      .env
    REDDIT_CLIENT_SECRET  .env
    REDDIT_USER_AGENT     optional; Reddit wants a descriptive, non-generic UA

Measured against the live API, and the reason callers should not trust search:
    - `q=работа Европа` in r/Ukraine returns ZERO results.
    - r/belgium `q=bouw` returns "Jolan De Bouw", matching a surname, not the topic.
  /top listings with a local regex filter are far more reliable; that is what
  fb_research.py does.
"""
import base64, json, os, sys, time, urllib.error, urllib.parse, urllib.request

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"
UA_DEFAULT = "macos:fb-agent:1.0 (by /u/reser4)"

# Reddit throttles with 429 and shrugs with 5xx; both are worth one more try.
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_SLEEPS = (2, 5, 10)


class RedditError(RuntimeError):
    """A failure worth showing the operator verbatim: no key, no token, no access."""


def credentials():
    cid = (os.environ.get("REDDIT_CLIENT_ID") or "").strip()
    sec = (os.environ.get("REDDIT_CLIENT_SECRET") or "").strip()
    if not (cid and sec):
        sys.exit(
            "error: Reddit credentials are not set.\n"
            "       Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to the shared .env\n"
            "       (one app serves every site). Self-service app creation is closed,\n"
            "       so these must come from an app that already exists — see\n"
            "       docs/reddit-research.md."
        )
    return cid, sec


class Reddit:
    def __init__(self, ua=None):
        self.cid, self.sec = credentials()
        self.ua = (ua or os.environ.get("REDDIT_USER_AGENT") or UA_DEFAULT).strip()
        self._tok = None
        self.calls = 0

    # ------------------------------------------------------------------ auth
    def token(self):
        """App-only token. Cached in-process; it is valid for 24h but TTL is irrelevant here."""
        if self._tok:
            return self._tok
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        auth = base64.b64encode(f"{self.cid}:{self.sec}".encode()).decode()
        req = urllib.request.Request(TOKEN_URL, data=body, headers={
            "Authorization": "Basic " + auth,
            "User-Agent": self.ua,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            payload = json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            # 401 here means the pair is wrong or the app was deleted — say that plainly,
            # because "unauthorized" alone sends people hunting through the wrong dashboard.
            raise RedditError(
                f"Reddit rejected these credentials (HTTP {e.code}). The client id/secret "
                "are wrong, or the app no longer exists."
            ) from None
        except urllib.error.URLError as e:
            raise RedditError(f"could not reach Reddit: {e.reason}") from None
        if "access_token" not in payload:
            raise RedditError(f"Reddit returned no access_token: {payload}")
        self._tok = payload["access_token"]
        return self._tok

    # --------------------------------------------------------------- request
    def get(self, path, **params):
        params.setdefault("raw_json", "1")
        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        last = None
        for attempt, sleep in enumerate(RETRY_SLEEPS + (None,)):
            req = urllib.request.Request(url, headers={
                "Authorization": "bearer " + self.token(),
                "User-Agent": self.ua,
            })
            try:
                self.calls += 1
                return json.load(urllib.request.urlopen(req, timeout=30))
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (403, 404):
                    return None          # private, banned, or nonexistent — skip silently
                if e.code not in RETRY_STATUS or sleep is None:
                    break
            except urllib.error.URLError as e:
                last = e
                if sleep is None:
                    break
            time.sleep(sleep)
        raise RedditError(f"GET {path} failed: {last}")

    # ---------------------------------------------------------------- reads
    def listing(self, sub, sort="top", window="month", limit=100):
        """A subreddit listing. Returns [] instead of raising for subs we cannot read."""
        d = self.get(f"/r/{sub}/{sort}", t=window, limit=min(int(limit), 100))
        if not d or not isinstance(d.get("data"), dict):
            return []
        return [c["data"] for c in d["data"].get("children", [])
                if c.get("kind") == "t3" and isinstance(c.get("data"), dict)]

    def comments(self, post_id, limit=15):
        """Top-level comments of one post. Second listing element holds them."""
        d = self.get(f"/comments/{post_id}", limit=limit, depth=1, sort="top")
        if not isinstance(d, list) or len(d) < 2:
            return []
        out = []
        for c in d[1].get("data", {}).get("children", []):
            if c.get("kind") != "t1":
                continue
            b = c.get("data") or {}
            body = " ".join((b.get("body") or "").split())
            if not body or body in ("[deleted]", "[removed]"):
                continue
            if (b.get("author") or "").lower() in ("automoderator", "[deleted]"):
                continue
            out.append({
                "author": b.get("author") or "?",
                "body": body,
                "score": b.get("score") or 0,
            })
        return out

    def check(self):
        """Prove the credentials work end to end, without spending anything."""
        self.token()
        d = self.get("/api/v1/me")
        # An app-only token has no user, which is the expected result for client_credentials.
        return {"token": True, "user": (d or {}).get("name") if isinstance(d, dict) else None}
