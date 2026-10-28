"""Offline preprocessing of the Threads MBG 2027 dataset (IndoBERTweet sentiment input).

Run: python preprocessing/preprocess_v1.py  (iteration 1; the final data comes from preprocess_v2.py)

Raw (data/raw, never modified) -> flags -> data/interim -> model text -> data/interim (iteration 1, kept for traceability).
Quality problems (bot, campaign, duplicates, missing text) are flagged, not silently dropped, so
every analysis can be run with and without them (`in_all` vs `in_clean`).
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import emoji
import pandas as pd

# ---- Parameters: edit here, then re-run. The functions below contain no dataset-specific values.
PIPELINE_VERSION = "1.0"
DATASET_VERSION = "2026-09_v1"
ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT / f"data/raw/threads_units_{DATASET_VERSION}.csv"
EXPECTED_INPUT_SHA256 = "95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df"
INTERIM_DIR = ROOT / "data/interim"
REPORT_DIR = ROOT / "reports"
MANIFEST_PATH = ROOT / "metadata/preprocessing_manifest_pp1.json"
INTERIM_FILE = INTERIM_DIR / "threads_2026-09_pp1_flagged.csv"
ANALYSIS_CSV = INTERIM_DIR / "threads_2026-09_pp1_analysis.csv"
START_WIB = pd.Timestamp("2026-09-03T00:00:00+07:00")
END_WIB = pd.Timestamp("2026-09-30T23:59:59+07:00")
# Account with 818 automatic answers (reported as Meta AI); identity still needs a manual permalink check.
BOT_AUTHOR_HASH = "80ac16d6a37404aab983670ed2377d29d47475f8f68e3b6036b379ede67eb0c7"
CAMPAIGN_HASHTAGS = ("#jagaindonesia", "#gizidanpendidikan")
URL_TOKEN = "HTTPURL"   # IndoBERTweet training format
USER_TOKEN = "@USER"    # IndoBERTweet training format

MBG_PATTERN = re.compile(
    r"\b(mbg|kmbg|bgn|sppg)\b|makan\s+bergizi|makan\s+siang\s+gratis|badan\s+gizi", re.I)
# "MBG 2027" also appears in unrelated Malaysian posts (driving license, vespa, emcee); 5 units found.
OFFTOPIC_PATTERN = re.compile(r"vespa|jentera|\blesen\b|emcee|@mbgvlj", re.I)
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.I)
MENTION_PATTERN = re.compile(r"(?<!\w)@\w(?:[\w.]*\w)?")
REQUIRED = (
    "platform", "unit_id", "unit_type", "parent_id", "root_id", "text",
    "created_at_utc", "created_at_wib", "like_count", "reply_count", "repost_count",
    "quote_count", "permalink", "author_hash", "matched_keywords", "search_mode",
    "scraped_at_utc",
)
ANALYSIS_COLUMNS = (
    "unit_id", "unit_type", "thread_root_id", "created_at_wib", "author_hash",
    "text_model", "context_model", "flag_bot", "flag_campaign", "in_clean",
)


def step1_load_validate(path: Path = INPUT_CSV) -> pd.DataFrame:
    """Check the frozen input, read IDs as strings, keep the source text untouched in text_raw."""
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != EXPECTED_INPUT_SHA256:
        raise ValueError(f"Input SHA-256 differs from frozen snapshot: {actual}")
    df = pd.read_csv(path, dtype={"unit_id": str, "parent_id": str, "root_id": str,
                                  "author_hash": str, "text": str})
    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if df.unit_id.isna().any() or df.unit_id.duplicated().any():
        raise ValueError("unit_id must be present and unique")
    for column in ("unit_id", "parent_id", "root_id"):
        if not df[column].dropna().str.fullmatch(r"[0-9]+").all():
            raise ValueError(f"{column} must remain a digit-only string")
    times = pd.to_datetime(df.created_at_wib, utc=True, errors="coerce")
    if times.isna().any():
        raise ValueError("Invalid created_at_wib timestamp")
    df["created_at"] = times.dt.tz_convert("Asia/Jakarta")
    df["text_raw"] = df.text.copy()
    return df


def clean_characters(value: str | None) -> str:
    """Repair Unicode and whitespace only; words, case, hashtags, and emoji stay as written."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def step2_clean_and_flag(df: pd.DataFrame) -> pd.DataFrame:
    """Light character cleaning plus the row-level quality flags (missing, no words, off-topic, window, bot, campaign)."""
    df = df.copy()
    df["text_clean"] = df.text_raw.map(clean_characters)
    df["flag_text_missing"] = df.text_clean.eq("")
    df["flag_out_of_window"] = ~df.created_at.between(START_WIB, END_WIB)
    df["flag_bot"] = df.author_hash.eq(BOT_AUTHOR_HASH)
    signature = re.compile("|".join(re.escape(tag) + r"\b" for tag in CAMPAIGN_HASHTAGS), re.I)
    df["flag_campaign"] = df.text_clean.map(lambda s: bool(signature.search(s)))
    df["mentions_mbg"] = df.text_clean.map(lambda s: bool(MBG_PATTERN.search(s)))
    df["flag_offtopic"] = df.text_clean.map(lambda s: bool(OFFTOPIC_PATTERN.search(s)))
    # Nothing but URL/mention tokens or symbols left (emoji count as words: they carry sentiment).
    stripped = df.text_clean.map(model_text).str.replace(URL_TOKEN, "").str.replace(USER_TOKEN, "")
    df["flag_no_words"] = ~df.flag_text_missing & ~stripped.str.contains(r"[^\W\d_]", regex=True)
    return df


