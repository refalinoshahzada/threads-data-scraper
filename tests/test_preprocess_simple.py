"""Tests for the single-file preprocessing contract and frozen snapshot."""
import unittest

import emoji
import pandas as pd

import preprocess as pp


class TextTests(unittest.TestCase):
    def test_light_clean_does_not_remove_words_or_emoji(self):
        self.assertEqual(pp.clean_characters("Ａ MBG\u200b\r\n😭  "), "A MBG\n😭")
        self.assertEqual(pp.make_text_key("#MBG @user https://example.org Halo!"), "halo")

    def test_sentiment_variants(self):
        sample = "@user Aku GAKKK suka 😭!!! #FilmIndonesia https://x.co"
        a = pp.sentiment_text(sample)
        b = pp.sentiment_text("MBG yg 240T itu gak masuk akal bgt", slang=True)
        self.assertIn("[USER]", a)
        self.assertIn("[URL]", a)
        self.assertIn("GAKK", a)
        self.assertIn("Film Indonesia", a)
        self.assertNotIn("@", a)
        self.assertNotIn("😭", a)
        self.assertIn("yang", b)
        self.assertIn("gak", b)
        self.assertIn("banget", b)

    def test_topic_keeps_words_and_normalizes_money(self):
        got = pp.topic_text("MBG yg 240T itu gak masuk akal bgt!!! 😭", {
            "yg": "yang", "gak": "tidak", "bgt": "banget"})
        self.assertIn("240 triliun", got)
        self.assertIn("tidak", got)
        self.assertNotIn("😭", got)


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = pp.PROCESSED_DIR / "threads_full.parquet"
        if not path.exists():
            raise unittest.SkipTest("Run python preprocess.py against the private snapshot first")
        cls.full = pd.read_parquet(path)

    def test_reference_counts_and_raw_integrity(self):
        df = self.full
        self.assertEqual(len(df), 9368)
        self.assertEqual(df.unit_id.nunique(), 9368)
        self.assertTrue(df.unit_id.str.fullmatch(r"[0-9]+").all())
        self.assertEqual(df.unit_type.value_counts().to_dict(),
                         {"reply": 6835, "post": 2196, "self_thread": 337})
        self.assertEqual(int(df.flag_text_missing.sum()), 81)
        self.assertTrue(130 <= int(df.flag_dup_same_author.sum()) <= 180)
        self.assertTrue(1300 <= int(df.flag_campaign.sum()) <= 1500)
        self.assertEqual(int(df.flag_bot.sum()), 818)
        self.assertEqual(int((df.unit_type.eq("post") & df.mentions_mbg).sum()), 2191)
        self.assertTrue(df.text_raw.equals(df.text))

    def test_model_text_and_main_export(self):
        df = self.full
        for column in ("text_sent_a", "text_sent_b", "text_topic"):
            self.assertFalse(df[column].str.contains("http|@", case=False, regex=True).any())
            self.assertFalse(df[column].map(lambda x: emoji.emoji_count(x) > 0).any())
        main = pd.read_csv(pp.PROCESSED_DIR / "threads_main.csv", dtype={"unit_id": str})
        self.assertEqual(len(main), int(df.in_main.sum()))
        self.assertEqual(list(main.columns), list(pp.MAIN_COLUMNS))
        self.assertNotIn("permalink", main.columns)
        self.assertNotIn("text_raw", main.columns)
        self.assertEqual(int(df.use_for_topic_fit.sum()), int((df.in_main & ~df.flag_dup_cross_author &
                         df.text_topic.map(lambda x: len(x.split()) >= pp.MIN_TOPIC_WORDS)).sum()))

    def test_group_split_and_annotation(self):
        df = self.full[self.full.split.notna()].copy()
        group = df.thread_root_id.fillna(df.unit_id)
        self.assertFalse(df.assign(group=group).groupby("group").split.nunique().gt(1).any())
        label = pd.read_csv(pp.ANNOTATION_DIR / "to_label.csv", dtype={"unit_id": str})
        self.assertEqual(len(label), pp.ANNOTATION_SAMPLE_SIZE)
        self.assertEqual(set(label.columns), {"unit_id", "split", "parent_text", "text_clean", "label"})
        self.assertTrue(set(label.unit_id).issubset(set(df.unit_id)))
        self.assertFalse(label.text_clean.fillna("").str.contains(r"(?<!\w)@[\w.]+", regex=True).any())

    def test_relevance_sample_and_funnel(self):
        df = self.full
        check = pd.read_csv(pp.REPORT_DIR / "relevance_check.csv", dtype={"unit_id": str})
        self.assertEqual(len(check), min(50, int(df.is_relevant.sum())) +
                         min(50, int((~df.is_relevant).sum())))
        funnel = pd.read_csv(pp.REPORT_DIR / "funnel.csv")
        self.assertEqual(int(funnel.loc[funnel.step.eq("main dataset"), "n_out"].iloc[0]),
                         int(df.in_main.sum()))
        self.assertEqual(int(funnel.iloc[-1].n_out), int(df.use_for_topic_fit.sum()))


if __name__ == "__main__":
    unittest.main()
