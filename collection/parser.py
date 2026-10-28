"""Threads JSON -> output rows. See docs/history/threads_recon_2026-10-26.md."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
PERMALINK = "https://www.threads.com/t/{code}"  # redirects to /@user/post/code; keeps usernames out of the data
COLUMNS = ["platform", "unit_id", "unit_type", "parent_id", "root_id", "text", "created_at_utc",
           "created_at_wib", "like_count", "reply_count", "repost_count", "quote_count", "permalink",
           "author_hash", "matched_keywords", "search_mode", "scraped_at_utc"]
# team's cross-platform dataset schema (shared with the Reddit collector)
FINAL_COLUMNS = ["content_id", "platform", "text", "created_at", "content_type", "permalink"]


def final_row(row):
    return {"content_id": f"threads:{row['unit_id']}", "platform": row["platform"], "text": row["text"],
            "created_at": row["created_at_utc"], "content_type": "post" if row["unit_type"] == "post" else "reply",
            "permalink": row["permalink"]}


def parse_body(raw):
    """GraphQL bodies may carry a 'for (;;);' prefix or be several JSON docs, one per line."""
    raw = raw.removeprefix("for (;;);").strip()
    try:
        return json.loads(raw)
    except ValueError:
        docs = []
        for line in raw.splitlines():
            try:
                docs.append(json.loads(line))
            except ValueError:
                return raw  # keep unparseable bodies verbatim
        return docs


def find_key(obj, key):
    """Yield every value stored under `key`, at any depth."""
    if isinstance(obj, dict):
        if key in obj:
            yield obj[key]
        for v in obj.values():
            yield from find_key(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from find_key(v, key)


def author_hash(username, salt):
    return hashlib.sha256((salt + (username or "")).encode("utf-8")).hexdigest()


def _username(post):
    return (post.get("user") or {}).get("username")


def unit_type(post):
    tpa = post.get("text_post_app_info") or {}
    if not tpa.get("is_reply"):
        return "post"
    me = _username(post)
    # author continuing their own post: replying to themself on their own root
    if me and me == (tpa.get("reply_to_author") or {}).get("username") == (tpa.get("root_post_author") or {}).get("username"):
        return "self_thread"
    return "reply"


def to_row(post, utype, parent_id, root_id, salt, keyword, mode, scraped_at):
    tpa = post.get("text_post_app_info") or {}
    t = post["taken_at"]
    return {
        "platform": "threads",
        "unit_id": str(post["pk"]),
        "unit_type": utype,
        "parent_id": parent_id or "",
        "root_id": root_id or "",
        "text": (post.get("caption") or {}).get("text") or "",
        "created_at_utc": datetime.fromtimestamp(t, timezone.utc).isoformat(),
        "created_at_wib": datetime.fromtimestamp(t, WIB).isoformat(),
        "like_count": post.get("like_count"),
        "reply_count": tpa.get("direct_reply_count"),
        "repost_count": tpa.get("repost_count"),
        "quote_count": tpa.get("quote_count"),
        "permalink": PERMALINK.format(code=post["code"]),
        "author_hash": author_hash(_username(post), salt),
        "matched_keywords": keyword or "",
        "search_mode": mode,
        "scraped_at_utc": scraped_at,
    }


def search_pages(obj):
    """Each searchResults block in a response -> (matched hits, has_next_page).

    A hit is (post, parent_post_or_None). The matched post is always the LAST thread_item;
    earlier items are context parents and are not hits (dated recon notes).
    """
    pages = []
    for sr in find_key(obj, "searchResults"):
        if not isinstance(sr, dict):
            continue
        hits = []
        for e in sr.get("edges") or []:
            items = ((e.get("node") or {}).get("thread") or {}).get("thread_items") or []
            if items and "taken_at" in items[-1]["post"]:
                hits.append((items[-1]["post"], items[-2]["post"] if len(items) > 1 else None))
        pages.append((hits, bool((sr.get("page_info") or {}).get("has_next_page"))))
    return pages


def search_row(post, parent, salt, keyword, mode, scraped_at):
    utype = unit_type(post)
    if parent is None:
        parent_id = root_id = ""
    else:
        parent_id = str(parent["pk"])
        # root is only known when the parent is itself the root
        root_id = "" if (parent.get("text_post_app_info") or {}).get("is_reply") else parent_id
    if utype == "post":
        root_id = str(post["pk"])
    return to_row(post, utype, parent_id, root_id, salt, keyword, mode, scraped_at)


def matching_queries(text, queries):
    """Queries whose every word occurs in text (case-insensitive). Threads search ORs 3+ word queries, so we AND here.

    shortcut: substring match ("240" also hits "2400", "MBG" hits "#MBG"); fine for recall, the analysis filters relevance.
    """
    t = (text or "").lower()
    return [q for q in queries if all(w in t for w in q.lower().split())]


def reply_chains(obj):
    """Reply chains on a post page: lists of posts, each replying to the previous.

    Also yields the root's self-thread container as one chain. Returns (chains, has_next_page)
    where has_next_page refers to the top-level direct_replies list (None if not present).
    """
    chains, has_next = [], None
    for dr in find_key(obj, "direct_replies"):
        if not isinstance(dr, dict):
            continue
        has_next = bool((dr.get("page_info") or {}).get("has_next_page")) or bool(has_next)
        for e in dr.get("edges") or []:
            posts = [pe["node"] for pe in ((e.get("node") or {}).get("posts") or {}).get("edges") or []]
            if posts:
                chains.append(posts)
    for st in find_key(obj, "self_thread"):
        if isinstance(st, dict):
            posts = [pe["node"] for pe in (st.get("posts") or {}).get("edges") or []]
            if posts:
                chains.append(posts)
    return chains, has_next


def reply_rows(chains, root_pk, salt, scraped_at):
    rows = []
    for chain in chains:
        parent = str(root_pk)
        for post in chain:
            if "taken_at" in post and "pk" in post:
                rows.append(to_row(post, unit_type(post), parent, str(root_pk), salt, "", "reply_crawl", scraped_at))
                parent = str(post["pk"])
    return rows


def merge_rows(rows):
    """Dedupe by unit_id: union matched_keywords, keep first-seen fields, refresh counts from the latest."""
    out = {}
    for r in rows:
        cur = out.get(r["unit_id"])
        if cur is None:
            out[r["unit_id"]] = dict(r)
            continue
        kws = [k for k in cur["matched_keywords"].split(";") if k]
        for k in r["matched_keywords"].split(";"):
            if k and k not in kws:
                kws.append(k)
        cur["matched_keywords"] = ";".join(kws)
        for c in ("like_count", "reply_count", "repost_count", "quote_count"):
            if r[c] is not None:
                cur[c] = r[c]
        for c in ("parent_id", "root_id"):  # a reply crawl can fill links search could not
            cur[c] = cur[c] or r[c]
    return list(out.values())
