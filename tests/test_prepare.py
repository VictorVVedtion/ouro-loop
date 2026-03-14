"""
Tests for prepare.py — project scanning, initialization, and template installation.

Run with:
    python3 -m unittest tests.test_prepare -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO

# Add project root to path so imports work regardless of cwd
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import prepare


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tmp() -> str:
    """Create and return a fresh temporary directory path."""
    return tempfile.mkdtemp()


def _write(path: str, content: str = ""):
    """Write content to a file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# scan_project() — basic shape
# ---------------------------------------------------------------------------

class TestScanProjectBasicShape(unittest.TestCase):
    """scan_project() always returns the expected dict shape."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_dict_with_required_keys(self):
        result = prepare.scan_project(self.tmp)
        required_keys = {
            "path", "name", "scanned_at", "project_types", "languages",
            "file_count", "dir_count", "total_lines", "top_directories",
            "has_claude_md", "has_tests", "has_ci", "bound_detected", "danger_zones",
        }
        self.assertTrue(required_keys.issubset(result.keys()))

    def test_path_is_absolute(self):
        result = prepare.scan_project(self.tmp)
        self.assertTrue(os.path.isabs(result["path"]))

    def test_name_is_basename(self):
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["name"], os.path.basename(self.tmp))

    def test_languages_is_dict_not_counter(self):
        # Counter must be serialised to plain dict before return
        result = prepare.scan_project(self.tmp)
        self.assertIsInstance(result["languages"], dict)

    def test_scanned_at_is_iso_string(self):
        result = prepare.scan_project(self.tmp)
        from datetime import datetime
        # Must be parseable — just check it doesn't raise
        dt_str = result["scanned_at"]
        self.assertIsInstance(dt_str, str)
        self.assertGreater(len(dt_str), 10)


# ---------------------------------------------------------------------------
# scan_project() — empty directory
# ---------------------------------------------------------------------------

class TestScanProjectEmptyDir(unittest.TestCase):
    """Empty project directory — all counters zero, no detections."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_dir_file_count_zero(self):
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 0)

    def test_empty_dir_no_languages(self):
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["languages"], {})

    def test_empty_dir_no_claude_md(self):
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["has_claude_md"])

    def test_empty_dir_no_tests(self):
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["has_tests"])

    def test_empty_dir_no_bound(self):
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["bound_detected"])

    def test_empty_dir_no_project_types(self):
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["project_types"], [])

    def test_empty_dir_total_lines_zero(self):
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["total_lines"], 0)

    def test_empty_dir_top_directories_empty(self):
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["top_directories"], [])


# ---------------------------------------------------------------------------
# scan_project() — language detection
# ---------------------------------------------------------------------------

