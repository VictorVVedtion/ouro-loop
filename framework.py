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
import re
import sys
import json
import shutil
import argparse
import subprocess
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OURO_DIR = ".ouro"
STATE_FILE = "state.json"
RESULTS_FILE = "ouro-results.tsv"
REFLECTIVE_LOG = "reflective-log.jsonl"
CLAUDE_MD_FILENAME = "CLAUDE.md"

STAGES = ["BOUND", "MAP", "PLAN", "BUILD", "VERIFY", "LOOP"]

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

COMPLEXITY_ROUTES = {
    "trivial": {"max_lines": 20, "max_files": 1, "phases": 0},
    "simple": {"max_lines": 100, "max_files": 3, "phases": 2},
    "complex": {"max_lines": 500, "max_files": 10, "phases": 5},
    "architectural": {"max_lines": None, "max_files": None, "phases": None},
}

# Shared BOUND markers — used by both framework.py and prepare.py (DRY)
BOUND_SECTION_MARKERS = ["## BOUND", "# BOUND"]
BOUND_CONTENT_MARKERS = [
    "DANGER ZONE",
    "DANGER_ZONE",
    "NEVER DO",
    "NEVER_DO",
    "IRON LAW",
    "IRON_LAW",
]
BOUND_ALL_MARKERS = BOUND_SECTION_MARKERS + BOUND_CONTENT_MARKERS

# Template placeholders indicating unfilled CLAUDE.md
TEMPLATE_PLACEHOLDERS = [
    "[PROJECT_NAME]",
    "[why it's dangerous]",
    "[action]",
    "[Invariant 1",
]

# Magic values extracted as named constants
GIT_TIMEOUT_SECONDS = 10
HOT_FILE_EDIT_THRESHOLD = 3
HISTORY_LIMIT = 50
MAX_RETRY_BEFORE_ESCALATE = 3

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
        print(
            f"Run: python prepare.py init {project_path}  (or delete .ouro/ to reset)"
        )
        sys.exit(1)


def save_state(project_path: str, state: dict):
    """Save ouro state to .ouro/state.json (atomic write)."""
    state_path = os.path.join(project_path, OURO_DIR, STATE_FILE)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp_path = state_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
    try:
        os.replace(tmp_path, state_path)
    except OSError:
        shutil.move(tmp_path, state_path)


# ---------------------------------------------------------------------------
# CLAUDE.md parsing
# ---------------------------------------------------------------------------


def _get_claude_md_path(project_path: str) -> str:
    """Return the path to CLAUDE.md within the project."""
    return os.path.join(project_path, CLAUDE_MD_FILENAME)


