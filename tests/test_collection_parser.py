"""Offline tests for collection/parser.py, with optional private recon captures."""
import glob
import json
import unittest
from pathlib import Path

from collection import parser as p

RECON_DIR = Path(__file__).resolve().parents[1] / "recon"

SALT = "test-salt"
NOW = "2026-10-26T00:00:00+00:00"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@unittest.skipUnless(glob.glob(str(RECON_DIR / "graphql" / "*")), "no recon captures")
class TestOnRecon(unittest.TestCase):
    def test_search_refetch(self):
        r = load(RECON_DIR / "graphql" / "0108_BarcelonaSearchResultsRefetchableQuery.json")
        pages = p.search_pages(r["response"])
        self.assertEqual(len(pages), 1)
        hits, has_next = pages[0]
        self.assertEqual(len(hits), 10)
        self.assertTrue(has_next)
        for post, parent in hits:
            text = post["caption"]["text"].lower()
            self.assertIn("anggaran", text)
            self.assertIn("mbg", text)
            row = p.search_row(post, parent, SALT, "anggaran MBG", "recent", NOW)
            self.assertEqual(list(row), p.COLUMNS)
            self.assertTrue(row["permalink"].startswith("https://www.threads.com/t/"))
            if parent:
                self.assertEqual(row["parent_id"], parent["pk"])
                self.assertIn(row["unit_type"], ("reply", "self_thread"))
            else:
                self.assertEqual(row["root_id"], row["unit_id"])
            # no raw usernames anywhere in the row
            self.assertNotIn(post["user"]["username"], json.dumps(row, ensure_ascii=False))

    def test_search_embedded(self):
        hits = [h for pg in p.search_pages(load(RECON_DIR / "embedded" / "search_recent_anggaran_MBG_00.json"))
                for h in pg[0]]
        self.assertGreater(len(hits), 0)

    def test_feed_page_has_no_search_results(self):
        # Top 'anggaran MBG' landed on the home feed during onboarding (dated recon notes).
        self.assertEqual(p.search_pages(load(RECON_DIR / "embedded" / "search_top_anggaran_MBG_00.json")), [])

    def test_reply_refetch_chain_parents(self):
        r = load(RECON_DIR / "graphql" / "0491_BarcelonaPostPageDirectRepliesRefetchQuery.json")
        root = r["variables"]["postID"]
        chains, has_next = p.reply_chains(r["response"])
        self.assertTrue(has_next)
        rows = p.reply_rows(chains, root, SALT, NOW)
        ids = {row["unit_id"] for row in rows}
        self.assertEqual(len(ids), len(rows))
        for chain in chains:
            chain_rows = [row for row in rows if row["unit_id"] in {x["pk"] for x in chain}]
            self.assertEqual(chain_rows[0]["parent_id"], root)
            for a, b in zip(chain_rows, chain_rows[1:]):
                self.assertEqual(b["parent_id"], a["unit_id"])
        self.assertTrue(all(row["root_id"] == root and row["search_mode"] == "reply_crawl" for row in rows))

    def test_reply_embedded(self):
        root = load(RECON_DIR / "embedded" / "post_1_00.json")
        root_pk = next(p.find_key(root, "media"))["pk"]
        chains, _ = p.reply_chains(load(RECON_DIR / "embedded" / "post_1_01.json"))
        self.assertGreater(len(p.reply_rows(chains, root_pk, SALT, NOW)), 0)


class TestPure(unittest.TestCase):
    def test_merge_unions_keywords(self):
        base = {c: "" for c in p.COLUMNS} | {"unit_id": "1", "like_count": 1, "reply_count": 0,
                                              "repost_count": 0, "quote_count": 0}
        merged = p.merge_rows([base | {"matched_keywords": "a"}, base | {"matched_keywords": "b;a", "like_count": 5}])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["matched_keywords"], "a;b")
        self.assertEqual(merged[0]["like_count"], 5)

    def test_self_thread(self):
        post = {"user": {"username": "u"}, "text_post_app_info": {
            "is_reply": True, "reply_to_author": {"username": "u"}, "root_post_author": {"username": "u"}}}
        self.assertEqual(p.unit_type(post), "self_thread")
        post["text_post_app_info"]["reply_to_author"] = {"username": "v"}
        self.assertEqual(p.unit_type(post), "reply")

    def test_matching_queries(self):
        qs = ["RKA BGN 2027", "MBG 2027"]
        self.assertEqual(p.matching_queries("RKA #BGN tahun 2027 untuk MBG", qs), qs)
        self.assertEqual(p.matching_queries("BGN 2027 saja", qs), [])
        self.assertEqual(p.matching_queries(None, qs), [])

    def test_final_row(self):
        row = p.to_row({"pk": "1", "code": "c", "taken_at": 1788368400}, "self_thread", "0", "0", SALT, "k", "recent", NOW)
        out = p.final_row(row)
        self.assertEqual(list(out), p.FINAL_COLUMNS)
        self.assertEqual((out["content_id"], out["content_type"]), ("threads:1", "reply"))
        self.assertEqual(out["created_at"], "2026-09-02T17:00:00+00:00")

    def test_wib_offset(self):
        row = p.to_row({"pk": "1", "code": "c", "taken_at": 1788368400}, "post", "", "1", SALT, "k", "recent", NOW)
        self.assertEqual(row["created_at_utc"], "2026-09-02T17:00:00+00:00")
        self.assertEqual(row["created_at_wib"], "2026-09-03T00:00:00+07:00")


if __name__ == "__main__":
    unittest.main()
