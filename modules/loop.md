# Stage 5: LOOP — Feedback Closure

The stage that makes the methodology self-improving.
Every discovery feeds back into the system.

## Four Feedback Loops

### Loop 1: Within-Phase (Immediate)

**Trigger**: Verification failure within a phase.
**Action**: Fix → re-verify → continue.
**Scope**: Current phase only.

```
BUILD → VERIFY → FAIL → FIX → VERIFY → PASS → continue
```

This is the tightest loop. Most issues resolve here.
Budget: 3 retries max before escalating.

### Loop 2: Between-Phase (Adaptive)

**Trigger**: Discovery in phase N that affects phase N+1 plan.
**Action**: Update remaining phase plans.
**Scope**: Current task's remaining phases.

Common triggers:
- "This API is more complex than expected" → add a phase
- "These two phases can be merged" → simplify the plan
- "Phase 3 depends on something we haven't built" → reorder

Document what changed and why in the phase plan.

### Loop 3: Project (Strategic)

**Trigger**: New constraint or pattern discovered during development.
**Action**: Update BOUND in CLAUDE.md.
**Scope**: Entire project going forward.

Examples:
- Found an undocumented invariant → add to IRON LAWS
- Discovered a fragile module → add to DANGER ZONES
- Nearly made a dangerous mistake → add to NEVER DO

This loop is what makes BOUND grow organically from real experience,
not hypothetical risk assessment.

### Loop 4: Cross-Project (Meta)

**Trigger**: Pattern that works across multiple projects.
**Action**: Extract to template or methodology module.
**Scope**: Ouro Loop framework itself.

Examples:
- The "similar bug" heuristic works in every project → it's in BUILD
- DANGER ZONES always include payments and auth → add to template
- Complexity routing thresholds need adjustment → update PLAN module

This loop is how Ouro Loop evolves.

## Loop Mechanics

### Feedback Recording

Every loop iteration is logged:

```
ouro-results.tsv:
phase  verdict  bound_violations  test_pass_rate  scope_deviation  notes
2/5    RETRY    1                 50/52           none             iron law violation, fixed
2/5    PASS     0                 52/52           none             re-verified after fix
```

### Trend Detection

After 3+ phases, look for patterns:
- Increasing bound violations → BOUND is too loose or code is drifting
- Increasing retries → complexity was underestimated
- Scope deviations growing → plan needs replanning
- Stable passes → methodology is calibrated for this project

### BOUND Update Protocol

When updating BOUND from a discovery:

1. Document what happened: "During Phase 3, we discovered that..."
2. Propose the new BOUND element: "New IRON LAW: ..."
3. For additions: apply immediately, inform user.
4. For modifications: require user approval.
5. For removals: require explicit user sign-off with reasoning.

## Anti-Patterns

- **Skipping LOOP**: Moving to the next task without reflecting. Always check: did we learn anything that should change BOUND?
- **Over-looping**: Spending more time on process than code. LOOP should be brief — 2 minutes, not 20.
- **Ignoring trends**: Three RETRYs in a row means something systemic is wrong. Don't just keep retrying.
- **BOUND ossification**: BOUND should grow and evolve. If it hasn't changed in 10 phases, it might be too generic.

## Loop Completion

A task is complete when:
1. All phases pass VERIFY.
2. BOUND is updated with any discoveries.
3. Results are logged to ouro-results.tsv.
4. No open RETRY verdicts.

Then: return to Stage 0 (BOUND review) for the next task.
