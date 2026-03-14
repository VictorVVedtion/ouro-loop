"""
Additional tests for prepare.py — covering print_scan_report(), OSError paths,
and the missing-template edge case.

Run with:
    python3 -m unittest tests.test_prepare_extra -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, mock_open, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import prepare


def _make_tmp() -> str:
    return tempfile.mkdtemp()


def _write(path: str, content: str = ""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# print_scan_report()
# ---------------------------------------------------------------------------

class TestPrintScanReport(unittest.TestCase):
    """print_scan_report() produces correctly formatted output."""

    def _capture_report(self, scan: dict) -> str:
        buf = StringIO()
        with patch("sys.stdout", buf):
            prepare.print_scan_report(scan)
        return buf.getvalue()

    def _minimal_scan(self, **overrides) -> dict:
        base = {
            "name": "test-project",
            "path": "/tmp/test-project",
            "project_types": [],
            "file_count": 0,
            "dir_count": 0,
            "total_lines": 0,
            "languages": {},
            "has_claude_md": False,
            "bound_detected": False,
            "has_tests": False,
            "has_ci": False,
            "top_directories": [],
            "scanned_at": "2026-01-01T00:00:00+00:00",
        }
        base.update(overrides)
        return base

    def test_output_contains_project_name(self):
        scan = self._minimal_scan(name="my-app")
        out = self._capture_report(scan)
        self.assertIn("my-app", out)

    def test_output_contains_file_count(self):
        scan = self._minimal_scan(file_count=42)
        out = self._capture_report(scan)
        self.assertIn("42", out)

    def test_output_contains_total_lines(self):
        scan = self._minimal_scan(total_lines=1234)
        out = self._capture_report(scan)
        self.assertIn("1,234", out)

    def test_output_contains_claude_md_found_when_true(self):
        scan = self._minimal_scan(has_claude_md=True)
        out = self._capture_report(scan)
        self.assertIn("Found", out)

    def test_output_contains_bound_detected_when_true(self):
        scan = self._minimal_scan(bound_detected=True)
        out = self._capture_report(scan)
        self.assertIn("Detected", out)

    def test_output_contains_tests_found_when_true(self):
        scan = self._minimal_scan(has_tests=True)
        out = self._capture_report(scan)
        self.assertIn("Found", out)

    def test_output_contains_ci_found_when_true(self):
        scan = self._minimal_scan(has_ci=True)
        out = self._capture_report(scan)
        self.assertIn("Found", out)

    def test_languages_section_printed_when_present(self):
        scan = self._minimal_scan(languages={"Python": 10, "JavaScript": 5})
        out = self._capture_report(scan)
        self.assertIn("Python", out)
        self.assertIn("JavaScript", out)

    def test_languages_section_skipped_when_empty(self):
        scan = self._minimal_scan(languages={})
        out = self._capture_report(scan)
        self.assertNotIn("Languages:", out)

    def test_project_types_unknown_when_empty(self):
        scan = self._minimal_scan(project_types=[])
        out = self._capture_report(scan)
        self.assertIn("Unknown", out)

    def test_project_types_listed_when_present(self):
        scan = self._minimal_scan(project_types=["Python", "Docker"])
        out = self._capture_report(scan)
        self.assertIn("Python", out)
        self.assertIn("Docker", out)

    def test_recommendation_for_missing_bound(self):
        scan = self._minimal_scan(bound_detected=False)
        out = self._capture_report(scan)
        self.assertIn("BOUND", out)

    def test_recommendation_for_missing_tests(self):
        scan = self._minimal_scan(has_tests=False)
        out = self._capture_report(scan)
        self.assertIn("test", out.lower())

    def test_recommendation_for_missing_claude_md(self):
        scan = self._minimal_scan(has_claude_md=False)
        out = self._capture_report(scan)
        self.assertIn("CLAUDE.md", out)

    def test_no_recommendations_when_all_present(self):
        scan = self._minimal_scan(
            has_claude_md=True, bound_detected=True,
            has_tests=True, has_ci=True,
        )
        out = self._capture_report(scan)
        self.assertNotIn("Recommendations:", out)

    def test_top_directories_listed(self):
        scan = self._minimal_scan(top_directories=["src", "docs", "tests"])
        out = self._capture_report(scan)
        self.assertIn("src", out)

    def test_top_directories_truncated_at_10(self):
        dirs = [f"dir{i}" for i in range(15)]
        scan = self._minimal_scan(top_directories=dirs)
        out = self._capture_report(scan)
        self.assertIn("and 5 more", out)

    def test_output_has_separator_lines(self):
        scan = self._minimal_scan()
        out = self._capture_report(scan)
        self.assertIn("=" * 60, out)


# ---------------------------------------------------------------------------
# scan_project() — OSError / PermissionError paths
# ---------------------------------------------------------------------------

class TestScanProjectOSErrorPaths(unittest.TestCase):
    """scan_project() handles OSError on file reads without crashing."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_oserror_reading_code_file_skips_gracefully(self):
        """OSError on a .py file open should not crash scan_project."""
        py_file = os.path.join(self.tmp, "main.py")
        _write(py_file, "x = 1\n")
        original_open = open

        def patched_open(path, *args, **kwargs):
            if str(path) == py_file and kwargs.get("errors") == "ignore":
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            result = prepare.scan_project(self.tmp)
        # Should not raise; total_lines may be 0 due to skipped file
        self.assertIsInstance(result, dict)

    def test_oserror_reading_claude_md_skips_bound_check(self):
        """OSError on CLAUDE.md open should leave bound_detected=False."""
        claude_path = os.path.join(self.tmp, "CLAUDE.md")
        _write(claude_path, "## BOUND\nstuff\n")
        original_open = open

        def patched_open(path, *args, **kwargs):
            if str(path) == claude_path and "encoding" in kwargs:
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            result = prepare.scan_project(self.tmp)
        # has_claude_md still True (os.path.exists), but bound_detected stays False
        self.assertTrue(result["has_claude_md"])
        self.assertFalse(result["bound_detected"])


# ---------------------------------------------------------------------------
# install_template() — missing source template
# ---------------------------------------------------------------------------

class TestInstallTemplateMissingSource(unittest.TestCase):
    """install_template() exits when source template file is missing."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_source_template_exits(self):
        # Temporarily point TEMPLATES_DIR to an empty dir
        empty_dir = _make_tmp()
        try:
            original = prepare.TEMPLATES_DIR
            prepare.TEMPLATES_DIR = empty_dir
            with self.assertRaises(SystemExit):
                prepare.install_template("claude", self.tmp)
        finally:
            prepare.TEMPLATES_DIR = original
            shutil.rmtree(empty_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# init_ralph() — OSError on listdir (top_directories)
# ---------------------------------------------------------------------------

class TestScanProjectTopDirOSError(unittest.TestCase):
    """top_directories returns [] when listdir raises OSError."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_oserror_on_listdir_handled(self):
        with patch("os.listdir", side_effect=OSError("permission denied")):
            result = prepare.scan_project(self.tmp)
        self.assertEqual(result["top_directories"], [])


if __name__ == "__main__":
    unittest.main()
