"""
Ouro Sentinel — Autonomous code review loop for any project.

Scans project structure, generates partitions with risk scoring,
auto-detects build/test/lint commands, and installs a 24/7 review runner.

Usage:
    ouro-sentinel init <path>        # Initialize sentinel for a project
    ouro-sentinel partition <path>   # Regenerate partitions
    ouro-sentinel status <path>      # Show sentinel run status
    ouro-sentinel install <path>     # Install runner + dashboard scripts

Zero external dependencies — pure stdlib.
"""

import os
import sys
import json
import stat
import shutil
import argparse
import subprocess
from datetime import datetime, timezone
from collections import Counter
from typing import Optional

# Import shared infrastructure (read-only reuse)
from framework import (
    OURO_DIR,
    CLAUDE_MD_FILENAME,
    parse_claude_md,
    _file_in_danger_zone,
)
from prepare import (
    scan_project,
    LANG_MAP,
    SKIP_DIRS,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENTINEL_DIR = os.path.join(OURO_DIR, "sentinel")
SENTINEL_CONFIG = "sentinel-config.json"
PARTITIONS_FILE = "partitions.json"
SENTINEL_STATE = "state.json"
FINDINGS_FILE = "findings.jsonl"
ITERATION_LOG = "iteration-log.jsonl"
LEARNINGS_FILE = "learnings.md"


def _find_templates_dir():
    """Locate sentinel templates: ouro_templates package first, then adjacent dir."""
    try:
        import ouro_templates

        pkg_dir = os.path.join(os.path.dirname(ouro_templates.__file__), "sentinel")
        if os.path.isdir(pkg_dir):
            return pkg_dir
    except ImportError:
        pass
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ouro_templates", "sentinel"
    )


TEMPLATES_DIR = _find_templates_dir()

VERSION = "0.3.0"

# Command detection: marker file → {build, test, lint}
COMMAND_DETECTION = {
    "go.mod": {
        "build": "go build ./...",
        "test": "go test ./...",
        "lint": "go vet ./...",
    },
    "Cargo.toml": {
        "build": "cargo build",
        "test": "cargo test",
        "lint": "cargo clippy",
    },
    "package.json": {
        "build": "npm run build",
        "test": "npm test",
        "lint": "npx eslint .",
    },
    "pyproject.toml": {
        "build": None,
        "test": "python -m pytest",
        "lint": "ruff check .",
    },
    "setup.py": {"build": None, "test": "python -m pytest", "lint": "ruff check ."},
    "Makefile": {"build": "make build", "test": "make test", "lint": "make lint"},
    "CMakeLists.txt": {"build": "cmake --build .", "test": "ctest", "lint": None},
    "Gemfile": {
        "build": None,
        "test": "bundle exec rspec",
        "lint": "bundle exec rubocop",
    },
    "pom.xml": {
        "build": "mvn compile",
        "test": "mvn test",
        "lint": "mvn checkstyle:check",
    },
    "build.gradle": {
        "build": "gradle build",
        "test": "gradle test",
        "lint": "gradle check",
    },
}

# Priority order for command detection (first match wins)
COMMAND_PRIORITY = [
    "go.mod",
    "Cargo.toml",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "pom.xml",
    "build.gradle",
    "Gemfile",
    "CMakeLists.txt",
    "Makefile",
]

# Default config values
DEFAULT_CONFIG = {
    "version": VERSION,
    "project_name": "",
    "commands": {
        "build": None,
        "test": None,
        "lint": None,
    },
    "review": {
        "max_fix_attempts": 3,
        "blast_radius_limit": 3,
        "confidence_threshold": 0.8,
        "fix_confidence_threshold": 0.9,
        "auto_pr": False,
        "pr_prefix": "sentinel/",
    },
    "runner": {
        "model": "claude-opus-4-6",
        "max_turns": 200,
        "session_timeout_minutes": 120,
        "cooldown_seconds": 30,
    },
    "partitioning": {
        "strategy": "directory",
        "criticality_overrides": {},
    },
}

# Git timeout for subprocess calls
GIT_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Command Detection
# ---------------------------------------------------------------------------


