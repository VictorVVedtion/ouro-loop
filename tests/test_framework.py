"""
Tests for framework.py — state management, gates, self-assessment, logging,
phase advancement, and BOUND checking.

Run with:
    python3 -m unittest tests.test_framework -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

# Add project root to path so imports work regardless of cwd
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import framework


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tmp() -> str:
    return tempfile.mkdtemp()


def _write(path: str, content: str = ""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_state(project_path: str, **overrides) -> dict:
    """Create a minimal valid state file and return the state dict."""
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
    ouro_dir = os.path.join(project_path, ".ouro")
    os.makedirs(ouro_dir, exist_ok=True)
    with open(os.path.join(ouro_dir, "state.json"), "w") as f:
        json.dump(state, f, indent=2)
    return state


# ---------------------------------------------------------------------------
# load_state()
# ---------------------------------------------------------------------------

class TestLoadStateNormal(unittest.TestCase):
    """load_state() returns parsed dict when state file exists."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_returns_dict(self):
        _make_state(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertIsInstance(state, dict)

    def test_load_returns_correct_project_name(self):
        _make_state(self.tmp, project_name="my-project")
        state = framework.load_state(self.tmp)
        self.assertEqual(state["project_name"], "my-project")

    def test_load_returns_correct_current_stage(self):
        _make_state(self.tmp, current_stage="VERIFY")
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "VERIFY")

    def test_load_required_false_returns_none_when_missing(self):
        result = framework.load_state(self.tmp, required=False)
        self.assertIsNone(result)

    def test_load_required_true_exits_when_missing(self):
        with self.assertRaises(SystemExit):
            framework.load_state(self.tmp, required=True)

    def test_load_all_fields_preserved(self):
        _make_state(self.tmp, current_phase=2, total_phases=5, history=[{"v": "PASS"}])
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_phase"], 2)
        self.assertEqual(state["total_phases"], 5)
        self.assertEqual(state["history"], [{"v": "PASS"}])


