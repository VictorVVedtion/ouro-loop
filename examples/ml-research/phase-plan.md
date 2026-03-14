# Phase Plan: Explore Alternative Attention Mechanisms

## Meta

- **Complexity**: Simple (single file modifications)
- **Total Phases**: 2
- **BOUND Interaction**: None (train.py only, prepare.py untouched)
- **Estimated Effort**: ~30 min (3 experiment runs at 5 min each + analysis)

## Task Summary

Current model uses standard multi-head attention. Explore whether alternative
attention mechanisms (linear attention, sliding window) can improve val_bpb
within the same 5-minute time budget.

## Core Metric

val_bpb — lower is better. Current baseline: 0.997900.

---

## Phase 1: Linear Attention — HIGH

**Entry criteria:**
- [x] Baseline run logged: val_bpb = 0.997900
- [x] Current train.py committed

**Scope:**
- `train.py` — replace attention computation with linear attention variant

**Exit criteria:**
- [x] Training completes within 5 minutes
- [x] val_bpb logged to results.tsv
- [x] If improved: keep commit. If not: revert.

**Verification:**
```bash
uv run train.py > run.log 2>&1
grep "^val_bpb:\|^peak_vram_mb:" run.log
```

---

## Phase 2: Sliding Window + Full Attention Mix — MEDIUM

**Entry criteria:**
- [x] Phase 1 result logged (keep or discard)

**Scope:**
- `train.py` — implement alternating sliding window / full attention pattern

**Exit criteria:**
- [x] Training completes within 5 minutes
- [x] val_bpb logged
- [x] Final verdict: which approach wins

---

## Autonomous Discovery & Remediation Log

| Phase | Discovery / Trigger | Action Taken (Autonomous) | Verification |
|-------|---------------------|---------------------------|--------------|
| 1 | VERIFY Failed: Linear attention saves VRAM but val_bpb is 3% worse than baseline. | Consulted `remediation.md`. Metric regression detected. Autonomously reverted the commit to restore the baseline state. | Baseline val_bpb restored. |
| 2 | VERIFY Passed: SSSL pattern (3 sliding + 1 full) matches baseline val_bpb with 20% less VRAM. | Kept the change. Logged to `results.tsv`. | Improvement recorded. |
