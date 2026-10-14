#!/usr/bin/env python3
"""Facebook Page Graph API helper: token, verification, scheduling.

Reads .env (FB_APP_ID, FB_APP_SECRET, FB_PAGE_ID, FB_PAGE_TOKEN).
See docs/meta-api-setup.md for how to obtain those.

  ./scripts/fb_api.py check                        verify token + Page + tasks
  ./scripts/fb_api.py token [PAGE_ID]            1x: short-lived user token -> long-lived Page token
                                                 (re-run with a PAGE_ID to switch Pages)
  ./scripts/fb_api.py test-post [--now]            create a scheduled test post
  ./scripts/fb_api.py list                         list scheduled / unpublished posts
  ./scripts/fb_api.py past-posts [--limit N]       sync published posts -> data/past_posts.txt
  ./scripts/fb_api.py cancel POST_ID               delete a post
  ./scripts/fb_api.py schedule --start DATE [--every N] [--at HH:MM] [--dry-run]
                                                   schedule approved/ posts, then move to done/
                                                   (defaults: every 2 days at 19:05 local)
"""
import json, mimetypes, os, sys, urllib.error, urllib.parse, urllib.request, uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).parent.parent
ENV_PATH = BASE / ".env"
LEDGER = BASE / "done" / "scheduled_posts.json"   # local record of posts we scheduled
API = "https://graph.facebook.com/v26.0"  # pinned: v18/v19/v20 are already dead

# Measured against the live Page on 2026-10-14: +29.00d is accepted, +29.01d is rejected
# with "(#100) The specified scheduled publish time is invalid". The limit is exactly 29
# days from the moment of the request. Meta's docs claim 30 days (Pages API guide) and
# 75 days (Page Feed reference) — both are wrong in practice.
MAX_DAYS_AHEAD = 29


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def env(key, required=True):
    v = os.environ.get(key)
    if required and not v:
        die(f"{key} is not set — add it to {ENV_PATH}")
    return v


def app_token():
    return f"{env('FB_APP_ID')}|{env('FB_APP_SECRET')}"


def _ctype_for(path):
    """Content type from magic bytes, not the extension.

    The generated images are JPEG data saved as .png (Pollinations returns JPEG), so
    trusting the extension would send Content-Type: image/png with JPEG bytes.
    """
    head = Path(path).read_bytes()[:12]
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:4] == b"GIF8":
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _multipart(fields, files):
    b = "----fbapi" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, path in files.items():
        ctype = _ctype_for(path)
        out.append(
            f'--{b}\r\nContent-Disposition: form-data; name="{k}"; '
            f'filename="{Path(path).name}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
        )
        out.append(Path(path).read_bytes())
        out.append(b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


def graph(path, params=None, method="GET", files=None, soft=False, timeout=120):
    """One Graph API call. Dies with Meta's own error text unless soft=True."""
    params = dict(params or {})
    url = f"{API}/{path.lstrip('/')}"
    if files:
        body, ctype = _multipart(params, files)
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", ctype)
    elif method == "GET":
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(f"{url}?{qs}" if qs else url, method="GET")
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="ignore")
        if soft:
            return None
        try:
            err = json.loads(raw)["error"]
            sub = f", subcode {err['error_subcode']}" if err.get("error_subcode") else ""
            hint = ""
            if err.get("code") == 190:
                hint = "  -> token invalid/expired; re-run `token`"
            die(f"{err.get('message')} (code {err.get('code')}{sub}){hint}")
        except (ValueError, KeyError):
            die(f"HTTP {e.code}: {raw[:300]}")


def set_env(updates):
    """Update keys in .env in place, preserving comments and order. chmod 600."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    seen, out = set(), []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() in updates:
            k = s.split("=", 1)[0].strip()
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    ENV_PATH.write_text("\n".join(out).rstrip("\n") + "\n")
    os.chmod(ENV_PATH, 0o600)


def local_ts(d, hhmm):
    """Naive local date+time -> unix ts, using the machine's timezone (DST-safe)."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    return int(datetime(d.year, d.month, d.day, hh, mm).astimezone().timestamp())


# ---------------------------------------------------------------- subcommands