class TestLoadStateCorrupted(unittest.TestCase):
    """load_state() handles corrupted JSON gracefully."""

    def setUp(self):
        self.tmp = _make_tmp()
        ouro_dir = os.path.join(self.tmp, ".ouro")
        os.makedirs(ouro_dir)
        self.state_path = os.path.join(ouro_dir, "state.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_corrupted_json_required_true_exits(self):
        with open(self.state_path, "w") as f:
            f.write("{not valid json!!!")
        with self.assertRaises(SystemExit):
            framework.load_state(self.tmp, required=True)

    def test_corrupted_json_required_false_returns_none(self):
        with open(self.state_path, "w") as f:
            f.write("{{{{broken")
        result = framework.load_state(self.tmp, required=False)
        self.assertIsNone(result)

    def test_empty_file_required_true_exits(self):
        with open(self.state_path, "w") as f:
            f.write("")
        with self.assertRaises(SystemExit):
            framework.load_state(self.tmp, required=True)

    def test_empty_file_required_false_returns_none(self):
        with open(self.state_path, "w") as f:
            f.write("")
        result = framework.load_state(self.tmp, required=False)
        self.assertIsNone(result)

    def test_truncated_json_required_true_exits(self):
        with open(self.state_path, "w") as f:
            f.write('{"key": "val')  # truncated
        with self.assertRaises(SystemExit):
            framework.load_state(self.tmp, required=True)


# ---------------------------------------------------------------------------
# save_state()
# ---------------------------------------------------------------------------

class TestSaveState(unittest.TestCase):
    """save_state() writes state correctly and adds updated_at."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_then_load_roundtrip(self):
        state = framework.load_state(self.tmp)
        state["project_name"] = "updated-name"
        framework.save_state(self.tmp, state)
        reloaded = framework.load_state(self.tmp)
        self.assertEqual(reloaded["project_name"], "updated-name")

    def test_save_adds_updated_at_field(self):
        state = framework.load_state(self.tmp)
        framework.save_state(self.tmp, state)
        reloaded = framework.load_state(self.tmp)
        self.assertIn("updated_at", reloaded)

    def test_updated_at_is_string(self):
        state = framework.load_state(self.tmp)
        framework.save_state(self.tmp, state)
        reloaded = framework.load_state(self.tmp)
        self.assertIsInstance(reloaded["updated_at"], str)

    def test_save_writes_valid_json(self):
        state = framework.load_state(self.tmp)
        state["new_field"] = [1, 2, 3]
        framework.save_state(self.tmp, state)
        state_path = os.path.join(self.tmp, ".ouro", "state.json")
        with open(state_path) as f:
            raw = json.load(f)
        self.assertEqual(raw["new_field"], [1, 2, 3])

    def test_save_preserves_history(self):
        state = framework.load_state(self.tmp)
        state["history"] = [{"verdict": "PASS", "phase": "1/3"}]
        framework.save_state(self.tmp, state)
        reloaded = framework.load_state(self.tmp)
        self.assertEqual(len(reloaded["history"]), 1)
        self.assertEqual(reloaded["history"][0]["verdict"], "PASS")

    def test_save_mutates_state_dict_in_place_with_updated_at(self):
        state = framework.load_state(self.tmp)
        framework.save_state(self.tmp, state)
        # The passed-in dict is mutated to include updated_at
        self.assertIn("updated_at", state)


# ---------------------------------------------------------------------------
# run_gates() — EXIST gate
# ---------------------------------------------------------------------------

class TestRunGatesExist(unittest.TestCase):
    """EXIST gate checks for CLAUDE.md presence and bound_defined state."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exist_pass_when_claude_md_present(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Project\n")
        gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["EXIST"]["status"], "PASS")

    def test_exist_detail_mentions_claude_md_exists(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Project\n")
        gates = framework.run_gates(self.tmp)
        self.assertIn("CLAUDE.md", gates["EXIST"]["detail"])

    def test_exist_warn_when_no_claude_md_and_bound_not_expected(self):
        # State says bound_defined=False and no CLAUDE.md
        _make_state(self.tmp, bound_defined=False)
        gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["EXIST"]["status"], "WARN")

    def test_exist_fail_when_no_claude_md_but_bound_was_expected(self):
        # State says bound_defined=True but CLAUDE.md is missing
        _make_state(self.tmp, bound_defined=True)
        gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["EXIST"]["status"], "FAIL")

    def test_exist_fail_detail_mentions_missing(self):
        _make_state(self.tmp, bound_defined=True)
        gates = framework.run_gates(self.tmp)
        detail = gates["EXIST"]["detail"].lower()
        self.assertTrue("missing" in detail or "expected" in detail)

    def test_exist_warn_when_no_state_file_and_no_claude_md(self):
        # No state file at all (required=False path)
        empty_tmp = _make_tmp()
        try:
            gates = framework.run_gates(empty_tmp)
            self.assertEqual(gates["EXIST"]["status"], "WARN")
        finally:
            shutil.rmtree(empty_tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# run_gates() — RELEVANCE gate (git subprocess)
# ---------------------------------------------------------------------------

class TestRunGatesRelevance(unittest.TestCase):
    """RELEVANCE gate uses git status output."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# P\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_with_git_output(self, stdout: str) -> dict:
        """Helper: run run_gates with mocked git status output."""
        mock_result = MagicMock()
        mock_result.stdout = stdout
        mock_result.returncode = 0
        with patch("framework.subprocess.run", return_value=mock_result):
            return framework.run_gates(self.tmp)

    def test_relevance_pass_when_git_returns_clean(self):
        gates = self._run_with_git_output("")
        self.assertEqual(gates["RELEVANCE"]["status"], "PASS")

    def test_relevance_pass_with_changed_files(self):
        gates = self._run_with_git_output(" M framework.py\n M prepare.py\n")
        self.assertEqual(gates["RELEVANCE"]["status"], "PASS")

    def test_relevance_detail_includes_file_count(self):
        gates = self._run_with_git_output(" M framework.py\n M prepare.py\n")
        self.assertIn("2", gates["RELEVANCE"]["detail"])

    def test_relevance_skip_when_git_not_found(self):
        with patch("framework.subprocess.run", side_effect=FileNotFoundError):
            gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["RELEVANCE"]["status"], "SKIP")

    def test_relevance_skip_when_git_times_out(self):
        import subprocess
        with patch("framework.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["RELEVANCE"]["status"], "SKIP")

    def test_relevance_files_list_capped_at_20(self):
        # 25 changed files
        lines = "\n".join(f" M file{i}.py" for i in range(25))
        gates = self._run_with_git_output(lines)
        self.assertLessEqual(len(gates["RELEVANCE"]["files"]), 20)

    def test_relevance_zero_files_when_clean_tree(self):
        gates = self._run_with_git_output("")
        self.assertEqual(len(gates["RELEVANCE"]["files"]), 0)


# ---------------------------------------------------------------------------
# run_gates() — ROOT_CAUSE gate
# ---------------------------------------------------------------------------

class TestRunGatesRootCause(unittest.TestCase):
    """ROOT_CAUSE gate detects hot files (edited >= 3 times)."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# P\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_with_log_output(self, stdout: str) -> dict:
        """Mock git log --name-only output."""
        # We need two subprocess.run calls: one for git status (RELEVANCE)
        # and one for git log (ROOT_CAUSE) and one for git log --oneline (MOMENTUM).
        # Use side_effect list to return different mocks per call order.
        status_mock = MagicMock()
        status_mock.stdout = ""
        log_mock = MagicMock()
        log_mock.stdout = stdout
        oneline_mock = MagicMock()
        oneline_mock.stdout = "abc123 commit1\ndef456 commit2\n"
        with patch("framework.subprocess.run",
                   side_effect=[status_mock, log_mock, oneline_mock]):
            return framework.run_gates(self.tmp)

    def test_root_cause_pass_when_no_hot_files(self):
        # Each file appears only once — no hot files
        gates = self._run_with_log_output("file_a.py\nfile_b.py\nfile_c.py\n")
        self.assertEqual(gates["ROOT_CAUSE"]["status"], "PASS")

    def test_root_cause_warn_when_file_edited_3_plus_times(self):
        # Same file repeated 3 times
        gates = self._run_with_log_output("hot.py\nhot.py\nhot.py\nother.py\n")
        self.assertEqual(gates["ROOT_CAUSE"]["status"], "WARN")

    def test_root_cause_detail_names_hot_file(self):
        gates = self._run_with_log_output("hot.py\nhot.py\nhot.py\n")
        self.assertIn("hot.py", gates["ROOT_CAUSE"]["detail"])

    def test_root_cause_pass_when_file_edited_only_twice(self):
        gates = self._run_with_log_output("a.py\na.py\nb.py\nb.py\n")
        self.assertEqual(gates["ROOT_CAUSE"]["status"], "PASS")

    def test_root_cause_skip_when_git_not_found(self):
        status_mock = MagicMock()
        status_mock.stdout = ""
        oneline_mock = MagicMock()
        oneline_mock.stdout = "abc123 commit1\ndef456 commit2\n"
        with patch("framework.subprocess.run",
                   side_effect=[status_mock, FileNotFoundError(), oneline_mock]):
            gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["ROOT_CAUSE"]["status"], "SKIP")

    def test_root_cause_pass_detail_for_clean_history(self):
        gates = self._run_with_log_output("a.py\nb.py\n")
        self.assertIn("No repeated edits", gates["ROOT_CAUSE"]["detail"])


