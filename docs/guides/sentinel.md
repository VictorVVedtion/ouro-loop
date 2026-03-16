# Sentinel — 24/7 Autonomous Code Review

Sentinel is a built-in Ouro Loop module that runs continuous, unattended code review loops on any project. It scans your codebase partition-by-partition, finds real issues across 7 dimensions, fixes what it can safely, and records everything.

!!! info "Production-validated"
    Sentinel's architecture was extracted from a system that ran 292 rounds over 13 hours on a production blockchain codebase, finding 438 issues (17 CRITICAL) with 100% fix success rate and zero abandoned fixes.

---

## Quick Start

```bash
pip install ouro-loop

cd your-project/
ouro-sentinel init .       # Scan -> detect commands -> generate partitions + config
ouro-sentinel install .    # Generate runner + dashboard scripts
make sentinel-start        # Start the 24/7 review loop
make sentinel-dashboard    # Watch live progress
```

---

## Prerequisites

- **Python 3.10+** with `pip install ouro-loop`
- **Claude Code CLI** (`claude`) in PATH
- **Git** -- used for activity scoring, worktree-based fixes, and PR creation

!!! warning "Security"
    The runner uses `--permission-mode bypassPermissions` for unattended operation. Only run in trusted, sandboxed environments.

---

## What `init` Does

When you run `ouro-sentinel init .`, Sentinel:

1. **Scans** your project (languages, file count, LOC)
2. **Detects** build/test/lint commands automatically:

    | Marker File | Build | Test | Lint |
    |-------------|-------|------|------|
    | `go.mod` | `go build ./...` | `go test ./...` | `go vet ./...` |
    | `Cargo.toml` | `cargo build` | `cargo test` | `cargo clippy` |
    | `package.json` | `npm run build` | `npm test` | `npx eslint .` |
    | `pyproject.toml` | -- | `python -m pytest` | `ruff check .` |
    | `pom.xml` | `mvn compile` | `mvn test` | `mvn checkstyle:check` |
    | `Makefile` | `make build` | `make test` | `make lint` |

3. **Generates partitions** -- directories scored by risk:
    - `high` -- overlaps with DANGER ZONES from your CLAUDE.md
    - `medium` -- high git activity or file count
    - `low` -- default

4. **Renders** a Sentinel-specific `CLAUDE.md` with your BOUND rules inherited

5. **Creates** `.ouro/sentinel/` with all state files

---

## The Review Loop

Each Claude session executes this 6-step loop:

### 1. MAP -- Select Review Target

Priority formula: `recency x 0.30 + criticality x 0.25 + staleness x 0.25 + density x 0.10 + gap x 0.10`

Review rhythm: every iteration = 1 file, every 10 = module-level, every 30 = cross-module.

### 2. SCAN -- 7-Dimension Analysis

| Dimension | What to Look For |
|-----------|-----------------|
| Security | Injection, auth bypass, secrets, unsafe crypto |
| Quality | Dead code, complexity, naming, error handling |
| Performance | N+1 queries, unnecessary allocations, blocking I/O |
| Test Coverage | Missing tests, edge cases, test quality |
| Architecture | Coupling, SRP violations, dependency direction |
| Doc Sync | Stale comments, missing docs, misleading names |
| Project Rules | BOUND violations, IRON LAW compliance |

Only findings with confidence > 0.8 are recorded.

### 3. FIX -- Isolated Repair

Each fix runs in an isolated git worktree -> build -> test -> commit -> PR. Requires confidence >= 0.9, not in DANGER ZONE, blast radius <= 3 files.

### 4. VERIFY -- Three-Layer Check

L1: `ouro verify .` | L2: BOUND compliance | L3: Lint command

### 5. REMEDIATE -- Autonomous Decision

3 retries max. After 3 failures -> `human-intervention-required`. Never asks for help.

### 6. LOOP -- Record and Rotate

Update state, log iteration, write learnings every 10 rounds. At ~70% context -> `ROTATE`. If 5 consecutive zero-finding iterations -> `DONE`.

---

## Runner

```bash
.ouro/sentinel/sentinel-runner.sh start    # Start daemon
.ouro/sentinel/sentinel-runner.sh stop     # Graceful shutdown
.ouro/sentinel/sentinel-runner.sh status   # Check if running
.ouro/sentinel/sentinel-runner.sh restart  # Stop + start
```

Features: session rotation, crash recovery, PID management, log rotation at 10MB, interruptible sleep.

---

## Dashboard

```bash
.ouro/sentinel/sentinel-dashboard.sh           # One-shot display
.ouro/sentinel/sentinel-dashboard.sh --watch   # Auto-refresh every 5s
```

Shows: runner status, severity breakdown, coverage progress bar, recent iteration history.

---

## Configuration

Key settings in `sentinel-config.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `confidence_threshold` | 0.8 | Minimum confidence to record a finding |
| `fix_confidence_threshold` | 0.9 | Minimum confidence to attempt a fix |
| `blast_radius_limit` | 3 | Maximum files changed per fix |
| `max_fix_attempts` | 3 | Retries before marking human-required |
| `auto_pr` | false | Automatically create PRs for fixes |
| `model` | claude-opus-4-6 | Claude model for review sessions |
| `max_turns` | 200 | Maximum tool calls per session |
| `cooldown_seconds` | 30 | Pause between sessions |

---

## CLI Reference

```bash
ouro-sentinel init <path>        # Initialize sentinel for a project
ouro-sentinel partition <path>   # Regenerate partitions
ouro-sentinel status <path>      # Show iteration count, findings, coverage
ouro-sentinel install <path>     # Install runner + dashboard + Makefile targets
```
