# RECON.md — Threads reconnaissance findings

Historical note: this document records the original 26 October reconnaissance. References to `recon.py`, old exploratory queries, and root-level parser paths describe that run; the throwaway reconnaissance script is no longer part of the active code. The current collection implementation is under `collection/`.

Run: 26 Oct 2026, ~20:00–20:10 WIB, Account A (`profiles/account_a`), `recon.py` defaults.
Captured: 781 GraphQL responses (780 × HTTP 200, 1 × 502 on an unrelated promo query), 10 page sources, 13 embedded JSON blobs. All raw data is in `./recon/` (gitignored).

Pages visited: Top + Recent for `anggaran MBG`, `makan bergizi gratis`, `MBG 2027` (10 scrolls each), a "deep" Recent run of `anggaran MBG`, and 3 post pages (10 scrolls each).

## 1. Verdict on the "how Threads works" assumptions

| Assumption | Verdict |
|---|---|
| React SPA, obfuscated classes | **Confirmed**. We never needed the DOM. |
| Data in `<script type="application/json">` on first load | **Confirmed**. Path prefix: `require[0][3][0].__bbox.require[0][3][1].__bbox.result.data` |
| GraphQL POSTs while scrolling | **Confirmed**. Endpoint `POST https://www.threads.com/graphql/query`, form-encoded, `doc_id` + `variables` (JSON) + `fb_api_req_friendly_name`. No `for (;;);` prefix seen. |
| `thread_items -> post` | **Confirmed** for search results (`thread.thread_items[].post`). Post pages use a different shape (see §3). |
| `pk`, `code`, `caption.text`, `taken_at`, `like_count`, `user.username` | **Confirmed**. Reply/repost/quote counts are under `text_post_app_info`. |
| `/search?q=` needs login | **Confirmed** (we were logged in; logged-out behavior not tested). |
| Recent via `filter=recent` | **Confirmed**: `&filter=recent` → `variables.recent = 1`. Top (no filter) → `recent = 0`. |
| No date filter, scroll Recent and cut on `taken_at` | **Confirmed**. Recent is strictly newest-first (100% monotonic on the matched posts). |
| Post page shows nested replies + self-thread | **Partly**. Replies are in chains; nested replies are truncated (needs extra fetches). Self-thread has its own container, but it was empty on all 3 posts, so **not observed**. |

**New and important: Recent search returns mostly replies, not root posts.** About 80% of Recent results are replies that contain the keyword, shown together with their parent. Top returns root posts only.

## 2. Requests that matter

All other ~70 query types are UI noise (screen-time, notifications, messages, side nav).

| friendly_name | doc_id (26 Oct) | Carries |
|---|---|---|
| `BarcelonaSearchResultsRefetchableQuery` | `28826209087035478` | search results, pages 2..N |
| *(embedded, first load of /search)* | – | search results, page 1 (`data.searchResults`) |
| `BarcelonaPostPageDirectRepliesRefetchQuery` | `29021675817426421` | replies, pages 2..N |
| *(embedded, first load of a post page)* | – | blob `_00`: the root post (`data.media`); blob `_01`: first replies (`data.media.text_post_app_info.direct_replies`) |
| `useBarcelonaBatchedDynamicPostCountsSubscriptionQuery` | `39332564219721461` | live count updates. Ignore; take counts from the result objects. |

`doc_id`s change when Threads deploys, so the scraper must match on `friendly_name`, never on `doc_id`.

### Search pagination
- `variables`: `query`, `recent` (0/1), `search_surface:"default"`, `first:10`, `after:"<session-hex>:<page#>"`.
- Response: `data.searchResults.edges[].node.thread` plus `data.searchResults.page_info {end_cursor, has_next_page}`.
- The cursor is just a search-session ID plus an incrementing page number (`…:1`, `…:2`, …). There are 10 results per page, and `has_next_page` was still `true` when we stopped on every query.

### Reply pagination
- `variables`: `postID` (root pk), `first:4`, `after:<base64 cursor>`, `sortOrder:"TOP"`, `filterType:null`.
- Response: `data.media.text_post_app_info.direct_replies.edges[]` plus `direct_replies.page_info {end_cursor, has_next_page}`.
- Only 4 reply chains come back per request, about 20 replies per scroll.

## 3. JSON paths → output schema

Let `P` = a post object: `searchResults.edges[].node.thread.thread_items[i].post` (search), `data.media` (root on a post page), or `direct_replies.edges[].node.posts.edges[j].node` (reply).

