"""
Regression tests for the 4 behavioral edge cases found in E2E testing:

1. init snapshot bound_defined doesn't update → verify now refreshes it
2. Single RETRY triggers DECELERATING → requires 6+ entries + 0.3 threshold
3. All WARN/SKIP gates → overall was PASS, now correctly WARN
4. DZ substring match "auth" vs "unauthorized.py" → path-segment matching

Run with:
    python3 -m pytest tests/test_edge_case_fixes.py -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import framework


def _make_tmp():
    return tempfile.mkdtemp()


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_state(project_path, **overrides):
    state = {
        "version": "0.1.0",
        "project_name": "test",
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
# Edge Case 1: bound_defined refresh
# ---------------------------------------------------------------------------

class TestBoundDefinedRefresh(unittest.TestCase):
    """verify refreshes bound_defined when CLAUDE.md is added after init."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run")
    def test_bound_defined_updated_when_claude_md_added(self, mock_run):
        """Init without BOUND → add CLAUDE.md → verify updates state."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _make_state(self.tmp, bound_defined=False)

        # Initially no BOUND
        state = framework.load_state(self.tmp)
        self.assertFalse(state["bound_defined"])

        # Now add CLAUDE.md with BOUND markers
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "## BOUND\n### DANGER ZONES\n- `src/` — core\n"
               "### IRON LAWS\n- Rule 1\n")

        # Run verify — should refresh bound_defined
        framework.run_verification(self.tmp)

        state = framework.load_state(self.tmp)
        self.assertTrue(state["bound_defined"])

    @patch("framework.subprocess.run")
    def test_bound_defined_cleared_when_claude_md_removed(self, mock_run):
        """Remove CLAUDE.md → verify clears bound_defined."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nstuff\n")
        _make_state(self.tmp, bound_defined=True)

        # Remove CLAUDE.md
        os.remove(os.path.join(self.tmp, "CLAUDE.md"))

        framework.run_verification(self.tmp)

        state = framework.load_state(self.tmp)
        self.assertFalse(state["bound_defined"])


# ---------------------------------------------------------------------------
# Edge Case 2: Single RETRY no longer triggers DECELERATING
# ---------------------------------------------------------------------------

class TestVelocitySensitivity(unittest.TestCase):
    """Single RETRY among passes should not trigger DECELERATING."""

    def test_single_retry_among_passes_is_unknown(self):
        """[PASS, PASS, PASS, RETRY] has only 4 entries → UNKNOWN."""
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "UNKNOWN")

    def test_single_retry_among_five_passes_is_unknown(self):
        """[PASS, PASS, PASS, PASS, RETRY] has 5 entries → still UNKNOWN."""
        history = [
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "PASS", "stage": "BUILD"},
            {"verdict": "RETRY", "stage": "BUILD"},
        ]
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "UNKNOWN")

    def test_genuine_deceleration_requires_clear_signal(self):
        """3 PASS then 3 FAIL → genuine DECELERATING (swing = 1.0 > 0.3)."""
        history = (
            [{"verdict": "PASS", "stage": "BUILD"}] * 3 +
            [{"verdict": "FAIL", "stage": "BUILD"}] * 3
        )
        result = framework.detect_patterns(history)
        self.assertEqual(result["velocity_trend"], "DECELERATING")

    def test_mild_variation_is_stable(self):
        """Alternating results within threshold → STABLE."""
        history = (
            [{"verdict": "PASS", "stage": "BUILD"}] * 2 +
            [{"verdict": "FAIL", "stage": "BUILD"}] * 1 +
            [{"verdict": "PASS", "stage": "BUILD"}] * 2 +
            [{"verdict": "FAIL", "stage": "BUILD"}] * 1
        )
        result = framework.detect_patterns(history)
        # first half: [P,P,F] = 0.67, second half: [P,P,F] = 0.67
        # diff = 0.0, within ±0.3 threshold → STABLE
        self.assertEqual(result["velocity_trend"], "STABLE")


# ---------------------------------------------------------------------------
# Edge Case 3: All WARN/SKIP → overall WARN
# ---------------------------------------------------------------------------

