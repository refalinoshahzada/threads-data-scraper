"""Collect Threads posts + replies about the MBG 2027 budget. See README.md and docs/collection_pipeline.md.

Flow: for each keyword run Recent then Top search (scroll + intercept GraphQL), then crawl replies of the
kept root posts, most-replied first. Every observation is appended to raw_observations.jsonl; the deduped
CSV/JSONL are rebuilt from it after each keyword and every few posts.
"""
import argparse
import base64
import csv
import hashlib
import json
import logging
import math
import random
import secrets
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from selenium import webdriver

from collection import config
from collection import parser as P

SEARCH_Q = "BarcelonaSearchResultsRefetchableQuery"
REPLIES_Q = "BarcelonaPostPageDirectRepliesRefetchQuery"
STOP_URL_PARTS = ("/challenge", "/checkpoint", "/accounts/suspended", "/accounts/login")
STOP_TEXTS = ("try again later", "coba lagi nanti", "confirm it's you", "konfirmasi bahwa ini anda")
START_TS = config.START_UTC.timestamp()
END_TS = config.END_UTC.timestamp()
log = logging.getLogger("scraper")


class Blocked(Exception):
    pass


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- browser + capture
class Browser:
    def __init__(self, profile):
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={config.PROFILES_DIR / profile}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--lang=id-ID")
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        self.d = webdriver.Chrome(options=opts)
        self.d.execute_cdp_cmd("Network.enable", {"maxTotalBufferSize": 200_000_000,
                                                   "maxResourceBufferSize": 50_000_000})
        self.pending = {}
        self.captured = []  # (friendly_name, variables, response)

    def drain(self):
        for entry in self.d.get_log("performance"):
            msg = json.loads(entry["message"])["message"]
            m, p = msg.get("method"), msg.get("params", {})
            if m == "Network.requestWillBeSent":
                req = p["request"]
                if p.get("type") == "Document":
                    self.check_url(req["url"])
                if "graphql" not in req["url"]:
                    continue
                name = next((v for k, v in req.get("headers", {}).items() if k.lower() == "x-fb-friendly-name"), None)
                if name not in (SEARCH_Q, REPLIES_Q):
                    continue
                post = req.get("postData")
                if post is None and req.get("postDataEntries"):
                    post = "".join(base64.b64decode(e.get("bytes", "")).decode("utf-8", "replace")
                                   for e in req["postDataEntries"])
                if post is None and req.get("hasPostData"):
                    try:
                        post = self.d.execute_cdp_cmd("Network.getRequestPostData",
                                                      {"requestId": p["requestId"]})["postData"]
                    except Exception:
                        post = ""
                try:
                    variables = json.loads(parse_qs(post or "").get("variables", ["{}"])[0])
                except ValueError:
                    variables = {}
                self.pending[p["requestId"]] = (name, variables)
            elif m == "Network.responseReceived":
                status = p["response"]["status"]
                # image/CDN hosts (fbcdn.net) 429 on their own; only Threads itself rate-limiting the account counts
                if status == 429 and (urlparse(p["response"]["url"]).hostname or "").endswith("threads.com"):
                    raise Blocked(f"HTTP 429 (rate limited) on {p['response']['url'][:80]}")
                if p["requestId"] in self.pending and status != 200:
                    log.warning("GraphQL %s returned HTTP %s", self.pending[p["requestId"]][0], status)
            elif m == "Network.loadingFinished" and p["requestId"] in self.pending:
                name, variables = self.pending.pop(p["requestId"])
                try:
                    body = self.d.execute_cdp_cmd("Network.getResponseBody", {"requestId": p["requestId"]})
                except Exception as e:
                    log.warning("lost response body of %s: %s", name, e)
                    continue
                raw = body["body"]
                if body.get("base64Encoded"):
                    raw = base64.b64decode(raw).decode("utf-8", "replace")
                resp = P.parse_body(raw)
                if isinstance(resp, dict) and resp.get("errors"):
                    log.warning("GraphQL %s errors: %s", name, str(resp["errors"])[:300])
                self.captured.append((name, variables, resp))
            elif m == "Network.loadingFailed":
                self.pending.pop(p["requestId"], None)

    def take(self, name, match):
        """Pop captured responses of query `name` whose variables satisfy `match`."""
        self.drain()
        keep, out = [], []
        for c in self.captured:
            (out if c[0] == name and match(c[1]) else keep).append(c)
        self.captured = keep
        return [c[2] for c in out]

    def check_url(self, url):
        # /login/oidc is the normal Instagram SSO handshake after login (dated recon notes).
        if any(s in url for s in STOP_URL_PARTS) or ("/login" in url and "/login/oidc" not in url):
            raise Blocked(f"redirected to {url[:100]}")

    def check_page(self):
        """Called only when a scroll brought nothing new, so post texts rarely trigger it."""
        self.check_url(self.d.current_url)
        text = (self.d.execute_script("return document.body ? document.body.innerText : ''") or "").lower()
        hit = next((t for t in STOP_TEXTS if t in text), None)
        if hit:
            raise Blocked(f"page says '{hit}'")

    def pause(self, lo=config.DELAY_MIN, hi=config.DELAY_MAX):
        end = time.time() + random.uniform(lo, hi)
        while time.time() < end:
            time.sleep(0.5)
            self.drain()

    def open(self, url):
        self.drain()
        self.captured.clear()
        self.d.get(url)
        self.pause()
        self.check_url(self.d.current_url)

    def scroll(self):
        self.d.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        self.pause()

    def embedded(self, marker):
        blobs = self.d.execute_script(
            "return [...document.querySelectorAll('script[type=\"application/json\"]')]"
            ".map(s => s.textContent).filter(t => t.includes(arguments[0]))", marker)
        out = []
        for b in blobs:
            try:
                out.append(json.loads(b))
            except ValueError:
                pass
        return out

    def ensure_login(self):
        self.d.get(config.BASE_URL + "/")
        time.sleep(4)
        if self.d.get_cookie("sessionid"):
            return
        try:
            input("\nNot logged in. Log in manually in the Chrome window, then press Enter here... ")
        except EOFError:
            raise Blocked("not logged in and no terminal to wait in; run once in an interactive terminal")
        self.d.get(config.BASE_URL + "/")
        time.sleep(4)
        if not self.d.get_cookie("sessionid"):
            raise Blocked("still no sessionid cookie after manual login")