| Column | Source |
|---|---|
| `unit_id` | `P.pk` (numeric string, e.g. `4016458748334752908`). Not `P.id`, which is `pk_userid` and embeds the user ID. |
| `text` | `P.caption.text`. `caption` can be `null` (media-only posts), which gives empty text. |
| `created_at_*` | `P.taken_at` (unix seconds, UTC) |
| `like_count` | `P.like_count` |
| `reply_count` | `P.text_post_app_info.direct_reply_count` |
| `repost_count` / `quote_count` | `P.text_post_app_info.repost_count` / `.quote_count` |
| `permalink` | `https://www.threads.com/@{P.user.username}/post/{P.code}`. **Contains the username, see §7 Q3.** |
| `author_hash` | `sha256(salt + P.user.username)` |
| reply flag | `P.text_post_app_info.is_reply` |
| self-thread position | `P.text_post_app_info.self_thread_info {self_thread_length, post_position_in_self_thread}` |
| root author | `P.text_post_app_info.root_post_author.username` (on replies) |

### parent_id / root_id

**There is no parent ID field.** Only `reply_to_author` (a username) is present, so the parent is inferred from position:
- **Post page:** each `direct_replies.edges[].node.posts.edges[]` is a chain.
  - The first post in a chain replies to the page's root post. Checked: 662/662 have `reply_to_author == root_post_author`.
  - Each following post replies to the one before it. Checked: 24/24 have `reply_to_author == previous post's author`.
  - So `parent_id` = the previous post in the chain (or the root), and `root_id` = the page's `postID`.
- **Recent search:** `thread_items` holds 1 or 2 items. The **matched post is always the last item**: 100% contain every query term, versus ~5% for the first item.
  - With 2 items, item 0 is its parent, so `parent_id = items[-2].post.pk`.
  - `root_id` is not known from search alone when the parent is itself a reply (item 0 had `is_reply=true` in ~45% of cases). We'll fill it during the reply crawl, or leave it empty with a flag.
- Parents included only as context (item 0) can be older than 3 Sep or off-topic. **They are not matched units.** I suggest recording only matched items as rows; parents get their own row only if a crawl reaches them.

### Self-threads
- `self_thread_info.self_thread_length` > 1 shows up often in search results (up to 11).
- The post page has `data.media.text_post_app_info.self_thread.posts.edges` (empty on our 3 posts).
- Assumed rule: a reply whose author equals the root author and whose `self_thread_info.id` matches the root's → `self_thread`. This still needs one post with a real self-thread to confirm.

## 4. How far back Recent goes

### Depth probe: `MBG 2027`, Recent, 26 Oct ~20:30 WIB, Account A
Command: `recon.py --deep-only "MBG 2027" --deep-max 250 --out recon/deep_mbg2027`. The stop check is now fixed to use matched items only.

- **250 scrolls loaded 360 search pages and 3,394 matched results**, in 22 min (3.7 s per page). There were 1,103 GraphQL responses, all HTTP 200, with no warnings or block signals.
- **It reached 12 Sep 2026 06:41 UTC and `has_next_page` was still `true`**. We saw no depth cutoff, so reaching 3 Sep is very likely (9 days further), though not proven.
- **Threads mixes newer posts into Recent.** The time-ordered stream is real, but from around result #290 (and steadily after ~18 Sep), roughly 1 result per page is a post from *today*. Those often match only part of the query (e.g. "MBG" without "2027").
  - 1,335 of the 3,394 matched results were these mixed-in posts.
  - They are real search hits, so we keep them (dedup handles repeats).
  - They are always *newer* than the time-ordered stream, never older.
  - **Stop rule:** use the *minimum* matched `taken_at` seen so far, never the last item's date. To guard against a single odd old item, stop only after 2 consecutive pages whose median `taken_at` is before START.
- The real (time-ordered) volume for `MBG 2027`:
  - 12 Sep–24 Oct: **median 29, mean 46 matches per day**.
  - Spike: 30 Sep with 500.
  - The 25–26 Oct numbers below were inflated by the mixed-in posts; the real counts were 45 and 33.
- **Estimate for `MBG 2027` down to 3 Sep:** about 430 pages, about 27 min.
- **Rough Phase 2 sizing:**
  - pages per keyword ≈ (time-ordered matches per day × 54 days) / ~6, since about 6 of every 10 results per page are time-ordered once the mixing starts
  - plus ~4 s per page
  - so a keyword 3× busier than `MBG 2027` ≈ 1,300 pages ≈ 1.5 h

### First recon run (10 scrolls; superseded by the probe above)
The first deep run stopped too early because of a bug in `recon.py`: its stop check looked at *all* posts, including old parents shown as context (a June 2026 parent triggered the stop after 10 scrolls).

What the matched posts showed in that run. **These rates were measured on 26 Oct, a high-volume day, and overstate the typical rate by about 10–20×.**

| Query (Recent) | Matched in ~13–16 pages | Time covered | Rate |
|---|---|---|---|
| `anggaran MBG` | 138 | 5.6 h | ~25 / hour |
| `makan bergizi gratis` | 136 | 9.6 h | ~14 / hour |
| `MBG 2027` | 114 | 67.8 h | ~1.7 / hour |

Extrapolating to 3 Sep (~1,280 h back), *if* today's rate held:
- `anggaran MBG`: ~32k results, about 3,200 pages, about 4.5 h of scrolling.
- `MBG 2027`: ~2,200 results, about 220 pages, about 20 min.

