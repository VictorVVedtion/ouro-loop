# Project: autoresearch — Autonomous ML Experiment Framework

## Overview

Give an AI agent a small but real LLM training setup and let it experiment
autonomously. Based on karpathy/autoresearch. The agent modifies training code,
trains for 5 minutes, checks if val_bpb improved, keeps or discards, and repeats.

## BOUND

### DANGER ZONES

- `prepare.py` — Fixed evaluation harness. Modifying this invalidates all comparisons.
- `evaluate_bpb()` — The ground truth metric. Must never change.
- Data pipeline — Tokenizer and dataloader are fixed constants.

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
- Only train.py is modified — everything else is fixed
- Every experiment is logged: commit hash, val_bpb, memory, status
- Improvements keep the commit, regressions revert to previous
- Simplicity wins: equal val_bpb with less code is a positive result

## Architecture

- Single file training: `train.py` contains model, optimizer, training loop
- Fixed evaluation: `prepare.py` contains dataloader, tokenizer, val_bpb metric
- Tab-separated log: `results.tsv` tracks all experiments

## Development Workflow

### Run Experiment
```bash
uv run train.py > run.log 2>&1
grep "^val_bpb:" run.log
```

### Log Result
```
commit	val_bpb	memory_gb	status	description
a1b2c3d	0.997900	44.0	keep	baseline
```
