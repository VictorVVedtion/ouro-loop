"""
Additional tests for framework.py — covering show_status(), print_verification(),
run_self_assessment() OSError path, and bound_violations counting.

Run with:
    python3 -m unittest tests.test_framework_extra -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import framework


def _make_tmp() -> str:
    return tempfile.mkdtemp()


def _write(path: str, content: str = ""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_state(project_path: str, **overrides) -> dict:
    state = {
        "version": "0.1.0",
        "project_name": "test-project",
        "current_stage": "BUILD",
        "current_phase": 1,
        "total_phases": 3,
        "bound_defined": False,
        "history": [],
    }
    state.update(overrides)
    ralph_dir = os.path.join(project_path, ".ouro")
    os.makedirs(ralph_dir, exist_ok=True)
    with open(os.path.join(ralph_dir, "state.json"), "w") as f:
        json.dump(state, f, indent=2)
    return state


# ---------------------------------------------------------------------------
# show_status()
# ---------------------------------------------------------------------------

class TestShowStatus(unittest.TestCase):
    """show_status() prints the current state to stdout."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture_status(self) -> str:
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.show_status(self.tmp)
        return buf.getvalue()

    def test_shows_project_name(self):
        _make_state(self.tmp, project_name="my-project")
        out = self._capture_status()
        self.assertIn("my-project", out)

    def test_shows_current_stage(self):
        _make_state(self.tmp, current_stage="VERIFY")
        out = self._capture_status()
        self.assertIn("VERIFY", out)

    def test_shows_phase_fraction_when_phase_active(self):
        _make_state(self.tmp, current_phase=2, total_phases=5)
        out = self._capture_status()
        self.assertIn("2/5", out)

    def test_shows_na_when_no_phase(self):
        _make_state(self.tmp, current_phase=None, total_phases=0)
        out = self._capture_status()
        self.assertIn("N/A", out)

    def test_shows_bound_defined_when_true(self):
        _make_state(self.tmp, bound_defined=True)
        out = self._capture_status()
        self.assertIn("Defined", out)

    def test_shows_bound_not_defined_when_false(self):
        _make_state(self.tmp, bound_defined=False)
        out = self._capture_status()
        self.assertIn("Not defined", out)

    def test_shows_history_counts(self):
        history = [
            {"verdict": "PASS", "stage": "BUILD", "phase": "1/3",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"verdict": "FAIL", "stage": "VERIFY", "phase": "2/3",
             "timestamp": "2026-01-01T01:00:00+00:00"},
            {"verdict": "PASS", "stage": "BUILD", "phase": "3/3",
             "timestamp": "2026-01-01T02:00:00+00:00"},
        ]
        _make_state(self.tmp, history=history)
        out = self._capture_status()
        self.assertIn("2 passed", out)
        self.assertIn("1 failed", out)
        self.assertIn("3 total", out)

    def test_shows_last_history_entry(self):
        history = [
            {"verdict": "PASS", "stage": "BUILD", "phase": "1/3",
             "timestamp": "2026-01-01T00:00:00+00:00"},
        ]
        _make_state(self.tmp, history=history)
        out = self._capture_status()
        self.assertIn("PASS", out)
        self.assertIn("BUILD", out)

    def test_empty_history_shows_zero_counts(self):
        _make_state(self.tmp, history=[])
        out = self._capture_status()
        self.assertIn("0 passed", out)
        self.assertIn("0 failed", out)

    def test_separator_lines_present(self):
        _make_state(self.tmp)
        out = self._capture_status()
        self.assertIn("=" * 50, out)

    def test_retry_verdict_counted_as_failed(self):
        history = [
            {"verdict": "RETRY", "stage": "BUILD", "phase": "1/3",
             "timestamp": "2026-01-01T00:00:00+00:00"},
        ]
        _make_state(self.tmp, history=history)
        out = self._capture_status()
        self.assertIn("1 failed", out)


# ---------------------------------------------------------------------------
# print_verification()
# ---------------------------------------------------------------------------