# ---------------------------------------------------------------------------
# run_gates() — MOMENTUM gate
# ---------------------------------------------------------------------------

class TestRunGatesMomentum(unittest.TestCase):
    """MOMENTUM gate checks commit frequency."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# P\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_with_commit_count(self, n: int) -> dict:
        """Mock git responses, setting MOMENTUM git log to n commits."""
        commits = "\n".join(f"abc{i} commit {i}" for i in range(n))
        status_mock = MagicMock()
        status_mock.stdout = ""
        log_mock = MagicMock()
        log_mock.stdout = ""
        oneline_mock = MagicMock()
        oneline_mock.stdout = commits
        with patch("framework.subprocess.run",
                   side_effect=[status_mock, log_mock, oneline_mock]):
            return framework.run_gates(self.tmp)

    def test_momentum_pass_with_two_or_more_commits(self):
        gates = self._run_with_commit_count(2)
        self.assertEqual(gates["MOMENTUM"]["status"], "PASS")

    def test_momentum_pass_with_five_commits(self):
        gates = self._run_with_commit_count(5)
        self.assertEqual(gates["MOMENTUM"]["status"], "PASS")

    def test_momentum_warn_with_one_commit(self):
        gates = self._run_with_commit_count(1)
        self.assertEqual(gates["MOMENTUM"]["status"], "WARN")

    def test_momentum_warn_with_zero_commits(self):
        gates = self._run_with_commit_count(0)
        self.assertEqual(gates["MOMENTUM"]["status"], "WARN")

    def test_momentum_detail_includes_commit_count(self):
        gates = self._run_with_commit_count(3)
        self.assertIn("3", gates["MOMENTUM"]["detail"])

    def test_momentum_skip_when_git_not_found(self):
        status_mock = MagicMock()
        status_mock.stdout = ""
        log_mock = MagicMock()
        log_mock.stdout = ""
        with patch("framework.subprocess.run",
                   side_effect=[status_mock, log_mock, FileNotFoundError()]):
            gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["MOMENTUM"]["status"], "SKIP")


# ---------------------------------------------------------------------------
# run_gates() — all gates present in result
# ---------------------------------------------------------------------------

class TestRunGatesOutputStructure(unittest.TestCase):
    """run_gates() always returns the 4 required gate keys."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# P\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_four_gates_present(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            gates = framework.run_gates(self.tmp)
        self.assertIn("EXIST", gates)
        self.assertIn("RELEVANCE", gates)
        self.assertIn("ROOT_CAUSE", gates)
        self.assertIn("MOMENTUM", gates)

    def test_each_gate_has_status_and_detail(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            gates = framework.run_gates(self.tmp)
        for gate_name, gate_data in gates.items():
            self.assertIn("status", gate_data, f"Gate {gate_name} missing 'status'")
            self.assertIn("detail", gate_data, f"Gate {gate_name} missing 'detail'")

    def test_each_gate_status_is_valid_value(self):
        valid_statuses = {"PASS", "FAIL", "WARN", "SKIP"}
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            gates = framework.run_gates(self.tmp)
        for gate_name, gate_data in gates.items():
            self.assertIn(gate_data["status"], valid_statuses,
                          f"Gate {gate_name} has invalid status {gate_data['status']!r}")


# ---------------------------------------------------------------------------
# run_self_assessment() — bound_compliance
# ---------------------------------------------------------------------------

class TestRunSelfAssessmentBoundCompliance(unittest.TestCase):
    """bound_compliance check in self-assessment."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bound_compliance_pass_with_bound_section(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules here\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "PASS")

    def test_bound_compliance_pass_with_danger_zone(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "DANGER ZONE: avoid db\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "PASS")

    def test_bound_compliance_pass_with_iron_law(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "IRON LAW: always test\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "PASS")

    def test_bound_compliance_pass_with_single_hash_bound(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# BOUND\nrules\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "PASS")

    def test_bound_compliance_warn_when_claude_md_has_no_bound_markers(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Just a readme\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "WARN")

    def test_bound_compliance_skip_when_no_claude_md(self):
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["bound_compliance"]["status"], "SKIP")

    def test_bound_compliance_detail_mentions_found_when_pass(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertIn("found", checks["bound_compliance"]["detail"].lower())

    def test_bound_compliance_detail_informative_on_warn(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# unrelated\n")
        checks = framework.run_self_assessment(self.tmp)
        self.assertGreater(len(checks["bound_compliance"]["detail"]), 0)


# ---------------------------------------------------------------------------
# run_self_assessment() — tests_exist
# ---------------------------------------------------------------------------

class TestRunSelfAssessmentTestsExist(unittest.TestCase):
    """tests_exist check in self-assessment."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tests_exist_pass_when_test_file_present(self):
        _write(os.path.join(self.tmp, "test_main.py"), "")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["tests_exist"]["status"], "PASS")

    def test_tests_exist_pass_when_spec_file_present(self):
        _write(os.path.join(self.tmp, "app.spec.js"), "")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["tests_exist"]["status"], "PASS")

    def test_tests_exist_warn_when_no_test_files(self):
        _write(os.path.join(self.tmp, "main.py"), "")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["tests_exist"]["status"], "WARN")

    def test_tests_exist_pass_in_subdirectory(self):
        _write(os.path.join(self.tmp, "tests", "test_api.py"), "")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["tests_exist"]["status"], "PASS")

    def test_tests_exist_detail_informative_on_warn(self):
        checks = framework.run_self_assessment(self.tmp)
        self.assertGreater(len(checks["tests_exist"]["detail"]), 0)

    def test_tests_exist_ouro_dir_not_scanned(self):
        # Files in .ouro should not influence test detection
        _write(os.path.join(self.tmp, ".ouro", "test_internal.py"), "")
        checks = framework.run_self_assessment(self.tmp)
        self.assertEqual(checks["tests_exist"]["status"], "WARN")