# ---------------------------------------------------------------- storage
class Store:
    def __init__(self, data_dir, resume):
        self.state_path = data_dir / "state" / "checkpoint.json"
        self.raw_path = data_dir / "output" / "raw_observations.jsonl"
        self.csv_path = data_dir / "output" / "threads_raw.csv"
        self.jsonl_path = data_dir / "output" / "threads_raw.jsonl"
        self.dataset_path = data_dir / "output" / "threads_dataset.csv"
        for p in (self.state_path, self.raw_path):
            p.parent.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists() and not resume:
            sys.exit(f"{self.state_path} exists. Use --resume to continue, or move state/ and output/ away to start over.")
        self.state = (json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists()
                      else {"search_done": {}, "replies_done": []})
        self.raw = self.raw_path.open("a", encoding="utf-8")

    def append(self, rows):
        for r in rows:
            self.raw.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.raw.flush()

    def save_state(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.state_path)

    def merged(self):
        self.raw.flush()
        with self.raw_path.open(encoding="utf-8") as f:
            return P.merge_rows(json.loads(line) for line in f if line.strip())

    def export(self):
        rows = self.merged()
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=P.COLUMNS)
            w.writeheader()
            w.writerows(rows)
        with self.jsonl_path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with self.dataset_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=P.FINAL_COLUMNS)
            w.writeheader()
            w.writerows(P.final_row(r) for r in rows)
        return len(rows)


def in_window(row):
    return START_TS <= datetime.fromisoformat(row["created_at_utc"]).timestamp() < END_TS