def step3_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Flag repeated text. Identical text is kept once (non-flagged, then earliest) before any train/test split."""
    df = df.copy()
    eligible = ~(df.flag_text_missing | df.flag_no_words | df.flag_offtopic | df.flag_out_of_window)
    # Identical = identical model input (case, URLs, and mentions masked), so no near-copy can leak across a later split.
    df["dup_key"] = df.text_clean.map(model_text)
    pool = df[eligible].assign(_flagged=df.flag_bot | df.flag_campaign)
    chronological = pool.sort_values(["created_at", "unit_id"], kind="stable")
    same_author = chronological.duplicated(["author_hash", "dup_key"])
    keep_order = pool.sort_values(["_flagged", "created_at", "unit_id"], kind="stable")
    extra_copy = keep_order.duplicated("dup_key")
    df["flag_dup_same_author"] = same_author.reindex(df.index, fill_value=False)
    df["flag_dup_text"] = extra_copy.reindex(df.index, fill_value=False)
    df["dup_group_size"] = (pool.groupby("dup_key").unit_id.transform("size")
                            .reindex(df.index).fillna(0).astype(int))
    df["in_all"] = eligible & ~df.flag_dup_text
    df["in_clean"] = df.in_all & ~df.flag_bot & ~df.flag_campaign
    return df


def step4_thread_context(df: pd.DataFrame) -> pd.DataFrame:
    """Find the thread root and attach the parent text to replies that do not mention MBG."""
    df = df.copy()
    parent_of = dict(zip(df.unit_id, df.parent_id))
    known = set(parent_of)

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
            parent = parent_of[current]
            if pd.isna(parent):
                return current
            current = parent
        return None

    df["thread_root_id"] = df.apply(root, axis=1)
    reply = df.unit_type.ne("post")
    df["flag_context_needed"] = reply & ~df.mentions_mbg
    parent_text = df.parent_id.map(dict(zip(df.unit_id, df.text_clean))).fillna("")
    df["context_text"] = parent_text.where(df.flag_context_needed, "")
    df["flag_no_context"] = df.flag_context_needed & df.context_text.eq("")
    return df


def model_text(text: str) -> str:
    """IndoBERTweet input: lowercase, @USER / HTTPURL tokens, emoji as text; negation and words kept."""
    if not text:
        return ""
    text = URL_PATTERN.sub(f" {URL_TOKEN} ", text.lower())
    text = MENTION_PATTERN.sub(f" {USER_TOKEN} ", text)
    text = emoji.demojize(text)
    return re.sub(r"\s+", " ", text).strip()


def step5_model_text(df: pd.DataFrame) -> pd.DataFrame:
    """Add the minimal model-ready text and its optional parent context (tokenizer text pair)."""
    df = df.copy()
    df["text_model"] = df.text_clean.map(model_text)
    df["context_model"] = df.context_text.map(model_text)
    return df


def step6_write_reports(df: pd.DataFrame) -> dict:
    """Write aggregate funnel, flag summary, and the list of replies whose text must be re-checked."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    active = pd.Series(True, index=df.index)
    funnel = []
    for step, excluded in (
        ("input", pd.Series(False, index=df.index)),
        ("missing text", df.flag_text_missing),
        ("no words after masking", df.flag_no_words),
        ("off-topic MBG 2027", df.flag_offtopic),
        ("out of window", df.flag_out_of_window),
        ("identical text (keep one)", df.flag_dup_text),
        ("bot account", df.flag_bot),
        ("campaign hashtag", df.flag_campaign),
    ):
        n_before = int(active.sum())
        removed = int((active & excluded).sum())
        active &= ~excluded
        funnel.append((step, n_before, removed, int(active.sum())))
        if step == "identical text (keep one)":
            funnel.append(("-> in_all (analysis with flagged data)", int(active.sum()), 0, int(active.sum())))
    funnel.append(("-> in_clean (analysis without flagged data)", int(active.sum()), 0, int(active.sum())))
    pd.DataFrame(funnel, columns=["step", "n_in", "n_flagged", "n_out"]).to_csv(
        REPORT_DIR / "funnel_pp1.csv", index=False, encoding="utf-8")

    last_day = df.created_at.dt.date.eq(pd.Timestamp("2026-09-30").date())
    flags = {
        "units": len(df),
        "flag_text_missing": int(df.flag_text_missing.sum()),
        "flag_no_words": int(df.flag_no_words.sum()),
        "flag_offtopic": int(df.flag_offtopic.sum()),
        "flag_out_of_window": int(df.flag_out_of_window.sum()),
        "flag_bot": int(df.flag_bot.sum()),
        "flag_campaign": int(df.flag_campaign.sum()),
        "flag_campaign_authors": int(df[df.flag_campaign].author_hash.nunique()),
        "flag_campaign_on_30_sep": int((df.flag_campaign & last_day).sum()),
        "rows_in_identical_text_groups": int((df.dup_group_size > 1).sum()),
        "flag_dup_text_extra_copies": int(df.flag_dup_text.sum()),
        "flag_dup_same_author": int(df.flag_dup_same_author.sum()),
        "max_same_text_by_one_author": int(df[~df.flag_text_missing]
                                           .groupby(["author_hash", "dup_key"]).size().max()),
        "reply_crawl_units": int(df.search_mode.eq("reply_crawl").sum()),
        "reply_crawl_without_mbg": int((df.search_mode.eq("reply_crawl") & ~df.mentions_mbg).sum()),
        "flag_context_needed": int(df.flag_context_needed.sum()),
        "flag_no_context": int(df.flag_no_context.sum()),
        "in_all": int(df.in_all.sum()),
        "in_clean": int(df.in_clean.sum()),
    }
    pd.DataFrame(sorted(flags.items()), columns=["metric", "value"]).to_csv(
        REPORT_DIR / "flag_summary_pp1.csv", index=False, encoding="utf-8")

    check = df[df.flag_text_missing][["unit_id", "unit_type", "search_mode", "permalink",
                                      "like_count", "reply_count"]].copy()
    check["decision"] = ""  # image_only -> drop; fetch_failed -> re-collect
    check.to_csv(REPORT_DIR / "missing_text_check_pp1.csv", index=False, encoding="utf-8")
    return flags


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state() -> dict:
    def run(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def step7_write_outputs(df: pd.DataFrame, flags: dict) -> None:
    """Write processed files and a provenance manifest (inputs, parameters, versions, outputs)."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    df.loc[df.in_all, list(ANALYSIS_COLUMNS)].to_csv(
        ANALYSIS_CSV, index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
    manifest = {
        "pipeline": {"script": Path(__file__).name, "version": PIPELINE_VERSION,
                     "script_sha256": sha256_of(Path(__file__)), "git": git_state()},
        "dataset_version": DATASET_VERSION,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": {"file": INPUT_CSV.name, "sha256": EXPECTED_INPUT_SHA256},
        "parameters": {
            "window_wib": [START_WIB.isoformat(), END_WIB.isoformat()],
            "campaign_hashtags": list(CAMPAIGN_HASHTAGS), "bot_author_hash": BOT_AUTHOR_HASH,
            "model_tokens": {"url": URL_TOKEN, "user": USER_TOKEN},
            "target_model": "indolem/indobertweet-base-uncased",
        },
        "software": {"python": platform.python_version(), "pandas": pd.__version__,
                     "emoji": emoji.__version__},
        "counts": flags,
        "outputs": {p.relative_to(ROOT).as_posix(): sha256_of(p)
                    for p in (INTERIM_FILE, ANALYSIS_CSV,
                              REPORT_DIR / "funnel_pp1.csv", REPORT_DIR / "flag_summary_pp1.csv",
                              REPORT_DIR / "missing_text_check_pp1.csv")},
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    df = step1_load_validate()
    original_rows = len(df)
    df = step2_clean_and_flag(df)
    df = step3_duplicates(df)
    df = step4_thread_context(df)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["created_at"]).to_csv(INTERIM_FILE, index=False, encoding="utf-8",
                                           quoting=csv.QUOTE_ALL)  # flags only; no model text yet
    df = step5_model_text(df)
    if len(df) != original_rows or not df.text_raw.equals(df.text) or df.unit_id.nunique() != len(df):
        raise AssertionError("Rows, IDs, or raw text changed during preprocessing")
    flags = step6_write_reports(df)
    # Reports are written before the manifest so their hashes can be recorded.
    step7_write_outputs(df, flags)
    for key in ("units", "flag_text_missing", "flag_no_words", "flag_offtopic", "flag_bot", "flag_campaign", "flag_campaign_on_30_sep",
                "rows_in_identical_text_groups", "flag_context_needed", "in_all", "in_clean"):
        print(f"{key}={flags[key]}")


if __name__ == "__main__":
    main()