def cmd_check():
    tok, pid = env("FB_PAGE_TOKEN"), env("FB_PAGE_ID")
    dbg = graph("debug_token", {"input_token": tok, "access_token": app_token()}, soft=True)
    if dbg and dbg.get("data"):
        d = dbg["data"]
        exp = d.get("expires_at", 0)
        when = "never" if not exp else datetime.fromtimestamp(exp).isoformat()
        print(f"token valid  : {d.get('is_valid')}")
        print(f"token type   : {d.get('type')}")
        print(f"expires      : {when}")
        print(f"scopes       : {', '.join(d.get('scopes', [])) or '(none reported)'}")
        if d.get("is_valid") is False:
            die("token is not valid — re-run `token`")
    else:
        print("token check  : skipped (FB_APP_ID/FB_APP_SECRET not usable)")
    page = graph(pid, {"fields": "name", "access_token": tok}, soft=True)
    if page is None:
        die(f"the Page token cannot read Page {pid} — is FB_PAGE_ID correct?")
    print(f"page         : {page.get('name')} ({pid})")

    # `tasks` lives on the user's accounts edge, not on the Page node, so it can only be
    # read with a user token. Without one, say so rather than implying a role problem.
    tasks = None
    long_user = os.environ.get("FB_LONG_USER_TOKEN", "").strip()
    if long_user:
        for p in _fetch_pages(long_user) or []:
            if p["id"] == pid:
                tasks = p.get("tasks", [])
    if tasks is None:
        print("tasks        : (not checked — FB_LONG_USER_TOKEN empty or expired)")
    else:
        print(f"tasks        : {', '.join(tasks) or '(none)'}")
        if "CREATE_CONTENT" not in tasks:
            print("  !! CREATE_CONTENT missing — you need a Page role that allows publishing")
    print("ok" if not tasks or "CREATE_CONTENT" in tasks else "NOT READY")


def _fetch_pages(user_token):
    """Pages this user can act on, or None if the token is dead."""
    r = graph("me/accounts", {
        "access_token": user_token,
        "fields": "name,id,access_token,tasks",
    }, soft=True)
    return None if r is None else r.get("data", [])


def cmd_token(argv):
    """Exchange for a long-lived Page token. Optional arg: PAGE_ID."""
    long_user = os.environ.get("FB_LONG_USER_TOKEN", "").strip()
    pages = None

    if long_user:
        print("reusing the stored long-lived user token (~60 days)")
        pages = _fetch_pages(long_user)
        if pages is None:
            print("  ...it has expired; falling back to the short-lived token")
            long_user = ""

    if not long_user:
        short = os.environ.get("FB_USER_TOKEN", "").strip()
        if not short:
            die("no usable token: FB_LONG_USER_TOKEN is expired or empty and FB_USER_TOKEN is "
                "blank. Generate a fresh short-lived token in the Graph API Explorer, paste it "
                "into FB_USER_TOKEN, and re-run.")
        r = graph("oauth/access_token", {
            "grant_type": "fb_exchange_token",
            "client_id": env("FB_APP_ID"),
            "client_secret": env("FB_APP_SECRET"),
            "fb_exchange_token": short,
        }, soft=True)
        if not r or "access_token" not in r:
            die("exchange failed — short-lived tokens last ~1-2 hours, so grab a fresh one "
                "from the Graph API Explorer and retry")
        long_user = r["access_token"]
        print(f"long-lived user token: ok (~{r.get('expires_in', 0) // 86400} days)")
        pages = _fetch_pages(long_user)
        # Persist it: a half-finished run must not cost another Explorer trip.
        set_env({"FB_LONG_USER_TOKEN": long_user})

    pages = pages or []
    if not pages:
        die("this user administers no Pages — did you regenerate the Explorer token AFTER "
            "ticking pages_show_list?")

    want = (argv[0] if argv else "") or os.environ.get("FB_PAGE_ID", "")
    if want:
        match = [p for p in pages if p["id"] == want]
        if not match:
            die(f"{want} is not among your Pages: "
                + ", ".join(f"{p['name']}={p['id']}" for p in pages))
    elif len(pages) == 1:
        match = pages
    else:
        print("you administer several Pages — pass the id (or set FB_PAGE_ID), then re-run:")
        for p in pages:
            print(f"  ./scripts/fb_api.py token {p['id']}    # {p['name']}")
        return

    p = match[0]
    set_env({"FB_PAGE_ID": p["id"], "FB_PAGE_TOKEN": p["access_token"], "FB_USER_TOKEN": ""})
    print(f"page        : {p['name']} ({p['id']})")
    print(f"tasks       : {', '.join(p.get('tasks', []))}")
    print(f"wrote FB_PAGE_ID + FB_PAGE_TOKEN to {ENV_PATH} (chmod 600)")
    print("the Page token has no expiry; it only dies on password change / de-authorization.")
    print("FB_LONG_USER_TOKEN was kept (~60 days) so switching Pages needs no new Explorer token;")
    print("delete that line if you'd rather not store a user-scoped secret.")
    print("next: ./scripts/fb_api.py check")


