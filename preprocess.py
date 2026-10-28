"""Eight-step, offline Threads MBG 2027 preprocessing. Run: python preprocess.py."""
from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from pathlib import Path

import emoji
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

# Adjust project parameters here; the functions below contain no dataset-specific paths.
ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "data/raw/threads_units_2026-09_v1.csv"
EXPECTED_INPUT_SHA256 = "95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df"
PROCESSED_DIR = ROOT / "data/processed"
ANNOTATION_DIR = ROOT / "data/annotation"
REPORT_DIR = ROOT / "reports"
SLANG_FILE = ROOT / "resources/slang_id.csv"
STOPWORDS_FILE = ROOT / "resources/stopwords_id.txt"
START_WIB = pd.Timestamp("2026-09-03T00:00:00+07:00")
END_WIB = pd.Timestamp("2026-09-30T23:59:59+07:00")
SEED = 42
MIN_DUP_CHARS = 30
MIN_TOPIC_WORDS = 5
ANNOTATION_SAMPLE_SIZE = 1200
BOT_AUTHOR_HASH = "80ac16d6a37404aab983670ed2377d29d47475f8f68e3b6036b379ede67eb0c7"
CAMPAIGN_HASHTAGS = (
    "#jagaindonesia", "#gizidanpendidikan", "#singtenangbolo",
    "#sengtenangbolo", "#kawalgizianak", "#kabngw8",
)
DOMAIN_STOPWORDS = (
    "mbg", "makan", "bergizi", "gratis", "program", "anggaran", "bgn",
    "2027", "kak", "bang", "sih", "deh", "nih", "dong", "aja", "ya", "gitu",
)
SHORT_SLANG = {
    "yg": "yang", "utk": "untuk", "dgn": "dengan", "tdk": "tidak",
    "krn": "karena", "sdh": "sudah", "blm": "belum", "jg": "juga",
    "lbh": "lebih", "bgt": "banget", "kalo": "kalau",
}
MBG_PATTERN = re.compile(
    r"\b(mbg|kmbg|bgn|sppg)\b|makan\s+bergizi|makan\s+siang\s+gratis|badan\s+gizi", re.I
)
OFFTOPIC_PATTERN = re.compile(r"vespa|jentera|\blesen\b|emcee|@mbgvlj", re.I)
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.I)
MENTION_PATTERN = re.compile(r"(?<!\w)@[\w.]+")
HASHTAG_PATTERN = re.compile(r"(?<!\w)#[\w]+")
METRICS = ("like_count", "reply_count", "repost_count", "quote_count")
REQUIRED = (
    "platform", "unit_id", "unit_type", "parent_id", "root_id", "text",
    "created_at_utc", "created_at_wib", *METRICS, "permalink", "author_hash",
    "matched_keywords", "search_mode", "scraped_at_utc",
)
MAIN_COLUMNS = (
    "unit_id", "unit_type", "thread_root_id", "created_at_wib", "author_hash",
    "like_count", "reply_count", "text_clean", "text_sent_a", "text_sent_b",
    "text_topic", "use_for_topic_fit", "flag_dup_cross_author", "split",
)


def step1_load_validate(path: Path = INPUT_CSV) -> pd.DataFrame:
    """Read IDs as strings, preserve source text, and flag missing/out-of-window records."""
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != EXPECTED_INPUT_SHA256:
        raise ValueError(f"Input SHA-256 differs from frozen snapshot: {actual}")
    df = pd.read_csv(
        path, dtype={"unit_id": str, "parent_id": str, "root_id": str,
                     "author_hash": str, "text": str}, keep_default_na=True,
    )
    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if df.unit_id.isna().any() or df.unit_id.duplicated().any():
        raise ValueError("unit_id must be present and unique")
    for column in ("unit_id", "parent_id", "root_id"):
        if not df[column].dropna().str.fullmatch(r"[0-9]+").all():
            raise ValueError(f"{column} must remain a digit-only string")
    df["text_raw"] = df.text.copy()
    df["flag_text_missing"] = df.text.isna() | df.text.fillna("").str.strip().eq("")
    times = pd.to_datetime(df.created_at_wib, utc=True, errors="coerce")
    if times.isna().any():
        raise ValueError("Invalid created_at_wib timestamp")
    local = times.dt.tz_convert("Asia/Jakarta")
    df["flag_out_of_window"] = ~local.between(START_WIB, END_WIB)
    return df