def parse_claude_md(project_path: str) -> dict:
    """Parse CLAUDE.md into structured BOUND data.

    Returns a dict with:
        danger_zones: list[str] — paths/patterns from DANGER ZONES section
        never_do: list[str] — prohibitions from NEVER DO section
        iron_laws: list[str] — invariants from IRON LAWS section
        has_bound: bool — whether any BOUND markers were found
        raw_content: str — full file content (empty string if file missing)
    """
    result = {
        "danger_zones": [],
        "never_do": [],
        "iron_laws": [],
        "has_bound": False,
        "raw_content": "",
        "parse_source": "none",  # "structured", "fallback", or "none"
    }

    claude_md = _get_claude_md_path(project_path)
    if not os.path.exists(claude_md):
        return result

    try:
        with open(claude_md, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return result

    result["raw_content"] = content
    result["has_bound"] = any(m in content for m in BOUND_ALL_MARKERS)

    # --- Primary extraction: standard section headers ---

    # Extract DANGER ZONES — lines with backtick-wrapped paths
    dz_match = re.search(
        r"(?:###?\s*DANGER\s*ZONES?)(.*?)(?=\n###?\s|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if dz_match:
        zone_text = dz_match.group(1)
        result["danger_zones"] = re.findall(r"`([^`]+)`", zone_text)

    # Extract NEVER DO — list items
    nd_match = re.search(
        r"(?:###?\s*NEVER\s*DO)(.*?)(?=\n###?\s|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if nd_match:
        nd_text = nd_match.group(1)
        result["never_do"] = [
            line.strip().lstrip("-*").strip()
            for line in nd_text.strip().split("\n")
            if line.strip() and line.strip().startswith(("-", "*"))
        ]

    # Extract IRON LAWS — list items
    il_match = re.search(
        r"(?:###?\s*IRON\s*LAWS?)(.*?)(?=\n###?\s|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if il_match:
        il_text = il_match.group(1)
        result["iron_laws"] = [
            line.strip().lstrip("-*").strip()
            for line in il_text.strip().split("\n")
            if line.strip() and line.strip().startswith(("-", "*"))
        ]

    # Mark source if primary extraction succeeded
    if any([result["danger_zones"], result["never_do"], result["iron_laws"]]):
        result["parse_source"] = "structured"
        return result

    # --- Fallback extraction: prose-style CLAUDE.md without standard headers ---
    # Only runs if primary extraction found nothing but has_bound is True
    # (keywords exist but not in structured sections)

    if result["has_bound"] and not any(
        [result["danger_zones"], result["never_do"], result["iron_laws"]]
    ):
        # Fallback DANGER ZONES: backtick-wrapped paths on lines near
        # "DANGER" keyword (within 3 lines)
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "DANGER" in line.upper():
                # Scan this line and nearby lines for backtick paths
                window = lines[max(0, i - 1) : i + 4]
                for wline in window:
                    for path in re.findall(r"`([^`]+)`", wline):
                        # Only include path-like strings (contain / or .)
                        if "/" in path or path.endswith(
                            (".py", ".sh", ".js", ".ts", ".rs", ".go")
                        ):
                            if path not in result["danger_zones"]:
                                result["danger_zones"].append(path)

        # Fallback NEVER DO: lines starting with "Never" or "Do not" or
        # "- Never" anywhere in the file
        for line in lines:
            stripped = line.strip().lstrip("-*").strip()
            if re.match(r"^(Never|Do not|NEVER)\b", stripped):
                if stripped not in result["never_do"]:
                    result["never_do"].append(stripped)

        # Fallback IRON LAWS: lines containing "must" or "always" near
        # backtick-wrapped code/paths (heuristic for invariants)
        for line in lines:
            stripped = line.strip().lstrip("-*").strip()
            if re.search(r"\b(must|always|required)\b", stripped, re.IGNORECASE):
                if "`" in line and stripped not in result["iron_laws"]:
                    result["iron_laws"].append(stripped)

        if any([result["danger_zones"], result["never_do"], result["iron_laws"]]):
            result["parse_source"] = "fallback"

    return result


def _file_in_danger_zone(file_path: str, danger_zones: list) -> Optional[str]:
    """Check if a file path matches any DANGER ZONE pattern.

    Uses path-segment-aware matching to avoid false positives:
    - Zone "auth/" matches "auth/login.py" but NOT "unauthorized.py"
    - Zone "auth/core.py" matches exactly that file
    - Zone ending with "/" is treated as a directory prefix

    Returns the matched zone pattern, or None if no match.
    """
    if not file_path:
        return None

    # Normalize separators
    norm_file = file_path.replace("\\", "/")
    file_segments = norm_file.split("/")

    for zone in danger_zones:
        if not zone:
            continue

        norm_zone = zone.replace("\\", "/")

        # Exact match
        if norm_file == norm_zone:
            return zone

        # Directory prefix: zone "src/payments/" → file must start with that path
        if norm_zone.endswith("/"):
            if norm_file.startswith(norm_zone):
                return zone
            continue

        # File match: zone "auth/core.py" → exact path segment match
        zone_segments = norm_zone.split("/")

        # Check if zone segments appear as contiguous subsequence in file path
        zone_len = len(zone_segments)
        for i in range(len(file_segments) - zone_len + 1):
            if file_segments[i : i + zone_len] == zone_segments:
                return zone

    return None


# ---------------------------------------------------------------------------
# Complexity detection
# ---------------------------------------------------------------------------


def detect_complexity(
    project_path: str, changed_files: list = None, danger_zones: list = None
) -> dict:
    """Detect task complexity based on file count and DANGER ZONE proximity.

    Returns:
        level: str — trivial/simple/complex/architectural
        reason: str — why this level was chosen
        route: dict — the matching COMPLEXITY_ROUTES entry
    """
    if changed_files is None:
        changed_files = []
    if danger_zones is None:
        danger_zones = []

    num_files = len(changed_files)
    dz_touched = [f for f in changed_files if _file_in_danger_zone(f, danger_zones)]

    # Determine level
    if dz_touched:
        if any("IRON" in str(dz).upper() for dz in dz_touched):
            level = "architectural"
            reason = f"Modifies IRON LAW area: {', '.join(dz_touched[:3])}"
        else:
            level = "complex"
            reason = f"Touches DANGER ZONE: {', '.join(dz_touched[:3])}"
    elif num_files <= 1:
        level = "trivial"
        reason = f"{num_files} file(s), no DANGER ZONE contact"
    elif num_files <= 3:
        level = "simple"
        reason = f"{num_files} files, no DANGER ZONE contact"
    else:
        level = "complex"
        reason = f"{num_files} files across multiple areas"

    return {
        "level": level,
        "reason": reason,
        "route": COMPLEXITY_ROUTES[level],
    }


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def show_status(project_path: str):
    """Display current Ouro state."""
    state = load_state(project_path)

    print(f"{'=' * 50}")
    print("  Ouro Loop — Status")
    print(f"{'=' * 50}")
    print(f"  Project:    {state.get('project_name', 'Unknown')}")
    print(f"  Stage:      {state.get('current_stage', 'UNKNOWN')}")

    phase = state.get("current_phase")
    total = state.get("total_phases", 0)
    if phase is not None and total > 0:
        print(f"  Phase:      {phase}/{total}")
    else:
        print("  Phase:      N/A")

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
    """Run multi-layer verification checks (Layer 1 + 2 + 3)."""
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layer1_gates": {},
        "layer2_self": {},
        "layer3_review": {},
        "overall": "PASS",
    }

    # Refresh bound_defined in state — init snapshot may be stale
    # (user might have added BOUND to CLAUDE.md after init)
    bound_data = parse_claude_md(project_path)
    state = load_state(project_path, required=False)
    if state and state.get("bound_defined") != bound_data["has_bound"]:
        state["bound_defined"] = bound_data["has_bound"]
        save_state(project_path, state)

    # Layer 1: Gates (pass cached bound_data to avoid re-parsing)
    results["layer1_gates"] = run_gates(project_path, _bound_data=bound_data)

    # Layer 2: Self-assessment
    results["layer2_self"] = run_self_assessment(project_path, _bound_data=bound_data)

    # Layer 3: External review triggers
    results["layer3_review"] = _check_layer3_triggers(
        project_path, results, _bound_data=bound_data
    )

    # Determine overall verdict
    gate_failures = [
        g for g, v in results["layer1_gates"].items() if v["status"] == "FAIL"
    ]
    self_failures = [
        s for s, v in results["layer2_self"].items() if v["status"] == "FAIL"
    ]
    review_required = results["layer3_review"].get("required", False)

    if gate_failures or self_failures:
        results["overall"] = "FAIL"
        results["failures"] = gate_failures + self_failures
    elif review_required:
        results["overall"] = "REVIEW"
        results["review_reasons"] = results["layer3_review"].get("reasons", [])
    else:
        # Check if everything is WARN/SKIP with no PASS — project likely not set up
        all_statuses = [v["status"] for v in results["layer1_gates"].values()] + [
            v["status"] for v in results["layer2_self"].values()
        ]
        if all_statuses and "PASS" not in all_statuses:
            results["overall"] = "WARN"

    return results


def _check_layer3_triggers(
    project_path: str, current_results: dict, _bound_data: dict = None
) -> dict:
    """Layer 3: Check if external (human) review is required.

    Triggers:
    - Changes touch a DANGER ZONE
    - IRON LAW needs modification
    - 3+ consecutive RETRY verdicts
    - Failed Layer 1 gate
    """
    review = {"required": False, "reasons": []}

    # Check DANGER ZONE contact via RELEVANCE gate
    relevance = current_results.get("layer1_gates", {}).get("RELEVANCE", {})
    dz_files = relevance.get("danger_zone_files", [])
    if dz_files:
        review["required"] = True
        review["reasons"].append(f"DANGER ZONE touched: {', '.join(dz_files[:3])}")

    # Check for Layer 1 gate failures
    gate_failures = [
        g
        for g, v in current_results.get("layer1_gates", {}).items()
        if v["status"] == "FAIL"
    ]
    if gate_failures:
        review["required"] = True
        review["reasons"].append(f"Layer 1 gate failed: {', '.join(gate_failures)}")

    # Check consecutive RETRY count from state history
    state = load_state(project_path, required=False)
    if state:
        history = state.get("history", [])
        consecutive_retries = 0
        for entry in reversed(history):
            if entry.get("verdict") == "RETRY":
                consecutive_retries += 1
            else:
                break
        if consecutive_retries >= MAX_RETRY_BEFORE_ESCALATE:
            review["required"] = True
            review["reasons"].append(
                f"{consecutive_retries} consecutive RETRY verdicts — "
                f"mandatory user review"
            )

    # Check complexity level (architectural = always review)
    if _bound_data is None:
        _bound_data = parse_claude_md(project_path)
    changed_files = relevance.get("files", [])
    if changed_files:
        complexity = detect_complexity(
            project_path, changed_files, _bound_data["danger_zones"]
        )
        if complexity["level"] == "architectural":
            review["required"] = True
            review["reasons"].append(
                f"Architectural complexity: {complexity['reason']}"
            )

    return review


def run_gates(project_path: str, _bound_data: dict = None) -> dict:
    """Layer 1: Automated gates (EXIST, RELEVANCE, ROOT_CAUSE, RECALL, MOMENTUM)."""
    gates = {}
    if _bound_data is None:
        _bound_data = parse_claude_md(project_path)
    bound_data = _bound_data
    danger_zones = bound_data["danger_zones"]

    # EXIST gate: check that key files exist + DANGER ZONE awareness
    claude_md = _get_claude_md_path(project_path)
    claude_exists = os.path.exists(claude_md)
    if claude_exists:
        gates["EXIST"] = {"status": "PASS", "detail": "CLAUDE.md exists"}
    else:
        state = load_state(project_path, required=False)
        bound_expected = state.get("bound_defined", False) if state else False
        if bound_expected:
            gates["EXIST"] = {
                "status": "FAIL",
                "detail": "CLAUDE.md missing but BOUND was expected",
            }
        else:
            gates["EXIST"] = {
                "status": "WARN",
                "detail": "No CLAUDE.md — define BOUND before BUILD",
            }

    # RELEVANCE gate: check git status for scope + DANGER ZONE overlap
    changed_files = []
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        changed_files = [
            line.strip().split()[-1]
            for line in result.stdout.strip().split("\n")
            if line.strip()
        ]

        # Check if any changed files are in DANGER ZONES
        dz_hits = []
        for f in changed_files:
            zone = _file_in_danger_zone(f, danger_zones)
            if zone:
                dz_hits.append(f"{f} (zone: {zone})")

        if dz_hits:
            gates["RELEVANCE"] = {
                "status": "WARN",
                "detail": f"{len(changed_files)} files changed, "
                f"{len(dz_hits)} in DANGER ZONE: {', '.join(dz_hits[:5])}",
                "files": changed_files[:20],
                "danger_zone_files": dz_hits,
            }
        else:
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
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        freq = Counter(files)
        hot_files = {f: c for f, c in freq.items() if c >= HOT_FILE_EDIT_THRESHOLD}
        gates["ROOT_CAUSE"] = {
            "status": "WARN" if hot_files else "PASS",
            "detail": (
                f"Hot files: {', '.join(hot_files.keys())}"
                if hot_files
                else "No repeated edits detected"
            ),
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        gates["ROOT_CAUSE"] = {"status": "SKIP", "detail": "git not available"}

    # RECALL gate: verify BOUND constraints are accessible and recently read
    if bound_data["has_bound"]:
        recall_issues = []
        if not bound_data["danger_zones"]:
            recall_issues.append("no DANGER ZONES parsed")
        if not bound_data["iron_laws"]:
            recall_issues.append("no IRON LAWS parsed")
        if recall_issues:
            gates["RECALL"] = {
                "status": "WARN",
                "detail": f"BOUND exists but incomplete: {', '.join(recall_issues)}",
            }
        else:
            gates["RECALL"] = {
                "status": "PASS",
                "detail": (
                    f"BOUND loaded: {len(bound_data['danger_zones'])} zones, "
                    f"{len(bound_data['never_do'])} prohibitions, "
                    f"{len(bound_data['iron_laws'])} laws"
                ),
            }
    else:
        gates["RECALL"] = {
            "status": "WARN",
            "detail": "No BOUND defined — constraints may be forgotten",
        }

    # MOMENTUM gate: check recent commit frequency
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        commits = [line for line in result.stdout.strip().split("\n") if line.strip()]
        gates["MOMENTUM"] = {
            "status": "PASS" if len(commits) >= 2 else "WARN",
            "detail": f"{len(commits)} recent commits",
        }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        gates["MOMENTUM"] = {"status": "SKIP", "detail": "git not available"}

    return gates


def run_self_assessment(project_path: str, _bound_data: dict = None) -> dict:
    """Layer 2: Self-assessment checks."""
    checks = {}

    # BOUND compliance: use parse_claude_md() for structured check
    bound_data = (
        _bound_data if _bound_data is not None else parse_claude_md(project_path)
    )
    claude_md = _get_claude_md_path(project_path)
    if os.path.exists(claude_md):
        # File exists but parse returned empty content → read error
        if not bound_data["raw_content"] and os.path.getsize(claude_md) > 0:
            checks["bound_compliance"] = {
                "status": "SKIP",
                "detail": "Cannot read CLAUDE.md",
            }
        elif bound_data["has_bound"]:
            checks["bound_compliance"] = {
                "status": "PASS",
                "detail": "BOUND section found",
            }
        else:
            checks["bound_compliance"] = {
                "status": "WARN",
                "detail": "No BOUND section in CLAUDE.md",
            }
    else:
        checks["bound_compliance"] = {"status": "SKIP", "detail": "No CLAUDE.md"}

    # Test detection
    test_found = False
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d
            for d in dirs
            if d not in {".git", "node_modules", "__pycache__", ".venv", ".ouro"}
        ]
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
    print("  Ouro Loop — Verification")
    print(f"{'=' * 50}")

    print("  Layer 1 — Gates:")
    for gate, info in results.get("layer1_gates", {}).items():
        icon = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}.get(
            info["status"], "?"
        )
        print(f"    [{icon}] {gate:15s} {info['detail']}")

    print()
    print("  Layer 2 — Self-Assessment:")
    for check, info in results.get("layer2_self", {}).items():
        icon = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}.get(
            info["status"], "?"
        )
        print(f"    [{icon}] {check:15s} {info['detail']}")

    # Layer 3
    layer3 = results.get("layer3_review", {})
    print()
    if layer3.get("required"):
        print("  Layer 3 — External Review: REQUIRED")
        for reason in layer3.get("reasons", []):
            print(f"    [!] {reason}")
    else:
        print("  Layer 3 — External Review: Not required")

    print()
    overall = results.get("overall", "UNKNOWN")
    print(f"  Overall: {overall}")

    if overall == "FAIL":
        failures = results.get("failures", [])
        print(f"  Failures: {', '.join(failures)}")
    elif overall == "REVIEW":
        print("  Action: Human review required before continuing")

    print(f"{'=' * 50}")


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

# Pattern detection thresholds
CONSECUTIVE_FAIL_THRESHOLD = 2
VELOCITY_WINDOW = 5
DRIFT_DIRECTORY_THRESHOLD = 5


def detect_patterns(history: list, current_gates: dict = None) -> dict:
    """Analyze history to detect behavioral patterns.

    This is the "Pattern" layer of the reflective log — it identifies
    recurring behaviors that an LLM should be aware of when starting
    a new iteration.

    Returns:
        consecutive_failures: int — how many FAIL/RETRY in a row (tail)
        stuck_loop: bool — same file failing repeatedly
        velocity_trend: str — ACCELERATING / STABLE / DECELERATING / STALLED
        hot_files: list — files appearing in ROOT_CAUSE warnings
        drift_signal: bool — RELEVANCE gate has been warning
        retry_rate: float — percentage of RETRY verdicts in recent history
    """
    patterns = {
        "consecutive_failures": 0,
        "stuck_loop": False,
        "velocity_trend": "UNKNOWN",
        "hot_files": [],
        "drift_signal": False,
        "retry_rate": 0.0,
    }

    # Extract gate-based signals (even with empty history)
    if current_gates:
        root_cause = current_gates.get("ROOT_CAUSE", {})
        detail = root_cause.get("detail", "")
        if "Hot files:" in detail:
            files_str = detail.replace("Hot files: ", "")
            patterns["hot_files"] = [f.strip() for f in files_str.split(",")]

        relevance = current_gates.get("RELEVANCE", {})
        if relevance.get("danger_zone_files"):
            patterns["drift_signal"] = True

    if not history:
        return patterns

    # Consecutive failures (from tail)
    for entry in reversed(history):
        if entry.get("verdict") in ("FAIL", "RETRY"):
            patterns["consecutive_failures"] += 1
        else:
            break

    # Retry rate in recent window
    window = history[-VELOCITY_WINDOW:]
    retries = sum(1 for e in window if e.get("verdict") == "RETRY")
    patterns["retry_rate"] = retries / len(window) if window else 0.0

    # Velocity trend: compare pass rates in two halves of recent history
    # Require >= 6 entries for meaningful trend detection — with 4-5 entries
    # a single RETRY creates misleading DECELERATING signal
    recent = (
        history[-VELOCITY_WINDOW * 2 :]
        if len(history) >= VELOCITY_WINDOW * 2
        else history
    )
    if len(recent) >= 6:
        mid = len(recent) // 2
        first_half = recent[:mid]
        second_half = recent[mid:]
        first_pass_rate = sum(
            1 for e in first_half if e.get("verdict") == "PASS"
        ) / len(first_half)
        second_pass_rate = sum(
            1 for e in second_half if e.get("verdict") == "PASS"
        ) / len(second_half)
        diff = second_pass_rate - first_pass_rate
        # Require > 0.3 swing (not 0.2) to reduce false positives
        if diff > 0.3:
            patterns["velocity_trend"] = "ACCELERATING"
        elif diff < -0.3:
            patterns["velocity_trend"] = "DECELERATING"
        elif second_pass_rate == 0:
            patterns["velocity_trend"] = "STALLED"
        else:
            patterns["velocity_trend"] = "STABLE"

    # Stuck loop: same stage appearing 3+ times consecutively
    if len(history) >= 3:
        last_stages = [e.get("stage") for e in history[-3:]]
        last_verdicts = [e.get("verdict") for e in history[-3:]]
        if len(set(last_stages)) == 1 and all(
            v in ("FAIL", "RETRY") for v in last_verdicts
        ):
            patterns["stuck_loop"] = True

    return patterns


# ---------------------------------------------------------------------------
# Reflective logging (three-layer structured log)
# ---------------------------------------------------------------------------

REFLECTIVE_LOG_LIMIT = 30  # keep last N entries


def build_reflective_entry(
    project_path: str, verdict: str, verification: dict, notes: str = ""
) -> dict:
    """Build a three-layer reflective log entry.

    Layer 1 — WHAT: what happened this iteration (facts, signals)
    Layer 2 — WHY: why decisions were made (causal chain)
    Layer 3 — PATTERN: behavioral patterns detected (self-awareness)

    This structured entry is designed to be quickly parseable by an LLM
    at the start of the next iteration, providing ambient self-awareness
    without requiring raw session replay.
    """
    state = load_state(project_path, required=False) or {}
    bound_data = parse_claude_md(project_path)
    gates = verification.get("layer1_gates", {})
    layer3 = verification.get("layer3_review", {})

    # Collect changed files from RELEVANCE gate
    changed_files = gates.get("RELEVANCE", {}).get("files", [])

    # Detect complexity
    complexity = detect_complexity(
        project_path, changed_files, bound_data["danger_zones"]
    )

    # Detect patterns from history
    history = state.get("history", [])
    patterns = detect_patterns(history, gates)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iteration": len(history) + 1,
        # Layer 1 — WHAT (facts)
        "what": {
            "stage": state.get("current_stage", "UNKNOWN"),
            "phase": f"{state.get('current_phase', '?')}/{state.get('total_phases', '?')}",
            "verdict": verdict,
            "overall": verification.get("overall", "UNKNOWN"),
            "gates": {
                gate: {
                    "status": info.get("status", "?"),
                    "detail": info.get("detail", ""),
                }
                for gate, info in gates.items()
            },
            "changed_files": changed_files[:10],
            "danger_zone_contact": gates.get("RELEVANCE", {}).get(
                "danger_zone_files", []
            ),
            "bound_violations": sum(
                1 for v in gates.values() if v.get("status") == "FAIL"
            ),
            "review_required": layer3.get("required", False),
        },
        # Layer 2 — WHY (decisions and causal chain)
        "why": {
            "complexity": complexity["level"],
            "complexity_reason": complexity["reason"],
            "review_reasons": layer3.get("reasons", []),
            "bound_state": {
                "danger_zones": len(bound_data["danger_zones"]),
                "never_do": len(bound_data["never_do"]),
                "iron_laws": len(bound_data["iron_laws"]),
            },
            "notes": notes,
        },
        # Layer 3 — PATTERN (self-awareness)
        "pattern": {
            "consecutive_failures": patterns["consecutive_failures"],
            "stuck_loop": patterns["stuck_loop"],
            "velocity_trend": patterns["velocity_trend"],
            "retry_rate": round(patterns["retry_rate"], 2),
            "hot_files": patterns["hot_files"],
            "drift_signal": patterns["drift_signal"],
        },
    }

    # Add actionable summary for quick LLM consumption
    alerts = []
    if patterns["stuck_loop"]:
        alerts.append(
            "STUCK: same stage failing 3+ times — try fundamentally different approach"
        )
    if patterns["consecutive_failures"] >= MAX_RETRY_BEFORE_ESCALATE:
        alerts.append(
            f"ESCALATE: {patterns['consecutive_failures']} consecutive failures — consider user review"
        )
    if patterns["velocity_trend"] == "DECELERATING":
        alerts.append("SLOWING: pass rate declining — reassess approach")
    if patterns["velocity_trend"] == "STALLED":
        alerts.append("STALLED: no passes in recent window — step back and remap")
    if patterns["drift_signal"]:
        alerts.append("DRIFT: working in DANGER ZONE — extra caution required")
    if patterns["hot_files"]:
        alerts.append(
            f"HOT FILES: {', '.join(patterns['hot_files'][:3])} — possible symptom-chasing"
        )

    entry["alerts"] = alerts

    return entry