# ---------------------------------------------------------------------------
# run_self_assessment() — output structure
# ---------------------------------------------------------------------------

class TestRunSelfAssessmentStructure(unittest.TestCase):
    """run_self_assessment() always returns expected keys."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_both_check_keys_present(self):
        checks = framework.run_self_assessment(self.tmp)
        self.assertIn("bound_compliance", checks)
        self.assertIn("tests_exist", checks)

    def test_each_check_has_status_and_detail(self):
        checks = framework.run_self_assessment(self.tmp)
        for key, data in checks.items():
            self.assertIn("status", data, f"Check {key!r} missing 'status'")
            self.assertIn("detail", data, f"Check {key!r} missing 'detail'")

    def test_each_check_status_is_valid_value(self):
        valid_statuses = {"PASS", "FAIL", "WARN", "SKIP"}
        checks = framework.run_self_assessment(self.tmp)
        for key, data in checks.items():
            self.assertIn(data["status"], valid_statuses,
                          f"Check {key!r} has invalid status {data['status']!r}")


# ---------------------------------------------------------------------------
# run_verification() — overall verdict logic
# ---------------------------------------------------------------------------

class TestRunVerification(unittest.TestCase):
    """run_verification() aggregates gates and self-assessment into overall verdict."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_overall_pass_when_no_failures(self):
        # All gates PASS/WARN, no FAILs
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        _write(os.path.join(self.tmp, "test_something.py"), "")
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            results = framework.run_verification(self.tmp)
        self.assertEqual(results["overall"], "PASS")

    def test_overall_fail_when_gate_fails(self):
        # Force EXIST gate to FAIL by mocking run_gates directly
        _make_state(self.tmp, bound_defined=True)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        mock_result = MagicMock()
        mock_result.stdout = ""
        fake_gates = {
            "EXIST": {"status": "FAIL", "detail": "forced fail for test"},
        }
        with patch("framework.subprocess.run", return_value=mock_result), \
             patch("framework.run_gates", return_value=fake_gates):
            results = framework.run_verification(self.tmp)
        self.assertEqual(results["overall"], "FAIL")

    def test_result_has_timestamp(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            results = framework.run_verification(self.tmp)
        self.assertIn("timestamp", results)

    def test_result_has_layer1_gates(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            results = framework.run_verification(self.tmp)
        self.assertIn("layer1_gates", results)
        self.assertIsInstance(results["layer1_gates"], dict)

    def test_result_has_layer2_self(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            results = framework.run_verification(self.tmp)
        self.assertIn("layer2_self", results)
        self.assertIsInstance(results["layer2_self"], dict)

    def test_failures_key_populated_on_fail(self):
        # Force a genuine FAIL: create CLAUDE.md with bound markers so
        # bound_defined stays True, then mock run_gates to return a FAIL.
        _make_state(self.tmp, bound_defined=True)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        mock_result = MagicMock()
        mock_result.stdout = ""
        fake_gates = {
            "EXIST": {"status": "FAIL", "detail": "forced fail for test"},
        }
        with patch("framework.subprocess.run", return_value=mock_result), \
             patch("framework.run_gates", return_value=fake_gates):
            results = framework.run_verification(self.tmp)
        self.assertIn("failures", results)
        self.assertIsInstance(results["failures"], list)
        self.assertGreater(len(results["failures"]), 0)

    def test_failures_key_not_present_on_pass(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        _write(os.path.join(self.tmp, "test_something.py"), "")
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            results = framework.run_verification(self.tmp)
        # "failures" key should not appear when overall is PASS
        self.assertNotIn("failures", results)

    def test_warn_status_does_not_cause_overall_fail(self):
        # WARN gates must not flip overall to FAIL
        # No CLAUDE.md (EXIST=WARN) and no tests (tests_exist=WARN)
        _make_state(self.tmp, bound_defined=False)
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            results = framework.run_verification(self.tmp)
        # WARN should not cause FAIL
        self.assertEqual(results["overall"], "PASS")


# ---------------------------------------------------------------------------
# log_phase_result()
# ---------------------------------------------------------------------------

class TestLogPhaseResult(unittest.TestCase):
    """log_phase_result() writes TSV rows and updates state history."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _setup_project(self, **state_kwargs) -> str:
        """Create a minimal project ready for logging."""
        _make_state(self.tmp, **state_kwargs)
        # Create results TSV with header
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n")
        return self.tmp

    def _log_with_mocked_git(self, verdict: str, notes: str = "", **state_kwargs):
        """Run log_phase_result with all git calls mocked."""
        self._setup_project(**state_kwargs)
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, verdict, notes)

    def test_tsv_row_appended_after_log(self):
        self._log_with_mocked_git("PASS", current_phase=1, total_phases=3)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            lines = f.readlines()
        # Header + 1 data row
        self.assertEqual(len(lines), 2)

    def test_tsv_row_contains_verdict(self):
        self._log_with_mocked_git("FAIL", current_phase=2, total_phases=4)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            content = f.read()
        self.assertIn("FAIL", content)

    def test_tsv_row_contains_phase_string_with_slash(self):
        self._log_with_mocked_git("PASS", current_phase=1, total_phases=3)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            lines = f.readlines()
        data_row = lines[1]
        self.assertIn("1/3", data_row)

    def test_tsv_row_has_tab_separators(self):
        self._log_with_mocked_git("PASS", current_phase=1, total_phases=3)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            lines = f.readlines()
        data_row = lines[1]
        self.assertGreaterEqual(data_row.count("\t"), 4)

    def test_tsv_row_contains_notes(self):
        self._log_with_mocked_git("PASS", notes="all green", current_phase=1, total_phases=2)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            content = f.read()
        self.assertIn("all green", content)

    def test_history_entry_appended_to_state(self):
        self._log_with_mocked_git("PASS", current_phase=1, total_phases=3)
        state = framework.load_state(self.tmp)
        self.assertEqual(len(state["history"]), 1)

    def test_history_entry_has_correct_verdict(self):
        self._log_with_mocked_git("RETRY", current_phase=1, total_phases=3)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["history"][0]["verdict"], "RETRY")

    def test_history_entry_has_timestamp(self):
        self._log_with_mocked_git("PASS", current_phase=1, total_phases=3)
        state = framework.load_state(self.tmp)
        self.assertIn("timestamp", state["history"][0])

    def test_history_capped_at_50_entries(self):
        # Seed state with 50 existing history entries
        existing = [{"verdict": "PASS", "timestamp": "t", "stage": "BUILD",
                     "phase": "1/1", "bound_violations": 0, "notes": ""}
                    for _ in range(50)]
        _make_state(self.tmp, current_phase=1, total_phases=3, history=existing)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n")
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS")
        state = framework.load_state(self.tmp)
        self.assertLessEqual(len(state["history"]), 50)

    def test_phase_str_uses_current_stage_when_no_phase_plan(self):
        # current_phase=None means no phase plan active
        self._log_with_mocked_git("PASS", current_phase=None, total_phases=0,
                                  current_stage="BOUND")
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            lines = f.readlines()
        data_row = lines[1]
        self.assertIn("BOUND", data_row)

    def test_multiple_logs_append_multiple_rows(self):
        self._setup_project(current_phase=1, total_phases=3)
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS")
            framework.log_phase_result(self.tmp, "FAIL")
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            lines = f.readlines()
        # header + 2 data rows
        self.assertEqual(len(lines), 3)


# ---------------------------------------------------------------------------
# advance_phase()
# ---------------------------------------------------------------------------

class TestAdvancePhase(unittest.TestCase):
    """advance_phase() increments current_phase and manages stage transitions."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_advance_increments_phase_by_one(self):
        _make_state(self.tmp, current_phase=1, total_phases=3)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_phase"], 2)

    def test_advance_sets_stage_to_build(self):
        _make_state(self.tmp, current_phase=1, total_phases=3, current_stage="VERIFY")
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "BUILD")

    def test_advance_past_last_phase_sets_loop_stage(self):
        _make_state(self.tmp, current_phase=3, total_phases=3)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "LOOP")

    def test_advance_past_last_phase_clears_current_phase(self):
        _make_state(self.tmp, current_phase=3, total_phases=3)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertIsNone(state["current_phase"])

    def test_advance_when_no_phase_plan_does_not_modify_state(self):
        _make_state(self.tmp, current_phase=None, total_phases=0)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        # Phase should still be None
        self.assertIsNone(state["current_phase"])

    def test_advance_from_phase_2_to_3(self):
        _make_state(self.tmp, current_phase=2, total_phases=5)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_phase"], 3)

    def test_advance_saves_updated_at(self):
        _make_state(self.tmp, current_phase=1, total_phases=3)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertIn("updated_at", state)

    def test_advance_exactly_at_boundary(self):
        # phase == total means all phases complete
        _make_state(self.tmp, current_phase=5, total_phases=5)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "LOOP")
        self.assertIsNone(state["current_phase"])

    def test_advance_phase_1_of_1(self):
        _make_state(self.tmp, current_phase=1, total_phases=1)
        framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "LOOP")


