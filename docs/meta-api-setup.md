# Auto-posting via the Meta Graph API — verified setup path

**Verdict: yes, it still works.** Scheduling Page posts through the Graph API is fully
supported in 2026 (current API version: `v26.0`). Nothing about Page publishing was
removed — it is *hidden behind the new use-case UI*, which is why the old tutorials fail.

**You do not need App Review, and you do not need Business Verification**, as long as the
app is only ever used by you (someone with a role on the app, or a role in the business
portfolio connected to it). That is the whole trick.

Source of truth (all fetched 2026-10-14, doc "Updated" dates noted):

| Doc | Updated | What it proves |
| --- | --- | --- |
| [Pages API – Posts](https://developers.facebook.com/docs/pages-api/posts) | Apr 17, 2026 | `POST /{page-id}/feed` + `published=false` + `scheduled_publish_time` still documented |
| [Pages API – Get started](https://developers.facebook.com/docs/pages-api/getting-started) | Jun 30, 2026 | End-to-end post flow, Graph API `v26.0` |
| [Access Levels](https://developers.facebook.com/docs/graph-api/overview/access-levels) | — | Standard access = role users only ⇒ no review needed for self-use |
| [Create an App](https://developers.facebook.com/docs/development/create-an-app) | — | "App Review … is required if your app will be used by people without a role on your app or a role on the business that is connected to your app." |
| [Pages use case](https://developers.facebook.com/docs/development/create-an-app/pages-use-case) | — | `pages_manage_posts` is **optional**, must be added manually |
| [Long-lived tokens](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived) | Jun 30, 2026 | Long-lived Page tokens "do not have an expiration date" |
| [App Types](https://developers.facebook.com/docs/development/create-an-app/app-dashboard/app-types) | May 5, 2025 | Business apps have no app modes, only access levels |
| [App Review process](https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review) | — | "If your app will only be used by app users who have a role on the app itself, App Review is not required." |
| [Business Verification](https://developers.facebook.com/docs/development/release/business-verification) | — | "If your app will only be used by app users who have a role on the app itself you do not need to complete verification" |
| [App Modes](https://developers.facebook.com/docs/development/build-and-test/app-modes) | — | Development-mode posts are only visible to role users — see Step 2b |

---

## Why the old workflow "doesn't exist anymore"

| Old world | Now (2026) |
| --- | --- |
| Add a **Product** (e.g. "Facebook Login") in the sidebar | Products are gone. You pick **use cases** at app creation; they bundle products + permissions |
| Permissions listed openly under App Review → Permissions | Permissions live inside **Customize *<use case>***; only *required* ones show by default |
| Add `manage_pages` / `publish_pages` | Long dead. `pages_manage_posts` is the current permission |
| App type chosen in a dropdown | App type is inferred from the use case, and **cannot be changed afterwards** |
| Development/Live toggle | **Business apps have no app modes at all** — access levels replace them |

The permission you need is simply not in the default list. That is the single most common
reason people conclude "Meta removed it".

---

## Step 1 — Create the app

1. Go to <https://developers.facebook.com/apps/creation/>.
2. App name + contact email → **Next**.
3. **Use cases:** select **"Manage everything on your Page"**
   ("Publish content and videos, moderate posts and comments from followers on your Page
   and get insights on engagement.").
4. **Business:** connect your Business portfolio (the one that owns/claims
   `constructief-bouw.be`'s Page). Verified is *not* required for this use case.
5. Requirements → Next → **Go to dashboard**.

Do **not** pick "Authenticate and request data from users with Facebook Login" — it is
incompatible with the Pages use case and is greyed out anyway.

## Step 2 — Add the permission that is hiding

This is the step everything hinges on.

1. Dashboard → select **Manage everything on your Page** → **Customize**.
2. You will see only three permissions, added automatically and not removable:
   `business_management`, `pages_show_list`, `public_profile`.
3. Click **Add** next to:
   - **`pages_manage_posts`** ← the one that actually publishes
   - **`pages_read_engagement`**
   - optionally `pages_manage_engagement`, `pages_manage_metadata`
4. **Ready to test** → this unlocks the Graph API Explorer against this app.

The rendered mapping table (it renders empty in the plain-text doc view) confirms the split
exactly — for *Manage everything on your Page*:

| | Permissions |
| --- | --- |
| **Required** (auto-added, not removable) | `business_management`, `pages_show_list`, `public_profile` |
| **Optional** (must click **Add**) | `email`, Page Mentions, `pages_read_engagement`, `pages_read_user_content`, **`pages_manage_posts`**, `pages_manage_engagement`, `pages_manage_metadata`, `read_insights`, … |

**`pages_manage_posts` declares `pages_read_engagement` and `pages_show_list` as
dependencies.** Omit `pages_read_engagement` and publishing breaks on an otherwise-perfect
token (symptoms: error 283 or `(#200)`).

> **Careful — Meta's own docs contain two permission names that do not exist.**
> The [Pages API get-started page](https://developers.facebook.com/docs/pages-api/getting-started)
> tells you to select `pages_manage_read_engagement`, and the
> [Posts page](https://developers.facebook.com/docs/pages-api/posts) says
> `pages_read_user_engagement`. Neither appears anywhere in the Permissions Reference.
> The real names are `pages_read_engagement` and `pages_manage_engagement`. If you searched
> for those typo'd names and found nothing, that's why.

Leave access levels at **Standard**. Do not click "Get Advanced Access" — that is what
triggers App Review *and* Business Verification, and you do not need either.

## Step 2b — Do NOT skip: go Live, or your posts are invisible

This is the trap that convinces people the whole thing is broken, and it fails *silently*.

Per [App Modes](https://developers.facebook.com/docs/development/build-and-test/app-modes):

> "**Any data generated while an app is in Development mode, such as test posts, can only be
> seen by role users.** However, that data will be visible to non-role users once the app is
> switched to Live mode."

So while the app is in Development mode, **the API calls succeed and your posts really do
publish — but only you can see them.** No error, no warning. A
[first-hand 2026-10-09 report](https://github.com/cobrasmashbc/Cobrasmash/issues/39) describes
exactly this ("publishes … successfully, but nobody can see the posts"), resolved by going
Live — with the useful detail that **the posts became publicly visible retroactively, and did
not need reposting.** The same report confirms the encouraging part: "No App Review was
needed — posting to the club's own Page with a Page token works under Standard Access.
Going Live only required Settings → Basic to be complete."

To go Live, fill in **Settings → Basic** — app icon, category, Privacy Policy URL, Data
Deletion URL, and **App Purpose set to "Yourself or your own business"** (not "Clients") —
then use **Publish → Go live**. For use-case apps the dashboard exposes "Go live" rather
than a Development/Live toggle.

> **Honest caveat — Meta's docs are internally inconsistent here.** The App Types page says
> "Business apps **do not have app modes** and instead rely exclusively on access levels",
> while the App Modes page documents the Development/Live visibility rule above, and the
> use-case dashboard has a "Publish → Go live" button. Which one governs your app is not
> something I could resolve from the docs alone. **Practical rule: open your dashboard, look
> for a "Go live" button, and if it exists, click it** (after Settings → Basic is complete).
> If your posts publish successfully but are invisible when you check the Page logged out,
> this is the cause. Worst case you've wasted one click.

Two cautions:

- **Verify posting works *before* going Live.** Meta warns that switching prematurely
  "may make your app unusable for users who have a role on your app".
- **Going Live may trigger an annual Data Use Checkup** obligation. It's dormant for
  Standard Access apps in Development mode, so it only appears once you publish.


## Step 3 — Mint a never-expiring Page token

In the [Graph API Explorer](https://developers.facebook.com/tools/explorer):

1. Top right: select your app.
2. **User or Page** dropdown → **Get User Access Token** → tick
   `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `business_management`.
3. `GET /me/accounts` → find your Page → copy its `id` and `access_token`.
   Confirm `tasks` contains `CREATE_CONTENT`.
   *(The token in this response is short-lived — do not stop here.)*

Then, server-side, exchange it for a token that never expires:

```bash
# 1. short-lived user token -> long-lived user token (~60 days)
curl -s "https://graph.facebook.com/v26.0/oauth/access_token?grant_type=fb_exchange_token&client_id=$APP_ID&client_secret=$APP_SECRET&fb_exchange_token=$SHORT_USER_TOKEN"

# 2. long-lived user token -> long-lived PAGE token (no expiry)
curl -s "https://graph.facebook.com/v26.0/me/accounts?access_token=$LONG_LIVED_USER_TOKEN"
```

The `access_token` in the second response is the Page token. Per Meta's docs it
"do[es] not have an expiration date" and is only invalidated by a password change, losing
your Page role, removing the app, etc. Store it in `.env` as `FB_PAGE_TOKEN`, never in git.

**Do not use `/me/accounts` with a user token from the Explorer for the cron job** — that
one dies within hours, which is the second most common reason people think it's broken.

### Alternative: Business Manager System User — usually a dead end here

A System User token is the *architecturally* nicer option (no human in the loop, so a
password change can't silently kill your cron). `pages_manage_posts` is an explicitly
supported system-user scope, and you assign the Page via
`POST /{PAGE_ID}/assigned_users` with `tasks=['CREATE_CONTENT']`.

**But check the gate before investing time in it:** per
[System Users → Overview](https://developers.facebook.com/docs/business-management-apis/system-users/overview),
"To create a system user access token, this app must have **Standard Access**", and
"Only apps with **Ads Management API standard access and above** can be installed."

So a plain Pages-only app that has never touched the Marketing API may **not be able to
install itself onto a system user at all**. Also required: the system user and the app must
belong to the *same* business portfolio, the Page must be an asset of that portfolio,
`appsecret_proof` on the token call, and Standard tier caps you at **1** system user
(Advanced: 10). Employee system users must be granted each asset individually.

Meta now also marks expiring system-user tokens as **"Recommended"** and warns that "some
businesses must use expiring tokens. If this requirement applies to your business, omitting
this parameter or setting it to `false` results in an error" — i.e. permanent system-user
tokens look like they're being staged out.

**For a single self-owned Page, the long-lived Page token above is the simpler path.**
Revisit System Users only if this grows into multi-Page or multi-client work.

## Step 4 — The publishing calls

Text post, scheduled:

```bash
curl -X POST "https://graph.facebook.com/v26.0/{page-id}/feed" \
  -d "message=Post text" \
  -d "published=false" \
  -d "scheduled_publish_time=$(date -d '+2 days 10:00' +%s)" \
  -d "access_token=$FB_PAGE_TOKEN"
```

Photo post, scheduled (`POST /{page-id}/photos`, `source` = binary upload or `url`).
Note the `/photos` reference states no window, and that `temporary` photos
"`published` must be false, and you can't set `scheduled_publish_time`" — use normal uploads:

```bash
curl -X POST "https://graph.facebook.com/v26.0/{page-id}/photos" \
  -F "source=@images/02.png" \
  -F "message=Caption" \
  -F "published=false" \
  -F "scheduled_publish_time=$(date -d '+2 days 10:00' +%s)" \
  -F "access_token=$FB_PAGE_TOKEN"
```

Verify / cancel:

```bash
curl -s "https://graph.facebook.com/v26.0/{page-id}/feed?fields=id,message,is_published,scheduled_publish_time&access_token=$FB_PAGE_TOKEN"
curl -X DELETE "https://graph.facebook.com/v26.0/{post-id}?access_token=$FB_PAGE_TOKEN"
```

### ⚠️ Gotcha: `GET /{page-id}/feed` fails — use `/{page-id}/posts`

**Meta's own get-started guide tells you to verify a post with
`GET /{page-id}/feed`. That call fails** with Standard Access:

```
(#10) This endpoint requires the 'pages_read_engagement' permission or the
'Page Public Content Access' feature.
```

This is misleading: the token genuinely *has* `pages_read_engagement` (confirmed via
`debug_token`). Verified on a real 2026 Page across **v21.0, v23.0, v25.0 and v26.0** — it
fails on all of them, with both a Page token and a user token. It is not a version
regression.

The reason is logical once you see it: **`/feed` includes posts by *other people* on your
Page**, which is what the broader "Page Public Content Access" entitlement gates.
`/{page-id}/posts` returns only posts the Page itself created, and works fine:

```bash
curl -s "https://graph.facebook.com/v26.0/{page-id}/posts?fields=id,message,created_time&limit=10&access_token=$FB_PAGE_TOKEN"
```

**But note the second half of the trap: `/posts` and `/published_posts` return only
*published* posts.** A scheduled post appears in neither, and there is no
"list my scheduled posts" edge available here. Reading an individual post *does* work, so
scheduled posts must be tracked by ID:

```bash
curl -s "https://graph.facebook.com/v26.0/{post-id}?fields=is_published,scheduled_publish_time,message&access_token=$FB_PAGE_TOKEN"
```

`fb_api.py` therefore keeps a local ledger (`done/scheduled_posts.json`, gitignored) and
verifies each ID against the API. Writing a post works fine — only reading the bulk feed
is gated.

If you ever add video: Facebook no longer supports regular feed video via the API — videos
publish as **Reels**. This applies to every tool, including Business Suite, so it's a platform
constraint rather than something your integration can avoid. Text + image posts (this
pipeline's output) are unaffected.

### Scheduling window — measured, not documented

Meta's docs contradict themselves, so this was **measured against a live Page on 2026-10-14**:

| `scheduled_publish_time` | Result |
| --- | --- |
| now + 28.75d … +29.00d | **accepted** |
| now + 29.01d | **rejected** — `(#100) The specified scheduled publish time is invalid` |
| now + 30d, 45d, 60d, 75d, 90d, 180d | rejected |

**The real limit is exactly 29 days from the moment of the request.** The documented figures
are all wrong for current practice:

| Source | Stated window | Verdict |
| --- | --- | --- |
| [Pages API – Posts](https://developers.facebook.com/docs/pages-api/posts) (Updated Apr 17, 2026) | "between 10 minutes and **30 days**" | ❌ 30d rejected |
| [Page Feed reference](https://developers.facebook.com/docs/graph-api/reference/page/feed) | "between 10 minutes and **75 days**" | ❌ stale |
| [Page Videos reference](https://developers.facebook.com/docs/graph-api/reference/page/videos) | "between 10 mins and **6 months**" | untested |

**Because the limit is a rolling 29 days from when you *run* the command, but posts land at a
fixed clock time, the batch size depends on the gap between those two hours.** Posting at
19:05 and starting tomorrow: 14 posts fit; the 15th would land 29.2 days out. Start today, or
post at 10:00, and the 15th fits. `fb_api.py` refuses over-limit batches and reports how many
posts actually fit.

**The lower bound is a real 10 minutes**, so a post can't go out instantly by scheduling —
use `published=true` for that.

### Alternative worth considering: schedule app-side, not API-side

### Alternative worth considering: schedule app-side, not API-side

Instead of `published=false` + `scheduled_publish_time`, let cron wake up on the day and
post with `published=true`. You trade "survives my laptop being off" for:

- no 30-vs-75-day ambiguity to reason about
- real, immediate error feedback per post, plus your own retry logic
- identical mechanics if you ever add Instagram — the IG Content Publishing API has **no**
  `scheduled_publish_time` parameter at all; Meta's own guidance there is "we recommend that
  your app also enforce the publishing rate limit, especially if your app allows app users
  to schedule posts to be published in the future"

Pick API-side scheduling if the machine isn't reliably on; API-side + a read-back of
`scheduled_publish_time` after creation is a good hedge either way.

---

## Gating: do I need App Review?

No — and this is worth stating precisely, because the dashboard's wording is scary.

- **Standard Access** permissions "can only be requested from app users who have a
  [role] on the requesting app". You are the admin ⇒ Standard Access is sufficient.
- **Advanced Access** (anyone, including non-role users) requires Business Verification
  plus, in some cases, App Review.
- Meta's Create an App doc: App Review "is required if your app will be used by people
  without a role on your app or a role on the business that is connected to your app."

So: while this stays a *personal posting bot for your own Page*, you are permanently in the
no-review lane. The moment a client or colleague without an app/business role needs to
authorise it, you need Advanced Access + Business Verification (and "Tech Provider" for
other businesses' assets).

**There is a third gate you'd otherwise trip over: Access Verification**, which lists
`pages_manage_posts` among its triggers. It exempts you at the mechanism level —
"If the person **does** have a role on the app, the endpoint accepts the call and continues
processing the request." It only applies to apps claimed by a business, so if you never
connect a business portfolio it does not apply at all.

**Consumer app type can't generate access tokens** — if you ever see that option, don't take
it. And app types and use cases **cannot be changed after creation**, so a wrong pick means
creating a new app from scratch.

## Gotchas checklist

- [ ] `pages_manage_posts` added via **Customize** (not visible by default)
- [ ] `pages_read_engagement` also added — `pages_manage_posts` depends on it
- [ ] **Went Live** (Publish → Go live) — otherwise posts publish but only you can see them
- [ ] Settings → Basic complete; **App Purpose = "Yourself or your own business"**
- [ ] Using the **Page** token, not the user token (Explorer: "User or Page" dropdown)
- [ ] Page `tasks` includes `CREATE_CONTENT` — you must have a role on the Page
- [ ] Token exchanged to long-lived, stored in `.env`; `Expires` reads `Never` in the
      [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/)
- [ ] API version pinned explicitly (`v26.0` in the URL path — never rely on the default)
- [ ] Schedule ≤ 29 days out (the real limit; docs claim 30 and 75)
- [ ] Don't let the app go **90 days idle** — an Inactive app has "all access tokens
      associated with the app … invalidated", and permissions removed for disuse must go
      back through App Review. This pipeline's 2-day cadence is fine; a dormant quarter is not
- [ ] Rate limits: non-issue. Pages API with a Page token is
      `4800 × engaged users` calls/24h — even 10 engaged users gives 48,000.
      Only error-code `190` (bad token) / `32` (page limit) / `4` / `17` handling is needed
- [ ] **Deadline 2026-10-27:** v26.0 deprecates the `pretty`, `debug`, and `date_format`
      query params, root `GET /?ids=`, and ETag / `If-None-Match`. This applies to *all*
      remaining versions on that date. `debug_token` is unaffected, so it's still your
      token-inspection tool

## What was actually removed (so you don't chase ghosts)

- **Graph API version death is silent and fast.** ~4-month release cadence, ~2-year support,
  ~6 versions alive at once. As of October 2026, **v18.0, v19.0 and v20.0 are already dead.**
  Pin the version; a dead one returns errors with no advance warning.
- Page/Post **Insights** metrics: `page_impressions_*`, `page_posts_impressions*`,
  `post_impressions*`, `page_video_views_unique` are deprecated per the v25/v26 changelogs
  (replaced by `page_media_view`, `page_total_media_view_unique`, `post_media_view`).
  The `metadata=1` query param is also deprecated.
- Legacy Page fields `current_location`, `genre`, `network`, `parking`, `start_info` and the
  `auto_publish_page_info_updates` setting error out on v26.0+ for New Pages Experience.
- `manage_pages` / `publish_pages` — gone since 2020.
- The old "Products" sidebar and the app-type dropdown — replaced by use cases.

Publishing itself: untouched. **No documented change to `POST /{page-id}/feed` publishing
semantics anywhere in the v23–v26 changelogs.**

### Token failures are silent by design

From Meta's error-handling doc: "**Facebook will not notify you that an access token has
become invalid.** Unless you have sent the `expiry` time to your app along with the access
token, your app may only learn that a given token has become invalid when you attempt to
make a request to the API." Also: "access tokens may be invalidated before the expected
expiration time" due to security events.

So call `GET /debug_token` at the start of each run and fail loudly. Subcodes to catch:
`460` (password change / logout), `458` (de-authorized), `463` (session expired).

## "Meta killed use-case apps" — a misdiagnosis worth knowing about

You'll find confident 2026 write-ups concluding use cases are broken and you should create an
app *without* one. One widely-cited example is a merged
[Postiz docs PR](https://github.com/gitroomhq/postiz-docs/pulls/241) reporting that
"apps created through a use case cannot request the permissions Postiz needs; the OAuth dialog
fails immediately with 'Invalid Scopes'".

That test used the **"Authenticate and request data from users with Facebook Login"** use case
— which, per the mapping table above, only ever offers `public_profile` and `user_*`
permissions. It never offered `pages_manage_posts` at all, so the scope failure was expected,
not a wizard defect.

The lesson generalizes: **the use case you pick determines which permissions exist for your
app.** Pick the Page one and `pages_manage_posts` is right there in the optional list. This is
the single most common reason people conclude the capability was removed — that, plus Meta's
own two phantom permission names in the Pages docs, plus the invisible-posts Development-mode
trap.

## Alternatives, if you'd rather not own a Meta app at all

Worth knowing before you commit, because **owning the app means owning token hygiene,
version upgrades, and the 90-day-inactivity rule forever.**

**The key structural fact: essentially no third-party scheduler offers a "bring your own Meta
app" model for Facebook.** They hold App Review and Business Verification themselves; you just
OAuth-connect the Page. The sole exception is Make's White Label track, which *requires* your
own reviewed app. So using a vendor means you skip the entire App Review question — but you
also don't control the integration.

For a small Belgian business, EU data posture matters more than for a US one:

| Option | Cost | API | EU posture |
| --- | --- | --- | --- |
| **Buffer** | **Free tier** — API works on every plan including Free | GraphQL, self-serve token | US storage; DPF-certified + Irish DataRep; **no public DPA found** |
| **Publer** | **~$10/mo** (Business) | REST | 🇩🇪 **Frankfurt servers**, self-serve DPA, Art. 27 EU rep — best of the set |
| **Metricool** | **€43/mo** (Advanced) | REST | 🇪🇸 All data in the EU, "does not carry out international data transfers" |
| **Ayrshare** | $149/mo | REST | US; BYO-keys is X-only since Mar 2026 |
| **Later** | $18.75/mo+ | ❌ **No scheduling API** | Disqualified for programmatic use |

**Recommendation if you go this route: Publer Business (~$10/mo)** — cheapest real REST
scheduling API, and the cleanest GDPR story of the set. **Buffer Free** is the cheapest
experiment if US storage is acceptable.

Also note: **Buffer retires its legacy REST API on 2027-02-01**, with brownouts on
2026-11-11 and 2026-12-09, and new legacy clients are already closed — build on the GraphQL API.

### Why not just automate the browser?

Because the exposure is your Page and your business portfolio, not a fine. Meta's ToS §3.2.3
bars accessing data "using **automated means** (without our prior permission) … **regardless of
whether such automated access … is undertaken while logged-in to a Facebook account**", and
the [Automated Data Collection Terms](https://www.facebook.com/legal/automated_data_collection_terms)
state that accepting those terms "**does not constitute the required written permission**".
Platform Terms §7.e.ii permits enforcement "**with or without notice**", including suspension.

To be precise and fair: **no clause prohibits "browser automation" in those words**, and §3.2.3
is framed around *collecting data* rather than *posting* — so the case against automating
Business Suite is strong but inferential. Realistic worst case is Business Manager / Page admin
restriction, with appeal through Meta's own slow review. That's a bad trade against ~$10/mo,
which is why the official API (or a vendor holding the review) is the sane path.

