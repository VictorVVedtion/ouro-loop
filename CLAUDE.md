# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ouro Loop** — an open-source framework providing structured autonomous loops with runtime-enforced guardrails for AI coding agents (Claude Code, Cursor, Aider, Codex). Python 3.10+, zero external dependencies (pure stdlib).

Four-file core:
- `program.md` — methodology instructions (6-stage loop: BOUND → MAP → PLAN → BUILD → VERIFY → LOOP)
- `framework.py` — runtime CLI state machine (`.ouro/state.json`, verification gates, logging)
- `prepare.py` — project initialization and scanning (read-only operations)
- `sentinel.py` — 24/7 autonomous code review (partition scanning, runner, dashboard)

## Commands

### Tests
```bash
python -m pytest tests/ -v          # run all tests
python -m pytest tests/test_framework.py -v   # single test file
python -m pytest tests/test_framework.py::TestClassName::test_name -v  # single test
```

### Lint (hooks only)
```bash
shellcheck hooks/*.sh
```

### Framework CLI (used by agents, not for development)
```bash
python framework.py status .        # show current state
python framework.py verify .        # run verification gates
python framework.py log PASS --path .  # record phase result
python framework.py advance .       # advance to next stage
python framework.py bound-check .   # BOUND compliance check
```

### Prepare CLI
```bash
python prepare.py scan .            # scan project structure
python prepare.py init .            # initialize .ouro/ directory
python prepare.py template claude . # install CLAUDE.md template
```

### Sentinel CLI
```bash
ouro-sentinel init .        # scan project → generate partitions + config + CLAUDE.md
ouro-sentinel partition .   # regenerate partitions
ouro-sentinel status .      # show iteration/findings/coverage
ouro-sentinel install .     # install runner + dashboard scripts
```

### Docs (MkDocs Material)
```bash
pip install mkdocs-material pymdown-extensions
mkdocs serve                        # local preview
mkdocs build                        # build static site
```

## Architecture

### Runtime Flow

```
Agent reads program.md (methodology)
  → prepare.py scan/init (one-time setup, creates .ouro/)
  → framework.py drives the loop:
      status → verify (Layer 1 gates + Layer 2 self-eval) → log → advance
  → hooks/ enforce BOUND at tool-call level (exit 2 = hard block)
```

### Hooks System (Claude Code integration)

Four bash scripts in `hooks/`, configured via `settings.json.template`:

| Hook | Event | Purpose |
|------|-------|---------|
| `bound-guard.sh` | PreToolUse (Edit\|Write) | Parses DANGER ZONES from CLAUDE.md, exit 2 blocks edits to protected paths |
| `drift-detector.sh` | PreToolUse (Edit\|Write) | Warns when edits span 5+ directories (scope drift) |
| `root-cause-tracker.sh` | PostToolUse (Edit\|Write) | Tracks per-file edit count, warns at 3+ (symptom-chasing) |
| `recall-gate.sh` | PreCompact | Re-injects BOUND section before context compression |

Hooks read `$TOOL_INPUT` from stdin (JSON with `file_path` field). `$OURO_LOOP_DIR` must point to this repo.

### Verification Gates (framework.py)

**Layer 1** — automated gates: `EXIST`, `RELEVANCE`, `ROOT_CAUSE`, `MOMENTUM`
**Layer 2** — self-evaluation: `bound_compliance`, `tests_exist`

### State & Logging

- `.ouro/state.json` — phase tracking, history, BOUND definitions
- `ouro-results.tsv` — append-only audit log (phase, result, timestamp)

### Module Docs (`modules/`)

Deep-dive references for each stage: `bound.md`, `map.md`, `plan.md`, `build.md`, `verify.md`, `loop.md`, `remediation.md` (autonomous fix decision tree).

### Examples (`examples/`)

Five examples: `blockchain-l1/`, `consumer-product/`, `financial-system/`, `ml-research/`, `sentinel-review/` — each with domain-specific BOUND definitions.

### Sentinel Architecture

```
ouro-sentinel init → scan_project() + detect_commands() + generate_partitions()
                   → render CLAUDE.md from template + project BOUND
                   → create .ouro/sentinel/ (state, config, findings, logs)

ouro-sentinel install → generate sentinel-runner.sh + sentinel-dashboard.sh
                      → scripts derive paths from $0 location (portable)

Runner loop: launch claude session → ROTATE/DONE/BLOCKED → cooldown → restart
```

State files in `.ouro/sentinel/`: `state.json`, `findings.jsonl`, `iteration-log.jsonl`, `suppressed.json`, `learnings.md`, `partitions.json`.

## CI

GitHub Actions (`.github/workflows/test.yml`):
- pytest + coverage across Python 3.10–3.13 (framework + prepare + sentinel)
- Ruff lint + format on all three modules
- Bandit security scan
- ShellCheck on all `hooks/*.sh`

## Key Conventions

- Zero dependencies — all code uses Python stdlib only. Do not add external packages.
- `framework.py`, `prepare.py`, and `sentinel.py` are the Python modules (`tool.setuptools.py-modules`).
- Hook scripts must pass ShellCheck. Quote all variables, use `${var}` syntax.
- `program.md` is human-authored methodology — agents read it but don't modify it.
- BOUND enforcement uses exit codes: `exit 2` = hard block, `exit 0` = allow, stderr messages = warnings.