# ---------------------------------------------------------------------------
# check_bound()
# ---------------------------------------------------------------------------

class TestCheckBound(unittest.TestCase):
    """check_bound() inspects CLAUDE.md for the three BOUND sections."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _full_bound_content(self) -> str:
        return (
            "# My Project\n"
            "## BOUND\n"
            "### DANGER ZONES\npath/to/db — direct writes\n"
            "### NEVER DO\nNever delete prod data\n"
            "### IRON LAWS\nIRON LAW: all writes go through service layer\n"
        )

    def test_no_claude_md_returns_without_error(self):
        # Must not raise — just print a message
        try:
            framework.check_bound(self.tmp)
        except SystemExit:
            self.fail("check_bound raised SystemExit when CLAUDE.md missing")

    def test_template_content_detected(self):
        # Install-as-is template has [PROJECT_NAME] etc.
        src = os.path.join(PROJECT_ROOT, "templates", "CLAUDE.md.template")
        dst = os.path.join(self.tmp, "CLAUDE.md")
        shutil.copy2(src, dst)
        # Should print template warning without crashing
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("template", output.lower())

    def test_all_three_sections_present_prints_ready(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), self._full_bound_content())
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("BOUND fully defined", output)

    def test_danger_zone_marker_detected(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), self._full_bound_content())
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("[+]", output)

    def test_missing_section_shows_cross_marker(self):
        # NEVER DO missing
        content = (
            "# My Project\n"
            "DANGER ZONE: risky path\n"
            "IRON LAW: always test\n"
            # no NEVER DO
        )
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("[X]", output)

    def test_missing_section_names_missing_in_output(self):
        # Only DANGER ZONE present
        _write(os.path.join(self.tmp, "CLAUDE.md"), "DANGER ZONE: db\n")
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("Missing", output)

    def test_danger_zone_underscore_variant_detected(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "DANGER_ZONE: risky\nNEVER DO: bad\nIRON LAW: test\n")
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("BOUND fully defined", output)

    def test_never_do_underscore_variant_detected(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "DANGER ZONE: risky\nNEVER_DO: bad\nIRON LAW: test\n")
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("BOUND fully defined", output)

    def test_iron_law_underscore_variant_detected(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "DANGER ZONE: risky\nNEVER DO: bad\nIRON_LAW: test\n")
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        self.assertIn("BOUND fully defined", output)

    def test_empty_claude_md_all_three_missing(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "")
        captured = StringIO()
        with patch("sys.stdout", captured):
            framework.check_bound(self.tmp)
        output = captured.getvalue()
        # All three X marks should appear
        self.assertEqual(output.count("[X]"), 3)


# ---------------------------------------------------------------------------
# Integration: init -> log -> advance cycle
# ---------------------------------------------------------------------------

class TestIntegrationInitLogAdvance(unittest.TestCase):
    """End-to-end cycle: initialize, log results, advance phases."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_cycle_phase_advancement(self):
        """Initialize with 3 phases, advance through all of them."""
        import prepare as prep
        prep.init_ouro(self.tmp)

        # Manually set up a phase plan in state
        state = framework.load_state(self.tmp)
        state["current_phase"] = 1
        state["total_phases"] = 3
        state["current_stage"] = "BUILD"
        framework.save_state(self.tmp, state)

        # Create TSV
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n")

        mock_result = MagicMock()
        mock_result.stdout = ""

        # Phase 1 -> 2
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS", "phase 1 done")
        framework.advance_phase(self.tmp)

        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_phase"], 2)

        # Phase 2 -> 3
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS", "phase 2 done")
        framework.advance_phase(self.tmp)

        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_phase"], 3)

        # Phase 3 -> LOOP
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS", "phase 3 done")
        framework.advance_phase(self.tmp)

        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "LOOP")
        self.assertIsNone(state["current_phase"])
        self.assertEqual(len(state["history"]), 3)

    def test_tsv_has_correct_row_count_after_cycle(self):
        import prepare as prep
        prep.init_ouro(self.tmp)

        state = framework.load_state(self.tmp)
        state["current_phase"] = 1
        state["total_phases"] = 2
        framework.save_state(self.tmp, state)

        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n")

        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("framework.subprocess.run", return_value=mock_result):
            framework.log_phase_result(self.tmp, "PASS")
            framework.advance_phase(self.tmp)
            framework.log_phase_result(self.tmp, "PASS")
            framework.advance_phase(self.tmp)

        with open(results_path) as f:
            lines = f.readlines()
        # header + 2 data rows
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