def clean_characters(value: str | None) -> str:
    """Only repair Unicode/whitespace; keep words, case, hashtags, and emoji."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def step2_clean_characters(df: pd.DataFrame) -> pd.DataFrame:
    """Stage 2: add a lightly cleaned text view without touching text_raw."""
    df = df.copy()
    df["text_clean"] = df.text_raw.map(clean_characters)
    return df


def make_text_key(text: str) -> str:
    """Comparison-only key; never use this stripped string as model input."""
    text = URL_PATTERN.sub(" ", text.lower())
    text = MENTION_PATTERN.sub(" ", text)
    text = HASHTAG_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def step3_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Flag repeated same-author text and exact long text across authors."""
    df = df.copy()
    df["text_key"] = df.text_clean.map(make_text_key)
    ordered = df.sort_values(["created_at_utc", "unit_id"], kind="stable")
    nonempty = ordered.text_key.ne("")
    same = nonempty & ordered.duplicated(["author_hash", "text_key"])
    df["flag_dup_same_author"] = same.reindex(df.index).fillna(False).astype(bool)
    df["flag_dup_cross_author"] = False
    long = ordered[ordered.text_key.str.len().ge(MIN_DUP_CHARS)]
    author_counts = long.groupby("text_key").author_hash.transform("nunique")
    is_later = long.duplicated("text_key")
    df.loc[long.index, "flag_dup_cross_author"] = (author_counts.gt(1) & is_later).to_numpy()
    return df


def step4_campaign_bot(df: pd.DataFrame) -> pd.DataFrame:
    """Mark campaign hashtag signatures and the specified account for manual verification."""
    df = df.copy()
    signature = re.compile("|".join(re.escape(tag) + r"\b" for tag in CAMPAIGN_HASHTAGS), re.I)
    df["flag_campaign"] = df.text_clean.map(lambda s: bool(signature.search(s)))
    df["flag_bot"] = df.author_hash.eq(BOT_AUTHOR_HASH)
    return df


def step5_relevance(df: pd.DataFrame) -> pd.DataFrame:
    """Inherit reply relevance from a collected root, with bounded parent traversal."""
    df = df.copy()
    df["mentions_mbg"] = df.text_clean.map(lambda s: bool(MBG_PATTERN.search(s)))
    df["is_offtopic"] = df.text_clean.map(lambda s: bool(OFFTOPIC_PATTERN.search(s)))
    by_id = df.set_index("unit_id")
    known = set(by_id.index)

    def root(row: pd.Series) -> str | None:
        if pd.notna(row.root_id):
            return row.root_id
        current, seen = row.unit_id, set()
        for _ in range(50):
            if current in seen:
                return None
            seen.add(current)
            if current not in known:
                return current
            parent = by_id.at[current, "parent_id"]
            if pd.isna(parent):
                return current
            current = parent
        return None

    df["thread_root_id"] = df.apply(root, axis=1)
    root_mbg = df.thread_root_id.map(by_id.mentions_mbg).eq(True)
    root_offtopic = df.thread_root_id.map(by_id.is_offtopic).eq(True)
    post = df.unit_type.eq("post")
    df["is_relevant"] = ((post & df.mentions_mbg) |
                         (~post & (df.mentions_mbg | root_mbg)))
    df["is_relevant"] &= ~df.is_offtopic & ~root_offtopic
    df["flag_no_context"] = ~post & ~df.mentions_mbg & ~df.thread_root_id.isin(known)
    df["parent_text"] = df.parent_id.map(by_id.text_clean)
    return df


def split_hashtag(match: re.Match) -> str:
    word = match.group()[1:]
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)", " ", word)


