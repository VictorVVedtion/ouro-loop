"""
Tests for the three-layer reflective logging system:
- detect_patterns() — behavioral pattern detection
- build_reflective_entry() — three-layer structured entry construction
- write_reflective_log() / read_reflective_log() — JSONL persistence
- print_reflective_summary() — human-readable output
- Integration with log_phase_result()

Run with:
    python3 -m pytest tests/test_reflective_log.py -v
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

### NEVER DO
- Never use float for money calculations
- Never delete migration files

### IRON LAWS
- All API responses must include request_id
- Test coverage must stay above 90%
"""


# ---------------------------------------------------------------------------
# detect_patterns()
# ---------------------------------------------------------------------------

class TestDetectPatterns(unittest.TestCase):
    """detect_patterns() identifies behavioral patterns in history."""

    def test_empty_history_returns_defaults(self):
        result = framework.detect_patterns([])
        self.assertEqual(result["consecutive_failures"], 0)
        self.assertFalse(result["stuck_loop"])
        self.assertEqual(result["velocity_trend"], "UNKNOWN")
        self.assertEqual(result["hot_files"], [])
        self.assertFalse(result["drift_signal"])
        self.assertEqual(result["retry_rate"], 0.0)

    def test_consecutive_failures_counted_from_tail(self):
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["consecutive_failures"], 3)

    def test_pass_breaks_consecutive_count(self):
        history = [
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["consecutive_failures"], 1)

    def test_retry_rate_calculated(self):
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertAlmostEqual(result["retry_rate"], 0.4, places=1)

    def test_stuck_loop_detected(self):
        history = [
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertTrue(result["stuck_loop"])

    def test_stuck_loop_not_detected_with_different_stages(self):
        history = [
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "VERIFY"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertFalse(result["stuck_loop"])

    def test_stuck_loop_not_detected_with_pass(self):
        history = [
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertFalse(result["stuck_loop"])

    def test_velocity_stable_with_consistent_passes(self):
        history = [{"verdict": "PASS", "stage": "BUILD"}] * 6
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "STABLE")

    def test_velocity_unknown_with_few_entries(self):
        """< 6 entries → UNKNOWN (avoids false DECELERATING from single RETRY)."""
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "UNKNOWN")

    def test_velocity_decelerating(self):
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "DECELERATING")

    def test_velocity_accelerating(self):
        history = [
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "ACCELERATING")

    def test_velocity_stalled(self):
        history = [{"verdict": "FAIL", "stage": "BUILD"}] * 6
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "STALLED")

    def test_hot_files_extracted_from_gates(self):
        gates = {
            "ROOT_CAUSE": {
                "status": "WARN",
                "detail": "Hot files: framework.py, prepare.py",
            }
        }
        result = framework.detect_patterns([], gates)
        self.assertEqual(result["hot_files"], ["framework.py", "prepare.py"])

    def test_drift_signal_from_danger_zone_files(self):
        gates = {
            "RELEVANCE": {
                "status": "WARN",
                "danger_zone_files": ["src/payments/stripe.py"],
            }
        }
        result = framework.detect_patterns([], gates)
        self.assertTrue(result["drift_signal"])

    def test_no_drift_without_dz_files(self):
        gates = {
            "RELEVANCE": {
                "status": "PASS",
                "files": ["utils.py"],
            }
        }
        result = framework.detect_patterns([], gates)
        self.assertFalse(result["drift_signal"])


# ---------------------------------------------------------------------------
# build_reflective_entry()
# ---------------------------------------------------------------------------

