"""Meaningful offline checks for the snapshot audit and handoff verifier."""

import csv
import tempfile
import unittest
from pathlib import Path

from collection import parser as threads_parser
from scripts.audit_collection import ROOT, START_UTC, audit

TEST_TMP = ROOT / "runs" / "test_tmp"
TEST_TMP.mkdir(parents=True, exist_ok=True)


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class CollectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEST_TMP)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.raw_path = self.folder / "threads_raw.csv"
        self.team_path = self.folder / "threads_dataset.csv"
        self.row = threads_parser.to_row(
            {"pk": "123", "code": "abc", "taken_at": int(START_UTC.timestamp()),
             "caption": {"text": "Anggaran MBG 2027"}, "like_count": 0,
             "text_post_app_info": {"direct_reply_count": 0, "repost_count": 0, "quote_count": 0}},
            "post", "", "123", "test-salt", "MBG 2027", "recent", "2026-10-27T00:00:00+00:00",
        )

    def test_consistent_projection_and_wib_boundary(self):
        write_csv(self.raw_path, threads_parser.COLUMNS, [self.row])
        write_csv(self.team_path, threads_parser.FINAL_COLUMNS, [threads_parser.final_row(self.row)])
        report = audit(self.raw_path, self.team_path)
        self.assertEqual(report["issues"], {})
        self.assertEqual(report["counts"]["by_publication_date_wib"], {"2026-09-03": 1})
        self.assertEqual(report["counts"]["unique_unit_ids"], 1)

    def test_projection_and_period_errors_are_reported(self):
        wrong = dict(self.row, created_at_utc="2026-10-01T00:00:00+00:00")
        write_csv(self.raw_path, threads_parser.COLUMNS, [wrong])
        write_csv(self.team_path, threads_parser.FINAL_COLUMNS, [threads_parser.final_row(self.row)])
        report = audit(self.raw_path, self.team_path)
        self.assertEqual(report["issues"]["outside_study_window"], 1)
        self.assertEqual(report["issues"]["utc_wib_mismatch"], 1)
        self.assertEqual(report["issues"]["team_projection_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
