"""
Tests for new framework features:
- parse_claude_md() parser
- detect_complexity() routing
- _file_in_danger_zone() helper
- RECALL gate
- Layer 3 verification triggers
- advance_phase() edge cases
- run_verification() coordination
- prepare.py integration (init → scan → template)

Run with:
    python3 -m pytest tests/test_new_features.py -v
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
import prepare


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


FULL_CLAUDE_MD = """\
# CLAUDE.md

## BOUND

### DANGER ZONES
- `src/payments/` — payment processing logic
- `migrations/` — database migrations
- `auth/core.py` — authentication core

### NEVER DO
- Never use float for money calculations
- Never delete migration files
- Never bypass auth checks

### IRON LAWS
- All API responses must include request_id
- Test coverage must stay above 90%
- All database queries must use parameterized statements
"""


# ---------------------------------------------------------------------------
# parse_claude_md()
# ---------------------------------------------------------------------------

class TestParseClaude(unittest.TestCase):
    """parse_claude_md() correctly extracts BOUND sections."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_parse_extracts_danger_zones(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(result["danger_zones"],
                         ["src/payments/", "migrations/", "auth/core.py"])

    def test_full_parse_extracts_never_do(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(len(result["never_do"]), 3)
        self.assertIn("Never use float for money calculations",
                      result["never_do"])

    def test_full_parse_extracts_iron_laws(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(len(result["iron_laws"]), 3)
        self.assertIn("All API responses must include request_id",
                      result["iron_laws"])

    def test_has_bound_true_when_markers_present(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        result = framework.parse_claude_md(self.tmp)
        self.assertTrue(result["has_bound"])

    def test_has_bound_false_when_no_markers(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Just a project\n")
        result = framework.parse_claude_md(self.tmp)
        self.assertFalse(result["has_bound"])

    def test_missing_file_returns_empty(self):
        result = framework.parse_claude_md(self.tmp)
        self.assertFalse(result["has_bound"])
        self.assertEqual(result["danger_zones"], [])
        self.assertEqual(result["never_do"], [])
        self.assertEqual(result["iron_laws"], [])

    def test_raw_content_populated(self):
        content = "# Test\n## BOUND\nstuff"
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(result["raw_content"], content)

    def test_oserror_returns_empty(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        original_open = open

        def patched_open(path, *args, **kwargs):
            if "CLAUDE.md" in str(path):
                raise OSError("cannot read")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            result = framework.parse_claude_md(self.tmp)
        self.assertFalse(result["has_bound"])

    def test_partial_bound_only_danger_zones(self):
        content = "## BOUND\n### DANGER ZONES\n- `src/core/` — core logic\n"
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(result["danger_zones"], ["src/core/"])
        self.assertEqual(result["never_do"], [])
        self.assertEqual(result["iron_laws"], [])

    def test_danger_zone_with_multiple_backtick_items(self):
        content = ("### DANGER ZONES\n"
                   "- `src/a/` — thing A\n"
                   "- `src/b/` — thing B\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(result["danger_zones"], ["src/a/", "src/b/"])


# ---------------------------------------------------------------------------
# _file_in_danger_zone()
# ---------------------------------------------------------------------------

class TestFileInDangerZone(unittest.TestCase):
    """_file_in_danger_zone() matches file paths against zones."""

    def test_exact_prefix_match(self):
        result = framework._file_in_danger_zone(
            "src/payments/stripe.py", ["src/payments/"]
        )
        self.assertEqual(result, "src/payments/")

    def test_file_zone_segment_match_in_nested_path(self):
        """File zone 'auth/core.py' matches 'lib/auth/core.py' via segment subsequence."""
        result = framework._file_in_danger_zone(
            "lib/auth/core.py", ["auth/core.py"]
        )
        self.assertEqual(result, "auth/core.py")

    def test_no_match_returns_none(self):
        result = framework._file_in_danger_zone(
            "src/utils/helpers.py", ["src/payments/", "migrations/"]
        )
        self.assertIsNone(result)

    def test_empty_zones_returns_none(self):
        result = framework._file_in_danger_zone("any/file.py", [])
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# detect_complexity()
# ---------------------------------------------------------------------------

class TestDetectComplexity(unittest.TestCase):
    """detect_complexity() routes based on file count and DANGER ZONE."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_trivial_single_file_no_dz(self):
        result = framework.detect_complexity(self.tmp, ["file.py"], [])
        self.assertEqual(result["level"], "trivial")

    def test_trivial_no_files(self):
        result = framework.detect_complexity(self.tmp, [], [])
        self.assertEqual(result["level"], "trivial")

    def test_simple_two_files_no_dz(self):
        result = framework.detect_complexity(
            self.tmp, ["a.py", "b.py"], []
        )
        self.assertEqual(result["level"], "simple")

    def test_simple_three_files_no_dz(self):
        result = framework.detect_complexity(
            self.tmp, ["a.py", "b.py", "c.py"], []
        )
        self.assertEqual(result["level"], "simple")

    def test_complex_many_files_no_dz(self):
        files = [f"f{i}.py" for i in range(5)]
        result = framework.detect_complexity(self.tmp, files, [])
        self.assertEqual(result["level"], "complex")

    def test_complex_when_dz_touched(self):
        result = framework.detect_complexity(
            self.tmp,
            ["src/payments/stripe.py"],
            ["src/payments/"]
        )
        self.assertEqual(result["level"], "complex")

    def test_result_has_route_dict(self):
        result = framework.detect_complexity(self.tmp, ["a.py"], [])
        self.assertIn("route", result)
        self.assertIn("max_lines", result["route"])

    def test_result_has_reason(self):
        result = framework.detect_complexity(self.tmp, ["a.py"], [])
        self.assertIsInstance(result["reason"], str)
        self.assertGreater(len(result["reason"]), 0)


# ---------------------------------------------------------------------------
# RECALL gate
# ---------------------------------------------------------------------------

class TestRecallGate(unittest.TestCase):
    """RECALL gate checks BOUND constraint accessibility."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_recall_pass_when_full_bound(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        gates = framework.run_gates(self.tmp)
        self.assertIn("RECALL", gates)
        self.assertEqual(gates["RECALL"]["status"], "PASS")

    @patch("framework.subprocess.run")
    def test_recall_warn_when_no_bound(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["RECALL"]["status"], "WARN")

    @patch("framework.subprocess.run")
    def test_recall_warn_incomplete_bound(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        # BOUND exists but no IRON LAWS
        content = "## BOUND\n### DANGER ZONES\n- `src/` — core\n"
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        gates = framework.run_gates(self.tmp)
        self.assertEqual(gates["RECALL"]["status"], "WARN")
        self.assertIn("incomplete", gates["RECALL"]["detail"])

    @patch("framework.subprocess.run")
    def test_recall_detail_shows_counts(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        gates = framework.run_gates(self.tmp)
        self.assertIn("3 zones", gates["RECALL"]["detail"])
        self.assertIn("3 laws", gates["RECALL"]["detail"])


# ---------------------------------------------------------------------------
# Layer 3 verification triggers
# ---------------------------------------------------------------------------

class TestLayer3Triggers(unittest.TestCase):
    """_check_layer3_triggers() detects human review conditions."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_triggers_returns_not_required(self):
        results = {
            "layer1_gates": {
                "EXIST": {"status": "PASS"},
                "RELEVANCE": {"status": "PASS", "files": []},
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        self.assertFalse(review["required"])

    def test_danger_zone_files_trigger_review(self):
        results = {
            "layer1_gates": {
                "RELEVANCE": {
                    "status": "WARN",
                    "files": ["src/payments/stripe.py"],
                    "danger_zone_files": ["src/payments/stripe.py"],
                },
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        self.assertTrue(review["required"])
        self.assertTrue(any("DANGER ZONE" in r for r in review["reasons"]))

    def test_gate_failure_triggers_review(self):
        results = {
            "layer1_gates": {
                "EXIST": {"status": "FAIL", "detail": "missing"},
                "RELEVANCE": {"status": "PASS", "files": []},
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        self.assertTrue(review["required"])
        self.assertTrue(any("gate failed" in r for r in review["reasons"]))

    def test_consecutive_retries_trigger_review(self):
        _make_state(self.tmp, history=[
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ])
        results = {
            "layer1_gates": {
                "RELEVANCE": {"status": "PASS", "files": []},
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        self.assertTrue(review["required"])
        self.assertTrue(any("RETRY" in r for r in review["reasons"]))

    def test_two_retries_do_not_trigger(self):
        _make_state(self.tmp, history=[
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ])
        results = {
            "layer1_gates": {
                "RELEVANCE": {"status": "PASS", "files": []},
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        # Only RETRY check — no other triggers
        retry_reasons = [r for r in review["reasons"] if "RETRY" in r]
        self.assertEqual(len(retry_reasons), 0)


# ---------------------------------------------------------------------------
# run_verification() coordination
# ---------------------------------------------------------------------------

class TestRunVerificationCoordination(unittest.TestCase):
    """run_verification() correctly combines Layer 1+2+3 results."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_all_pass_returns_pass(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        results = framework.run_verification(self.tmp)
        self.assertEqual(results["overall"], "PASS")

    @patch("framework.subprocess.run")
    def test_has_layer3_key(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        results = framework.run_verification(self.tmp)
        self.assertIn("layer3_review", results)

    @patch("framework.subprocess.run")
    def test_gate_fail_sets_overall_fail(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _make_state(self.tmp, bound_defined=True)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        fake_gates = {"EXIST": {"status": "FAIL", "detail": "forced"}}
        with patch("framework.run_gates", return_value=fake_gates):
            results = framework.run_verification(self.tmp)
        self.assertEqual(results["overall"], "FAIL")
        self.assertIn("EXIST", results.get("failures", []))

    @patch("framework.subprocess.run")
    def test_failures_list_populated(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _make_state(self.tmp, bound_defined=True)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")
        fake_gates = {"EXIST": {"status": "FAIL", "detail": "forced"}}
        with patch("framework.run_gates", return_value=fake_gates):
            results = framework.run_verification(self.tmp)
        self.assertIsInstance(results.get("failures"), list)


# ---------------------------------------------------------------------------
# advance_phase() edge cases
# ---------------------------------------------------------------------------

class TestAdvancePhaseEdgeCases(unittest.TestCase):
    """Edge cases for advance_phase()."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_advance_with_total_zero(self):
        """total_phases=0 and current_phase=0 → goes to LOOP."""
        _make_state(self.tmp, current_phase=0, total_phases=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "LOOP")

    def test_advance_at_boundary_exactly_equal(self):
        """current_phase == total_phases → LOOP transition."""
        _make_state(self.tmp, current_phase=3, total_phases=3)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_stage"], "LOOP")
        self.assertIsNone(state["current_phase"])

    def test_advance_none_phase_prints_message(self):
        """No phase plan → message printed, state unchanged."""
        _make_state(self.tmp, current_phase=None, total_phases=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.advance_phase(self.tmp)
        output = buf.getvalue()
        self.assertIn("No phase plan", output)

    def test_advance_increments_correctly(self):
        """Normal case: phase increments by 1."""
        _make_state(self.tmp, current_phase=2, total_phases=5)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.advance_phase(self.tmp)
        state = framework.load_state(self.tmp)
        self.assertEqual(state["current_phase"], 3)
        self.assertEqual(state["current_stage"], "BUILD")


# ---------------------------------------------------------------------------
# log_phase_result() TSV error handling
# ---------------------------------------------------------------------------

class TestLogPhaseResultErrorHandling(unittest.TestCase):
    """log_phase_result() handles TSV write failures gracefully."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        # Create the results TSV
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_log_succeeds_normally(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS", "test note")
        self.assertIn("Logged", buf.getvalue())


# ---------------------------------------------------------------------------
# prepare.py integration tests
# ---------------------------------------------------------------------------

class TestPrepareIntegration(unittest.TestCase):
    """Integration test: init → scan → template flow."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_then_scan_consistent(self):
        """After init, scan should show bound_detected matching state."""
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        buf = StringIO()
        with patch("sys.stdout", buf):
            prepare.init_ouro(self.tmp)

        # State says bound_defined=True
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertTrue(state["bound_defined"])

        # Scan also says bound_detected=True
        scan = prepare.scan_project(self.tmp)
        self.assertTrue(scan["bound_detected"])

    def test_scan_populates_danger_zones(self):
        """scan_project() now fills danger_zones from parse_claude_md()."""
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        scan = prepare.scan_project(self.tmp)
        self.assertEqual(scan["danger_zones"],
                         ["src/payments/", "migrations/", "auth/core.py"])

    def test_scan_empty_danger_zones_without_claude_md(self):
        scan = prepare.scan_project(self.tmp)
        self.assertEqual(scan["danger_zones"], [])

    def test_template_then_scan_detects_bound(self):
        """After installing claude template, scan detects BOUND."""
        buf = StringIO()
        with patch("sys.stdout", buf):
            prepare.install_template("claude", self.tmp)

        scan = prepare.scan_project(self.tmp)
        self.assertTrue(scan["has_claude_md"])
        # Template has BOUND markers
        self.assertTrue(scan["bound_detected"])

    def test_init_scan_template_full_cycle(self):
        """Full cycle: template → init → scan → verify consistency."""
        # Install template
        buf = StringIO()
        with patch("sys.stdout", buf):
            prepare.install_template("claude", self.tmp)
            prepare.init_ouro(self.tmp)

        # Verify state exists and is valid
        state_path = os.path.join(self.tmp, ".ouro", "state.json")
        self.assertTrue(os.path.exists(state_path))
        with open(state_path) as f:
            state = json.load(f)
        self.assertEqual(state["current_stage"], "BOUND")

        # Verify scan matches
        scan = prepare.scan_project(self.tmp)
        self.assertTrue(scan["has_claude_md"])


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

class TestSharedConstants(unittest.TestCase):
    """Shared constants are accessible from both framework and prepare."""

    def test_bound_all_markers_includes_section_markers(self):
        for marker in framework.BOUND_SECTION_MARKERS:
            self.assertIn(marker, framework.BOUND_ALL_MARKERS)

    def test_bound_all_markers_includes_content_markers(self):
        for marker in framework.BOUND_CONTENT_MARKERS:
            self.assertIn(marker, framework.BOUND_ALL_MARKERS)

    def test_claude_md_filename_constant(self):
        self.assertEqual(framework.CLAUDE_MD_FILENAME, "CLAUDE.md")

    def test_magic_constants_are_positive(self):
        self.assertGreater(framework.GIT_TIMEOUT_SECONDS, 0)
        self.assertGreater(framework.HOT_FILE_EDIT_THRESHOLD, 0)
        self.assertGreater(framework.HISTORY_LIMIT, 0)
        self.assertGreater(framework.MAX_RETRY_BEFORE_ESCALATE, 0)


if __name__ == "__main__":
    unittest.main()
