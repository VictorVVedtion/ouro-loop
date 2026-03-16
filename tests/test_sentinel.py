"""
Tests for sentinel.py — partition scanning, command detection, config,
template rendering, init flow, and status display.

Run with:
    python -m pytest tests/test_sentinel.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import sentinel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tmp() -> str:
    return tempfile.mkdtemp()


def _write(path: str, content: str = ""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_project(tmp: str, files: dict = None, claude_md: str = None):
    """Create a minimal project structure."""
    if claude_md:
        _write(os.path.join(tmp, "CLAUDE.md"), claude_md)
    if files:
        for rel_path, content in files.items():
            _write(os.path.join(tmp, rel_path), content)


def _make_sentinel_state(tmp: str, **overrides):
    """Create a sentinel state file."""
    sdir = os.path.join(tmp, ".ouro", "sentinel")
    os.makedirs(sdir, exist_ok=True)
    state = sentinel._init_state()
    state.update(overrides)
    with open(os.path.join(sdir, "state.json"), "w") as f:
        json.dump(state, f, indent=2)
    return state


# ---------------------------------------------------------------------------
# TestCommandDetection
# ---------------------------------------------------------------------------


class TestCommandDetection(unittest.TestCase):
    """detect_commands() identifies build/test/lint from marker files."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_python_project(self):
        _write(os.path.join(self.tmp, "pyproject.toml"), "[project]\nname='x'")
        cmds = sentinel.detect_commands(self.tmp)
        self.assertIsNone(cmds["build"])
        self.assertEqual(cmds["test"], "python -m pytest")
        self.assertEqual(cmds["lint"], "ruff check .")

    def test_go_project(self):
        _write(os.path.join(self.tmp, "go.mod"), "module example.com/x")
        cmds = sentinel.detect_commands(self.tmp)
        self.assertEqual(cmds["build"], "go build ./...")
        self.assertEqual(cmds["test"], "go test ./...")
        self.assertEqual(cmds["lint"], "go vet ./...")

    def test_node_project(self):
        _write(os.path.join(self.tmp, "package.json"), '{"name":"x"}')
        cmds = sentinel.detect_commands(self.tmp)
        self.assertEqual(cmds["build"], "npm run build")
        self.assertEqual(cmds["test"], "npm test")
        self.assertEqual(cmds["lint"], "npx eslint .")

    def test_rust_project(self):
        _write(os.path.join(self.tmp, "Cargo.toml"), "[package]\nname='x'")
        cmds = sentinel.detect_commands(self.tmp)
        self.assertEqual(cmds["build"], "cargo build")
        self.assertEqual(cmds["test"], "cargo test")
        self.assertEqual(cmds["lint"], "cargo clippy")

    def test_no_markers(self):
        cmds = sentinel.detect_commands(self.tmp)
        self.assertIsNone(cmds["build"])
        self.assertIsNone(cmds["test"])
        self.assertIsNone(cmds["lint"])

    def test_multiple_markers_priority(self):
        """First match in priority order wins."""
        _write(os.path.join(self.tmp, "go.mod"), "module x")
        _write(os.path.join(self.tmp, "Makefile"), "build:\n\tgo build")
        cmds = sentinel.detect_commands(self.tmp)
        # go.mod has higher priority than Makefile
        self.assertEqual(cmds["build"], "go build ./...")

    def test_makefile_only(self):
        _write(os.path.join(self.tmp, "Makefile"), "build:\n\techo build")
        cmds = sentinel.detect_commands(self.tmp)
        self.assertEqual(cmds["build"], "make build")
        self.assertEqual(cmds["test"], "make test")
        self.assertEqual(cmds["lint"], "make lint")


# ---------------------------------------------------------------------------
# TestPartitionScanner
# ---------------------------------------------------------------------------