def post_id_for(res, tok):
    """Resolve a create-response to the POST id.

    POST /{page}/feed returns the post id directly. POST /{page}/photos returns a
    PHOTO id instead, and the post id only appears as the photo's `page_story_id` —
    so without this the ledger would store ids that can never be read back.
    """
    ident = res.get("id", "")
    if res.get("post_id"):
        return res["post_id"]
    if "_" in ident:                      # already a {page}_{post} id
        return ident
    d = graph(ident, {"fields": "page_story_id", "access_token": tok}, soft=True)
    return (d or {}).get("page_story_id") or ident


def cmd_test_post(argv):
    tok, pid = env("FB_PAGE_TOKEN"), env("FB_PAGE_ID")
    msg = "Testpost via de Graph API — mag verwijderd worden."
    if "--now" in argv:
        res = graph(f"{pid}/feed", {"message": msg, "access_token": tok}, method="POST")
        print(f"published immediately: {res['id']}")
    else:
        when = datetime.now().astimezone() + timedelta(days=2)
        ts = local_ts(when.date(), "10:00")
        res = graph(f"{pid}/feed", {
            "message": msg, "published": "false",
            "scheduled_publish_time": ts, "access_token": tok,
        }, method="POST")
        ledger_note(res["id"], ts, msg)
        print(f"scheduled for {datetime.fromtimestamp(ts).isoformat()}")
        print(f"post id: {res['id']}")
    print("verify: ./scripts/fb_api.py list    delete: ./scripts/fb_api.py cancel <post-id>")


def ledger_load():
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text())
        except ValueError:
            return []
    return []


def ledger_note(post_id, when_ts, text):
    """Record a post we created: there is no API edge that lists scheduled posts."""
    rows = ledger_load()
    rows = [r for r in rows if r.get("id") != post_id]
    rows.append({"id": post_id, "scheduled": when_ts,
                 "text": (text or "")[:120]})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")