def sentiment_text(text: str, *, slang: bool = False) -> str:
    """Stage 6: mask links/accounts, expand emoji, preserve negation and punctuation."""
    if not text:
        return ""
    text = URL_PATTERN.sub(" [URL] ", text)
    text = MENTION_PATTERN.sub(" [USER] ", text)
    text = re.sub(r"(?<=\w)@(?=\w)", "a", text).replace("@", " ")
    text = HASHTAG_PATTERN.sub(split_hashtag, text)
    text = emoji.demojize(text, language="en")
    text = re.sub(r":([\w-]+):", lambda m: " " + m.group(1).replace("_", " ").replace("-", " ") + " ", text)
    text = re.sub(r"([^\W\d_])\1{2,}", r"\1\1", text, flags=re.I)
    text = re.sub(r"([!?.])\1{2,}", r"\1\1", text)
    if slang:
        text = re.sub(r"\b\w+\b", lambda m: SHORT_SLANG.get(m.group().lower(), m.group()), text)
    return re.sub(r"\s+", " ", text).strip()


def step6_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """Produce unchanged-word and lightly normalized variants for later model comparison."""
    df = df.copy()
    df["text_sent_a"] = df.text_clean.map(sentiment_text)
    df["text_sent_b"] = df.text_clean.map(lambda x: sentiment_text(x, slang=True))
    return df


