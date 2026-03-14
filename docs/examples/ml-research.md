# Example: ML Research

This example shows how Ouro Loop's BOUND system applies to an autonomous ML experiment framework based on karpathy/autoresearch. The BOUND definition reframes single-metric optimization (val_bpb) as a formal constraint system, protecting the evaluation harness and data pipeline while granting the agent full autonomy over the training code. This is the closest example to autoresearch's original paradigm, demonstrating how Ouro Loop generalizes the ML experiment loop with explicit constraints.

---

## Project Overview

| | |
|---|---|
| **Project** | autoresearch — Autonomous ML Experiment Framework |
| **Language** | Python |
| **Architecture** | Single-file training (`train.py`), fixed evaluation harness (`prepare.py`), TSV result log |
| **Domain** | LLM training, autonomous experiment iteration |

---

## BOUND Definition

### DANGER ZONES

| Path | Risk |
|------|------|
| `prepare.py` | Fixed evaluation harness. Modifying this invalidates all comparisons. |
| `evaluate_bpb()` | The ground truth metric. Must never change. |
| Data pipeline | Tokenizer and dataloader are fixed constants. |

### NEVER DO

- Never modify `prepare.py` — it is read-only
- Never install new packages or add dependencies
- Never modify the evaluation harness
- Never skip logging results to results.tsv
- Never use more than 5 minutes training time budget
- Never commit results.tsv to git (keep untracked)

### IRON LAWS

- val_bpb is the only metric that matters — lower is better
- Training always runs for exactly 5 minutes wall clock
- Only `train.py` is modified — everything else is fixed
- Every experiment is logged: commit hash, val_bpb, memory, status
- Improvements keep the commit, regressions revert to previous
- Simplicity wins: equal val_bpb with less code is a positive result

---

## Development Workflow

```bash
# Run experiment
uv run train.py > run.log 2>&1
grep "^val_bpb:" run.log

# Log result
# commit	val_bpb	memory_gb	status	description
# a1b2c3d	0.997900	44.0	keep	baseline
```

---

## How autoresearch Maps to BOUND

The autoresearch paradigm maps cleanly onto the BOUND system:

| autoresearch Concept | BOUND Equivalent |
|---------------------|-----------------|
| `prepare.py` is read-only | DANGER ZONE: `prepare.py` |
| Only `train.py` is modified | IRON LAW: only `train.py` is modified |
| 5-minute training budget | IRON LAW: training time exactly 5 minutes |
| val_bpb is the metric | IRON LAW: val_bpb is the only metric |
| Regression reverts | IRON LAW: regressions revert to previous |
| No new dependencies | NEVER DO: never install new packages |
| Log every experiment | IRON LAW: every experiment is logged |

This mapping demonstrates that autoresearch was implicitly using a BOUND system all along — Ouro Loop makes that structure explicit and enforceable.

---

## What the BOUND Teaches

This ML research BOUND demonstrates several patterns specific to experiment-driven development:

### Fixed Evaluation Harness

The evaluation function (`evaluate_bpb()`) and data pipeline are DANGER ZONES because modifying them invalidates all previous comparisons. In ML research, the integrity of the evaluation is more important than any individual experiment result. If the agent could modify the evaluation function, it could "improve" val_bpb by lowering the bar rather than improving the model.

### Single Modifiable File

Constraining the agent to only modify `train.py` is an extreme form of BOUND — it limits the entire creative space to a single file. This constraint is powerful because it forces architectural creativity within a narrow scope. The agent must find better training strategies, not better infrastructure.

### Time Budget as an IRON LAW

The 5-minute training budget serves the same function as a financial test coverage threshold: it prevents the agent from trading compute for quality. Without this constraint, the agent might "improve" val_bpb by simply training for longer, which would not be a genuine algorithmic improvement.

### Revert-on-Regression

The IRON LAW "regressions revert to previous" implements autoresearch's core loop: try something, measure, keep or discard. This is autonomous remediation in its simplest form — the agent does not need to diagnose why a regression happened, it just reverts and tries something different.

### Simplicity Metric

The rule "equal val_bpb with less code is a positive result" is unusual — most systems optimize for a single numeric metric. This IRON LAW adds a second dimension: code simplicity. It prevents the agent from adding complexity that does not improve the metric, which is a common failure mode in ML experiment iteration.

---

## Applicable Domains

This BOUND pattern applies to any autonomous experiment loop:

- ML model training and hyperparameter search
- Compiler optimization passes
- Algorithm benchmarking and comparison
- Performance regression testing
- A/B test experiment frameworks

The key pattern is: fix the evaluation, fix the budget, let the agent iterate freely on the implementation.