def cmd_list():
    tok, pid = env("FB_PAGE_TOKEN"), env("FB_PAGE_ID")

    # Scheduled posts are invisible to every listing edge, so we track ids locally and
    # verify each one against the API. (`/{page-id}/feed` would list them, but it needs
    # Page Public Content Access; `/{page-id}/posts` returns only published posts.)
    rows = [r for r in ledger_load() if r.get("id", "").startswith(f"{pid}_")]
    print(f"scheduled (tracked locally in {LEDGER.relative_to(BASE)}, verified against the API):")
    if not rows:
        print("  (none)")
    for r in sorted(rows, key=lambda x: x.get("scheduled") or 0):
        d = graph(r["id"], {"fields": "is_published,scheduled_publish_time,message",
                            "access_token": tok}, soft=True)
        if d is None:
            print(f"  GONE      {r['id']}  (deleted, or no longer visible)")
            continue
        ts = d.get("scheduled_publish_time") or r.get("scheduled")
        when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "-"
        state = "published" if d.get("is_published") else "SCHEDULED"
        text = (d.get("message") or r.get("text") or "").replace("\n", " ")[:50]
        print(f"  {state:9} {when:16} {r['id']}  {text}")

    print("\nrecent published (times shown in your local timezone):")
    pub = graph(f"{pid}/posts", {
        "fields": "id,message,created_time", "limit": "5", "access_token": tok,
    }, soft=True)
    if pub is None:
        print("  (could not read /posts)")
    for p in (pub or {}).get("data", []):
        # created_time is UTC; convert or the displayed hour is misleading.
        try:
            when = datetime.fromisoformat(p["created_time"]).astimezone().strftime("%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            when = "?"
        print(f"  {when:16} {p['id']}  "
              f"{(p.get('message') or '').replace(chr(10), ' ')[:50]}")


def cmd_cancel(post_id):
    graph(post_id, {"access_token": env("FB_PAGE_TOKEN")}, method="DELETE")
    rows = [r for r in ledger_load() if r.get("id") != post_id]
    if rows != ledger_load():
        LEDGER.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(f"deleted {post_id}")


def cmd_past_posts(argv):
    """Sync published Page posts into data/past_posts.txt (newest first).

    The old route was a manual Business Suite CSV export piped through
    import_past_posts.py. We already hold a Page token, so just read /posts.
    """
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    tok, pid = env("FB_PAGE_TOKEN"), env("FB_PAGE_ID")
    want = int(opt("--limit", "0"))          # 0 = the whole history

    rows, after = [], None
    while True:
        p = {"fields": "id,message,created_time", "limit": "100", "access_token": tok}
        if after:
            p["after"] = after
        r = graph(f"{pid}/posts", p, soft=True)
        if r is None:
            die("could not read /posts — check FB_PAGE_TOKEN with `check`")
        rows += r.get("data", [])
        after = ((r.get("paging") or {}).get("cursors") or {}).get("after")
        if not after or (want and len(rows) >= want):
            break

    rows = [r for r in rows if (r.get("message") or "").strip()]
    rows.sort(key=lambda r: r.get("created_time", ""), reverse=True)
    if want:
        rows = rows[:want]

    out = BASE / "data" / "past_posts.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(r["message"].replace("\n", " ").strip() for r in rows) + "\n")

    print(f"[ok] {out.relative_to(BASE)}: {len(rows)} posts (newest first)")
    if rows:
        print(f"     newest {rows[0].get('created_time', '')[:10]} "
              f"→ oldest {rows[-1].get('created_time', '')[:10]}")
        print(f"     fb_plan.py sends the {min(10, len(rows))} newest in full, plus a "
              f"{min(400, len(rows))}-post angle digest")


def cmd_schedule(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    dry = "--dry-run" in argv
    tok, pid = (None, None) if dry else (env("FB_PAGE_TOKEN"), env("FB_PAGE_ID"))
    if not dry:
        (BASE / "done").mkdir(parents=True, exist_ok=True)   # gitignored: may not exist
    start = date.fromisoformat(opt("--start", (date.today() + timedelta(days=1)).isoformat()))
    every = int(opt("--every", "2"))          # every 2nd day
    at = opt("--at", "19:05")                 # matches this Page's existing cadence
    posts = sorted((BASE / "approved").glob("post_*.json"))
    if not posts:
        print("nothing in approved/ — run ./approve first")
        return

    for i, f in enumerate(posts):
        d = date.fromordinal(start.toordinal() + i * every)
        ts = local_ts(d, at)
        days_out = (ts - int(datetime.now().timestamp())) / 86400
        if days_out > MAX_DAYS_AHEAD:
            fits = max(0, int((MAX_DAYS_AHEAD * 86400 - (local_ts(start, at) - int(datetime.now().timestamp())))
                              / (every * 86400)) + 1)
            die(f"{f.name} would land {days_out:.1f} days out, past Meta's {MAX_DAYS_AHEAD}-day "
                f"limit (enforced, not the 30 the docs claim).\n"
                f"       Only {fits} post(s) fit from --start {start} at --every {every} "
                f"(--at {at}). Use a later start, or schedule this batch in two runs.")
        data = json.loads(f.read_text())
        num = f.stem.split("_")[1]
        img = BASE / "images" / f"{num}.png"
        print(f"[{'dry ' if dry else 'ok  '}] {d} {at}  post_{num}"
              f"{'  +' + img.name if img.exists() else '  (text only)'}")
        if dry:
            continue
        fields = {"message": data["post"], "published": "false",
                  "scheduled_publish_time": ts, "access_token": tok}
        if img.exists():
            res = graph(f"{pid}/photos", fields, files={"source": img})
            post_id = post_id_for(res, tok)
        else:
            res = graph(f"{pid}/feed", fields, method="POST")
            post_id = res["id"]
        ledger_note(post_id, ts, data["post"])
        print(f"        -> {post_id}")
        f.rename(BASE / "done" / f.name)

    if dry:
        print("\n--dry-run: nothing sent, nothing moved")
    else:
        print(f"\nscheduled {len(posts)} post(s); moved to done/")
        print("confirm with: ./scripts/fb_api.py list")


if __name__ == "__main__":
    load_dotenv(ENV_PATH)
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        raise SystemExit(0)
    cmd, rest = args[0], args[1:]
    if cmd == "check":
        cmd_check()
    elif cmd == "token":
        cmd_token(rest)
    elif cmd == "test-post":
        cmd_test_post(rest)
    elif cmd == "list":
        cmd_list()
    elif cmd == "cancel":
        cmd_cancel(rest[0] if rest else die("usage: cancel POST_ID"))
    elif cmd == "schedule":
        cmd_schedule(rest)
    elif cmd == "past-posts":
        cmd_past_posts(rest)
    else:
        die(f"unknown command {cmd!r} — try --help")