class TestScanProjectLanguageDetection(unittest.TestCase):
    """Language detection from file extensions."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_python_file_detected(self):
        _write(os.path.join(self.tmp, "main.py"), "x = 1\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Python", result["languages"])

    def test_javascript_file_detected(self):
        _write(os.path.join(self.tmp, "app.js"), "const x = 1;\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("JavaScript", result["languages"])

    def test_typescript_file_detected(self):
        _write(os.path.join(self.tmp, "app.ts"), "const x: number = 1;\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("TypeScript", result["languages"])

    def test_rust_file_detected(self):
        _write(os.path.join(self.tmp, "main.rs"), "fn main() {}\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Rust", result["languages"])

    def test_go_file_detected(self):
        _write(os.path.join(self.tmp, "main.go"), "package main\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Go", result["languages"])

    def test_unknown_extension_not_in_languages(self):
        _write(os.path.join(self.tmp, "data.xyz"), "some data\n")
        result = prepare.scan_project(self.tmp)
        # .xyz not in LANG_MAP — file counted but no language entry
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["languages"], {})

    def test_multiple_files_of_same_language_counted(self):
        for i in range(5):
            _write(os.path.join(self.tmp, f"module{i}.py"), f"# module {i}\n")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["languages"]["Python"], 5)

    def test_mixed_languages(self):
        _write(os.path.join(self.tmp, "a.py"), "")
        _write(os.path.join(self.tmp, "b.py"), "")
        _write(os.path.join(self.tmp, "c.js"), "")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["languages"]["Python"], 2)
        self.assertEqual(result["languages"]["JavaScript"], 1)

    def test_extension_case_insensitive(self):
        # .PY should be treated same as .py
        _write(os.path.join(self.tmp, "main.PY"), "")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Python", result["languages"])

    def test_languages_dict_at_most_10_entries(self):
        # LANG_MAP is large; result["languages"] uses .most_common(10)
        extensions = [".py", ".js", ".ts", ".rs", ".go", ".java", ".kt",
                      ".rb", ".php", ".c", ".cpp", ".cs"]
        for ext in extensions:
            _write(os.path.join(self.tmp, f"file{ext}"), "")
        result = prepare.scan_project(self.tmp)
        self.assertLessEqual(len(result["languages"]), 10)


# ---------------------------------------------------------------------------
# scan_project() — project marker detection
# ---------------------------------------------------------------------------

class TestScanProjectMarkerDetection(unittest.TestCase):
    """Project-type marker files are detected correctly."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cargo_toml_detected_as_rust(self):
        _write(os.path.join(self.tmp, "Cargo.toml"), "[package]\nname = \"foo\"\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Rust", result["project_types"])

    def test_go_mod_detected(self):
        _write(os.path.join(self.tmp, "go.mod"), "module example.com/foo\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Go", result["project_types"])

    def test_package_json_detected_as_nodejs(self):
        _write(os.path.join(self.tmp, "package.json"), '{"name":"foo"}')
        result = prepare.scan_project(self.tmp)
        self.assertIn("Node.js", result["project_types"])

    def test_pyproject_toml_detected_as_python(self):
        _write(os.path.join(self.tmp, "pyproject.toml"), "[project]\nname=\"foo\"\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Python", result["project_types"])

    def test_dockerfile_detected_as_docker(self):
        _write(os.path.join(self.tmp, "Dockerfile"), "FROM ubuntu\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Docker", result["project_types"])

    def test_multiple_markers_produce_multiple_types(self):
        _write(os.path.join(self.tmp, "package.json"), "{}")
        _write(os.path.join(self.tmp, "Dockerfile"), "FROM node\n")
        result = prepare.scan_project(self.tmp)
        self.assertIn("Node.js", result["project_types"])
        self.assertIn("Docker", result["project_types"])

    def test_no_markers_yields_empty_list(self):
        _write(os.path.join(self.tmp, "readme.txt"), "")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["project_types"], [])


# ---------------------------------------------------------------------------
# scan_project() — CLAUDE.md and BOUND detection
# ---------------------------------------------------------------------------

class TestScanProjectClaudeMdDetection(unittest.TestCase):
    """CLAUDE.md and BOUND marker detection."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_claude_md_found_when_present(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Project\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_claude_md"])

    def test_claude_md_not_found_when_absent(self):
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["has_claude_md"])

    def test_bound_detected_with_danger_zone_marker(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "DANGER ZONE: do not touch\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["bound_detected"])

    def test_bound_detected_with_never_do_marker(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## NEVER DO\n- never delete prod\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["bound_detected"])

    def test_bound_detected_with_iron_law_marker(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "IRON LAW: always test\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["bound_detected"])

    def test_bound_detected_with_hash_hash_bound_section(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nsome rules\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["bound_detected"])

    def test_bound_detected_with_single_hash_bound_section(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# BOUND\nsome rules\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["bound_detected"])

    def test_bound_not_detected_when_no_markers(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Just a project description\n")
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["bound_detected"])

    def test_bound_not_detected_without_claude_md(self):
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["bound_detected"])


# ---------------------------------------------------------------------------
# scan_project() — test file detection
# ---------------------------------------------------------------------------

class TestScanProjectTestDetection(unittest.TestCase):
    """Test file detection heuristics."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_named_test_something_detected(self):
        _write(os.path.join(self.tmp, "test_utils.py"), "")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_tests"])

    def test_file_named_something_test_detected(self):
        _write(os.path.join(self.tmp, "utils_test.go"), "")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_tests"])

    def test_spec_file_detected(self):
        _write(os.path.join(self.tmp, "app.spec.js"), "")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_tests"])

    def test_uppercase_test_in_filename_detected(self):
        _write(os.path.join(self.tmp, "TestAuth.kt"), "")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_tests"])

    def test_no_test_files_returns_false(self):
        _write(os.path.join(self.tmp, "main.py"), "")
        _write(os.path.join(self.tmp, "utils.py"), "")
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["has_tests"])

    def test_test_file_in_subdirectory_detected(self):
        _write(os.path.join(self.tmp, "tests", "test_main.py"), "")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_tests"])


