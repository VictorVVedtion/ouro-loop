# Stage 4: VERIFY — Multi-Layer Verification

Every change must pass through verification before advancing.
Three layers, each catching different failure modes.

## Layer 1: Gates (Automatic, Fast)

Five gates that run automatically. They catch mechanical errors.

### EXIST Gate

**Question**: Do all referenced files, functions, and APIs actually exist?

**How to check**:
- Before editing a file, verify it exists.
- Before calling a function, verify it's defined.
- Before importing a module, verify it's available.
- Before using an API endpoint, verify it's deployed.

**Prevents**: Hallucination — the most common AI coding error.

### RELEVANCE Gate

**Question**: Is this work related to the current task?

**How to check**:
- Compare current file edits against the phase plan scope.
- Flag any file not listed in the plan's scope.
- Check if the current action advances the phase's exit criteria.

**Prevents**: Drift — working on interesting but irrelevant things.

### ROOT_CAUSE Gate

**Question**: Is this fixing the root cause, not just a symptom?

**How to check**:
- If you've fixed the same type of error more than twice, pause.
- If the fix is a workaround (try/catch, ignore, retry), question it.
- If the error is in code you didn't write, investigate why before patching.

**Prevents**: Stuck loops — fix/break/fix/break cycles.

### RECALL Gate

**Question**: Can you still articulate the original constraints?

**How to check**:
- State the task goal in one sentence.
- List the IRON LAWS from memory.
- Name the DANGER ZONES relevant to current work.
- If you can't, re-read CLAUDE.md before continuing.

**Prevents**: Context decay — forgetting constraints as context grows.

### MOMENTUM Gate

**Question**: Are you making forward progress?

**How to check**:
- Count: how many files read vs. files written in the last 10 actions?
- If ratio is >3:1 reading, you may be stuck.
- Count: how many times has the same error appeared?
- If >2 times, the approach may be wrong.

**Prevents**: Velocity death — spinning wheels without progress.

## Layer 2: Self-Assessment (Per Phase)

Structured self-review at each phase boundary.

### BOUND Compliance

Walk through each BOUND element:
- [ ] No DANGER ZONE behavior changed without approval
- [ ] No NEVER DO rule violated
- [ ] All IRON LAWS still hold

### Test Status

- [ ] All existing tests still pass
- [ ] New tests added for new behavior
- [ ] Edge cases from MAP stage tested

### Metric Check

- [ ] Core metric from MAP stage: stable or improved
- [ ] No performance regression
- [ ] No increase in error rates

### Scope Check

- [ ] Changes contained within phase plan scope
- [ ] Any out-of-scope changes documented and justified
- [ ] No unintended side effects in adjacent modules

## Layer 3: External Review (Critical Gates)

For high-risk changes, require external verification.

### When Layer 3 Applies

| Condition | Action |
|-----------|--------|
| Architectural complexity | User approval at each phase |
| Inside DANGER ZONE | User verification before commit |
| IRON LAW modification | Mandatory user sign-off |
| Failed Layer 1 gate | Escalate before continuing |
| 3+ RETRY verdicts | Mandatory user review |

### External Review Format

```
Phase: 2/5 — Add payment validation
BOUND: DANGER ZONE (payments/) — changes to validation logic
Changed: src/payments/validator.py (+45/-12), tests/test_validator.py (+30)
Risk: Medium — validation rules changed, could reject valid payments
Request: Please review the validation logic changes before I continue.
```

## Verification Output

After running all applicable layers:

```
  stage:        VERIFY
  phase:        2/5
  layer1:       PASS (5/5 gates)
  layer2:       PASS (bound OK, tests 52/52, metric stable)
  layer3:       N/A (not required for Simple complexity)
  verdict:      PASS → advance to Phase 3
```

## Failure Handling

When verification fails:
1. Identify which layer and which specific check failed.
2. Diagnose root cause (not symptom).
3. Fix and re-verify.
4. If 3 consecutive failures: log RETRY, escalate to user.
