"""
Project initialization and scanning for Ouro Loop.
Scans project structure, generates initial state, installs templates.

Usage:
    python prepare.py scan [path]           # Scan project structure
    python prepare.py init [path]           # Initialize .ouro/ directory
    python prepare.py template <type> [path] # Copy template to project

This file is read-only in the Ouro Loop methodology.
The AI agent does not modify this file.
"""

import os
import sys
import json
import shutil
import argparse
from datetime import datetime, timezone
from collections import Counter

# Import shared constants from framework.py (DRY)
from framework import (
    OURO_DIR,
    STATE_FILE,
    RESULTS_FILE,
    CLAUDE_MD_FILENAME,
    parse_claude_md,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
def _find_templates_dir():
    """Locate templates: ouro_templates package first, then adjacent dir."""
    try:
        import ouro_templates

        pkg_dir = os.path.dirname(ouro_templates.__file__)
        if os.path.isdir(pkg_dir):
            return pkg_dir
    except ImportError:
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ouro_templates")


TEMPLATES_DIR = _find_templates_dir()
MODULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modules")

# File extensions to language mapping
LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".jsx": "JavaScript (React)",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".sol": "Solidity",
    ".move": "Move",
    ".vy": "Vyper",
    ".sql": "SQL",
    ".sh": "Shell",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".svelte": "Svelte",
    ".vue": "Vue",
}

# Directories to skip during scanning
SKIP_DIRS = {
    ".git",
    ".ouro",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "build",
    "dist",
    "target",
    ".idea",
    ".vscode",
    "vendor",
    "Pods",
    ".build",
    "DerivedData",
    ".cache",
}

# Marker files that indicate project type
PROJECT_MARKERS = {
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "package.json": "Node.js",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Gemfile": "Ruby",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Kotlin (Gradle)",
    "Package.swift": "Swift",
    "Podfile": "iOS",
    "hardhat.config.js": "Solidity (Hardhat)",
    "foundry.toml": "Solidity (Foundry)",
    "docker-compose.yml": "Docker",
    "Dockerfile": "Docker",
    "Makefile": "Make",
}

# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _detect_project_types(project_path: str) -> list:
    """Detect project types from marker files."""
    types = []
    for marker, ptype in PROJECT_MARKERS.items():
        if os.path.exists(os.path.join(project_path, marker)):
            types.append(ptype)
    return types


def _scan_files(project_path: str) -> dict:
    """Walk the project tree and collect file statistics.

    Returns a dict with: languages, file_count, dir_count, total_lines,
    has_claude_md, has_tests, has_ci.
    """
    stats = {
        "languages": Counter(),
        "file_count": 0,
        "dir_count": 0,
        "total_lines": 0,
        "has_claude_md": False,
        "has_tests": False,
        "has_ci": False,
    }

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        stats["dir_count"] += len(dirs)

        rel_root = os.path.relpath(root, project_path)

        for fname in files:
            filepath = os.path.join(root, fname)
            stats["file_count"] += 1

            # Language detection
            ext = os.path.splitext(fname)[1].lower()
            if ext in LANG_MAP:
                stats["languages"][LANG_MAP[ext]] += 1
                # Count lines for code files
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        stats["total_lines"] += sum(1 for _ in f)
                except (OSError, PermissionError):
                    pass

            # Special file detection
            if fname == CLAUDE_MD_FILENAME:
                stats["has_claude_md"] = True

            # Test detection
            if "test" in fname.lower() or "spec" in fname.lower():
                stats["has_tests"] = True

        # CI detection
        if rel_root in [".github/workflows", ".circleci", ".gitlab-ci"]:
            stats["has_ci"] = True

    return stats


def _get_top_directories(project_path: str) -> list:
    """List top-level directories, excluding SKIP_DIRS."""
    try:
        return sorted(
            [
                d
                for d in os.listdir(project_path)
                if os.path.isdir(os.path.join(project_path, d)) and d not in SKIP_DIRS
            ]
        )
    except OSError:
        return []


def scan_project(project_path: str) -> dict:
    """Scan a project directory and return a structured summary.

    Orchestrates sub-functions for project type detection, file scanning,
    BOUND detection, and directory listing (SRP).
    """
    project_path = os.path.abspath(project_path)
    if not os.path.isdir(project_path):
        print(f"Error: {project_path} is not a directory")
        sys.exit(1)

    # File statistics
    file_stats = _scan_files(project_path)

    # BOUND detection via shared parser
    bound_data = parse_claude_md(project_path)

    result = {
        "path": project_path,
        "name": os.path.basename(project_path),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "project_types": _detect_project_types(project_path),
        "languages": dict(file_stats["languages"].most_common(10)),
        "file_count": file_stats["file_count"],
        "dir_count": file_stats["dir_count"],
        "total_lines": file_stats["total_lines"],
        "top_directories": _get_top_directories(project_path),
        "has_claude_md": file_stats["has_claude_md"],
        "has_tests": file_stats["has_tests"],
        "has_ci": file_stats["has_ci"],
        "bound_detected": bound_data["has_bound"],
        "danger_zones": bound_data["danger_zones"],
    }

    return result