# ---------------------------------------------------------------------------
# scan_project() — SKIP_DIRS
# ---------------------------------------------------------------------------

class TestScanProjectSkipDirs(unittest.TestCase):
    """Directories in SKIP_DIRS must not be scanned."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_git_dir_skipped(self):
        _write(os.path.join(self.tmp, ".git", "HEAD"), "ref: refs/heads/main\n")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 0)

    def test_node_modules_skipped(self):
        _write(os.path.join(self.tmp, "node_modules", "lodash", "index.js"), "")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 0)

    def test_pycache_skipped(self):
        _write(os.path.join(self.tmp, "__pycache__", "main.cpython-311.pyc"), "")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 0)

    def test_ouro_dir_skipped(self):
        # .ouro is in SKIP_DIRS
        _write(os.path.join(self.tmp, ".ouro", "state.json"), "{}")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 0)

    def test_venv_skipped(self):
        _write(os.path.join(self.tmp, ".venv", "bin", "python"), "#!/usr/bin/env python3\n")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 0)

    def test_files_outside_skip_dirs_still_counted(self):
        _write(os.path.join(self.tmp, "main.py"), "")
        _write(os.path.join(self.tmp, "node_modules", "lib.js"), "")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["file_count"], 1)

    def test_skip_dirs_not_in_top_directories(self):
        os.makedirs(os.path.join(self.tmp, "node_modules"))
        os.makedirs(os.path.join(self.tmp, "src"))
        result = prepare.scan_project(self.tmp)
        self.assertNotIn("node_modules", result["top_directories"])
        self.assertIn("src", result["top_directories"])


# ---------------------------------------------------------------------------
# scan_project() — line counting
# ---------------------------------------------------------------------------

class TestScanProjectLineCount(unittest.TestCase):
    """Line counting for code files."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_line_count_accurate(self):
        _write(os.path.join(self.tmp, "file.py"), "line1\nline2\nline3\n")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["total_lines"], 3)

    def test_multiple_files_lines_summed(self):
        _write(os.path.join(self.tmp, "a.py"), "x = 1\ny = 2\n")  # 2 lines
        _write(os.path.join(self.tmp, "b.py"), "z = 3\n")          # 1 line
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["total_lines"], 3)

    def test_non_code_file_lines_not_counted(self):
        _write(os.path.join(self.tmp, "data.bin"), "binary content")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["total_lines"], 0)

    def test_empty_code_file_zero_lines(self):
        _write(os.path.join(self.tmp, "empty.py"), "")
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["total_lines"], 0)


# ---------------------------------------------------------------------------
# scan_project() — invalid path
# ---------------------------------------------------------------------------

class TestScanProjectInvalidPath(unittest.TestCase):
    """scan_project() exits on non-directory paths."""

    def test_nonexistent_path_exits(self):
        with self.assertRaises(SystemExit):
            prepare.scan_project("/does/not/exist/at/all/ever")

    def test_file_path_exits(self):
        with tempfile.NamedTemporaryFile() as f:
            with self.assertRaises(SystemExit):
                prepare.scan_project(f.name)


# ---------------------------------------------------------------------------
# scan_project() — top directories
# ---------------------------------------------------------------------------

