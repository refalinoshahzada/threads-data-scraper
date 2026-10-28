from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "profiles"

BASE_URL = "https://www.threads.com"

# 3 Sep 2026 00:00 WIB
START_UTC = datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc)
# end of 30 Sep 2026 WIB, exclusive (team spec: period 3-30 Sep 2026)
END_UTC = datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc)

# seconds between actions (random uniform)
DELAY_MIN = 3.0
DELAY_MAX = 7.0

# ---- scraper (Phase 2) ----
DEFAULT_PROFILE = "account_a"
KEYWORDS_FILE = ROOT / "keywords.txt"
MAX_PAGES_RECENT = 1500     # safety cap per keyword; ~10 results/page, ~4 s/page (docs/history/threads_recon_2026-10-26.md)
MAX_PAGES_TOP = 50          # Top is relevance-ordered over all dates; main source when Recent is too dense
RECENT_PROBE_PAGES = 50     # after this many Recent pages, give up if reaching START_UTC would exceed MAX_PAGES_RECENT
STOP_PAGES_BEFORE_START = 2 # Recent: stop after this many consecutive pages whose median date < START_UTC
STALE_SCROLLS = 4           # scrolls with no new data (while has_next_page) before treating it as a block
MIN_REPLIES_TO_CRAWL = 1    # crawl a post page only if direct_reply_count >= this
MAX_REPLY_SCROLLS = 15      # ~20 replies per scroll; caps huge threads
REPLIES_PER_SCROLL = 20
EXPORT_EVERY_POSTS = 10     # rebuild the CSV every N crawled posts

try:
    from config_local import SALT  # gitignored
except ImportError:
    SALT = None