class TestPartitionScanner(unittest.TestCase):
    """generate_partitions() scans project into risk-scored partitions."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_project(self):
        result = sentinel.generate_partitions(self.tmp)
        self.assertEqual(result["total_partitions"], 0)
        self.assertEqual(result["partitions"], [])

    def test_single_directory(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print('hello')\n")
        result = sentinel.generate_partitions(self.tmp)
        self.assertEqual(result["total_partitions"], 1)
        self.assertEqual(result["partitions"][0]["id"], "src")
        self.assertEqual(result["partitions"][0]["file_count"], 1)

    def test_multiple_directories(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\n")
        _write(os.path.join(self.tmp, "tests", "test_main.py"), "assert True\n")
        _write(os.path.join(self.tmp, "docs", "readme.md"), "# Docs\n")
        result = sentinel.generate_partitions(self.tmp)
        ids = [p["id"] for p in result["partitions"]]
        self.assertIn("src", ids)
        self.assertIn("tests", ids)

    def test_danger_zone_criticality(self):
        """Partitions overlapping DANGER ZONES get 'high' criticality."""
        _write(os.path.join(self.tmp, "auth", "login.py"), "def login(): pass\n")
        _write(
            os.path.join(self.tmp, "CLAUDE.md"),
            "## BOUND\n### DANGER ZONES\n- `auth/`\n",
        )
        result = sentinel.generate_partitions(self.tmp)
        auth_part = next(p for p in result["partitions"] if p["id"] == "auth")
        self.assertEqual(auth_part["criticality"], "high")
        self.assertIn("DANGER ZONE", auth_part["criticality_reason"])

    def test_skip_dirs(self):
        """SKIP_DIRS are not included as partitions."""
        _write(os.path.join(self.tmp, "node_modules", "pkg", "index.js"), "var x=1;")
        _write(os.path.join(self.tmp, "src", "app.js"), "console.log(1);")
        result = sentinel.generate_partitions(self.tmp)
        ids = [p["id"] for p in result["partitions"]]
        self.assertNotIn("node_modules", ids)
        self.assertIn("src", ids)

    @patch("sentinel._git_activity", return_value=0)
    def test_git_unavailable_degradation(self, mock_git):
        """Partitions still work when git is unavailable."""
        _write(os.path.join(self.tmp, "lib", "utils.py"), "def util(): pass\n")
        result = sentinel.generate_partitions(self.tmp)
        self.assertEqual(result["total_partitions"], 1)
        self.assertEqual(result["partitions"][0]["activity"], 0)

    def test_loc_counted(self):
        content = "\n".join(f"line {i}" for i in range(50))
        _write(os.path.join(self.tmp, "src", "big.py"), content)
        result = sentinel.generate_partitions(self.tmp)
        src_part = next(p for p in result["partitions"] if p["id"] == "src")
        self.assertEqual(src_part["loc"], 50)

    def test_language_detection(self):
        _write(os.path.join(self.tmp, "src", "app.py"), "x = 1\n")
        _write(os.path.join(self.tmp, "src", "util.py"), "y = 2\n")
        _write(os.path.join(self.tmp, "src", "index.js"), "var z = 3;\n")
        result = sentinel.generate_partitions(self.tmp)
        src_part = next(p for p in result["partitions"] if p["id"] == "src")
        self.assertEqual(src_part["languages"]["Python"], 2)
        self.assertEqual(src_part["languages"]["JavaScript"], 1)

    def test_no_double_counting_loc(self):
        """Parent partition should not include child partition's LOC."""
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\nx = 2\n")
        _write(os.path.join(self.tmp, "src", "auth", "login.py"), "y = 1\n")
        result = sentinel.generate_partitions(self.tmp)
        src_part = next(p for p in result["partitions"] if p["id"] == "src")
        auth_part = next(p for p in result["partitions"] if p["id"] == "src/auth")
        # src should only count main.py (2 lines), not auth/login.py
        self.assertEqual(src_part["loc"], 2)
        self.assertEqual(src_part["file_count"], 1)
        # src/auth should count login.py (1 line)
        self.assertEqual(auth_part["loc"], 1)
        self.assertEqual(auth_part["file_count"], 1)
        # No double counting: sum equals actual
        total_loc = sum(p["loc"] for p in result["partitions"])
        self.assertEqual(total_loc, 3)

    def test_criticality_overrides(self):
        _write(os.path.join(self.tmp, "utils", "helper.py"), "pass\n")
        config = {"partitioning": {"criticality_overrides": {"utils": "high"}}}
        result = sentinel.generate_partitions(self.tmp, config)
        utils_part = next(p for p in result["partitions"] if p["id"] == "utils")
        self.assertEqual(utils_part["criticality"], "high")
        self.assertEqual(utils_part["criticality_reason"], "manual override")


# ---------------------------------------------------------------------------
# TestSentinelConfig
# ---------------------------------------------------------------------------