# ---------------------------------------------------------------- phases
def load_queries(path):
    """Lines 'team query | recent fetch query' -> [(query, fetch)]; fetch defaults to the query."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            q, _, f = line.partition("|")
            out.append((q.strip(), f.strip() or q.strip()))
    return out


# hits are kept only if they contain every word of one of the team's queries (all of them, not just this machine's)
ALL_QUERIES = [q for q, _ in load_queries(config.KEYWORDS_FILE)]


def search_keyword(b, store, kw, mode, max_pages):
    recent = mode == "recent"
    b.open(f"{config.BASE_URL}/search?q={quote(kw)}&serp_type=default" + ("&filter=recent" if recent else ""))
    pages = [pg for blob in b.embedded("searchResults") for pg in P.search_pages(blob)]
    if not pages:
        b.check_page()
        raise Blocked(f"search page for '{kw}' returned no searchResults (landed on another page?)")
    match = lambda v: v.get("query") == kw and v.get("recent") == (1 if recent else 0)
    n_pages = posts = replies = kept = 0
    oldest, below, stale, has_next = None, 0, 0, True
    while True:
        for hits, has_next in pages:
            n_pages += 1
            rows = []
            for post, parent in hits:
                matched = P.matching_queries((post.get("caption") or {}).get("text"), ALL_QUERIES)
                if matched:
                    rows.append(P.search_row(post, parent, config.SALT, ";".join(matched), mode, now_iso()))
            good = [r for r in rows if in_window(r)]
            store.append(good)
            kept += len(good)
            posts += sum(r["unit_type"] == "post" for r in good)
            replies += sum(r["unit_type"] != "post" for r in good)
            times = [post["taken_at"] for post, _ in hits]
            if times:
                oldest = min([oldest or times[0]] + times)
                # Recent mixes in newer posts; use page median as the older stream clock.
                below = below + 1 if statistics.median(times) < START_TS else 0
        # pages this stream would need to reach START at its current pace (dense ORed queries need tens of thousands)
        needed = n_pages * (time.time() - START_TS) / max(time.time() - (oldest or time.time()), 1)
        too_dense = recent and n_pages >= config.RECENT_PROBE_PAGES and needed > max_pages
        done = (not has_next or n_pages >= max_pages or too_dense
                or (recent and below >= config.STOP_PAGES_BEFORE_START))
        if done:
            break
        b.scroll()
        pages = [pg for resp in b.take(SEARCH_Q, match) for pg in P.search_pages(resp)]
        if pages:
            stale = 0
            continue
        stale += 1
        b.check_page()
        if stale >= config.STALE_SCROLLS:
            raise Blocked(f"{stale} scrolls in a row returned nothing for '{kw}' ({mode}) while more pages exist")
    reason = ("end of results" if not has_next else "page cap" if n_pages >= max_pages
              else f"too dense (~{needed:.0f} pages to reach 3 Sep)" if too_dense else "reached start date")
    oldest_s = datetime.fromtimestamp(oldest, P.WIB).strftime("%Y-%m-%d %H:%M WIB") if oldest else "-"
    summary = {"pages": n_pages, "kept": kept, "posts": posts, "replies": replies, "oldest": oldest_s,
               "stop": reason, "finished_at": now_iso()}
    log.info("[%s | %s] pages %d, kept %d (posts %d, replies %d), oldest reached %s, stop: %s",
             mode, kw, n_pages, kept, posts, replies, oldest_s, reason)
    return summary


def crawl_replies(b, store, root):
    code = root["permalink"].rsplit("/", 1)[1]
    b.open(P.PERMALINK.format(code=code))
    chains, has_next = [], True
    for blob in b.embedded("direct_replies"):
        c, h = P.reply_chains(blob)
        chains += c
        has_next = h if h is not None else has_next
    match = lambda v: str(v.get("postID")) == root["unit_id"]
    max_scrolls = min(config.MAX_REPLY_SCROLLS, math.ceil((root["reply_count"] or 0) / config.REPLIES_PER_SCROLL))
    stale = 0
    for _ in range(max_scrolls):
        if not has_next:
            break
        b.scroll()
        got = b.take(REPLIES_Q, match)
        if not got:
            stale += 1
            b.check_page()
            if stale >= config.STALE_SCROLLS:
                break
            continue
        stale = 0
        for resp in got:
            c, h = P.reply_chains(resp)
            chains += c
            has_next = bool(h)
    rows = [r for r in P.reply_rows(chains, root["unit_id"], config.SALT, now_iso()) if in_window(r)]
    store.append(rows)
    return len(rows), has_next


def run(args):
    data_dir = Path(args.data_dir).resolve()
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(data_dir / "logs" / f"scrape_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)])
    store = Store(data_dir, args.resume)
    queries = [(q, q) for q in args.only] if args.only else load_queries(args.keywords)
    # Recent uses the 2-word fetch form (Threads ANDs those); Top uses the team query itself
    jobs = ([("recent", f) for f in dict.fromkeys(f for _, f in queries)] + [("top", q) for q, _ in queries])
    log.info("profile %s, %d queries from %s (%d searches), data dir %s", args.profile, len(queries),
             "--only" if args.only else args.keywords, len(jobs), data_dir)
    # teammates compare this: different fingerprints = author_hash values that can't be merged
    log.info("salt fingerprint %s", hashlib.sha256(config.SALT.encode()).hexdigest()[:8])

    b = Browser(args.profile)
    try:
        b.ensure_login()
        log.info("logged in")
        if args.phase in ("all", "search"):
            for mode, kw in jobs:
                cap = (args.max_pages or config.MAX_PAGES_RECENT if mode == "recent"
                       else min(args.max_pages or config.MAX_PAGES_TOP, config.MAX_PAGES_TOP))
                key = f"{mode}|{kw}"
                if key in store.state["search_done"]:
                    continue
                store.state["search_done"][key] = search_keyword(b, store, kw, mode, cap)
                store.save_state()
                log.info("export: %d unique units", store.export())
        if args.phase in ("all", "replies"):
            done = set(store.state["replies_done"])
            roots = sorted((r for r in store.merged() if r["unit_type"] == "post" and in_window(r)
                            and (r["reply_count"] or 0) >= config.MIN_REPLIES_TO_CRAWL and r["unit_id"] not in done),
                           key=lambda r: -(r["reply_count"] or 0))[:args.max_reply_posts]
            log.info("reply crawl: %d posts to visit (%d already done)", len(roots), len(done))
            empty_in_row = 0
            for i, root in enumerate(roots, 1):
                n, more = crawl_replies(b, store, root)
                store.state["replies_done"].append(root["unit_id"])
                store.save_state()
                log.info("[reply %d/%d] post %s: %d replies kept of %s%s", i, len(roots), root["unit_id"], n,
                         root["reply_count"], " (capped)" if more else "")
                empty_in_row = empty_in_row + 1 if n == 0 else 0
                if empty_in_row >= 5:
                    raise Blocked("5 posts in a row gave no replies; possible soft block")
                if i % config.EXPORT_EVERY_POSTS == 0:
                    store.export()
        log.info("DONE. %d unique units in %s", store.export(), store.csv_path)
        return 0
    except Blocked as e:
        log.error("STOPPED: %s", e)
        log.error("Checkpoint saved. Wait (hours, not minutes), then rerun with --resume. Not retrying.")
        store.save_state()
        store.export()
        return 2
    except KeyboardInterrupt:
        log.error("Interrupted. Checkpoint saved; rerun with --resume.")
        store.save_state()
        store.export()
        return 130
    finally:
        b.d.quit()


def merge(args):
    store = Store(Path(args.data_dir).resolve(), resume=True)
    if store.raw_path.stat().st_size:
        sys.exit(f"{store.raw_path} is not empty; merge into an empty --data-dir")
    for src in args.merge:
        with open(src, encoding="utf-8") as f:
            store.raw.writelines(line if line.endswith("\n") else line + "\n" for line in f if line.strip())
    print(f"merged {len(args.merge)} files: {store.export()} unique units in {store.csv_path}")


def ensure_salt(new_salt):
    if config.SALT:
        return
    local = config.ROOT / "config_local.py"
    if local.exists():
        sys.exit("config_local.py exists but has no SALT; add SALT = '...'")
    if not new_salt:
        sys.exit("No config_local.py. Get it from the teammate who created it (privately, not via git) so "
                 "author_hash values match across machines. Only the first person ever runs --new-salt.")
    local.write_text(f'SALT = "{secrets.token_hex(16)}"  # author_hash salt; keep private, never commit\n',
                     encoding="utf-8")
    from config_local import SALT
    config.SALT = SALT
    print(f"Created {local} with a new random salt. Back it up: changing it changes every author_hash.")


def main():
    ap = argparse.ArgumentParser(description="Threads MBG-budget scraper")
    ap.add_argument("--profile", default=config.DEFAULT_PROFILE, help="Chrome profile under ./profiles/")
    ap.add_argument("--resume", action="store_true", help="continue from state/checkpoint.json")
    ap.add_argument("--keywords", default=str(config.KEYWORDS_FILE), help="team query file (default: keywords.txt)")
    ap.add_argument("--only", action="append", metavar="KEYWORD", help="scrape only this keyword (repeatable)")
    ap.add_argument("--max-pages", type=int, help="override the per-keyword page cap (testing)")
    ap.add_argument("--max-reply-posts", type=int, help="crawl replies of at most N posts")
    ap.add_argument("--phase", choices=("all", "search", "replies"), default="all")
    ap.add_argument("--data-dir", default=str(config.ROOT), help="where state/, output/, logs/ go")
    ap.add_argument("--new-salt", action="store_true", help="create config_local.py with a new salt (first person only)")
    ap.add_argument("--merge", nargs="+", metavar="RAW_JSONL",
                    help="merge raw_observations.jsonl files into an empty --data-dir and export; no scraping")
    args = ap.parse_args()
    if args.merge:
        sys.exit(merge(args))
    ensure_salt(args.new_salt)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
