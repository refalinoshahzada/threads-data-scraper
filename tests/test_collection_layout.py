"""The compatibility CLI and runtime paths survive the package move."""

import contextlib
import importlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from collection import config


class CollectionLayoutTests(unittest.TestCase):
    def test_runtime_paths_remain_at_repository_root(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(config.ROOT, root)
        self.assertEqual(config.KEYWORDS_FILE, root / "keywords.txt")
        self.assertEqual(config.PROFILES_DIR, root / "profiles")
        self.assertEqual(config.DEFAULT_PROFILE, "account_a")

    def test_legacy_entrypoint_exposes_help_without_browser(self):
        # Selenium is imported at module load, but argparse help must not start Chrome.
        selenium = types.ModuleType("selenium")
        selenium.webdriver = types.SimpleNamespace()
        with patch.dict(sys.modules, {"selenium": selenium}):
            entrypoint = importlib.import_module("scraper")
            with patch.object(sys, "argv", ["scraper.py", "--help"]), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as result:
                    entrypoint.main()
        self.assertEqual(result.exception.code, 0)
        self.assertIn("--resume", output.getvalue())


if __name__ == "__main__":
    unittest.main()