def detect_commands(project_path: str) -> dict:
    """Auto-detect build/test/lint commands from project marker files.

    Scans for known marker files in priority order. For each command slot
    (build/test/lint), the first marker providing that slot wins.
    Returns dict with 'build', 'test', 'lint' keys (values may be None).
    """
    result = {"build": None, "test": None, "lint": None}
    for marker in COMMAND_PRIORITY:
        if os.path.exists(os.path.join(project_path, marker)):
            cmds = COMMAND_DETECTION[marker]
            for key in ("build", "test", "lint"):
                if result[key] is None and cmds.get(key):
                    result[key] = cmds[key]
    return result


# ---------------------------------------------------------------------------
# Partition Scanner
# ---------------------------------------------------------------------------


def _count_lines(filepath: str) -> int:
    """Count lines in a file, returning 0 on any error."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except (OSError, PermissionError):
        return 0


def _git_activity(project_path: str, rel_path: str, commits: int = 30) -> int:
    """Count how many of the last N commits touched files in rel_path.

    Returns 0 if git is unavailable or the path has no git history.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"--max-count={commits}",
                "--pretty=format:%h",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            cwd=project_path,
        )
        if result.returncode == 0:
            lines = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
            return len(lines)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return 0


def generate_partitions(project_path: str, config: Optional[dict] = None) -> dict:
    """Scan project directories and generate risk-scored partitions.

    Three stages:
    1. Directory grouping: os.walk by top-level dirs, skip SKIP_DIRS
    2. Metrics: LOC, file count, language distribution, git activity
    3. Risk scoring: cross-reference DANGER ZONES for criticality
    """
    project_path = os.path.abspath(project_path)
    bound_data = parse_claude_md(project_path)
    danger_zones = bound_data.get("danger_zones", [])
    overrides = {}
    if config and "partitioning" in config:
        overrides = config["partitioning"].get("criticality_overrides", {})

    partitions = []

    for root, dirs, files in os.walk(project_path):
        # Skip hidden/ignored directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        rel_root = os.path.relpath(root, project_path)
        if rel_root == ".":
            continue  # Process subdirectories, not root itself

        # Only process first-level and second-level directories
        depth = rel_root.count(os.sep)
        if depth > 1:
            dirs.clear()  # Don't recurse deeper than 2 levels for partition IDs
            continue

        # Collect metrics for this partition
        loc = 0
        file_count = 0
        languages = Counter()

        for dirpath, subdirs, dir_files in os.walk(
            os.path.join(project_path, rel_root)
        ):
            # Prune SKIP_DIRS to avoid traversing node_modules etc.
            subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS]
            # For depth-0 partitions, don't recurse into subdirs that become
            # their own depth-1 partitions (avoids double-counting LOC).
            if depth == 0 and dirpath == os.path.join(project_path, rel_root):
                subdirs.clear()
            for fname in dir_files:
                fpath = os.path.join(dirpath, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in LANG_MAP:
                    file_count += 1
                    languages[LANG_MAP[ext]] += 1
                    loc += _count_lines(fpath)

        if file_count == 0:
            continue  # Skip empty partitions

        # Git activity
        activity = _git_activity(project_path, rel_root)

        # Criticality assessment
        criticality = "low"
        criticality_reason = "default"

        # Check overrides first
        if rel_root in overrides:
            criticality = overrides[rel_root]
            criticality_reason = "manual override"
        else:
            # Check DANGER ZONE overlap
            zone_match = _file_in_danger_zone(rel_root + "/", danger_zones)
            if zone_match:
                criticality = "high"
                criticality_reason = f"DANGER ZONE overlap: {zone_match}"
            elif activity > 10 and file_count > 5:
                criticality = "medium"
                criticality_reason = "high activity + file count"
            elif activity > 5:
                criticality = "medium"
                criticality_reason = "moderate git activity"

        partitions.append(
            {
                "id": rel_root.replace(os.sep, "/"),
                "path": rel_root.replace(os.sep, "/"),
                "loc": loc,
                "file_count": file_count,
                "languages": dict(languages.most_common(5)),
                "activity": activity,
                "criticality": criticality,
                "criticality_reason": criticality_reason,
            }
        )

    # Sort: high criticality first, then by activity descending
    crit_order = {"high": 0, "medium": 1, "low": 2}
    partitions.sort(key=lambda p: (crit_order.get(p["criticality"], 2), -p["activity"]))

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_partitions": len(partitions),
        "partitions": partitions,
    }
    return result