class TestSentinelConfig(unittest.TestCase):
    """Config generation and validation."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_config(self):
        _write(os.path.join(self.tmp, "pyproject.toml"), "[project]\nname='x'")
        config = sentinel.generate_config(self.tmp)
        self.assertEqual(config["version"], sentinel.VERSION)
        self.assertEqual(config["commands"]["test"], "python -m pytest")

    def test_validate_valid_config(self):
        config = json.loads(json.dumps(sentinel.DEFAULT_CONFIG))
        config["project_name"] = "test"
        issues = sentinel.validate_config(config)
        self.assertEqual(issues, [])

    def test_validate_missing_version(self):
        config = {
            "commands": {},
            "review": {
                "max_fix_attempts": 3,
                "confidence_threshold": 0.8,
                "fix_confidence_threshold": 0.9,
            },
            "runner": {},
        }
        del config["commands"]  # also missing commands
        issues = sentinel.validate_config(config)
        self.assertIn("missing 'version' field", issues)

    def test_validate_bad_confidence(self):
        config = json.loads(json.dumps(sentinel.DEFAULT_CONFIG))
        config["review"]["confidence_threshold"] = 0
        issues = sentinel.validate_config(config)
        self.assertTrue(any("confidence_threshold" in i for i in issues))

    def test_validate_bad_fix_attempts(self):
        config = json.loads(json.dumps(sentinel.DEFAULT_CONFIG))
        config["review"]["max_fix_attempts"] = 0
        issues = sentinel.validate_config(config)
        self.assertTrue(any("max_fix_attempts" in i for i in issues))

    def test_load_config_missing(self):
        result = sentinel.load_config(self.tmp)
        self.assertIsNone(result)

    def test_load_config_valid(self):
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        os.makedirs(sdir, exist_ok=True)
        config = {"version": "0.1.0", "test": True}
        with open(os.path.join(sdir, "sentinel-config.json"), "w") as f:
            json.dump(config, f)
        result = sentinel.load_config(self.tmp)
        self.assertEqual(result["test"], True)

    def test_load_config_corrupted(self):
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "sentinel-config.json"), "w") as f:
            f.write("not json{{{")
        result = sentinel.load_config(self.tmp)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TestTemplateRendering
# ---------------------------------------------------------------------------


class TestTemplateRendering(unittest.TestCase):
    """Template rendering with placeholder replacement."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_with_bound(self):
        _write(
            os.path.join(self.tmp, "CLAUDE.md"),
            "## BOUND\n### DANGER ZONES\n- `auth/`\n- `db/`\n"
            "### NEVER DO\n- Never drop tables\n"
            "### IRON LAWS\n- All queries parameterized\n",
        )
        config = {
            "commands": {
                "build": "make build",
                "test": "make test",
                "lint": "make lint",
            }
        }
        partitions = {
            "total_partitions": 2,
            "partitions": [
                {
                    "id": "auth",
                    "loc": 100,
                    "file_count": 5,
                    "criticality": "high",
                    "criticality_reason": "DANGER ZONE",
                },
                {
                    "id": "src",
                    "loc": 200,
                    "file_count": 10,
                    "criticality": "low",
                    "criticality_reason": "default",
                },
            ],
        }
        result = sentinel.render_sentinel_claude_md(self.tmp, config, partitions)
        self.assertIn("auth/", result)
        self.assertIn("db/", result)
        self.assertIn("Never drop tables", result)
        self.assertIn("All queries parameterized", result)
        self.assertIn("make build", result)
        self.assertIn("make test", result)

    def test_render_missing_bound(self):
        """Graceful degradation when CLAUDE.md has no BOUND."""
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# My Project\nNo bound here.")
        config = {"commands": {"build": None, "test": None, "lint": None}}
        partitions = {"total_partitions": 0, "partitions": []}
        result = sentinel.render_sentinel_claude_md(self.tmp, config, partitions)
        self.assertIn("none defined", result)

    def test_render_no_claude_md(self):
        """Still renders when CLAUDE.md doesn't exist at all."""
        config = {"commands": {"build": None, "test": "pytest", "lint": None}}
        partitions = {"total_partitions": 0, "partitions": []}
        result = sentinel.render_sentinel_claude_md(self.tmp, config, partitions)
        self.assertIn("none defined", result)
        self.assertIn("pytest", result)

    def test_partition_summary_in_template(self):
        config = {"commands": {"build": None, "test": None, "lint": None}}
        partitions = {
            "total_partitions": 1,
            "partitions": [
                {
                    "id": "core",
                    "loc": 500,
                    "file_count": 20,
                    "criticality": "high",
                    "criticality_reason": "DANGER ZONE overlap",
                },
            ],
        }
        result = sentinel.render_sentinel_claude_md(self.tmp, config, partitions)
        self.assertIn("core", result)
        self.assertIn("500", result)


# ---------------------------------------------------------------------------
# TestSentinelInit
# ---------------------------------------------------------------------------