The depth probe above shows these extrapolations were far too high. 26 Oct was a spike; typical days are 10–20× quieter.

## 5. Login walls, rate limits, challenges

- **No** HTTP 429, no challenge/checkpoint page, and no "try again later" text. The HTML files only match those words inside JS bundle code.
- After the manual login there were 2 navigations through `/login/oidc/?code=…` (the Instagram SSO handshake) plus onboarding queries (`BarcelonaOnboardingTermsStepQuery`, `useBarcelonaSetOnboardingMutation`).
- Because of that, the **first search ("Top anggaran MBG") landed on the home feed** (embedded `feedData`, not `searchResults`). Top for that query has no usable data.
- Phase 2 lessons:
  - treat `/login/oidc` right after login as normal
  - check every page actually returned `searchResults`
  - treat a plain `/login` redirect as a stop
- 781 requests in ~10 minutes at 3–7 s delays caused no visible throttling. That's a small sample, not a safety guarantee.

## 6. GraphQL replay vs browser

- Each request needs session-bound tokens: form fields `fb_dtsg`, `lsd`, `jazoest`, `__user`, `__rev`, `__hs`, `__dyn`, …, and headers `X-CSRFToken`, `X-FB-LSD`, `X-IG-App-ID`, `X-ASBD-ID`, plus cookies.
- **Replay from outside the browser (requests/httpx): possible but fragile.** Tokens rotate per page load and `__rev` changes with deploys. It also looks least like a normal user. **Not recommended.**
- **Replay from inside the logged-in page** (`fetch('/graphql/query', …)` via `execute_async_script`, copying the form of the last captured search request and bumping `after`) is feasible and would skip rendering video. It sends the same number of requests, just faster. That's a fallback if scrolling turns out too slow, not the default.
- **Recommended default:** browser scroll plus CDP response interception, exactly as `recon.py` does. It's proven on this run.

## 7. Risks and recommended Phase 2 design

### Risks
1. **Volume.**
   - Broad keywords (`MBG`, `makan bergizi gratis`, `SPPG`) could need thousands of pages each to reach 3 Sep. `MBG` alone will be bigger than `anggaran MBG`.
   - Replies are heavy too: 37 matched posts had more than 500 replies. Post 1 had 4,737 replies, and 10 scrolls got 207 of them.
   - Full coverage of everything is not realistic by 28 Oct.
2. **Depth is likely fine** (12 Sep reached, no cutoff seen), but not proven down to 3 Sep. Newer posts are mixed into the results, so the stop rule must use the minimum date (§4).
3. **Copy-paste campaigns.** The same text was posted repeatedly by different accounts (e.g. 21 duplicates in 136 results for `makan bergizi gratis`; texts like "BGN HITUNG EFISIENSI MBG…"). We keep them raw, but flag it for the analysis team.
4. **Top is fuzzy.** It returns posts that match only some terms, or none, and some from 2024–2025. The date filter handles the old ones; relevance filtering happens later.
5. `doc_id` rotation and SSO/onboarding redirects (§5).

### Recommended design
- **Search:**
  - Recent first: scroll and intercept, keeping only the **last** `thread_items` post.
  - Stop a keyword when the matched `taken_at` < START, when `has_next_page` is false, or when a configurable `MAX_PAGES_PER_KEYWORD` is hit.
  - Then run Top with a small page cap (e.g. 10 pages), for popular posts.
- **Recent-matched replies become units directly** (`unit_type=reply`, `parent_id` from item −2). That alone captures much of the on-topic conversation cheaply.
- **Reply crawl:**
  - Applies to kept root posts with `direct_reply_count > 0`.
  - Open the post page, scroll until `has_next_page` is false or `MAX_REPLY_SCROLLS` is hit (configurable, e.g. 15 ≈ 300 replies).
  - Keep replies with `taken_at ≥ START`.
  - Truncated nested chains (`posts.page_info.has_next_page`) are **not** expanded by default; a flag can turn that on later.
- **Parsing:** pure functions in `parser.py`, keyed on `friendly_name` and the paths above, tested against these recon files.
- **Checkpoint:** per keyword (current cursor page + oldest date) and per crawled post.

## Questions before Phase 2
1. ~~Depth probe~~: done, see §4. Recent reached 12 Sep with more pages still available.
2. **Keyword scope / caps:** given the volume, drop `MBG` alone and `SPPG`, add the budget-specific ones (`25 triliun`, `240,2 triliun`, `RKA BGN 2027`, `Komisi IX BGN`, `anggaran BGN`, `APBN MBG`), and set per-keyword page caps?
3. **Permalink contains the username.** Store it as is, or store `code` only (permalink rebuilt later as `threads.com/post/{code}`, a URL format I haven't checked)?
4. **Parent-only context posts** (item 0 in Recent results): skip them (my default), or store them as rows too?
5. Still needed: the YouTube CSV header, so the columns can be aligned.