class TestBuildReflectiveEntry(unittest.TestCase):
    """build_reflective_entry() constructs a valid three-layer entry."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_entry_has_three_layers(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification, "test note"
        )
        self.assertIn("what", entry)
        self.assertIn("why", entry)
        self.assertIn("pattern", entry)

    def test_entry_has_timestamp(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        self.assertIn("timestamp", entry)
        self.assertIsInstance(entry["timestamp"], str)

    def test_what_layer_contains_verdict(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "FAIL", verification
        )
        self.assertEqual(entry["what"]["verdict"], "FAIL")

    def test_what_layer_contains_gates(self):
        verification = {
            "layer1_gates": {
                "EXIST": {"status": "PASS", "detail": "ok"},
                "RECALL": {"status": "WARN", "detail": "incomplete"},
            },
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        self.assertIn("EXIST", entry["what"]["gates"])
        self.assertEqual(entry["what"]["gates"]["EXIST"]["status"], "PASS")

    def test_why_layer_contains_complexity(self):
        verification = {
            "layer1_gates": {
                "RELEVANCE": {"status": "PASS", "detail": "2 files", "files": ["a.py", "b.py"]},
            },
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        self.assertIn(entry["why"]["complexity"],
                      ["trivial", "simple", "complex", "architectural"])

    def test_why_layer_contains_bound_state(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), FULL_CLAUDE_MD)
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        self.assertEqual(entry["why"]["bound_state"]["danger_zones"], 2)
        self.assertEqual(entry["why"]["bound_state"]["iron_laws"], 2)

    def test_why_layer_contains_notes(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification, "important context"
        )
        self.assertEqual(entry["why"]["notes"], "important context")

    def test_pattern_layer_has_required_fields(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        pattern = entry["pattern"]
        self.assertIn("consecutive_failures", pattern)
        self.assertIn("stuck_loop", pattern)
        self.assertIn("velocity_trend", pattern)
        self.assertIn("retry_rate", pattern)
        self.assertIn("hot_files", pattern)
        self.assertIn("drift_signal", pattern)

    def test_alerts_empty_when_healthy(self):
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        self.assertEqual(entry["alerts"], [])

    def test_alerts_populated_when_stuck(self):
        _make_state(self.tmp, history=[
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ])
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "FAIL",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "FAIL", verification
        )
        self.assertTrue(len(entry["alerts"]) > 0)
        self.assertTrue(any("STUCK" in a for a in entry["alerts"]))

    def test_alerts_on_consecutive_escalate(self):
        _make_state(self.tmp, history=[
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ])
        verification = {
            "layer1_gates": {},
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "FAIL",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "RETRY", verification
        )
        self.assertTrue(any("ESCALATE" in a for a in entry["alerts"]))

    def test_entry_is_json_serializable(self):
        verification = {
            "layer1_gates": {
                "EXIST": {"status": "PASS", "detail": "ok"},
            },
            "layer2_self": {},
            "layer3_review": {"required": False, "reasons": []},
            "overall": "PASS",
        }
        entry = framework.build_reflective_entry(
            self.tmp, "PASS", verification
        )
        # Must not raise
        serialized = json.dumps(entry, ensure_ascii=False)
        roundtrip = json.loads(serialized)
        self.assertEqual(roundtrip["what"]["verdict"], "PASS")


# ---------------------------------------------------------------------------
# write_reflective_log() / read_reflective_log()
# ---------------------------------------------------------------------------

class TestReflectiveLogPersistence(unittest.TestCase):
    """JSONL persistence for the reflective log."""

    def setUp(self):
        self.tmp = _make_tmp()
        os.makedirs(os.path.join(self.tmp, ".ouro"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_creates_file(self):
        entry = {"what": {"verdict": "PASS"}, "timestamp": "2026-01-01T00:00:00"}
        framework.write_reflective_log(self.tmp, entry)
        log_path = os.path.join(self.tmp, ".ouro", "reflective-log.jsonl")
        self.assertTrue(os.path.exists(log_path))

    def test_write_then_read_roundtrip(self):
        entry = {
            "what": {"verdict": "PASS"},
            "why": {"complexity": "simple"},
            "pattern": {"stuck_loop": False},
            "timestamp": "2026-01-01T00:00:00",
        }
        framework.write_reflective_log(self.tmp, entry)
        entries = framework.read_reflective_log(self.tmp)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["what"]["verdict"], "PASS")

    def test_multiple_writes_append(self):
        for i in range(3):
            entry = {"iteration": i, "timestamp": f"2026-01-0{i+1}T00:00:00"}
            framework.write_reflective_log(self.tmp, entry)
        entries = framework.read_reflective_log(self.tmp, last_n=10)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["iteration"], 0)
        self.assertEqual(entries[2]["iteration"], 2)

    def test_read_last_n_returns_subset(self):
        for i in range(10):
            entry = {"iteration": i, "timestamp": f"2026-01-{i+1:02d}T00:00:00"}
            framework.write_reflective_log(self.tmp, entry)
        entries = framework.read_reflective_log(self.tmp, last_n=3)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["iteration"], 7)
        self.assertEqual(entries[2]["iteration"], 9)

    def test_log_trimmed_to_limit(self):
        for i in range(framework.REFLECTIVE_LOG_LIMIT + 10):
            entry = {"iteration": i, "timestamp": f"2026-01-01T00:{i:02d}:00"}
            framework.write_reflective_log(self.tmp, entry)
        entries = framework.read_reflective_log(self.tmp, last_n=100)
        self.assertEqual(len(entries), framework.REFLECTIVE_LOG_LIMIT)
        # Oldest entries were trimmed
        self.assertEqual(entries[0]["iteration"], 10)

    def test_read_empty_returns_empty_list(self):
        entries = framework.read_reflective_log(self.tmp)
        self.assertEqual(entries, [])

    def test_read_nonexistent_dir_returns_empty_list(self):
        entries = framework.read_reflective_log("/nonexistent/path")
        self.assertEqual(entries, [])

    def test_corrupted_lines_skipped(self):
        log_path = os.path.join(self.tmp, ".ouro", "reflective-log.jsonl")
        with open(log_path, "w") as f:
            f.write('{"iteration": 0}\n')
            f.write('NOT VALID JSON\n')
            f.write('{"iteration": 1}\n')
        entries = framework.read_reflective_log(self.tmp, last_n=10)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["iteration"], 0)
        self.assertEqual(entries[1]["iteration"], 1)

    def test_each_line_is_valid_json(self):
        entry = {
            "what": {"verdict": "PASS"},
            "why": {"notes": "line with\nnewline should be escaped"},
            "timestamp": "2026-01-01T00:00:00",
        }
        framework.write_reflective_log(self.tmp, entry)
        log_path = os.path.join(self.tmp, ".ouro", "reflective-log.jsonl")
        with open(log_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertIn("\n", parsed["why"]["notes"])


# ---------------------------------------------------------------------------
# print_reflective_summary()
# ---------------------------------------------------------------------------

class TestPrintReflectiveSummary(unittest.TestCase):
    """print_reflective_summary() formats output correctly."""

    def setUp(self):
        self.tmp = _make_tmp()
        os.makedirs(os.path.join(self.tmp, ".ouro"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture(self, project_path, last_n=5) -> str:
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.print_reflective_summary(project_path, last_n)
        return buf.getvalue()

    def test_empty_log_shows_message(self):
        output = self._capture(self.tmp)
        self.assertIn("No reflective log", output)

    def test_single_entry_shows_what_why_pattern(self):
        entry = {
            "timestamp": "2026-01-01T12:00:00+00:00",
            "iteration": 1,
            "what": {
                "stage": "BUILD",
                "phase": "1/3",
                "verdict": "PASS",
                "overall": "PASS",
                "gates": {"EXIST": {"status": "PASS", "detail": "ok"}},
                "changed_files": [],
                "danger_zone_contact": [],
                "bound_violations": 0,
                "review_required": False,
            },
            "why": {
                "complexity": "simple",
                "complexity_reason": "2 files",
                "review_reasons": [],
                "bound_state": {"danger_zones": 2, "never_do": 2, "iron_laws": 2},
                "notes": "",
            },
            "pattern": {
                "consecutive_failures": 0,
                "stuck_loop": False,
                "velocity_trend": "STABLE",
                "retry_rate": 0.0,
                "hot_files": [],
                "drift_signal": False,
            },
            "alerts": [],
        }
        framework.write_reflective_log(self.tmp, entry)
        output = self._capture(self.tmp)
        self.assertIn("WHAT:", output)
        self.assertIn("WHY:", output)
        self.assertIn("PATTERN:", output)
        self.assertIn("BUILD", output)
        self.assertIn("PASS", output)

    def test_alerts_shown_in_output(self):
        entry = {
            "timestamp": "2026-01-01T12:00:00+00:00",
            "iteration": 1,
            "what": {"stage": "BUILD", "phase": "1/3", "verdict": "FAIL",
                     "overall": "FAIL", "gates": {},
                     "changed_files": [], "danger_zone_contact": [],
                     "bound_violations": 0, "review_required": False},
            "why": {"complexity": "simple", "complexity_reason": "",
                    "review_reasons": [],
                    "bound_state": {"danger_zones": 0, "never_do": 0, "iron_laws": 0},
                    "notes": ""},
            "pattern": {"consecutive_failures": 3, "stuck_loop": True,
                        "velocity_trend": "STALLED", "retry_rate": 1.0,
                        "hot_files": [], "drift_signal": False},
            "alerts": ["STUCK: same stage failing 3+ times"],
        }
        framework.write_reflective_log(self.tmp, entry)
        output = self._capture(self.tmp)
        self.assertIn("STUCK", output)

    def test_trend_shown_with_multiple_entries(self):
        for i in range(5):
            entry = {
                "timestamp": f"2026-01-0{i+1}T12:00:00+00:00",
                "iteration": i + 1,
                "what": {"stage": "BUILD", "phase": f"{i+1}/5",
                         "verdict": "PASS", "overall": "PASS",
                         "gates": {}, "changed_files": [],
                         "danger_zone_contact": [], "bound_violations": 0,
                         "review_required": False},
                "why": {"complexity": "simple", "complexity_reason": "",
                        "review_reasons": [],
                        "bound_state": {"danger_zones": 0, "never_do": 0, "iron_laws": 0},
                        "notes": ""},
                "pattern": {"consecutive_failures": 0, "stuck_loop": False,
                            "velocity_trend": "STABLE", "retry_rate": 0.0,
                            "hot_files": [], "drift_signal": False},
                "alerts": [],
            }
            framework.write_reflective_log(self.tmp, entry)
        output = self._capture(self.tmp)
        self.assertIn("Trend:", output)
        self.assertIn("Velocity:", output)


# ---------------------------------------------------------------------------
# Integration: log_phase_result() writes reflective log
# ---------------------------------------------------------------------------

class TestLogPhaseResultReflectiveIntegration(unittest.TestCase):
    """log_phase_result() now also writes to the reflective log."""

    def setUp(self):
        self.tmp = _make_tmp()
        _make_state(self.tmp)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path, "w") as f:
            f.write("phase\tverdict\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_log_creates_reflective_entry(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS", "test integration")
        entries = framework.read_reflective_log(self.tmp)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["what"]["verdict"], "PASS")

    @patch("framework.subprocess.run")
    def test_log_reflective_has_three_layers(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS")
        entries = framework.read_reflective_log(self.tmp)
        entry = entries[0]
        self.assertIn("what", entry)
        self.assertIn("why", entry)
        self.assertIn("pattern", entry)
        self.assertIn("alerts", entry)

    @patch("framework.subprocess.run")
    def test_multiple_logs_create_multiple_entries(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS", "first")
            framework.log_phase_result(self.tmp, "FAIL", "second")
            framework.log_phase_result(self.tmp, "RETRY", "third")
        entries = framework.read_reflective_log(self.tmp)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["what"]["verdict"], "PASS")
        self.assertEqual(entries[1]["what"]["verdict"], "FAIL")
        self.assertEqual(entries[2]["what"]["verdict"], "RETRY")

    @patch("framework.subprocess.run")
    def test_log_alerts_printed_to_stdout(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        # Create history with consecutive failures to trigger alerts
        _make_state(self.tmp, history=[
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
            {"verdict": "FAIL", "stage": "BUILD"},
        ])
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "FAIL", "still failing")
        output = buf.getvalue()
        self.assertIn(">>", output)

    @patch("framework.subprocess.run")
    def test_reflective_notes_preserved(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS", "important context here")
        entries = framework.read_reflective_log(self.tmp)
        self.assertEqual(entries[0]["why"]["notes"], "important context here")

    @patch("framework.subprocess.run")
    def test_reflective_iteration_increments(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        buf = StringIO()
        with patch("sys.stdout", buf):
            framework.log_phase_result(self.tmp, "PASS", "first")
            framework.log_phase_result(self.tmp, "PASS", "second")
        entries = framework.read_reflective_log(self.tmp)
        # Iteration numbers should increment
        self.assertEqual(entries[0]["iteration"], 1)
        self.assertEqual(entries[1]["iteration"], 2)


if __name__ == "__main__":
    unittest.main()