class TestScanProjectTopDirectories(unittest.TestCase):
    """top_directories only lists non-skipped dirs at the root level."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_top_dirs_listed_and_sorted(self):
        os.makedirs(os.path.join(self.tmp, "src"))
        os.makedirs(os.path.join(self.tmp, "docs"))
        os.makedirs(os.path.join(self.tmp, "tests"))
        result = prepare.scan_project(self.tmp)
        self.assertEqual(result["top_directories"], ["docs", "src", "tests"])

    def test_subdirectories_not_in_top_directories(self):
        os.makedirs(os.path.join(self.tmp, "src", "utils"))
        result = prepare.scan_project(self.tmp)
        # top_directories is root-level only
        self.assertIn("src", result["top_directories"])
        self.assertNotIn("utils", result["top_directories"])


# ---------------------------------------------------------------------------
# scan_project() — CI detection
# ---------------------------------------------------------------------------

class TestScanProjectCIDetection(unittest.TestCase):
    """CI directory detection."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_github_workflows_triggers_ci_flag(self):
        _write(os.path.join(self.tmp, ".github", "workflows", "ci.yml"), "name: CI\n")
        result = prepare.scan_project(self.tmp)
        self.assertTrue(result["has_ci"])

    def test_no_ci_dir_returns_false(self):
        _write(os.path.join(self.tmp, "main.py"), "")
        result = prepare.scan_project(self.tmp)
        self.assertFalse(result["has_ci"])


# ---------------------------------------------------------------------------
# init_ouro()
# ---------------------------------------------------------------------------