class TestSentinelInit(unittest.TestCase):
    """init_sentinel() creates complete sentinel setup."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_creates_directory(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        self.assertTrue(os.path.isdir(sdir))

    def test_init_creates_state(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "sentinel", "state.json")
        self.assertTrue(os.path.exists(state_path))
        with open(state_path) as f:
            state = json.load(f)
        self.assertEqual(state["current_iteration"], 0)
        self.assertEqual(state["status"], "initialized")

    def test_init_creates_config(self):
        _write(os.path.join(self.tmp, "pyproject.toml"), "[project]\nname='x'")
        sentinel.init_sentinel(self.tmp)
        config_path = os.path.join(
            self.tmp, ".ouro", "sentinel", "sentinel-config.json"
        )
        self.assertTrue(os.path.exists(config_path))
        with open(config_path) as f:
            config = json.load(f)
        self.assertEqual(config["commands"]["test"], "python -m pytest")

    def test_init_creates_partitions(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        part_path = os.path.join(self.tmp, ".ouro", "sentinel", "partitions.json")
        self.assertTrue(os.path.exists(part_path))
        with open(part_path) as f:
            parts = json.load(f)
        self.assertGreater(parts["total_partitions"], 0)

    def test_init_creates_claude_md(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        md_path = os.path.join(self.tmp, ".ouro", "sentinel", "CLAUDE.md")
        self.assertTrue(os.path.exists(md_path))
        with open(md_path) as f:
            content = f.read()
        self.assertIn("Sentinel", content)
        self.assertIn("Review Loop", content)

    def test_init_creates_empty_findings(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        findings = os.path.join(self.tmp, ".ouro", "sentinel", "findings.jsonl")
        self.assertTrue(os.path.exists(findings))

    def test_init_idempotent(self):
        """Second init does not overwrite existing state."""
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        # Modify state
        state_path = os.path.join(self.tmp, ".ouro", "sentinel", "state.json")
        with open(state_path) as f:
            state = json.load(f)
        state["current_iteration"] = 42
        with open(state_path, "w") as f:
            json.dump(state, f)
        # Run init again
        sentinel.init_sentinel(self.tmp)
        with open(state_path) as f:
            state = json.load(f)
        self.assertEqual(state["current_iteration"], 42)

    def test_init_creates_suppressed_json(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        path = os.path.join(self.tmp, ".ouro", "sentinel", "suppressed.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data, [])

    def test_init_creates_learnings_md(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        path = os.path.join(self.tmp, ".ouro", "sentinel", "learnings.md")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            content = f.read()
        self.assertIn("Sentinel Learnings", content)

    def test_init_state_has_session_fields(self):
        """New state schema includes session/fix tracking fields."""
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "sentinel", "state.json")
        with open(state_path) as f:
            state = json.load(f)
        self.assertEqual(state["session_count"], 0)
        self.assertEqual(state["fixes_attempted"], 0)
        self.assertEqual(state["fixes_merged"], 0)
        self.assertEqual(state["prs_created"], 0)
        self.assertIsInstance(state["partition_last_reviewed"], dict)
        self.assertIsNone(state["current_partition"])
        self.assertIsNone(state["last_session_exit"])


# ---------------------------------------------------------------------------
# TestSentinelStatus
# ---------------------------------------------------------------------------


class TestSentinelStatus(unittest.TestCase):
    """show_status() displays sentinel state."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_not_initialized(self):
        with self.assertRaises(SystemExit):
            sentinel.show_status(self.tmp)

    def test_status_shows_iteration(self):
        _make_sentinel_state(self.tmp, current_iteration=5, total_findings=3)
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("5", output)
        self.assertIn("3", output)

    def test_status_shows_severity_breakdown(self):
        _make_sentinel_state(
            self.tmp,
            total_findings=10,
            findings_by_severity={"CRITICAL": 2, "HIGH": 3, "MEDIUM": 4, "LOW": 1},
        )
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("CRITICAL: 2", output)


# ---------------------------------------------------------------------------
# TestSentinelState
# ---------------------------------------------------------------------------