# ---------------------------------------------------------------------------
# Template Rendering
# ---------------------------------------------------------------------------


def _read_template(template_name: str) -> str:
    """Read a template file from the sentinel templates directory."""
    path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(path):
        print(f"Error: Template not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _format_partition_summary(partitions: dict) -> str:
    """Generate a text summary of partitions for template insertion."""
    total = partitions["total_partitions"]
    parts = partitions["partitions"]

    high = sum(1 for p in parts if p["criticality"] == "high")
    medium = sum(1 for p in parts if p["criticality"] == "medium")
    low = sum(1 for p in parts if p["criticality"] == "low")
    total_loc = sum(p["loc"] for p in parts)

    lines = [
        f"Total: {total} partitions | {total_loc:,} LOC",
        f"Risk: {high} high, {medium} medium, {low} low",
        "",
        "| Partition | LOC | Files | Risk | Reason |",
        "|-----------|-----|-------|------|--------|",
    ]
    for p in parts[:20]:  # Cap at 20 for readability
        lines.append(
            f"| `{p['id']}` | {p['loc']:,} | {p['file_count']} "
            f"| {p['criticality']} | {p['criticality_reason']} |"
        )
    if total > 20:
        lines.append(f"| ... | | | | +{total - 20} more |")

    return "\n".join(lines)


def render_sentinel_claude_md(project_path: str, config: dict, partitions: dict) -> str:
    """Render the Sentinel CLAUDE.md from template + project data.

    Reads CLAUDE.md.template and replaces placeholders with project-specific
    BOUND data, auto-detected commands, and partition summary.
    """
    template = _read_template("CLAUDE.md.template")
    bound_data = parse_claude_md(project_path)

    # Format BOUND sections (graceful degradation if missing)
    danger_zones = ""
    if bound_data["danger_zones"]:
        danger_zones = "\n".join(f"- `{z}`" for z in bound_data["danger_zones"])
    else:
        danger_zones = "- (none defined — add DANGER ZONES to your project CLAUDE.md)"

    never_do = ""
    if bound_data["never_do"]:
        never_do = "\n".join(f"- {n}" for n in bound_data["never_do"])
    else:
        never_do = "- (none defined)"

    iron_laws = ""
    if bound_data["iron_laws"]:
        iron_laws = "\n".join(f"- {law}" for law in bound_data["iron_laws"])
    else:
        iron_laws = "- (none defined)"

    # Commands
    build_cmd = config.get("commands", {}).get("build") or "# no build command detected"
    test_cmd = config.get("commands", {}).get("test") or "# no test command detected"
    lint_cmd = config.get("commands", {}).get("lint") or "# no lint command detected"

    # Partition summary
    partition_summary = _format_partition_summary(partitions)

    # Replace placeholders
    result = template
    result = result.replace("{{DANGER_ZONES}}", danger_zones)
    result = result.replace("{{NEVER_DO}}", never_do)
    result = result.replace("{{IRON_LAWS}}", iron_laws)
    result = result.replace("{{BUILD_COMMAND}}", build_cmd)
    result = result.replace("{{TEST_COMMAND}}", test_cmd)
    result = result.replace("{{LINT_COMMAND}}", lint_cmd)
    result = result.replace("{{PARTITIONS_SUMMARY}}", partition_summary)

    return result


# ---------------------------------------------------------------------------
# Config Management
# ---------------------------------------------------------------------------


def generate_config(project_path: str) -> dict:
    """Generate sentinel config with auto-detected values."""
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    config["project_name"] = os.path.basename(os.path.abspath(project_path))
    config["commands"] = detect_commands(project_path)
    return config


def load_config(project_path: str) -> Optional[dict]:
    """Load sentinel config from project. Returns None if not found."""
    config_path = os.path.join(project_path, OURO_DIR, "sentinel", SENTINEL_CONFIG)
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def validate_config(config: dict) -> list:
    """Validate sentinel config, return list of issues (empty = valid)."""
    issues = []
    if "version" not in config:
        issues.append("missing 'version' field")
    if "commands" not in config:
        issues.append("missing 'commands' section")
    if "review" not in config:
        issues.append("missing 'review' section")
    else:
        review = config["review"]
        if review.get("max_fix_attempts", 0) < 1:
            issues.append("review.max_fix_attempts must be >= 1")
        if not (0 < review.get("confidence_threshold", 0) <= 1):
            issues.append("review.confidence_threshold must be in (0, 1]")
        if not (0 < review.get("fix_confidence_threshold", 0) <= 1):
            issues.append("review.fix_confidence_threshold must be in (0, 1]")
    if "runner" not in config:
        issues.append("missing 'runner' section")
    return issues


# ---------------------------------------------------------------------------
# Sentinel State
# ---------------------------------------------------------------------------


def _sentinel_dir(project_path: str) -> str:
    """Return the .ouro/sentinel/ path."""
    return os.path.join(project_path, SENTINEL_DIR)


def _init_state() -> dict:
    """Create initial sentinel state."""
    return {
        "version": VERSION,
        "initialized_at": datetime.now(timezone.utc).isoformat(),
        "current_iteration": 0,
        "session_count": 0,
        "total_findings": 0,
        "findings_by_severity": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
        "fixes_attempted": 0,
        "fixes_merged": 0,
        "prs_created": 0,
        "partition_last_reviewed": {},
        "coverage_percent": 0.0,
        "last_review": None,
        "current_partition": None,
        "last_session_exit": None,
        "status": "initialized",
    }


def load_sentinel_state(project_path: str) -> Optional[dict]:
    """Load sentinel state. Returns None if not initialized."""
    state_path = os.path.join(_sentinel_dir(project_path), SENTINEL_STATE)
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_sentinel_state(project_path: str, state: dict):
    """Save sentinel state (atomic write)."""
    sdir = _sentinel_dir(project_path)
    os.makedirs(sdir, exist_ok=True)
    state_path = os.path.join(sdir, SENTINEL_STATE)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
    try:
        os.replace(tmp_path, state_path)
    except OSError:
        try:
            shutil.move(tmp_path, state_path)
        except OSError:
            # Clean up tmp on failure to avoid stale files
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# Init Command
# ---------------------------------------------------------------------------


def init_sentinel(project_path: str):
    """Initialize sentinel for a project.

    Orchestrates: scan → detect commands → generate config →
    generate partitions → render CLAUDE.md → create state files.
    """
    project_path = os.path.abspath(project_path)
    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a directory")
        sys.exit(1)

    sdir = _sentinel_dir(project_path)

    # Check existing
    if os.path.exists(os.path.join(sdir, SENTINEL_STATE)):
        print(f"Sentinel already initialized at {sdir}")
        print("Use 'ouro-sentinel status' to view current state.")
        print("Use 'ouro-sentinel partition' to regenerate partitions.")
        return

    print("Initializing Ouro Sentinel...")

    # 1. Scan project
    scan = scan_project(project_path)
    print(f"  Scanned: {scan['file_count']} files, {scan['total_lines']:,} lines")

    # 2. Detect commands
    config = generate_config(project_path)
    cmds = config["commands"]
    detected = [k for k, v in cmds.items() if v]
    print(f"  Commands: {', '.join(detected) if detected else 'none detected'}")

    # 3. Create sentinel directory
    os.makedirs(sdir, exist_ok=True)

    # 4. Save config
    config_path = os.path.join(sdir, SENTINEL_CONFIG)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  Config: {config_path}")

    # 5. Generate partitions
    partitions = generate_partitions(project_path, config)
    part_path = os.path.join(sdir, PARTITIONS_FILE)
    with open(part_path, "w") as f:
        json.dump(partitions, f, indent=2)
    high = sum(1 for p in partitions["partitions"] if p["criticality"] == "high")
    print(f"  Partitions: {partitions['total_partitions']} ({high} high-risk)")

    # 6. Render sentinel CLAUDE.md
    sentinel_claude_md = render_sentinel_claude_md(project_path, config, partitions)
    claude_md_path = os.path.join(sdir, CLAUDE_MD_FILENAME)
    with open(claude_md_path, "w") as f:
        f.write(sentinel_claude_md)
    print(f"  Methodology: {claude_md_path}")

    # 7. Initialize state
    state = _init_state()
    save_sentinel_state(project_path, state)

    # 8. Create empty state files
    for fname in (FINDINGS_FILE, ITERATION_LOG):
        with open(os.path.join(sdir, fname), "a"):
            pass
    # suppressed.json — dedup store for confirmed false positives
    suppressed_path = os.path.join(sdir, "suppressed.json")
    if not os.path.exists(suppressed_path):
        with open(suppressed_path, "w") as f:
            json.dump([], f)
    # learnings.md — cross-session knowledge accumulator (written every 10 iterations)
    learnings_path = os.path.join(sdir, LEARNINGS_FILE)
    if not os.path.exists(learnings_path):
        with open(learnings_path, "w") as f:
            f.write(
                "# Sentinel Learnings\n\n"
                "This file is updated every 10 iterations with patterns and insights.\n\n"
            )

    print()
    print("Sentinel initialized successfully.")
    print(f"  Directory: {sdir}")
    print()
    print("Next steps:")
    print("  1. Review config:    cat " + config_path)
    print("  2. Install runner:   ouro-sentinel install " + project_path)
    print("  3. Start sentinel:   make sentinel-start  (after install)")


# ---------------------------------------------------------------------------
# Partition Command
# ---------------------------------------------------------------------------


def repartition(project_path: str):
    """Regenerate partitions for an existing sentinel setup."""
    project_path = os.path.abspath(project_path)
    config = load_config(project_path)
    if config is None:
        print("Sentinel not initialized. Run: ouro-sentinel init " + project_path)
        sys.exit(1)

    partitions = generate_partitions(project_path, config)
    part_path = os.path.join(_sentinel_dir(project_path), PARTITIONS_FILE)
    with open(part_path, "w") as f:
        json.dump(partitions, f, indent=2)

    high = sum(1 for p in partitions["partitions"] if p["criticality"] == "high")
    medium = sum(1 for p in partitions["partitions"] if p["criticality"] == "medium")
    low = sum(1 for p in partitions["partitions"] if p["criticality"] == "low")
    print(f"Partitions regenerated: {partitions['total_partitions']} total")
    print(f"  High: {high}  Medium: {medium}  Low: {low}")


# ---------------------------------------------------------------------------
# Status Command
# ---------------------------------------------------------------------------


def show_status(project_path: str):
    """Display sentinel status summary."""
    project_path = os.path.abspath(project_path)
    state = load_sentinel_state(project_path)
    if state is None:
        print("Sentinel not initialized. Run: ouro-sentinel init " + project_path)
        sys.exit(1)

    config = load_config(project_path)

    print("=" * 50)
    print("  Ouro Sentinel — Status")
    print("=" * 50)
    print(f"  Status:     {state.get('status', 'unknown')}")
    print(f"  Iteration:  {state.get('current_iteration', 0)}")
    print(f"  Sessions:   {state.get('session_count', 0)}")
    print(f"  Findings:   {state.get('total_findings', 0)}")

    findings = state.get("findings_by_severity", {})
    if any(findings.values()):
        parts = []
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            count = findings.get(sev, 0)
            if count > 0:
                parts.append(f"{sev}: {count}")
        print(f"  Breakdown:  {', '.join(parts)}")

    fixes_a = state.get("fixes_attempted", 0)
    fixes_m = state.get("fixes_merged", 0)
    prs = state.get("prs_created", 0)
    if fixes_a > 0:
        rate = f"{fixes_m}/{fixes_a} ({100 * fixes_m // fixes_a}%)"
        print(f"  Fixes:      {rate}  PRs: {prs}")

    reviewed = state.get("partition_last_reviewed", {})
    coverage = state.get("coverage_percent", 0.0)
    print(f"  Coverage:   {coverage:.1f}% ({len(reviewed)} partitions reviewed)")

    last = state.get("last_review")
    if last:
        if isinstance(last, dict):
            last = last.get("timestamp", str(last))
        print(f"  Last review: {last}")

    current = state.get("current_partition")
    if current:
        print(f"  Active:     {current}")

    if config:
        cmds = config.get("commands", {})
        print(f"  Build:  {cmds.get('build') or '(none)'}")
        print(f"  Test:   {cmds.get('test') or '(none)'}")
        print(f"  Lint:   {cmds.get('lint') or '(none)'}")

    print("=" * 50)


# ---------------------------------------------------------------------------
# Install Command
# ---------------------------------------------------------------------------


def install_sentinel(project_path: str):
    """Install runner, dashboard, and Makefile targets."""
    project_path = os.path.abspath(project_path)
    sdir = _sentinel_dir(project_path)

    if not os.path.exists(os.path.join(sdir, SENTINEL_STATE)):
        print("Sentinel not initialized. Run: ouro-sentinel init " + project_path)
        sys.exit(1)

    config = load_config(project_path) or generate_config(project_path)

    # Install runner
    _install_template_file(
        "sentinel-runner.sh.template",
        os.path.join(sdir, "sentinel-runner.sh"),
        config,
        project_path,
        executable=True,
    )

    # Install dashboard
    _install_template_file(
        "sentinel-dashboard.sh.template",
        os.path.join(sdir, "sentinel-dashboard.sh"),
        config,
        project_path,
        executable=True,
    )

    # Print Makefile targets
    makefile_content = _render_makefile_targets(sdir, config)

    print()
    print("Sentinel installed:")
    print(f"  Runner:    {os.path.join(sdir, 'sentinel-runner.sh')}")
    print(f"  Dashboard: {os.path.join(sdir, 'sentinel-dashboard.sh')}")
    print()
    print("Add these targets to your Makefile:")
    print("─" * 50)
    print(makefile_content)
    print("─" * 50)
    print()
    print("Usage:")
    print("  make sentinel-start     # Start 24/7 review loop")
    print("  make sentinel-stop      # Stop the loop")
    print("  make sentinel-dashboard # View live dashboard")
    print("  make sentinel-status    # Quick status check")


def _install_template_file(
    template_name: str,
    dest_path: str,
    config: dict,
    project_path: str,
    executable: bool = False,
):
    """Read a template, replace placeholders, write to dest."""
    template = _read_template(template_name)

    runner = config.get("runner", {})
    commands = config.get("commands", {})

    replacements = {
        "{{MODEL}}": runner.get("model", "claude-opus-4-6"),
        "{{MAX_TURNS}}": str(runner.get("max_turns", 200)),
        "{{TIMEOUT}}": str(runner.get("session_timeout_minutes", 120)),
        "{{COOLDOWN}}": str(runner.get("cooldown_seconds", 30)),
        "{{BUILD_COMMAND}}": commands.get("build") or "",
        "{{TEST_COMMAND}}": commands.get("test") or "",
        "{{LINT_COMMAND}}": commands.get("lint") or "",
    }

    content = template
    for key, value in replacements.items():
        content = content.replace(key, value)

    with open(dest_path, "w") as f:
        f.write(content)

    if executable:
        st = os.stat(dest_path)
        os.chmod(dest_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _render_makefile_targets(sdir: str, config: dict) -> str:
    """Generate Makefile target snippet with relative paths."""
    runner = ".ouro/sentinel/sentinel-runner.sh"
    dashboard = ".ouro/sentinel/sentinel-dashboard.sh"

    return f"""\
# --- Ouro Sentinel targets ---
sentinel-start:
\t@{runner} start

sentinel-stop:
\t@{runner} stop

sentinel-dashboard:
\t@{dashboard}

sentinel-status:
\t@ouro-sentinel status .
"""


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main():
    """CLI entry point for ouro-sentinel."""
    parser = argparse.ArgumentParser(
        description="Ouro Sentinel — Autonomous code review loop"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init
    init_parser = subparsers.add_parser(
        "init", help="Initialize sentinel for a project"
    )
    init_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory (default: current dir)",
    )

    # partition
    part_parser = subparsers.add_parser("partition", help="Regenerate partitions")
    part_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory (default: current dir)",
    )

    # status
    status_parser = subparsers.add_parser("status", help="Show sentinel status")
    status_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory (default: current dir)",
    )

    # install
    install_parser = subparsers.add_parser("install", help="Install runner + dashboard")
    install_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory (default: current dir)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        init_sentinel(args.path)
    elif args.command == "partition":
        repartition(args.path)
    elif args.command == "status":
        show_status(args.path)
    elif args.command == "install":
        install_sentinel(args.path)


if __name__ == "__main__":
    main()
