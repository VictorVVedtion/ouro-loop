"""
Ouro Loop — Lightweight runtime for development methodology.
State management, stage transitions, verification, and logging.

Usage:
    python framework.py status [path]       # Show current Ouro state
    python framework.py verify [path]       # Run verification checks
    python framework.py log <verdict> [path] # Log phase result
    python framework.py advance [path]      # Advance to next phase
    python framework.py bound-check [path]  # Check BOUND compliance

This file can be extended by AI agents with project-specific logic.
It corresponds to autoresearch's train.py — the file the agent iterates on.
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OURO_DIR = ".ouro"
STATE_FILE = "state.json"
RESULTS_FILE = "ouro-results.tsv"

STAGES = ["BOUND", "MAP", "PLAN", "BUILD", "VERIFY", "LOOP"]

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

COMPLEXITY_ROUTES = {
    "trivial": {"max_lines": 20, "max_files": 1, "phases": 0},
    "simple": {"max_lines": 100, "max_files": 3, "phases": 2},
    "complex": {"max_lines": 500, "max_files": 10, "phases": 5},
    "architectural": {"max_lines": None, "max_files": None, "phases": None},
}

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state(project_path: str, required: bool = True) -> dict:
    """Load ouro state from .ouro/state.json.

    If required=False, returns None when state doesn't exist (for verify).
    """
    state_path = os.path.join(project_path, OURO_DIR, STATE_FILE)
    if not os.path.exists(state_path):
        if not required:
            return None
        print(f"Ouro not initialized. Run: python prepare.py init {project_path}")
        sys.exit(1)
    try:
        with open(state_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        if not required:
            return None
        print(f"Corrupted state file: {state_path}")
        print(f"Error: {e}")
        print(f"Run: python prepare.py init {project_path}  (or delete .ouro/ to reset)")
        sys.exit(1)


def save_state(project_path: str, state: dict):
    """Save ouro state to .ouro/state.json."""
    state_path = os.path.join(project_path, OURO_DIR, STATE_FILE)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def show_status(project_path: str):
    """Display current Ouro state."""
    state = load_state(project_path)

    print(f"{'=' * 50}")
    print(f"  Ouro Loop — Status")
    print(f"{'=' * 50}")
    print(f"  Project:    {state.get('project_name', 'Unknown')}")
    print(f"  Stage:      {state.get('current_stage', 'UNKNOWN')}")

    phase = state.get("current_phase")
    total = state.get("total_phases", 0)
    if phase is not None and total > 0:
        print(f"  Phase:      {phase}/{total}")
    else:
        print(f"  Phase:      N/A")

    print(f"  BOUND:      {'Defined' if state.get('bound_defined') else 'Not defined'}")

    history = state.get("history", [])
    if history:
        last = history[-1]
        print(f"  Last:       {last.get('stage', '?')} — {last.get('verdict', '?')}")
        print(f"              at {last.get('timestamp', '?')}")

    passed = sum(1 for h in history if h.get("verdict") == "PASS")
    failed = sum(1 for h in history if h.get("verdict") in ("FAIL", "RETRY"))
    print(f"  History:    {passed} passed, {failed} failed, {len(history)} total")
    print(f"{'=' * 50}")

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def run_verification(project_path: str) -> dict:
    """Run multi-layer verification checks."""
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layer1_gates": {},
        "layer2_self": {},
        "overall": "PASS",
    }

    # Layer 1: Gates
    results["layer1_gates"] = run_gates(project_path)

    # Layer 2: Self-assessment
    results["layer2_self"] = run_self_assessment(project_path)

    # Determine overall verdict
    gate_failures = [g for g, v in results["layer1_gates"].items() if v["status"] == "FAIL"]
    self_failures = [s for s, v in results["layer2_self"].items() if v["status"] == "FAIL"]

    if gate_failures or self_failures:
        results["overall"] = "FAIL"
        results["failures"] = gate_failures + self_failures

    return results


def run_gates(project_path: str) -> dict:
    """Layer 1: Automated gates."""
    gates = {}

    # EXIST gate: check that key files exist
    claude_md = os.path.join(project_path, "CLAUDE.md")
    claude_exists = os.path.exists(claude_md)
    if claude_exists:
        gates["EXIST"] = {"status": "PASS", "detail": "CLAUDE.md exists"}
    else:
        # No CLAUDE.md — check if state says BOUND should be defined
        state = load_state(project_path, required=False)
        bound_expected = state.get("bound_defined", False) if state else False
        if bound_expected:
            gates["EXIST"] = {"status": "FAIL", "detail": "CLAUDE.md missing but BOUND was expected"}
        else:
            gates["EXIST"] = {"status": "WARN", "detail": "No CLAUDE.md — define BOUND before BUILD"}


    # RELEVANCE gate: check git status for scope
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, cwd=project_path, timeout=10
        )
        changed_files = [line.strip().split()[-1] for line in result.stdout.strip().split("\n") if line.strip()]
        gates["RELEVANCE"] = {
            "status": "PASS",
            "detail": f"{len(changed_files)} files changed",
            "files": changed_files[:20],
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        gates["RELEVANCE"] = {"status": "SKIP", "detail": "git not available"}

    # ROOT_CAUSE gate: check for repeated edits to same file
    try:
        result = subprocess.run(
            ["git", "log", "--name-only", "--pretty=format:", "-10"],
            capture_output=True, text=True, cwd=project_path, timeout=10
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        from collections import Counter
        freq = Counter(files)
        hot_files = {f: c for f, c in freq.items() if c >= 3}
        gates["ROOT_CAUSE"] = {
            "status": "WARN" if hot_files else "PASS",
            "detail": f"Hot files: {', '.join(hot_files.keys())}" if hot_files else "No repeated edits detected",
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        gates["ROOT_CAUSE"] = {"status": "SKIP", "detail": "git not available"}

    # MOMENTUM gate: check recent commit frequency
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, cwd=project_path, timeout=10
        )
        commits = [l for l in result.stdout.strip().split("\n") if l.strip()]
        gates["MOMENTUM"] = {
            "status": "PASS" if len(commits) >= 2 else "WARN",
            "detail": f"{len(commits)} recent commits",
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        gates["MOMENTUM"] = {"status": "SKIP", "detail": "git not available"}

    return gates


def run_self_assessment(project_path: str) -> dict:
    """Layer 2: Self-assessment checks."""
    checks = {}

    # BOUND compliance: check CLAUDE.md for BOUND section
    claude_md = os.path.join(project_path, "CLAUDE.md")
    if os.path.exists(claude_md):
        try:
            with open(claude_md, "r", encoding="utf-8") as f:
                content = f.read()
            has_bound = any(m in content for m in ["## BOUND", "# BOUND", "DANGER ZONE", "IRON LAW"])
            checks["bound_compliance"] = {
                "status": "PASS" if has_bound else "WARN",
                "detail": "BOUND section found" if has_bound else "No BOUND section in CLAUDE.md",
            }
        except OSError:
            checks["bound_compliance"] = {"status": "SKIP", "detail": "Cannot read CLAUDE.md"}
    else:
        checks["bound_compliance"] = {"status": "SKIP", "detail": "No CLAUDE.md"}

    # Test detection
    test_found = False
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv", ".ouro"}]
        for f in files:
            if "test" in f.lower() or "spec" in f.lower():
                test_found = True
                break
        if test_found:
            break

    checks["tests_exist"] = {
        "status": "PASS" if test_found else "WARN",
        "detail": "Test files found" if test_found else "No test files detected",
    }

    return checks


def print_verification(results: dict):
    """Print verification results."""
    print(f"{'=' * 50}")
    print(f"  Ouro Loop — Verification")
    print(f"{'=' * 50}")

    print("  Layer 1 — Gates:")
    for gate, info in results.get("layer1_gates", {}).items():
        icon = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}.get(info["status"], "?")
        print(f"    [{icon}] {gate:15s} {info['detail']}")

    print()
    print("  Layer 2 — Self-Assessment:")
    for check, info in results.get("layer2_self", {}).items():
        icon = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}.get(info["status"], "?")
        print(f"    [{icon}] {check:15s} {info['detail']}")

    print()
    overall = results.get("overall", "UNKNOWN")
    print(f"  Overall: {overall}")

    if overall == "FAIL":
        failures = results.get("failures", [])
        print(f"  Failures: {', '.join(failures)}")

    print(f"{'=' * 50}")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_phase_result(project_path: str, verdict: str, notes: str = ""):
    """Log a phase result to ouro-results.tsv and update state."""
    state = load_state(project_path)
    phase = state.get("current_phase")
    total = state.get("total_phases", 0)

    # Handle missing phase plan gracefully
    if phase is None:
        phase_str = state.get("current_stage", "N/A")
    else:
        phase_str = f"{phase}/{total}"

    # Run quick verification for the log
    results = run_verification(project_path)

    # Count bound violations
    gate_results = results.get("layer1_gates", {})
    bound_violations = sum(1 for v in gate_results.values() if v.get("status") == "FAIL")

    # Log to TSV
    results_path = os.path.join(project_path, RESULTS_FILE)
    with open(results_path, "a") as f:
        f.write(f"{phase_str}\t{verdict}\t{bound_violations}\t"
                f"N/A\tnone\t{notes}\n")

    # Update state history
    state.setdefault("history", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": state.get("current_stage", "UNKNOWN"),
        "phase": phase_str,
        "verdict": verdict,
        "bound_violations": bound_violations,
        "notes": notes,
    })

    # Keep last 50 history entries
    state["history"] = state["history"][-50:]
    save_state(project_path, state)

    print(f"Logged: {phase_str} — {verdict}")

# ---------------------------------------------------------------------------
# Phase advancement
# ---------------------------------------------------------------------------

def advance_phase(project_path: str):
    """Advance to the next phase."""
    state = load_state(project_path)
    phase = state.get("current_phase")
    total = state.get("total_phases", 0)

    if phase is None:
        print("No phase plan active. Use PLAN stage to define phases first.")
        return

    if phase >= total:
        print(f"All {total} phases complete.")
        state["current_stage"] = "LOOP"
        state["current_phase"] = None
        save_state(project_path, state)
        return

    state["current_phase"] = phase + 1
    state["current_stage"] = "BUILD"
    save_state(project_path, state)
    print(f"Advanced to phase {phase + 1}/{total}")

# ---------------------------------------------------------------------------
# BOUND check
# ---------------------------------------------------------------------------

def check_bound(project_path: str):
    """Check BOUND compliance in CLAUDE.md."""
    claude_md = os.path.join(project_path, "CLAUDE.md")
    if not os.path.exists(claude_md):
        print("No CLAUDE.md found. BOUND not defined.")
        print("Run: python prepare.py template claude")
        return

    with open(claude_md, "r", encoding="utf-8") as f:
        content = f.read()

    # Detect template placeholders — template has keywords but no real content
    template_markers = ["[PROJECT_NAME]", "[why it's dangerous]", "[action]", "[Invariant 1"]
    is_template = any(marker in content for marker in template_markers)
    if is_template:
        print(f"{'=' * 50}")
        print(f"  Ouro Loop — BOUND Check")
        print(f"{'=' * 50}")
        print(f"  [!] CLAUDE.md is still a template — fill in real BOUND values")
        print(f"  Edit CLAUDE.md to replace [placeholders] with actual boundaries")
        print(f"{'=' * 50}")
        return

    print(f"{'=' * 50}")
    print(f"  Ouro Loop — BOUND Check")
    print(f"{'=' * 50}")

    sections = {
        "DANGER ZONES": "DANGER ZONE" in content or "DANGER_ZONE" in content,
        "NEVER DO": "NEVER DO" in content or "NEVER_DO" in content,
        "IRON LAWS": "IRON LAW" in content or "IRON_LAW" in content,
    }

    all_defined = True
    for section, found in sections.items():
        icon = "+" if found else "X"
        print(f"  [{icon}] {section}")
        if not found:
            all_defined = False

    print()
    if all_defined:
        print("  BOUND fully defined. Ready for BUILD.")
    else:
        missing = [s for s, f in sections.items() if not f]
        print(f"  Missing: {', '.join(missing)}")
        print("  Define these before starting BUILD stage.")

    print(f"{'=' * 50}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ouro Loop — Development methodology runtime"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status
    status_parser = subparsers.add_parser("status", help="Show Ouro state")
    status_parser.add_argument("path", nargs="?", default=".", help="Project directory")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Run verification checks")
    verify_parser.add_argument("path", nargs="?", default=".", help="Project directory")

    # log
    log_parser = subparsers.add_parser("log", help="Log phase result")
    log_parser.add_argument("verdict", choices=["PASS", "FAIL", "RETRY", "SKIP"],
                            help="Phase verdict")
    log_parser.add_argument("--notes", default="", help="Notes for this phase")
    log_parser.add_argument("--path", default=".", help="Project directory")

    # advance
    advance_parser = subparsers.add_parser("advance", help="Advance to next phase")
    advance_parser.add_argument("path", nargs="?", default=".", help="Project directory")

    # bound-check
    bound_parser = subparsers.add_parser("bound-check", help="Check BOUND compliance")
    bound_parser.add_argument("path", nargs="?", default=".", help="Project directory")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "status":
        show_status(args.path)
    elif args.command == "verify":
        results = run_verification(args.path)
        print_verification(results)
    elif args.command == "log":
        log_phase_result(getattr(args, 'path', '.'), args.verdict, args.notes)
    elif args.command == "advance":
        advance_phase(args.path)
    elif args.command == "bound-check":
        check_bound(args.path)