class TestSentinelState(unittest.TestCase):
    """State load/save operations."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_state_missing(self):
        result = sentinel.load_sentinel_state(self.tmp)
        self.assertIsNone(result)

    def test_save_and_load_state(self):
        state = sentinel._init_state()
        state["current_iteration"] = 7
        sentinel.save_sentinel_state(self.tmp, state)
        loaded = sentinel.load_sentinel_state(self.tmp)
        self.assertEqual(loaded["current_iteration"], 7)
        self.assertIn("updated_at", loaded)

    def test_load_corrupted_state(self):
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        os.makedirs(sdir, exist_ok=True)
        with open(os.path.join(sdir, "state.json"), "w") as f:
            f.write("broken{{{")
        result = sentinel.load_sentinel_state(self.tmp)
        self.assertIsNone(result)

    @patch("sentinel.os.replace", side_effect=OSError("cross-device"))
    @patch("sentinel.shutil.move", side_effect=OSError("disk full"))
    def test_save_state_double_failure_cleans_tmp(self, _mock_move, _mock_replace):
        """os.replace fails, shutil.move fails → tmp cleaned, OSError raised."""
        state = sentinel._init_state()
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        os.makedirs(sdir, exist_ok=True)
        with self.assertRaises(OSError):
            sentinel.save_sentinel_state(self.tmp, state)
        # tmp file should be cleaned up
        tmp_path = os.path.join(sdir, "state.json.tmp")
        self.assertFalse(os.path.exists(tmp_path))

    @patch("sentinel.os.unlink", side_effect=OSError("permission denied"))
    @patch("sentinel.os.replace", side_effect=OSError("cross-device"))
    @patch("sentinel.shutil.move", side_effect=OSError("disk full"))
    def test_save_state_triple_failure(self, _mock_move, _mock_replace, _mock_unlink):
        """os.replace, shutil.move, os.unlink all fail → OSError raised."""
        state = sentinel._init_state()
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        os.makedirs(sdir, exist_ok=True)
        with self.assertRaises(OSError):
            sentinel.save_sentinel_state(self.tmp, state)

    @patch("sentinel.os.replace", side_effect=OSError("cross-device"))
    def test_save_state_replace_fails_move_succeeds(self, _mock_replace):
        """os.replace fails → shutil.move fallback succeeds."""
        state = sentinel._init_state()
        state["current_iteration"] = 99
        sentinel.save_sentinel_state(self.tmp, state)
        loaded = sentinel.load_sentinel_state(self.tmp)
        self.assertEqual(loaded["current_iteration"], 99)


# ---------------------------------------------------------------------------
# TestPartitionSummary
# ---------------------------------------------------------------------------


class TestPartitionSummary(unittest.TestCase):
    """_format_partition_summary() generates readable text."""

    def test_empty_partitions(self):
        parts = {"total_partitions": 0, "partitions": []}
        result = sentinel._format_partition_summary(parts)
        self.assertIn("0 partitions", result)

    def test_partition_summary_content(self):
        parts = {
            "total_partitions": 2,
            "partitions": [
                {
                    "id": "src",
                    "loc": 100,
                    "file_count": 5,
                    "criticality": "high",
                    "criticality_reason": "DANGER ZONE",
                },
                {
                    "id": "lib",
                    "loc": 50,
                    "file_count": 3,
                    "criticality": "low",
                    "criticality_reason": "default",
                },
            ],
        }
        result = sentinel._format_partition_summary(parts)
        self.assertIn("2 partitions", result)
        self.assertIn("src", result)
        self.assertIn("high", result)
        self.assertIn("1 high", result)


# ---------------------------------------------------------------------------
# TestGitActivity
# ---------------------------------------------------------------------------


class TestGitActivity(unittest.TestCase):
    """_git_activity() with real and failing git."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_git_activity_no_repo(self):
        """Returns 0 when not a git repo."""
        result = sentinel._git_activity(self.tmp, "src")
        self.assertEqual(result, 0)

    @patch("sentinel.subprocess.run", side_effect=FileNotFoundError("no git"))
    def test_git_not_installed(self, _mock):
        result = sentinel._git_activity(self.tmp, "src")
        self.assertEqual(result, 0)

    @patch("sentinel.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10))
    def test_git_timeout(self, _mock):
        result = sentinel._git_activity(self.tmp, "src")
        self.assertEqual(result, 0)

    @patch("sentinel.subprocess.run")
    def test_git_nonzero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = sentinel._git_activity(self.tmp, "src")
        self.assertEqual(result, 0)

    @patch("sentinel.subprocess.run")
    def test_git_success_with_commits(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\ndef5678\n")
        result = sentinel._git_activity(self.tmp, "src")
        self.assertEqual(result, 2)

    @patch("sentinel.subprocess.run")
    def test_git_success_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = sentinel._git_activity(self.tmp, "src")
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
# TestCountLines
# ---------------------------------------------------------------------------


class TestCountLines(unittest.TestCase):
    """_count_lines() edge cases."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_count_normal_file(self):
        path = os.path.join(self.tmp, "test.py")
        _write(path, "line1\nline2\nline3\n")
        self.assertEqual(sentinel._count_lines(path), 3)

    def test_count_nonexistent_file(self):
        self.assertEqual(sentinel._count_lines("/no/such/file.py"), 0)

    def test_count_empty_file(self):
        path = os.path.join(self.tmp, "empty.py")
        _write(path, "")
        self.assertEqual(sentinel._count_lines(path), 0)


# ---------------------------------------------------------------------------
# TestPartitionDepthAndEmpty
# ---------------------------------------------------------------------------


class TestPartitionDepthAndEmpty(unittest.TestCase):
    """Partition scanner depth pruning and empty partition skipping."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_depth_greater_than_1_pruned(self):
        """Directories 3+ levels deep don't become partitions."""
        _write(os.path.join(self.tmp, "a", "b", "c", "deep.py"), "x = 1\n")
        result = sentinel.generate_partitions(self.tmp)
        ids = [p["id"] for p in result["partitions"]]
        self.assertNotIn("a/b/c", ids)
        # a/b should exist as a partition
        self.assertIn("a/b", ids)

    def test_empty_directory_skipped(self):
        """Directories with no code files are not partitions."""
        os.makedirs(os.path.join(self.tmp, "empty_dir"))
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\n")
        result = sentinel.generate_partitions(self.tmp)
        ids = [p["id"] for p in result["partitions"]]
        self.assertNotIn("empty_dir", ids)
        self.assertIn("src", ids)

    def test_dir_with_only_non_code_files_skipped(self):
        """Directories with only non-code files (e.g., .txt) are skipped."""
        _write(os.path.join(self.tmp, "data", "readme.txt"), "hello\n")
        result = sentinel.generate_partitions(self.tmp)
        ids = [p["id"] for p in result["partitions"]]
        self.assertNotIn("data", ids)


# ---------------------------------------------------------------------------
# TestMediumCriticality
# ---------------------------------------------------------------------------


class TestMediumCriticality(unittest.TestCase):
    """Medium criticality paths in generate_partitions."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("sentinel._git_activity", return_value=15)
    def test_high_activity_and_file_count(self, _mock):
        """activity > 10 and file_count > 5 → medium."""
        for i in range(6):
            _write(os.path.join(self.tmp, "lib", f"mod{i}.py"), "x = 1\n")
        result = sentinel.generate_partitions(self.tmp)
        lib = next(p for p in result["partitions"] if p["id"] == "lib")
        self.assertEqual(lib["criticality"], "medium")
        self.assertIn("high activity", lib["criticality_reason"])

    @patch("sentinel._git_activity", return_value=7)
    def test_moderate_activity(self, _mock):
        """activity > 5 (but not >10 or file_count<=5) → medium."""
        _write(os.path.join(self.tmp, "core", "app.py"), "x = 1\n")
        result = sentinel.generate_partitions(self.tmp)
        core = next(p for p in result["partitions"] if p["id"] == "core")
        self.assertEqual(core["criticality"], "medium")
        self.assertIn("moderate git activity", core["criticality_reason"])


# ---------------------------------------------------------------------------
# TestReadTemplateMissing
# ---------------------------------------------------------------------------


class TestReadTemplateMissing(unittest.TestCase):
    """_read_template() exits when template doesn't exist."""

    def test_missing_template_exits(self):
        with self.assertRaises(SystemExit):
            sentinel._read_template("nonexistent-template.xyz")


# ---------------------------------------------------------------------------
# TestPartitionSummaryOver20
# ---------------------------------------------------------------------------


class TestPartitionSummaryOver20(unittest.TestCase):
    """_format_partition_summary with >20 partitions truncates."""

    def test_over_20_truncated(self):
        parts = {
            "total_partitions": 25,
            "partitions": [
                {
                    "id": f"dir{i}",
                    "loc": 10,
                    "file_count": 1,
                    "criticality": "low",
                    "criticality_reason": "default",
                }
                for i in range(25)
            ],
        }
        result = sentinel._format_partition_summary(parts)
        self.assertIn("+5 more", result)
        # Only first 20 should appear as table rows
        self.assertIn("dir0", result)
        self.assertIn("dir19", result)
        self.assertNotIn("dir20", result)


# ---------------------------------------------------------------------------
# TestValidateConfigGaps
# ---------------------------------------------------------------------------


class TestValidateConfigGaps(unittest.TestCase):
    """validate_config() missing sections."""

    def test_missing_review_section(self):
        config = {"version": "0.1.0", "commands": {}, "runner": {}}
        issues = sentinel.validate_config(config)
        self.assertIn("missing 'review' section", issues)

    def test_missing_runner_section(self):
        config = {
            "version": "0.1.0",
            "commands": {},
            "review": {
                "max_fix_attempts": 3,
                "confidence_threshold": 0.8,
                "fix_confidence_threshold": 0.9,
            },
        }
        issues = sentinel.validate_config(config)
        self.assertIn("missing 'runner' section", issues)

    def test_bad_fix_confidence(self):
        config = json.loads(json.dumps(sentinel.DEFAULT_CONFIG))
        config["review"]["fix_confidence_threshold"] = 1.5
        issues = sentinel.validate_config(config)
        self.assertTrue(any("fix_confidence_threshold" in i for i in issues))


# ---------------------------------------------------------------------------
# TestInitSentinelEdgeCases
# ---------------------------------------------------------------------------


class TestInitSentinelEdgeCases(unittest.TestCase):
    """init_sentinel edge cases."""

    def test_init_nonexistent_path(self):
        with self.assertRaises(SystemExit):
            sentinel.init_sentinel("/no/such/path/xyz")


# ---------------------------------------------------------------------------
# TestStatusWithConfig
# ---------------------------------------------------------------------------


class TestStatusWithConfig(unittest.TestCase):
    """show_status displays commands when config exists."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_shows_commands(self):
        _make_sentinel_state(self.tmp)
        # Create config
        sdir = os.path.join(self.tmp, ".ouro", "sentinel")
        config = {
            "commands": {
                "build": "make build",
                "test": "pytest",
                "lint": "ruff check .",
            }
        }
        with open(os.path.join(sdir, "sentinel-config.json"), "w") as f:
            json.dump(config, f)
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("make build", output)
        self.assertIn("pytest", output)
        self.assertIn("ruff check .", output)

    def test_status_shows_fix_stats(self):
        _make_sentinel_state(
            self.tmp,
            fixes_attempted=10,
            fixes_merged=8,
            prs_created=5,
        )
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("8/10", output)
        self.assertIn("80%", output)
        self.assertIn("PRs: 5", output)

    def test_status_shows_session_count(self):
        _make_sentinel_state(self.tmp, session_count=3)
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("Sessions:   3", output)

    def test_status_shows_active_partition(self):
        _make_sentinel_state(self.tmp, current_partition="src/auth")
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("src/auth", output)

    def test_status_coverage_uses_partition_dict(self):
        _make_sentinel_state(
            self.tmp,
            partition_last_reviewed={"src": "2026-01-01T00:00:00Z", "lib": "2026-01-02T00:00:00Z"},
            coverage_percent=40.0,
        )
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("40.0%", output)
        self.assertIn("2 partitions", output)


# ---------------------------------------------------------------------------
# TestClaudeMdNewSchemas
# ---------------------------------------------------------------------------


class TestClaudeMdNewSchemas(unittest.TestCase):
    """Rendered CLAUDE.md includes all new schema documentation."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rendered_claude_md_has_all_schemas(self):
        _write(os.path.join(self.tmp, "src", "app.py"), "pass\n")
        sentinel.init_sentinel(self.tmp)
        md_path = os.path.join(self.tmp, ".ouro", "sentinel", "CLAUDE.md")
        with open(md_path) as f:
            content = f.read()
        # state.json new fields
        self.assertIn("session_count", content)
        self.assertIn("partition_last_reviewed", content)
        self.assertIn("current_partition", content)
        self.assertIn("last_session_exit", content)
        self.assertIn("fixes_attempted", content)
        # suppressed.json schema
        self.assertIn("suppressed.json Schema", content)
        # learnings.md format
        self.assertIn("learnings.md Format", content)
        # finding lifecycle
        self.assertIn("Finding status lifecycle", content)
        self.assertIn('"status": "open"', content)
        # PR creation command
        self.assertIn("gh pr create", content)
        # convergence
        self.assertIn("Convergence check", content)
        # unique worktree
        self.assertIn("worktree-<id>", content)


# ---------------------------------------------------------------------------
# TestMainCLI
# ---------------------------------------------------------------------------


class TestMainCLI(unittest.TestCase):
    """main() CLI routing."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_command_shows_help(self):
        with patch("sys.argv", ["ouro-sentinel"]):
            with self.assertRaises(SystemExit) as ctx:
                sentinel.main()
            self.assertEqual(ctx.exception.code, 0)

    def test_dunder_main_guard(self):
        """if __name__ == '__main__': main() is exercised via runpy."""
        with patch("sys.argv", ["sentinel"]):
            with self.assertRaises(SystemExit):
                import runpy

                runpy.run_module("sentinel", run_name="__main__")

    def test_init_command(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\n")
        with patch("sys.argv", ["ouro-sentinel", "init", self.tmp]):
            sentinel.main()
        self.assertTrue(
            os.path.exists(os.path.join(self.tmp, ".ouro", "sentinel", "state.json"))
        )

    def test_status_command(self):
        _make_sentinel_state(self.tmp)
        captured = StringIO()
        with patch("sys.argv", ["ouro-sentinel", "status", self.tmp]):
            with patch("sys.stdout", captured):
                sentinel.main()
        self.assertIn("Sentinel", captured.getvalue())

    def test_partition_command(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\n")
        sentinel.init_sentinel(self.tmp)
        with patch("sys.argv", ["ouro-sentinel", "partition", self.tmp]):
            sentinel.main()

    def test_install_command(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\n")
        sentinel.init_sentinel(self.tmp)
        with patch("sys.argv", ["ouro-sentinel", "install", self.tmp]):
            sentinel.main()
        self.assertTrue(
            os.path.exists(
                os.path.join(self.tmp, ".ouro", "sentinel", "sentinel-runner.sh")
            )
        )


# ---------------------------------------------------------------------------
# TestInstallSentinel
# ---------------------------------------------------------------------------


class TestInstallSentinel(unittest.TestCase):
    """install_sentinel() installs runner + dashboard scripts."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_creates_runner(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        sentinel.install_sentinel(self.tmp)
        runner = os.path.join(self.tmp, ".ouro", "sentinel", "sentinel-runner.sh")
        self.assertTrue(os.path.exists(runner))
        # Check executable
        self.assertTrue(os.access(runner, os.X_OK))

    def test_install_creates_dashboard(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        sentinel.install_sentinel(self.tmp)
        dashboard = os.path.join(self.tmp, ".ouro", "sentinel", "sentinel-dashboard.sh")
        self.assertTrue(os.path.exists(dashboard))
        self.assertTrue(os.access(dashboard, os.X_OK))

    def test_install_no_unreplaced_placeholders(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "print(1)\n")
        sentinel.init_sentinel(self.tmp)
        sentinel.install_sentinel(self.tmp)
        runner = os.path.join(self.tmp, ".ouro", "sentinel", "sentinel-runner.sh")
        with open(runner) as f:
            content = f.read()
        self.assertNotIn("{{", content)
        self.assertNotIn("}}", content)

    def test_install_not_initialized(self):
        with self.assertRaises(SystemExit):
            sentinel.install_sentinel(self.tmp)


# ---------------------------------------------------------------------------
# TestRepartition
# ---------------------------------------------------------------------------


class TestRepartition(unittest.TestCase):
    """repartition() regenerates partitions for existing setup."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repartition_updates_file(self):
        _write(os.path.join(self.tmp, "src", "main.py"), "x = 1\n")
        sentinel.init_sentinel(self.tmp)
        # Add a new directory
        _write(os.path.join(self.tmp, "lib", "util.py"), "y = 2\n")
        sentinel.repartition(self.tmp)
        part_path = os.path.join(self.tmp, ".ouro", "sentinel", "partitions.json")
        with open(part_path) as f:
            parts = json.load(f)
        ids = [p["id"] for p in parts["partitions"]]
        self.assertIn("lib", ids)

    def test_repartition_not_initialized(self):
        with self.assertRaises(SystemExit):
            sentinel.repartition(self.tmp)


# ---------------------------------------------------------------------------
# TestStatusLastReviewDict
# ---------------------------------------------------------------------------


class TestStatusLastReviewDict(unittest.TestCase):
    """show_status() handles last_review as both string and dict."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_last_review_as_dict(self):
        _make_sentinel_state(
            self.tmp,
            last_review={"partition": "src/auth", "timestamp": "2026-01-01T00:00:00Z"},
        )
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("2026-01-01T00:00:00Z", output)
        # Should NOT contain the raw dict repr
        self.assertNotIn("{'partition'", output)

    def test_last_review_as_string(self):
        _make_sentinel_state(self.tmp, last_review="2026-03-15T10:00:00Z")
        captured = StringIO()
        with patch("sys.stdout", captured):
            sentinel.show_status(self.tmp)
        output = captured.getvalue()
        self.assertIn("2026-03-15T10:00:00Z", output)


# ---------------------------------------------------------------------------
# TestInitClaude MdPlaceholders
# ---------------------------------------------------------------------------


class TestInitClaudeMdPlaceholders(unittest.TestCase):
    """init_sentinel CLAUDE.md has all placeholders replaced."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_unreplaced_placeholders(self):
        _write(
            os.path.join(self.tmp, "CLAUDE.md"),
            "## BOUND\n### DANGER ZONES\n- `core/`\n"
            "### NEVER DO\n- Never rm -rf\n"
            "### IRON LAWS\n- Tests must pass\n",
        )
        _write(os.path.join(self.tmp, "src", "app.py"), "pass\n")
        sentinel.init_sentinel(self.tmp)
        md_path = os.path.join(self.tmp, ".ouro", "sentinel", "CLAUDE.md")
        with open(md_path) as f:
            content = f.read()
        self.assertNotIn("{{", content)
        self.assertNotIn("}}", content)
        self.assertIn("core/", content)
        self.assertIn("Never rm -rf", content)
        self.assertIn("Tests must pass", content)


# ---------------------------------------------------------------------------
# TestSkipDirsInPartitions
# ---------------------------------------------------------------------------


class TestSkipDirsInPartitions(unittest.TestCase):
    """Inner os.walk prunes SKIP_DIRS for LOC counting."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_node_modules_not_counted_in_loc(self):
        """node_modules inside a partition dir should not inflate LOC."""
        _write(os.path.join(self.tmp, "src", "app.js"), "var x = 1;\n")
        # Create node_modules inside src/
        for i in range(10):
            _write(
                os.path.join(self.tmp, "src", "node_modules", f"pkg{i}", "index.js"),
                "module.exports = {};\n" * 100,
            )
        result = sentinel.generate_partitions(self.tmp)
        src_part = next(p for p in result["partitions"] if p["id"] == "src")
        # Only app.js should be counted (1 file, 1 line), not node_modules
        self.assertEqual(src_part["file_count"], 1)
        self.assertEqual(src_part["loc"], 1)


if __name__ == "__main__":
    unittest.main()