class TestPrintVerification(unittest.TestCase):
    """print_verification() formats the results dict for display."""

    def _capture(self, results: dict) -> str:
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.print_verification(results)
        return buf.getvalue()

    def _make_results(self, overall="PASS", gate_status="PASS",
                      self_status="PASS", failures=None) -> dict:
        results = {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "overall": overall,
            "layer1_gates": {
                "EXIST": {"status": gate_status, "detail": "CLAUDE.md exists"},
                "RELEVANCE": {"status": "PASS", "detail": "0 files changed", "files": []},
            },
            "layer2_self": {
                "bound_compliance": {"status": self_status, "detail": "BOUND section found"},
                "tests_exist": {"status": "PASS", "detail": "Test files found"},
            },
        }
        if failures:
            results["failures"] = failures
        return results

    def test_shows_overall_pass(self):
        out = self._capture(self._make_results(overall="PASS"))
        self.assertIn("PASS", out)

    def test_shows_overall_fail(self):
        out = self._capture(self._make_results(overall="FAIL", failures=["EXIST"]))
        self.assertIn("FAIL", out)

    def test_shows_gate_names(self):
        out = self._capture(self._make_results())
        self.assertIn("EXIST", out)
        self.assertIn("RELEVANCE", out)

    def test_shows_self_assessment_keys(self):
        out = self._capture(self._make_results())
        self.assertIn("bound_compliance", out)
        self.assertIn("tests_exist", out)

    def test_pass_icon_shown_for_pass_status(self):
        out = self._capture(self._make_results(gate_status="PASS"))
        self.assertIn("[+]", out)

    def test_fail_icon_shown_for_fail_status(self):
        out = self._capture(self._make_results(gate_status="FAIL",
                                               overall="FAIL", failures=["EXIST"]))
        self.assertIn("[X]", out)

    def test_warn_icon_shown_for_warn_status(self):
        out = self._capture(self._make_results(gate_status="WARN"))
        self.assertIn("[!]", out)

    def test_skip_icon_shown_for_skip_status(self):
        out = self._capture(self._make_results(gate_status="SKIP"))
        self.assertIn("[-]", out)

    def test_failures_listed_when_fail(self):
        out = self._capture(self._make_results(overall="FAIL", failures=["EXIST", "ROOT_CAUSE"]))
        self.assertIn("EXIST", out)
        self.assertIn("ROOT_CAUSE", out)

    def test_failures_not_shown_when_pass(self):
        out = self._capture(self._make_results(overall="PASS"))
        self.assertNotIn("Failures:", out)

    def test_separator_lines_present(self):
        out = self._capture(self._make_results())
        self.assertIn("=" * 50, out)

    def test_layer1_section_header_present(self):
        out = self._capture(self._make_results())
        self.assertIn("Layer 1", out)

    def test_layer2_section_header_present(self):
        out = self._capture(self._make_results())
        self.assertIn("Layer 2", out)


# ---------------------------------------------------------------------------
# run_self_assessment() — OSError when reading CLAUDE.md
# ---------------------------------------------------------------------------

class TestRunSelfAssessmentOSError(unittest.TestCase):
    """run_self_assessment() falls back to SKIP when CLAUDE.md cannot be read."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bound_compliance_skip_on_oserror(self):
        claude_path = os.path.join(self.tmp, "CLAUDE.md")
        _write(claude_path, "## BOUND\nstuff\n")
        original_open = open

        def patched_open(path, *args, **kwargs):
            if str(path) == claude_path:
                raise OSError("cannot read")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "SKIP")

    def test_bound_compliance_skip_detail_on_oserror(self):
        claude_path = os.path.join(self.tmp, "CLAUDE.md")
        _write(claude_path, "## BOUND\nstuff\n")
        original_open = open

        def patched_open(path, *args, **kwargs):
            if str(path) == claude_path:
                raise OSError("cannot read")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            checks = framework.run_self_assessment(self.tmp)
        self.assertIn("Cannot read", checks["bound_compliance"]["detail"])


# ---------------------------------------------------------------------------
# run_verification() — bound_violations counting
# ---------------------------------------------------------------------------

class TestRunVerificationBoundViolations(unittest.TestCase):
    """log_phase_result counts FAIL gates as bound_violations."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bound_violations_zero_when_no_gate_fails(self):
        _make_state(self.tmp, current_phase=1, total_phases=3)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n")

        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS")

        with open(results_path) as f:
            lines = f.readlines()
        data_row = lines[1].split("\t")
        self.assertEqual(data_row[2], "0")  # bound_violations column

    def test_bound_violations_incremented_when_gate_fails(self):
        # Force EXIST gate to FAIL
        _make_state(self.tmp, current_phase=1, total_phases=3, bound_defined=True)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n")

        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "FAIL")

        with open(results_path) as f:
            lines = f.readlines()
        data_row = lines[1].split("\t")
        violations = int(data_row[2])
        self.assertGreater(violations, 0)


# ---------------------------------------------------------------------------
# show_status() — missing state exits
# ---------------------------------------------------------------------------

class TestShowStatusMissingState(unittest.TestCase):
    """show_status() calls load_state(required=True) which exits on missing state."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_show_status_exits_when_no_state(self):
        with self.assertRaises(SystemExit):
            framework.show_status(self.tmp)


# ---------------------------------------------------------------------------
# check_bound() — underscore variant completeness
# ---------------------------------------------------------------------------

class TestCheckBoundCompleteVariants(unittest.TestCase):
    """check_bound() recognises all underscore and space variants of BOUND sections."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture_bound(self, content: str) -> str:
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.check_bound(self.tmp)
        return buf.getvalue()

    def test_all_sections_space_variant(self):
        content = "DANGER ZONE: risky\nNEVER DO: forbidden\nIRON LAW: invariant\n"
        out = self._capture_bound(content)
        self.assertIn("BOUND fully defined", out)

    def test_all_sections_underscore_variant(self):
        content = "DANGER_ZONE: risky\nNEVER_DO: forbidden\nIRON_LAW: invariant\n"
        out = self._capture_bound(content)
        self.assertIn("BOUND fully defined", out)

    def test_partial_bound_lists_missing_items(self):
        # Only DANGER ZONE defined
        content = "DANGER ZONE: risky\n"
        out = self._capture_bound(content)
        self.assertIn("NEVER DO", out)
        self.assertIn("IRON LAWS", out)


if __name__ == "__main__":
    unittest.main()
