"""Offline, aggregate-only audit of a Threads collection snapshot.

This script never modifies its input CSVs and never writes post text to its report.
Run it before describing a collection snapshot in TK2 or handing data downstream.
"""

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collection import parser as threads_parser  # noqa: E402


START_UTC = datetime(2026, 9, 2, 17, tzinfo=timezone.utc)
END_UTC = datetime(2026, 9, 30, 17, tzinfo=timezone.utc)
WIB = timezone(timedelta(hours=7))
COUNT_COLUMNS = ("like_count", "reply_count", "repost_count", "quote_count")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report_path(path):
    """Prefer a portable repository-relative path in the saved report."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_csv(path, expected_columns):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != expected_columns:
            raise ValueError(f"{path}: unexpected columns: {reader.fieldnames}")
        return list(reader)


def audit(raw_path, team_path, checkpoint_path=None):
    raw = read_csv(raw_path, threads_parser.COLUMNS)
    team = read_csv(team_path, threads_parser.FINAL_COLUMNS)
    ids = Counter(row["unit_id"] for row in raw)
    content_ids = Counter(row["content_id"] for row in team)
    team_by_id = {row["content_id"]: row for row in team}
    exact_text = Counter(row["text"] for row in raw if row["text"].strip())
    issues = Counter()
    by_date_wib = Counter()
    unit_types = Counter()
    search_modes = Counter()
    missing = Counter()

    for row in raw:
        unit_types[row["unit_type"]] += 1
        search_modes[row["search_mode"]] += 1
        for column in threads_parser.COLUMNS:
            if not row[column].strip():
                missing[column] += 1
        if not row["unit_id"].isdigit():
            issues["invalid_unit_id"] += 1
        if row["platform"] != "threads":
            issues["invalid_platform"] += 1
        if row["unit_type"] not in ("post", "reply", "self_thread"):
            issues["invalid_unit_type"] += 1
        for column in COUNT_COLUMNS:
            try:
                if row[column] and int(row[column]) < 0:
                    issues["negative_" + column] += 1
            except ValueError:
                issues["invalid_" + column] += 1
        try:
            utc = datetime.fromisoformat(row["created_at_utc"])
            wib = datetime.fromisoformat(row["created_at_wib"])
            if utc.tzinfo is None or wib.tzinfo is None:
                raise ValueError("naive datetime")
            if not START_UTC <= utc < END_UTC:
                issues["outside_study_window"] += 1
            if utc != wib:
                issues["utc_wib_mismatch"] += 1
            by_date_wib[utc.astimezone(WIB).date().isoformat()] += 1
        except ValueError:
            issues["invalid_created_at"] += 1
        expected = threads_parser.final_row(row)
        if team_by_id.get(expected["content_id"]) != expected:
            issues["team_projection_mismatch"] += 1

    issues["duplicate_unit_id_extra_rows"] = sum(n - 1 for n in ids.values() if n > 1)
    issues["duplicate_content_id_extra_rows"] = sum(n - 1 for n in content_ids.values() if n > 1)
    issues["team_ids_without_raw"] = len(set(content_ids) - {f"threads:{uid}" for uid in ids})
    result = {
        "scope": "Threads, MBG 2027 budget, 2026-09-03 through 2026-09-30 WIB",
        "files": {
            "raw_units": {"path": report_path(raw_path), "sha256": sha256(raw_path), "rows": len(raw)},
            "team_export": {"path": report_path(team_path), "sha256": sha256(team_path), "rows": len(team)},
        },
        "collection_completion": "not_verified",
        "checkpoint_present": bool(checkpoint_path and checkpoint_path.is_file()),
        "counts": {
            "unique_unit_ids": len(ids),
            "unit_type": dict(sorted(unit_types.items())),
            "search_mode_first_seen": dict(sorted(search_modes.items())),
            "by_publication_date_wib": dict(sorted(by_date_wib.items())),
            "empty_text": sum(not row["text"].strip() for row in raw),
            "reply_or_self_thread_without_root_id": sum(
                row["unit_type"] != "post" and not row["root_id"] for row in raw
            ),
            "repeated_exact_text_groups": sum(n > 1 for n in exact_text.values()),
            "repeated_exact_text_rows": sum(n for n in exact_text.values() if n > 1),
        },
        "missing_by_column": dict(sorted(missing.items())),
        "issues": dict(sorted((key, value) for key, value in issues.items() if value)),
    }
    if checkpoint_path and checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        result["checkpoint_summary"] = {
            "completed_search_jobs": len(checkpoint.get("search_done", {})),
            "completed_reply_roots": len(checkpoint.get("replies_done", [])),
        }
    return result


def main():
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--raw", type=Path, required=True, help="17-column threads_raw.csv")
    command.add_argument("--team", type=Path, required=True, help="6-column threads_dataset.csv")
    command.add_argument("--checkpoint", type=Path, help="optional checkpoint.json for status evidence")
    command.add_argument("--output", type=Path, required=True, help="aggregate JSON report")
    args = command.parse_args()
    result = audit(args.raw.resolve(), args.team.resolve(), args.checkpoint.resolve() if args.checkpoint else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{result['files']['raw_units']['rows']} rows audited; {len(result['issues'])} issue types; {args.output}")
    if result["issues"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