def print_scan_report(scan: dict):
    """Print a human-readable scan report."""
    print(f"{'=' * 60}")
    print("  Ouro Loop — Project Scan")
    print(f"{'=' * 60}")
    print(f"  Project:    {scan['name']}")
    print(f"  Path:       {scan['path']}")
    print(f"  Types:      {', '.join(scan['project_types']) or 'Unknown'}")
    print(f"  Files:      {scan['file_count']}")
    print(f"  Dirs:       {scan['dir_count']}")
    print(f"  Lines:      {scan['total_lines']:,}")
    print()

    if scan["languages"]:
        print("  Languages:")
        for lang, count in scan["languages"].items():
            bar = "#" * min(count, 40)
            print(f"    {lang:20s} {count:4d} files  {bar}")
        print()

    print(f"  CLAUDE.md:  {'Found' if scan['has_claude_md'] else 'Not found'}")
    print(f"  BOUND:      {'Detected' if scan['bound_detected'] else 'Not defined'}")
    print(f"  Tests:      {'Found' if scan['has_tests'] else 'Not found'}")
    print(f"  CI:         {'Found' if scan['has_ci'] else 'Not found'}")
    print()

    if scan["top_directories"]:
        print(f"  Structure:  {', '.join(scan['top_directories'][:10])}")
        if len(scan["top_directories"]) > 10:
            print(f"              ... and {len(scan['top_directories']) - 10} more")

    print(f"{'=' * 60}")

    # Recommendations
    recommendations = []
    if not scan["bound_detected"]:
        recommendations.append(
            "Define BOUND (DANGER ZONES, NEVER DO, IRON LAWS) before building"
        )
    if not scan["has_tests"]:
        recommendations.append("Add tests — VERIFY stage requires testable assertions")
    if not scan["has_claude_md"]:
        recommendations.append(
            "Create CLAUDE.md with BOUND section (use: python prepare.py template claude)"
        )
    if not scan["has_ci"]:
        recommendations.append("Consider adding CI for automated Layer 2 verification")

    if recommendations:
        print()
        print("  Recommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"    {i}. {rec}")
        print()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def init_ouro(project_path: str):
    """Initialize .ouro/ directory with initial state."""
    ouro_path = os.path.join(project_path, OURO_DIR)

    if os.path.exists(os.path.join(ouro_path, STATE_FILE)):
        print(f"Ouro already initialized at {ouro_path}")
        print("Use 'python framework.py status' to view current state.")
        return

    os.makedirs(ouro_path, exist_ok=True)

    # Scan the project first
    scan = scan_project(project_path)

    # Create initial state
    state = {
        "version": "0.1.0",
        "initialized_at": datetime.now(timezone.utc).isoformat(),
        "project_name": scan["name"],
        "project_types": scan["project_types"],
        "current_stage": "BOUND",
        "current_phase": None,
        "total_phases": 0,
        "bound_defined": scan["bound_detected"],
        "history": [],
    }

    state_path = os.path.join(ouro_path, STATE_FILE)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Create results TSV header
    results_path = os.path.join(project_path, RESULTS_FILE)
    if not os.path.exists(results_path):
        with open(results_path, "w") as f:
            f.write(
                "phase\tverdict\tbound_violations\ttest_pass_rate\tscope_deviation\tnotes\n"
            )

    print(f"Ouro initialized at {ouro_path}")
    print(f"  State:   {state_path}")
    print(f"  Results: {results_path}")
    print()

    if not scan["bound_detected"]:
        print("Next step: Define BOUND before starting BUILD.")
        print("  Option 1: Add ## BOUND section to CLAUDE.md manually")
        print("  Option 2: Run 'python prepare.py template claude' for a template")
    else:
        print("BOUND detected. Ready to start the Ouro Loop.")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATE_MAP = {
    "claude": "CLAUDE.md.template",
    "phase": "phase-plan.md.template",
    "verify": "verify-checklist.md.template",
}


def install_template(template_type: str, project_path: str):
    """Copy a template to the project directory."""
    if template_type not in TEMPLATE_MAP:
        print(f"Unknown template type: {template_type}")
        print(f"Available: {', '.join(TEMPLATE_MAP.keys())}")
        sys.exit(1)

    template_name = TEMPLATE_MAP[template_type]
    src = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(src):
        print(f"Template not found: {src}")
        sys.exit(1)

    # Determine output filename (strip .template suffix)
    out_name = template_name.replace(".template", "")
    dst = os.path.join(project_path, out_name)

    if os.path.exists(dst):
        print(f"File already exists: {dst}")
        print("Remove it first or merge manually.")
        return

    shutil.copy2(src, dst)
    print(f"Template installed: {dst}")
    print(f"  Edit this file to define your project's {template_type} configuration.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ouro Loop — Project initialization and scanning"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan project structure")
    scan_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to scan (default: current dir)",
    )

    # init
    init_parser = subparsers.add_parser("init", help="Initialize .ouro/ directory")
    init_parser.add_argument(
        "path", nargs="?", default=".", help="Project directory (default: current dir)"
    )

    # template
    tmpl_parser = subparsers.add_parser("template", help="Install a template")
    tmpl_parser.add_argument(
        "type", choices=TEMPLATE_MAP.keys(), help="Template type to install"
    )
    tmpl_parser.add_argument(
        "path", nargs="?", default=".", help="Project directory (default: current dir)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "scan":
        scan = scan_project(args.path)
        print_scan_report(scan)
    elif args.command == "init":
        init_ouro(args.path)
    elif args.command == "template":
        install_template(args.type, args.path)