def topic_text(text: str, slang_map: dict[str, str]) -> str:
    """Stage 7: readable lowercase topic view; stopwords remain until vectorization."""
    text = URL_PATTERN.sub(" ", text)
    text = MENTION_PATTERN.sub(" ", text)
    text = re.sub(r"(?<=\w)@(?=\w)", "a", text).replace("@", " ")
    text = HASHTAG_PATTERN.sub(split_hashtag, text)
    text = emoji.replace_emoji(text, replace=" ")
    text = text.lower()
    text = re.sub(r"\b\w+\b", lambda m: slang_map.get(m.group(), m.group()), text)
    text = re.sub(r"(?<=\d)\s*t\b", " triliun", text)
    text = re.sub(r"([^\W\d_])\1{2,}", r"\1", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def step7_topic(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Create BERTopic text and an external stopword list; keep short replies in full data."""
    with SLANG_FILE.open(encoding="utf-8-sig", newline="") as f:
        slang = {r["slang"].lower(): r["formal"].lower() for r in csv.DictReader(f)}
    stopwords = sorted(set(STOPWORDS_FILE.read_text(encoding="utf-8-sig").split()) |
                       set(DOMAIN_STOPWORDS))
    df = df.copy()
    df["text_topic"] = df.text_clean.map(lambda x: topic_text(x, slang))
    df["use_for_topic_fit"] = (df.in_main & ~df.flag_dup_cross_author &
                               df.text_topic.map(lambda x: len(x.split()) >= MIN_TOPIC_WORDS))
    return df, stopwords


def step8_split(df: pd.DataFrame) -> pd.DataFrame:
    """Group-split eligible text before labels exist; sample each split for annotation."""
    df = df.copy()
    eligible = df.in_main & ~df.flag_dup_cross_author
    subset = df.loc[eligible].copy()
    subset["split_group"] = subset.thread_root_id.fillna(subset.unit_id)
    df["split"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    first = GroupShuffleSplit(n_splits=1, train_size=0.70, random_state=SEED)
    train, rest = next(first.split(subset, groups=subset.split_group))
    df.loc[subset.iloc[train].index, "split"] = "train"
    remaining = subset.iloc[rest]
    second = GroupShuffleSplit(n_splits=1, train_size=0.5, random_state=SEED + 1)
    val, test = next(second.split(remaining, groups=remaining.split_group))
    df.loc[remaining.iloc[val].index, "split"] = "val"
    df.loc[remaining.iloc[test].index, "split"] = "test"
    if df.loc[eligible].assign(group=subset.split_group).groupby("group").split.nunique().gt(1).any():
        raise AssertionError("A thread was placed in multiple splits")
    return df


def write_outputs(df: pd.DataFrame, stopwords: list[str]) -> None:
    """Write only the six requested output files, preserving the private full dataset."""
    for directory in (PROCESSED_DIR, ANNOTATION_DIR, REPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PROCESSED_DIR / "threads_full.parquet", index=False)
    df.loc[df.in_main, MAIN_COLUMNS].to_csv(
        PROCESSED_DIR / "threads_main.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
    (PROCESSED_DIR / "stopwords_topic.txt").write_text("\n".join(stopwords) + "\n", encoding="utf-8")

    sampled = []
    population = df[df.split.notna()]
    for name, fraction in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        part = population[population.split.eq(name)]
        sampled.append(part.sample(n=min(len(part), round(ANNOTATION_SAMPLE_SIZE * fraction)),
                                   random_state=SEED))
    batch = pd.concat(sampled).sample(frac=1, random_state=SEED)
    label = batch[["unit_id", "split", "parent_text", "text_clean"]].copy()
    label["parent_text"] = label.parent_text.fillna("").map(lambda x: MENTION_PATTERN.sub("[USER]", x))
    label["text_clean"] = label.text_clean.map(lambda x: MENTION_PATTERN.sub("[USER]", x))
    label["label"] = ""
    label.to_csv(ANNOTATION_DIR / "to_label.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)

    check = pd.concat([
        df[df.is_relevant].sample(n=min(50, int(df.is_relevant.sum())), random_state=SEED),
        df[~df.is_relevant].sample(n=min(50, int((~df.is_relevant).sum())), random_state=SEED),
    ])[["unit_id", "unit_type", "is_relevant", "text_clean", "parent_text"]].copy()
    for column in ("text_clean", "parent_text"):
        check[column] = check[column].fillna("").map(lambda x: MENTION_PATTERN.sub("[USER]", x))
    check["manual_relevant"] = ""
    check.to_csv(REPORT_DIR / "relevance_check.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)

    funnel = []
    active = pd.Series(True, index=df.index)
    for step, excluded in (
        ("input", pd.Series(False, index=df.index)),
        ("missing text", df.flag_text_missing),
        ("out of window", df.flag_out_of_window),
        ("not relevant", ~df.is_relevant),
        ("campaign", df.flag_campaign),
        ("bot", df.flag_bot),
        ("same-author duplicate", df.flag_dup_same_author),
    ):
        n_before = int(active.sum())
        flagged = int((active & excluded).sum())
        active &= ~excluded
        funnel.append((step, n_before, flagged, int(active.sum())))
    funnel.append(("main dataset", int(active.sum()), 0, int(active.sum())))
    funnel.append(("BERTopic fit", int(active.sum()), int((active & ~df.use_for_topic_fit).sum()),
                   int(df.use_for_topic_fit.sum())))
    pd.DataFrame(funnel, columns=["step", "n_in", "n_flagged", "n_out"]).to_csv(
        REPORT_DIR / "funnel.csv", index=False, encoding="utf-8")


def main() -> None:
    df = step1_load_validate()
    original_rows = len(df)
    df = step2_clean_characters(df)
    df = step3_duplicates(df)
    df = step4_campaign_bot(df)
    df = step5_relevance(df)
    df["in_main"] = (~df.flag_text_missing & ~df.flag_out_of_window & df.is_relevant &
                     ~df.flag_campaign & ~df.flag_bot & ~df.flag_dup_same_author)
    df = step6_sentiment(df)
    df, stopwords = step7_topic(df)
    df = step8_split(df)
    if len(df) != original_rows or not df.text_raw.equals(df.text) or df.unit_id.nunique() != len(df):
        raise AssertionError("Rows, IDs, or raw text changed during preprocessing")
    write_outputs(df, stopwords)
    print(f"Total={len(df)} post={int(df.unit_type.eq('post').sum())} "
          f"reply={int(df.unit_type.eq('reply').sum())} "
          f"self_thread={int(df.unit_type.eq('self_thread').sum())}")
    print(f"missing={int(df.flag_text_missing.sum())} campaign={int(df.flag_campaign.sum())} "
          f"bot={int(df.flag_bot.sum())} same_author_dup={int(df.flag_dup_same_author.sum())} "
          f"post_mentions_mbg={int((df.unit_type.eq('post') & df.mentions_mbg).sum())}")
    print(f"main={int(df.in_main.sum())} topic_fit={int(df.use_for_topic_fit.sum())} "
          f"relevance_check={min(50, int(df.is_relevant.sum()))}+"
          f"{min(50, int((~df.is_relevant).sum()))}")


if __name__ == "__main__":
    main()
