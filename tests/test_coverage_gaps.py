"""
Tests covering previously untested code paths identified by coverage gap analysis.

Covers:
- run_verification() returning "REVIEW" overall
- _check_layer3_triggers() architectural complexity branch
- detect_complexity() architectural level
- build_reflective_entry() all 4 alert types (DRIFT, HOT FILES, SLOWING, STALLED)
- write_reflective_log() OSError recovery paths
- log_phase_result() TSV write OSError warning
- print_verification() REVIEW output branch
- print_reflective_summary() conditional branches (DZ, notes, stuck, hot files)
- parse_claude_md() star (*) list markers, DANGER ZONE singular form, end-of-file
- _scan_files() CI detection for .circleci and .gitlab-ci
- _file_in_danger_zone() edge cases (exact match, empty zone string)
- detect_patterns() velocity_trend UNKNOWN with < 4 entries
- read_reflective_log() last_n larger than actual entries
- show_status() edge cases
- check_bound() parsed details output

Run with:
    python3 -m pytest tests/test_coverage_gaps.py -v
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


# ---------------------------------------------------------------------------
# run_verification() → overall = "REVIEW"
# ---------------------------------------------------------------------------

class TestRunVerificationReviewPath(unittest.TestCase):
    """run_verification() returns overall='REVIEW' when review is required
    but no gates have failed."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_review_when_dz_touched_no_gate_fail(self, mock_run):
        """DANGER ZONE contact with no FAIL gates → overall = REVIEW."""
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "## BOUND\n### DANGER ZONES\n- `src/pay/` — payments\n"
               "### IRON LAWS\n- Rule 1\n")
        # Git status returns a file in DZ
        def side_effect(cmd, **kwargs):
            if "status" in cmd:
                return MagicMock(stdout=" M src/pay/stripe.py\n", returncode=0)
            return MagicMock(stdout="", returncode=0)
        mock_run.side_effect = side_effect

        results = framework.run_verification(self.tmp)
        self.assertEqual(results["overall"], "REVIEW")
        self.assertIn("review_reasons", results)
        self.assertTrue(len(results["review_reasons"]) > 0)

    @patch("framework.subprocess.run")
    def test_fail_takes_priority_over_review(self, mock_run):
        """Gate FAIL + review required → overall = FAIL, not REVIEW."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _make_state(self.tmp, bound_defined=True)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nrules\n")

        # Force a deterministic FAIL by mocking run_gates
        fake_gates = {
            "EXIST": {"status": "FAIL", "detail": "forced"},
            "RELEVANCE": {
                "status": "WARN",
                "files": ["src/x.py"],
                "danger_zone_files": ["src/x.py (zone: src/)"],
            },
        }
        with patch("framework.run_gates", return_value=fake_gates):
            results = framework.run_verification(self.tmp)
        # FAIL must take priority even when review is also required
        self.assertEqual(results["overall"], "FAIL")
        self.assertIn("EXIST", results["failures"])


# ---------------------------------------------------------------------------
# _check_layer3_triggers() — architectural complexity
# ---------------------------------------------------------------------------

class TestLayer3ArchitecturalComplexity(unittest.TestCase):
    """architectural complexity triggers Layer 3 review."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_architectural_complexity_triggers_review(self):
        """Files touching IRON area should trigger architectural review."""
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "## BOUND\n### DANGER ZONES\n- `IRON_config/` — law config\n"
               "### IRON LAWS\n- Law 1\n")
        results = {
            "layer1_gates": {
                "RELEVANCE": {
                    "status": "PASS",
                    "files": ["IRON_config/rules.py"],
                },
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        self.assertTrue(review["required"])
        self.assertTrue(any("Architectural" in r for r in review["reasons"]))

    def test_empty_changed_files_skips_complexity(self):
        results = {
            "layer1_gates": {
                "RELEVANCE": {"status": "PASS", "files": []},
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        # Should not crash and should not trigger architectural
        arch_reasons = [r for r in review["reasons"] if "Architectural" in r]
        self.assertEqual(len(arch_reasons), 0)

    def test_multiple_triggers_accumulate_reasons(self):
        """Multiple trigger conditions produce multiple reasons."""
        _make_state(self.tmp, history=[
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ])
        results = {
            "layer1_gates": {
                "EXIST": {"status": "FAIL", "detail": "missing"},
                "RELEVANCE": {
                    "status": "WARN",
                    "files": ["a.py"],
                    "danger_zone_files": ["a.py (zone: src/)"],
                },
            }
        }
        review = framework._check_layer3_triggers(self.tmp, results)
        self.assertTrue(review["required"])
        self.assertGreaterEqual(len(review["reasons"]), 3)


# ---------------------------------------------------------------------------
# detect_complexity() — architectural level
# ---------------------------------------------------------------------------

class TestDetectComplexityArchitectural(unittest.TestCase):
    """detect_complexity() correctly identifies architectural level."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_iron_in_dz_triggers_architectural(self):
        result = framework.detect_complexity(
            self.tmp,
            ["IRON_config/rules.py"],
            ["IRON_config/"]
        )
        self.assertEqual(result["level"], "architectural")
        self.assertIn("IRON LAW", result["reason"])

    def test_exactly_four_files_is_complex(self):
        """4 files without DZ contact → complex (boundary: > 3)."""
        result = framework.detect_complexity(
            self.tmp,
            ["a.py", "b.py", "c.py", "d.py"],
            []
        )
        self.assertEqual(result["level"], "complex")

    def test_default_none_args(self):
        """None args default to empty lists without crash."""
        result = framework.detect_complexity(self.tmp)
        self.assertEqual(result["level"], "trivial")


# ---------------------------------------------------------------------------
# build_reflective_entry() — all alert types
# ---------------------------------------------------------------------------

class TestBuildReflectiveEntryAlerts(unittest.TestCase):
    """All alert types are correctly triggered."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build_with_gates(self, gates, history=None):
        if history:
            _make_state(self.tmp, history=history)
        verification = {
            "layer1_gates": gates,
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        return framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )

    def test_drift_alert(self):
        gates = {
            "RELEVANCE": {
                "status": "WARN",
                "files": ["src/payments/x.py"],
                "danger_zone_files": ["src/payments/x.py"],
            }
        }
        entry = self._build_with_gates(gates)
        self.assertTrue(any("DRIFT" in a for a in entry["alerts"]))

    def test_hot_files_alert(self):
        gates = {
            "ROOT_CAUSE": {
                "status": "WARN",
                "detail": "Hot files: framework.py, prepare.py",
            }
        }
        entry = self._build_with_gates(gates)
        self.assertTrue(any("HOT FILES" in a for a in entry["alerts"]))

    def test_slowing_alert(self):
        """DECELERATING velocity → SLOWING alert (requires 6+ entries, > 0.3 swing)."""
        history = (
            [{"verdict": "PASS", "stage": "BUILD"}] * 3 +
            [{"verdict": "FAIL", "stage": "BUILD"}] * 3
        )
        entry = self._build_with_gates({}, history=history)
        self.assertTrue(any("SLOWING" in a for a in entry["alerts"]))

    def test_stalled_alert(self):
        """All failures → STALLED alert (requires 6+ entries)."""
        history = [{"verdict": "FAIL", "stage": "BUILD"}] * 6
        entry = self._build_with_gates({}, history=history)
        self.assertTrue(any("STALLED" in a for a in entry["alerts"]))

    def test_no_alerts_when_healthy(self):
        entry = self._build_with_gates({})
        self.assertEqual(entry["alerts"], [])

    def test_bound_violations_counted_in_what(self):
        gates = {
            "EXIST": {"status": "FAIL", "detail": "missing"},
            "RECALL": {"status": "FAIL", "detail": "no bound"},
        }
        verification = {
            "layer1_gates": gates,
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "FAIL",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "FAIL", verification
        )
        self.assertEqual(entry["what"]["bound_violations"], 2)

    def test_review_required_in_what(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": True, "reasons": ["DZ touched"]},
            "overall": "REVIEW",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        self.assertTrue(entry["what"]["review_required"])


# ---------------------------------------------------------------------------
# write_reflective_log() — OSError recovery
# ---------------------------------------------------------------------------

class TestWriteReflectiveLogOSError(unittest.TestCase):
    """write_reflective_log() handles filesystem errors gracefully."""

    def setUp(self):
        self.tmp = _make_tmp()
        os.makedirs(os.path.join(self.tmp, ".ouro"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_oserror_on_write_prints_warning(self):
        """OSError during write prints warning but doesn't crash."""
        entry = {"test": True}
        original_open = open

        def fail_on_tmp(path, *args, **kwargs):
            if str(path).endswith(".tmp"):
                raise OSError("disk full")
            return original_open(path, *args, **kwargs)

        buf = StringIO()
        with patch("builtins.open", side_effect=fail_on_tmp), \
             patch("sys.stdout", buf):
            framework.write_reflective_log(self.tmp, entry)
        self.assertIn("Warning", buf.getvalue())

    def test_ouro_dir_auto_created(self):
        """write creates .ouro/ if it doesn't exist."""
        new_tmp = _make_tmp()
        try:
            entry = {"test": True}
            framework.write_reflective_log(new_tmp, entry)
            self.assertTrue(os.path.exists(
                os.path.join(new_tmp, ".ouro", "reflective-log.jsonl")
            ))
        finally:
            shutil.rmtree(new_tmp, ignore_errors=True)

    def test_non_ascii_content_preserved(self):
        """Non-ASCII characters are preserved in JSONL output."""
        entry = {"notes": "Chinese characters: \u4e2d\u6587\u6d4b\u8bd5, symbol: \u2705"}
        framework.write_reflective_log(self.tmp, entry)
        entries = framework.read_reflective_log(self.tmp)
        self.assertIn("\u4e2d\u6587", entries[0]["notes"])


# ---------------------------------------------------------------------------
# log_phase_result() — TSV OSError path
# ---------------------------------------------------------------------------

class TestLogPhaseResultTSVError(unittest.TestCase):
    """log_phase_result() handles TSV write failures gracefully."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_tsv_oserror_prints_warning_continues(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        # Make results file path point to a directory (can't write)
        results_dir = os.path.join(self.tmp, "ouro-results.tsv")
        os.makedirs(results_dir, exist_ok=True)

        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS")
        output = buf.getvalue()
        self.assertIn("Warning", output)
        # But log still completes
        self.assertIn("Logged", output)


# ---------------------------------------------------------------------------
# print_verification() — REVIEW path
# ---------------------------------------------------------------------------

class TestPrintVerificationReview(unittest.TestCase):
    """print_verification() correctly formats REVIEW overall status."""

    def _capture(self, results):
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.print_verification(results)
        return buf.getvalue()

    def test_review_overall_shows_action(self):
        results = {
            "layer1_gates": {"EXIST": {"status": "PASS", "detail": "ok"}},
            "layer2_self": {},
            "layer3_review": {
                "required": True,
                "reasons": ["DANGER ZONE touched: src/pay/"],
            },
            "overall": "REVIEW",
        }
        output = self._capture(results)
        self.assertIn("Human review required", output)
        self.assertIn("REQUIRED", output)
        self.assertIn("DANGER ZONE", output)

    def test_layer3_not_required_shows_text(self):
        results = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        output = self._capture(results)
        self.assertIn("Not required", output)


# ---------------------------------------------------------------------------
# print_reflective_summary() — conditional branches
# ---------------------------------------------------------------------------

class TestPrintReflectiveSummaryBranches(unittest.TestCase):
    """Conditional output branches in print_reflective_summary()."""

    def setUp(self):
        self.tmp = _make_tmp()
        os.makedirs(os.path.join(self.tmp, ".ouro"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture(self, last_n=5):
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.print_reflective_summary(self.tmp, last_n)
        return buf.getvalue()

    def _write_entry(self, **overrides):
        base = {
            "timestamp": "2026-01-01T12:00:00+00:00",
            "iteration": 1,
            "what": {"stage": "BUILD", "phase": "1/3", "verdict": "PASS",
                     "overall": "PASS", "gates": {},
                     "changed_files": [], "danger_zone_contact": [],
                     "bound_violations": 0, "review_required": False},
            "why": {"complexity": "simple", "complexity_reason": "",
                    "review_reasons": [],
                    "bound_state": {"danger_zones": 0, "never_do": 0, "iron_laws": 0},
                    "notes": ""},
            "pattern": {"consecutive_failures": 0, "stuck_loop": False,
                        "velocity_trend": "STABLE", "retry_rate": 0.0,
                        "hot_files": [], "drift_signal": False},
            "alerts": [],
        }
        # Deep merge overrides
        for key, val in overrides.items():
            if isinstance(val, dict) and key in base and isinstance(base[key], dict):
                base[key].update(val)
            else:
                base[key] = val
        framework.write_reflective_log(self.tmp, base)

    def test_dz_contact_shown(self):
        self._write_entry(what={
            "stage": "BUILD", "phase": "1/3", "verdict": "PASS",
            "overall": "PASS", "gates": {},
            "changed_files": [], "bound_violations": 0,
            "review_required": False,
            "danger_zone_contact": ["src/payments/stripe.py"],
        })
        output = self._capture()
        self.assertIn("DZ contact", output)

    def test_notes_shown(self):
        self._write_entry(why={
            "complexity": "simple", "complexity_reason": "",
            "review_reasons": [],
            "bound_state": {"danger_zones": 0, "never_do": 0, "iron_laws": 0},
            "notes": "important context here",
        })
        output = self._capture()
        self.assertIn("important context here", output)

    def test_stuck_loop_shown(self):
        self._write_entry(pattern={
            "consecutive_failures": 3, "stuck_loop": True,
            "velocity_trend": "STALLED", "retry_rate": 1.0,
            "hot_files": [], "drift_signal": False,
        })
        output = self._capture()
        self.assertIn("STUCK LOOP DETECTED", output)

    def test_hot_files_shown(self):
        self._write_entry(pattern={
            "consecutive_failures": 0, "stuck_loop": False,
            "velocity_trend": "STABLE", "retry_rate": 0.0,
            "hot_files": ["framework.py", "prepare.py"], "drift_signal": False,
        })
        output = self._capture()
        self.assertIn("hot:", output)
        self.assertIn("framework.py", output)

    def test_trend_not_shown_with_two_entries(self):
        self._write_entry()
        self._write_entry(iteration=2)
        output = self._capture()
        self.assertNotIn("Trend:", output)


# ---------------------------------------------------------------------------
# parse_claude_md() — edge cases
# ---------------------------------------------------------------------------

class TestParseClaude_EdgeCases(unittest.TestCase):
    """parse_claude_md() edge cases: star markers, singular form, end-of-file."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_star_list_markers_in_never_do(self):
        content = ("### NEVER DO\n"
                   "* Never use float for money\n"
                   "* Never skip tests\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(len(result["never_do"]), 2)
        self.assertIn("Never use float for money", result["never_do"])

    def test_star_list_markers_in_iron_laws(self):
        content = ("### IRON LAWS\n"
                   "* All API responses include request_id\n"
                   "* Coverage > 90%\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(len(result["iron_laws"]), 2)

    def test_singular_danger_zone_header(self):
        content = ("### DANGER ZONE\n"
                   "- `src/core/` — core logic\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(result["danger_zones"], ["src/core/"])

    def test_section_at_end_of_file_no_trailing_header(self):
        content = ("### IRON LAWS\n"
                   "- Must always log audit trail\n"
                   "- Coverage never below 80%\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(len(result["iron_laws"]), 2)

    def test_empty_file_has_bound_false(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "")
        result = framework.parse_claude_md(self.tmp)
        self.assertFalse(result["has_bound"])

    def test_whitespace_only_file(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "   \n\n   \n")
        result = framework.parse_claude_md(self.tmp)
        self.assertFalse(result["has_bound"])

    def test_danger_zone_without_backticks_not_extracted(self):
        content = ("### DANGER ZONES\n"
                   "- src/payments/ — no backticks\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertEqual(result["danger_zones"], [])

    def test_h2_bound_header_triggers_has_bound(self):
        content = "## BOUND\nSome rules here\n"
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertTrue(result["has_bound"])

    def test_h1_bound_header_triggers_has_bound(self):
        content = "# BOUND\nSome rules here\n"
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        result = framework.parse_claude_md(self.tmp)
        self.assertTrue(result["has_bound"])


# ---------------------------------------------------------------------------
# _file_in_danger_zone() — edge cases
# ---------------------------------------------------------------------------

class TestFileInDangerZoneEdgeCases(unittest.TestCase):

    def test_exact_equality(self):
        result = framework._file_in_danger_zone(
            "src/payments/", ["src/payments/"]
        )
        self.assertEqual(result, "src/payments/")

    def test_empty_zone_string_skipped(self):
        """Empty string zone is safely skipped (no false positive)."""
        result = framework._file_in_danger_zone("any/file.py", [""])
        self.assertIsNone(result)

    def test_multiple_zones_returns_first_match(self):
        result = framework._file_in_danger_zone(
            "src/payments/stripe.py",
            ["src/", "src/payments/"]
        )
        # Should return first matching zone
        self.assertEqual(result, "src/")


# ---------------------------------------------------------------------------
# detect_patterns() — velocity UNKNOWN with < 4 entries
# ---------------------------------------------------------------------------

class TestDetectPatternsEdgeCases(unittest.TestCase):

    def test_velocity_unknown_with_three_entries(self):
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "UNKNOWN")

    def test_velocity_unknown_with_five_entries(self):
        """5 entries is below the 6-entry threshold — still UNKNOWN."""
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "UNKNOWN")

    def test_velocity_unknown_with_one_entry(self):
        history = [{"verdict": "PASS", "stage": "BUILD"}]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "UNKNOWN")

    def test_retry_rate_window_larger_than_history(self):
        history = [{"verdict": "RETRY", "stage": "BUILD"}]
        result = framework.detect_patterns(history)
        self.assertAlmostEqual(result["retry_rate"], 1.0)

    def test_root_cause_no_hot_files_prefix(self):
        """Detail without 'Hot files:' prefix → empty hot_files."""
        gates = {
            "ROOT_CAUSE": {
                "status": "PASS",
                "detail": "No repeated edits detected",
            }
        }
        result = framework.detect_patterns([], gates)
        self.assertEqual(result["hot_files"], [])


# ---------------------------------------------------------------------------
# read_reflective_log() — last_n edge cases
# ---------------------------------------------------------------------------

class TestReadReflectiveLogEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmp = _make_tmp()
        os.makedirs(os.path.join(self.tmp, ".ouro"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_last_n_larger_than_entries(self):
        for i in range(3):
            framework.write_reflective_log(
                self.tmp, {"iteration": i}
            )
        entries = framework.read_reflective_log(self.tmp, last_n=100)
        self.assertEqual(len(entries), 3)

    def test_read_oserror_returns_empty(self):
        log_path = os.path.join(self.tmp, ".ouro", "reflective-log.jsonl")
        _write(log_path, '{"a": 1}\n')
        original_open = open

        def fail_open(path, *args, **kwargs):
            if "reflective-log" in str(path):
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=fail_open):
            entries = framework.read_reflective_log(self.tmp)
        self.assertEqual(entries, [])


# ---------------------------------------------------------------------------
# _scan_files() — CI detection for .circleci and .gitlab-ci
# ---------------------------------------------------------------------------

class TestScanFilesCIDetection(unittest.TestCase):
    """CI detection covers all three CI directory conventions."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_circleci_detected(self):
        _write(os.path.join(self.tmp, ".circleci", "config.yml"), "version: 2\n")
        scan = prepare.scan_project(self.tmp)
        self.assertTrue(scan["has_ci"])

    def test_gitlab_ci_detected(self):
        # .gitlab-ci is a directory check in rel_root comparison
        _write(os.path.join(self.tmp, ".gitlab-ci", "pipeline.yml"), "stages:\n")
        scan = prepare.scan_project(self.tmp)
        self.assertTrue(scan["has_ci"])

    def test_github_workflows_detected(self):
        _write(os.path.join(self.tmp, ".github", "workflows", "ci.yml"), "name: CI\n")
        scan = prepare.scan_project(self.tmp)
        self.assertTrue(scan["has_ci"])


# ---------------------------------------------------------------------------
# show_status() — edge cases
# ---------------------------------------------------------------------------

class TestShowStatusEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_project_name_shows_unknown(self):
        _make_state(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "state.json")
        with open(state_path) as f:
            state = json.load(f)
        del state["project_name"]
        with open(state_path, "w") as f:
            json.dump(state, f)

        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.show_status(self.tmp)
        self.assertIn("Unknown", buf.getvalue())

    def test_phase_not_none_but_total_zero_shows_na(self):
        _make_state(self.tmp, current_phase=1, total_phases=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.show_status(self.tmp)
        self.assertIn("N/A", buf.getvalue())


# ---------------------------------------------------------------------------
# check_bound() — parsed details output
# ---------------------------------------------------------------------------

class TestCheckBoundParsedDetails(unittest.TestCase):

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_shows_parsed_danger_zones(self):
        content = ("## BOUND\n"
                   "### DANGER ZONES\n"
                   "- `src/payments/` — payments\n"
                   "- `migrations/` — DB schema\n"
                   "### NEVER DO\n- Never delete\n"
                   "### IRON LAWS\n- Coverage > 90%\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.check_bound(self.tmp)
        output = buf.getvalue()
        self.assertIn("Parsed DANGER ZONES: 2", output)
        self.assertIn("src/payments/", output)

    def test_shows_parsed_iron_laws(self):
        content = ("## BOUND\n"
                   "### DANGER ZONES\n- `src/` — core\n"
                   "### NEVER DO\n- Never skip\n"
                   "### IRON LAWS\n"
                   "- All APIs include request_id\n"
                   "- Coverage > 90%\n")
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.check_bound(self.tmp)
        output = buf.getvalue()
        self.assertIn("Parsed IRON LAWS: 2", output)

    def test_truncates_at_five_danger_zones(self):
        zones = "\n".join(f"- `zone{i}/` — zone {i}" for i in range(8))
        content = f"## BOUND\n### DANGER ZONES\n{zones}\n### NEVER DO\n- X\n### IRON LAWS\n- Y\n"
        _write(os.path.join(self.tmp, "CLAUDE.md"), content)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.check_bound(self.tmp)
        output = buf.getvalue()
        # Should show "Parsed DANGER ZONES: 8" but only list 5
        self.assertIn("Parsed DANGER ZONES: 8", output)
        self.assertIn("zone4/", output)
        self.assertNotIn("zone5/", output)


# ---------------------------------------------------------------------------
# log_phase_result() with SKIP verdict
# ---------------------------------------------------------------------------

class TestLogSkipVerdict(unittest.TestCase):

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_skip_verdict_logged(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "SKIP", "skipped phase")
        self.assertIn("Logged", buf.getvalue())
        # Verify TSV has SKIP
        with open(os.path.join(self.tmp, "ouro-results.tsv")) as f:
            content = f.read()
        self.assertIn("SKIP", content)


if __name__ == "__main__":
    unittest.main()
