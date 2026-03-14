# Stage 2: PLAN — Decompose into Phases

Transform understanding into action through structured decomposition.

## Complexity Router

Every task enters the complexity router first:

| Level | Criteria | Phases | User Approval |
|-------|----------|--------|---------------|
| Trivial | <20 lines, 1 file, no DANGER ZONE | 0 (direct fix) | No |
| Simple | <100 lines, 2-3 files, clear scope | 1-2 | No |
| Complex | 100+ lines, multi-system, DANGER ZONE adjacent | 3-5 | At completion |
| Architectural | Cross-cutting, IRON LAW changes | Full plan | At each phase |

## Phase Decomposition Rules

### 1. Independence

Each phase must be independently deliverable and verifiable.

Bad: "Phase 1: Add database tables. Phase 2: Add API endpoints that use them."
(Phase 2 can't be verified without Phase 1.)

Good: "Phase 1: Add database tables with migration tests. Phase 2: Add API endpoints with integration tests."
(Each phase has its own verification.)

### 2. Severity Ordering

Order phases by impact severity:

1. **CRITICAL**: Data integrity, security, financial correctness
2. **HIGH**: Core functionality, user-facing features
3. **MEDIUM**: Supporting features, optimizations
4. **LOW**: Cosmetic, documentation, nice-to-haves

Handle the scary stuff first when your context is freshest.

### 3. Size Constraints

- Each phase should produce 100-300 lines of changes
- Each phase should be completable in one focused session
- Each phase should have a clear "done" criterion

If a phase feels too big, split it. If it feels too small, merge with adjacent.

### 4. Entry/Exit Criteria

Define for each phase:

```
Phase N: [title]
  Entry:  [what must be true before starting]
  Scope:  [exactly what files/modules are touched]
  Exit:   [what must be true when done]
  Verify: [specific verification steps]
```

## Phase Plan Template

```markdown
# Phase Plan: [Task Name]

Complexity: [Trivial/Simple/Complex/Architectural]
Total Phases: [N]
BOUND interaction: [None/Adjacent/Inside/Modifies]

## Phase 1: [Title] — CRITICAL
Entry:  BOUND defined, existing tests pass
Scope:  src/payments/calculator.py, tests/test_calculator.py
Exit:   New calculation logic passes all edge cases
Verify: Run test suite, verify IRON LAW compliance

## Phase 2: [Title] — HIGH
Entry:  Phase 1 verified
Scope:  src/api/payment_endpoint.py
Exit:   API endpoint uses new calculator
Verify: Integration tests pass, response format unchanged
```

## Adaptive Replanning

Plans change as you learn. When a discovery in phase N invalidates
assumptions for phase N+1:

1. Stop current work.
2. Document the discovery.
3. Replan remaining phases.
4. Continue with updated plan.

This is the between-phase feedback loop (LOOP Stage).

## Anti-Patterns

- **Big Bang**: All changes in one phase. No verification until the end.
- **Over-Planning**: 15 phases for a 50-line change. Match plan to complexity.
- **Phase Dependency Chains**: Phase 3 requires Phase 2 which requires Phase 1. Each phase should stand alone.
- **Scope Creep**: "While I'm here, let me also..." — only do what's in the plan.