def write_reflective_log(project_path: str, entry: dict):
    """Append a reflective log entry to .ouro/reflective-log.jsonl.

    Each line is a self-contained JSON object. The file is append-only
    and trimmed to REFLECTIVE_LOG_LIMIT entries on write.
    """
    log_path = os.path.join(project_path, OURO_DIR, REFLECTIVE_LOG)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # Read existing entries
    entries = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass

    entries.append(entry)

    # Trim to limit
    entries = entries[-REFLECTIVE_LOG_LIMIT:]

    # Write back (atomic-ish: write to tmp then rename)
    tmp_path = log_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        try:
            os.replace(tmp_path, log_path)
        except OSError:
            # Fallback for cross-device moves (Docker volumes, NFS, etc.)
            shutil.move(tmp_path, log_path)
    except OSError as e:
        print(f"Warning: Could not write reflective log: {e}")
        # Clean up temp file if write or move failed
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def read_reflective_log(project_path: str, last_n: int = 5) -> list:
    """Read the last N entries from the reflective log.

    Returns a list of dicts, newest last.
    """
    log_path = os.path.join(project_path, OURO_DIR, REFLECTIVE_LOG)
    if not os.path.exists(log_path):
        return []

    entries = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []

    return entries[-last_n:]


def print_reflective_summary(project_path: str, last_n: int = 5):
    """Print a human-readable summary of recent reflective log entries."""
    entries = read_reflective_log(project_path, last_n)
    if not entries:
        print("No reflective log entries found.")
        return

    print(f"{'=' * 60}")
    print(f"  Ouro Loop — Reflective Log (last {len(entries)} entries)")
    print(f"{'=' * 60}")

    for i, entry in enumerate(entries, 1):
        what = entry.get("what", {})
        why = entry.get("why", {})
        pattern = entry.get("pattern", {})
        alerts = entry.get("alerts", [])

        ts = entry.get("timestamp", "?")[:19]
        iteration = entry.get("iteration", "?")

        print(f"\n  #{iteration} [{ts}]")
        print(
            f"  WHAT: {what.get('stage', '?')} {what.get('phase', '?')} "
            f"→ {what.get('verdict', '?')} "
            f"(overall: {what.get('overall', '?')})"
        )

        # Gate summary (compact)
        gate_summary = []
        for gate, info in what.get("gates", {}).items():
            status = info.get("status", "?")
            icon = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}.get(status, "?")
            gate_summary.append(f"{gate}[{icon}]")
        if gate_summary:
            print(f"        Gates: {' '.join(gate_summary)}")

        if what.get("danger_zone_contact"):
            print(f"        DZ contact: {', '.join(what['danger_zone_contact'][:3])}")

        print(
            f"  WHY:  complexity={why.get('complexity', '?')} "
            f"| {why.get('complexity_reason', '')}"
        )
        if why.get("notes"):
            print(f"        notes: {why['notes']}")

        print(
            f"  PATTERN: velocity={pattern.get('velocity_trend', '?')} "
            f"| failures={pattern.get('consecutive_failures', 0)} "
            f"| retry_rate={pattern.get('retry_rate', 0):.0%}"
        )
        if pattern.get("stuck_loop"):
            print("        STUCK LOOP DETECTED")
        if pattern.get("hot_files"):
            print(f"        hot: {', '.join(pattern['hot_files'][:3])}")

        if alerts:
            for alert in alerts:
                print(f"  >> {alert}")

    # Overall trend
    if len(entries) >= 3:
        verdicts = [e.get("what", {}).get("verdict") for e in entries]
        pass_count = sum(1 for v in verdicts if v == "PASS")
        fail_count = sum(1 for v in verdicts if v in ("FAIL", "RETRY"))
        print(
            f"\n  Trend: {pass_count} PASS / {fail_count} FAIL in last {len(entries)}"
        )

        last_pattern = entries[-1].get("pattern", {})
        velocity = last_pattern.get("velocity_trend", "UNKNOWN")
        print(f"  Velocity: {velocity}")

    print(f"\n{'=' * 60}")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log_phase_result(project_path: str, verdict: str, notes: str = ""):
    """Log a phase result to ouro-results.tsv, state history, and reflective log."""
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
    bound_violations = sum(
        1 for v in gate_results.values() if v.get("status") == "FAIL"
    )

    # Log to TSV (with error handling for filesystem issues)
    results_path = os.path.join(project_path, RESULTS_FILE)
    try:
        with open(results_path, "a") as f:
            f.write(f"{phase_str}\t{verdict}\t{bound_violations}\tN/A\tnone\t{notes}\n")
    except OSError as e:
        print(f"Warning: Could not write to {results_path}: {e}")

    # Build reflective entry BEFORE updating state (so iteration count is correct)
    reflective_entry = build_reflective_entry(project_path, verdict, results, notes)

    # Update state history
    state.setdefault("history", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": state.get("current_stage", "UNKNOWN"),
            "phase": phase_str,
            "verdict": verdict,
            "bound_violations": bound_violations,
            "notes": notes,
        }
    )

    # Keep last N history entries
    state["history"] = state["history"][-HISTORY_LIMIT:]
    save_state(project_path, state)

    # Write reflective log after state is saved
    write_reflective_log(project_path, reflective_entry)

    print(f"Logged: {phase_str} — {verdict}")

    # Print alerts if any
    if reflective_entry.get("alerts"):
        for alert in reflective_entry["alerts"]:
            print(f"  >> {alert}")


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
    claude_md = _get_claude_md_path(project_path)
    if not os.path.exists(claude_md):
        print("No CLAUDE.md found. BOUND not defined.")
        print("Run: python prepare.py template claude")
        return

    bound_data = parse_claude_md(project_path)
    content = bound_data["raw_content"]

    # Detect template placeholders — template has keywords but no real content
    is_template = any(marker in content for marker in TEMPLATE_PLACEHOLDERS)
    if is_template:
        print(f"{'=' * 50}")
        print("  Ouro Loop — BOUND Check")
        print(f"{'=' * 50}")
        print("  [!] CLAUDE.md is still a template — fill in real BOUND values")
        print("  Edit CLAUDE.md to replace [placeholders] with actual boundaries")
        print(f"{'=' * 50}")
        return

    print(f"{'=' * 50}")
    print("  Ouro Loop — BOUND Check")
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

    # Show parsed BOUND details
    if bound_data["danger_zones"]:
        print(f"\n  Parsed DANGER ZONES: {len(bound_data['danger_zones'])}")
        for dz in bound_data["danger_zones"][:5]:
            print(f"    - {dz}")
    if bound_data["iron_laws"]:
        print(f"  Parsed IRON LAWS: {len(bound_data['iron_laws'])}")
        for il in bound_data["iron_laws"][:5]:
            print(f"    - {il}")

    source = bound_data.get("parse_source", "none")
    if source == "fallback":
        print(
            "\n  [!] Parse source: fallback (prose-style CLAUDE.md, results may be noisy)"
        )
    elif source == "structured":
        print("\n  Parse source: structured")

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
    log_parser.add_argument(
        "verdict", choices=["PASS", "FAIL", "RETRY", "SKIP"], help="Phase verdict"
    )
    log_parser.add_argument("--notes", default="", help="Notes for this phase")
    log_parser.add_argument("--path", default=".", help="Project directory")

    # advance
    advance_parser = subparsers.add_parser("advance", help="Advance to next phase")
    advance_parser.add_argument(
        "path", nargs="?", default=".", help="Project directory"
    )

    # bound-check
    bound_parser = subparsers.add_parser("bound-check", help="Check BOUND compliance")
    bound_parser.add_argument("path", nargs="?", default=".", help="Project directory")

    # reflect
    reflect_parser = subparsers.add_parser("reflect", help="Show reflective log")
    reflect_parser.add_argument(
        "path", nargs="?", default=".", help="Project directory"
    )
    reflect_parser.add_argument(
        "-n",
        "--last",
        type=int,
        default=5,
        help="Number of entries to show (default: 5)",
    )

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
        log_phase_result(getattr(args, "path", "."), args.verdict, args.notes)
    elif args.command == "advance":
        advance_phase(args.path)
    elif args.command == "bound-check":
        check_bound(args.path)
    elif args.command == "reflect":
        print_reflective_summary(args.path, args.last)