class TestInitOuroFreshInit(unittest.TestCase):
    """Fresh initialization creates the expected files and state."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ouro_dir_created(self):
        prepare.init_ouro(self.tmp)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".ouro")))

    def test_state_file_created(self):
        prepare.init_ouro(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "state.json")
        self.assertTrue(os.path.exists(state_path))

    def test_state_file_is_valid_json(self):
        prepare.init_ouro(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "state.json")
        with open(state_path) as f:
            state = json.load(f)
        self.assertIsInstance(state, dict)

    def test_state_has_required_keys(self):
        prepare.init_ouro(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "state.json")
        with open(state_path) as f:
            state = json.load(f)
        for key in ("version", "initialized_at", "project_name",
                    "project_types", "current_stage", "history"):
            self.assertIn(key, state)

    def test_state_initial_stage_is_bound(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertEqual(state["current_stage"], "BOUND")

    def test_state_history_empty_on_init(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertEqual(state["history"], [])

    def test_state_current_phase_is_none(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertIsNone(state["current_phase"])

    def test_state_total_phases_is_zero(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertEqual(state["total_phases"], 0)

    def test_results_tsv_created_with_header(self):
        prepare.init_ouro(self.tmp)
        # prepare.py uses RESULTS_FILE = "ouro-results.tsv"
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        self.assertTrue(os.path.exists(results_path))
        with open(results_path) as f:
            header = f.readline()
        self.assertIn("phase", header)
        self.assertIn("verdict", header)

    def test_results_tsv_has_tab_separated_columns(self):
        prepare.init_ouro(self.tmp)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")
        with open(results_path) as f:
            header = f.readline().strip()
        cols = header.split("\t")
        self.assertGreaterEqual(len(cols), 5)

    def test_project_name_matches_dir_basename(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertEqual(state["project_name"], os.path.basename(self.tmp))

    def test_version_field_present(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertIn("version", state)
        self.assertIsInstance(state["version"], str)


class TestInitOuroBoundDetection(unittest.TestCase):
    """bound_defined flag in state reflects actual CLAUDE.md content."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bound_defined_true_when_claude_md_has_bound(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "## BOUND\nDO NOT DELETE PROD\n")
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertTrue(state["bound_defined"])

    def test_bound_defined_false_when_no_claude_md(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertFalse(state["bound_defined"])

    def test_bound_defined_false_when_claude_md_has_no_bound_markers(self):
        _write(os.path.join(self.tmp, "CLAUDE.md"), "# Just a readme\nNo bound here.\n")
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertFalse(state["bound_defined"])


class TestInitOuroDoubleInit(unittest.TestCase):
    """Calling init_ouro twice is safe — does not overwrite existing state."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_double_init_does_not_overwrite_state(self):
        prepare.init_ouro(self.tmp)
        state_path = os.path.join(self.tmp, ".ouro", "state.json")

        # Tamper with state so we can detect if it gets overwritten
        with open(state_path) as f:
            state = json.load(f)
        state["__sentinel__"] = "do-not-overwrite"
        with open(state_path, "w") as f:
            json.dump(state, f)

        prepare.init_ouro(self.tmp)

        with open(state_path) as f:
            state2 = json.load(f)
        self.assertIn("__sentinel__", state2)
        self.assertEqual(state2["__sentinel__"], "do-not-overwrite")

    def test_double_init_does_not_overwrite_results_tsv(self):
        prepare.init_ouro(self.tmp)
        results_path = os.path.join(self.tmp, "ouro-results.tsv")

        # Append a fake result row
        with open(results_path, "a") as f:
            f.write("1/3\tPASS\t0\tN/A\tnone\t\n")

        prepare.init_ouro(self.tmp)

        with open(results_path) as f:
            lines = f.readlines()
        # Header + 1 data row = 2 lines; second init must not truncate
        self.assertEqual(len(lines), 2)


class TestInitOuroProjectTypes(unittest.TestCase):
    """project_types in state reflects detected markers."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_python_project_type_stored_in_state(self):
        _write(os.path.join(self.tmp, "pyproject.toml"), "[project]\nname=\"x\"\n")
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertIn("Python", state["project_types"])

    def test_empty_project_types_when_no_markers(self):
        prepare.init_ouro(self.tmp)
        with open(os.path.join(self.tmp, ".ouro", "state.json")) as f:
            state = json.load(f)
        self.assertEqual(state["project_types"], [])


# ---------------------------------------------------------------------------
# install_template()
# ---------------------------------------------------------------------------

class TestInstallTemplate(unittest.TestCase):
    """Template installation copies files and respects existing files."""

    def setUp(self):
        self.tmp = _make_tmp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_claude_template_installs_claude_md(self):
        prepare.install_template("claude", self.tmp)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "CLAUDE.md")))

    def test_phase_template_installs_phase_plan(self):
        prepare.install_template("phase", self.tmp)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "phase-plan.md")))

    def test_verify_template_installs_verify_checklist(self):
        prepare.install_template("verify", self.tmp)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "verify-checklist.md")))

    def test_installed_template_not_empty(self):
        prepare.install_template("claude", self.tmp)
        self.assertGreater(os.path.getsize(os.path.join(self.tmp, "CLAUDE.md")), 0)

    def test_installed_claude_template_contains_bound_section(self):
        prepare.install_template("claude", self.tmp)
        with open(os.path.join(self.tmp, "CLAUDE.md")) as f:
            content = f.read()
        self.assertIn("BOUND", content)

    def test_invalid_template_type_exits(self):
        with self.assertRaises(SystemExit):
            prepare.install_template("nonexistent_type", self.tmp)

    def test_already_existing_file_not_overwritten(self):
        dst = os.path.join(self.tmp, "CLAUDE.md")
        sentinel = "SENTINEL CONTENT — DO NOT OVERWRITE"
        with open(dst, "w") as f:
            f.write(sentinel)

        prepare.install_template("claude", self.tmp)

        with open(dst) as f:
            content = f.read()
        self.assertEqual(content, sentinel)

    def test_all_valid_template_types_succeed(self):
        for ttype in ("claude", "phase", "verify"):
            dst_dir = _make_tmp()
            try:
                # Must not raise or sys.exit
                prepare.install_template(ttype, dst_dir)
                files = os.listdir(dst_dir)
                self.assertTrue(len(files) > 0, f"No file created for template type {ttype!r}")
            finally:
                shutil.rmtree(dst_dir, ignore_errors=True)

    def test_output_filename_has_no_template_suffix(self):
        for ttype in ("claude", "phase", "verify"):
            dst_dir = _make_tmp()
            try:
                prepare.install_template(ttype, dst_dir)
                files = os.listdir(dst_dir)
                for fname in files:
                    self.assertFalse(
                        fname.endswith(".template"),
                        f"File {fname!r} still has .template suffix for type {ttype!r}"
                    )
            finally:
                shutil.rmtree(dst_dir, ignore_errors=True)

    def test_template_content_is_copied_faithfully(self):
        # Content of installed file must match the source template (minus .template ext)
        prepare.install_template("claude", self.tmp)
        dst = os.path.join(self.tmp, "CLAUDE.md")
        src = os.path.join(prepare.TEMPLATES_DIR, "CLAUDE.md.template")
        with open(dst) as f:
            installed = f.read()
        with open(src) as f:
            original = f.read()
        self.assertEqual(installed, original)


if __name__ == "__main__":
    unittest.main()