class TestOverallWarnWhenNoPass(unittest.TestCase):
    """Empty/unconfigured project should get overall=WARN, not PASS."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("framework.subprocess.run",
           side_effect=FileNotFoundError("no git"))
    def test_all_warn_skip_returns_overall_warn(self, mock_run):
        """No CLAUDE.md, no git, no tests → all WARN/SKIP → overall WARN."""
        results = framework.run_verification(self.tmp)
        self.assertEqual(results["overall"], "WARN")

    @patch("framework.subprocess.run")
    def test_mix_of_pass_and_warn_returns_pass(self, mock_run):
        """At least one PASS gate → overall PASS (not WARN)."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        _write(os.path.join(self.tmp, "CLAUDE.md"),
               "## BOUND\n### DANGER ZONES\n- `src/` — core\n"
               "### IRON LAWS\n- Rule 1\n")
        _write(os.path.join(self.tmp, "test_x.py"), "")
        results = framework.run_verification(self.tmp)
        # EXIST=PASS, so overall should be PASS not WARN
        self.assertEqual(results["overall"], "PASS")


# ---------------------------------------------------------------------------
# Edge Case 4: DZ substring false positive
# ---------------------------------------------------------------------------

class TestDangerZonePathSegmentMatching(unittest.TestCase):
    """Path-segment matching prevents false positives."""

    def test_auth_dir_does_not_match_unauthorized_file(self):
        """Zone 'auth/' must NOT match 'unauthorized.py'."""
        result = framework._file_in_danger_zone("unauthorized.py", ["auth/"])
        self.assertIsNone(result)

    def test_auth_dir_does_not_match_authenticated_dir(self):
        """Zone 'auth/' must NOT match 'authenticated/login.py'."""
        result = framework._file_in_danger_zone(
            "authenticated/login.py", ["auth/"]
        )
        self.assertIsNone(result)

    def test_auth_dir_matches_auth_subpath(self):
        """Zone 'auth/' correctly matches 'auth/login.py'."""
        result = framework._file_in_danger_zone("auth/login.py", ["auth/"])
        self.assertEqual(result, "auth/")

    def test_auth_dir_matches_nested_auth(self):
        """Zone 'auth/' matches 'src/auth/login.py' — prefix must match."""
        # "auth/" as a directory prefix only matches paths STARTING with "auth/"
        result = framework._file_in_danger_zone("src/auth/login.py", ["auth/"])
        # This should NOT match since "src/auth/login.py" doesn't start with "auth/"
        self.assertIsNone(result)

    def test_full_path_zone_matches_exactly(self):
        """Zone 'src/auth/' matches 'src/auth/login.py'."""
        result = framework._file_in_danger_zone(
            "src/auth/login.py", ["src/auth/"]
        )
        self.assertEqual(result, "src/auth/")

    def test_file_zone_matches_exact_file(self):
        """Zone 'auth/core.py' matches 'auth/core.py' exactly."""
        result = framework._file_in_danger_zone(
            "auth/core.py", ["auth/core.py"]
        )
        self.assertEqual(result, "auth/core.py")

    def test_file_zone_matches_in_nested_path(self):
        """Zone 'auth/core.py' matches 'src/auth/core.py' via segment match."""
        result = framework._file_in_danger_zone(
            "src/auth/core.py", ["auth/core.py"]
        )
        self.assertEqual(result, "auth/core.py")

    def test_file_zone_does_not_match_partial_name(self):
        """Zone 'core.py' does NOT match 'hardcore.py'."""
        result = framework._file_in_danger_zone("hardcore.py", ["core.py"])
        self.assertIsNone(result)

    def test_migration_dir_matches_subfiles(self):
        """Zone 'migrations/' matches 'migrations/001_init.sql'."""
        result = framework._file_in_danger_zone(
            "migrations/001_init.sql", ["migrations/"]
        )
        self.assertEqual(result, "migrations/")

    def test_migration_dir_does_not_match_my_migrations(self):
        """Zone 'migrations/' does NOT match 'my_migrations/x.sql'."""
        result = framework._file_in_danger_zone(
            "my_migrations/x.sql", ["migrations/"]
        )
        self.assertIsNone(result)

    def test_empty_file_path_returns_none(self):
        result = framework._file_in_danger_zone("", ["auth/"])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
