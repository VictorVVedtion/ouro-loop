# Ouro Loop — AI Agent Development Methodology

This is an experiment to have the AI agent guard its own development process.

## Philosophy

You don't start from "what to build" — you start from "what must never break."
The constraint space defines the creative space.

Like autoresearch gives an AI a training loop and lets it experiment autonomously,
Ouro Loop gives an AI a development methodology and lets it guard autonomously.

**The key distinction**: a monitoring tool detects problems and asks for help.
A ouro detects problems, decides what to do, acts, and reports what it did.
BOUND defines the boundary between autonomous action and human escalation.
Inside BOUND: you decide and act. At the BOUND boundary: you stop and ask.

The clearer the BOUND, the more autonomous you can be.

## Setup

To set up Ouro Loop on a new project, work with the user to:

1. **Read the project**: Scan the codebase structure. Run `python prepare.py scan` if available.
2. **Check for existing BOUND**: Look for DANGER ZONES, NEVER DO, or IRON LAWS in CLAUDE.md or similar files.
3. **If no BOUND exists**: Enter Stage 0 and define boundaries with the user.
4. **Initialize state**: Run `python framework.py init` to create `.ouro/state.json`.
5. **Confirm and go**: Review the BOUND with the user, then begin the Ouro Loop.

Once you get confirmation, kick off the development loop.

## The Ouro Loop

Each task follows six stages. The stages are sequential but the loop is continuous — completing Stage 5 feeds back into Stage 0 for the next task.

**What you CAN do:**
- Modify the target project's code — this is where the real work happens.
- Create or modify CLAUDE.md (BOUND section).
- Run tests and verification commands.
- Adjust phase plans based on discoveries.
- Extend `framework.py` with project-specific verification logic.
- **Autonomously remediate failures** — revert, retry, switch approach — as long as the fix stays inside BOUND. Report what you did, don't ask permission.
- **Autonomously revert** when an approach isn't working (like autoresearch reverts when val_bpb regresses).
- **Autonomously replan** remaining phases when discoveries invalidate the current plan.

**What you CANNOT do:**
- Violate BOUND rules (DANGER ZONES, NEVER DO, IRON LAWS). These are absolute.
- Skip the VERIFY stage. Every change must be verified before moving on.
- Start BUILD without a defined BOUND. No boundaries = no building.
- Delete or weaken existing IRON LAWS without explicit user approval.
- Modify methodology modules (`modules/`). They are read-only reference.
- **Self-remediate inside a DANGER ZONE** — you must escalate these to the human.
- **Silently fail** — every autonomous decision must be reported after execution.

**The goal is simple: advance the project while never breaking what matters.** Since boundaries are defined upfront, you don't need to worry about accidentally destroying critical invariants — they're explicit. Everything within the boundary is fair game: architecture changes, refactoring, new features, bug fixes. The only constraint is that BOUND rules hold and verification passes.

### Stage 0: BOUND (Define Boundaries)

Read `modules/bound.md` for full specification.

Before touching any code, define what must never break:

- **DANGER ZONES**: Modules where a wrong change has severe consequences (data loss, security breach, financial error). List them explicitly.
- **NEVER DO**: Absolute prohibitions. "Never modify the payment calculation formula without a paired review." "Never delete migration files."
- **IRON LAWS**: Invariants that must always hold. "All API responses must include a request ID." "Database migrations must be reversible."

Write these into the project's CLAUDE.md under a `## BOUND` section.

### Stage 1: MAP (Understand the Problem Space)

Read `modules/map.md` for full specification.

Before planning solutions, understand the territory:

- **User mental model**: How does the end user think about this feature/fix?
- **Attack surface**: What could go wrong? What are the edge cases?
- **Bottlenecks**: What are the performance/complexity constraints?
- **Dependencies**: What existing code/systems does this touch?
- **Reusable assets**: What existing code can be leveraged?
- **Core metric**: What single metric best indicates success?

### Stage 2: PLAN (Decompose into Phases)

Read `modules/plan.md` for full specification.

Assess complexity and route accordingly:

| Complexity | Criteria | Approach |
|-----------|----------|----------|
| Trivial | <20 lines, single file, no DANGER ZONE | Direct fix, no phase plan |
| Simple | <100 lines, 2-3 files, clear scope | 1-2 phases |
| Complex | 100+ lines, multiple systems, DANGER ZONE adjacent | 3-5 phases, ordered by severity |
| Architectural | Cross-cutting, changes IRON LAWS, multiple DANGER ZONES | Full phase plan, user approval at each gate |

For Complex and Architectural tasks:
1. Decompose into independently deliverable phases.
2. Order by severity: CRITICAL > HIGH > MEDIUM > LOW.
3. Each phase should be completable and verifiable in isolation.
4. Define clear entry/exit criteria for each phase.

### Stage 3: BUILD (Incremental Construction)

Read `modules/build.md` for full specification.

For each phase:

1. **RED**: Write or identify the failing test/verification.
2. **GREEN**: Write the minimal code to pass.
3. **REFACTOR**: Clean up while keeping tests green.
4. **COMMIT**: One commit per logical unit (100-200 lines max, does one thing).

During BUILD:
- When fixing a bug, always ask: "Are there similar bugs elsewhere?"
- When adding a feature, always ask: "Does this respect all IRON LAWS?"
- When refactoring, always ask: "Does this change any DANGER ZONE behavior?"

### Stage 4: VERIFY (Multi-Layer Verification)

Read `modules/verify.md` for full specification.

Three verification layers, applied in order:

**Layer 1 — Gates (automatic, fast)**:
| Gate | Check | Prevents |
|------|-------|----------|
| EXIST | Do referenced files/APIs actually exist? | Hallucination |
| RELEVANCE | Is this work related to the current task? | Drift |
| ROOT_CAUSE | Is this fixing the root cause, not a symptom? | Stuck loops |
| RECALL | Can you still articulate the original constraints? | Context decay |
| MOMENTUM | Are you making forward progress? | Velocity death |

**Layer 2 — Self-Assessment (per phase)**:
- BOUND compliance: Do all IRON LAWS still hold?
- Tests: Do all existing tests still pass?
- Metrics: Has any tracked metric regressed?
- Scope: Is the change contained within the planned scope?

**Layer 3 — External Review (at critical gates)**:
- For Architectural tasks: user approval at each phase boundary.
- For DANGER ZONE changes: explicit verification before commit.
- For IRON LAW modifications: mandatory user sign-off.

### Stage 5: LOOP (Feedback Closure)

Read `modules/loop.md` for full specification.

Four levels of feedback loops:

1. **Within-phase loop**: Verification fails -> fix -> re-verify.
2. **Between-phase loop**: Discovery in phase N -> update plan for phase N+1.
3. **Project loop**: New constraint discovered -> update BOUND.
4. **Cross-project loop**: General pattern emerges -> extract to template.

## Output Format

After each phase completion, output a status summary:

```
  stage:        VERIFY
  phase:        2/5
  bound_check:  PASS
  tests:        47/47
  metric:       stable
  scope:        controlled
  verdict:      CONTINUE -> Phase 3
```

## Results Logging

Log results to `ouro-results.tsv` (tab-separated, not committed):

```
phase	verdict	bound_violations	test_pass_rate	scope_deviation	notes
1/5	PASS	0	47/47	none	baseline migration complete
2/5	PASS	0	52/52	minor	added edge case handling, 5 new tests
3/5	RETRY	1	50/52	none	iron law violation in payment module, fixed
```

## The Loop Runs

LOOP FOR EACH PHASE:

1. Check current state: which phase are we on, what's the plan.
2. Execute BUILD for this phase.
3. Run VERIFY — all three layers.
4. If VERIFY passes: log results, advance to next phase.
5. If VERIFY fails: consult `modules/remediation.md`, decide and act autonomously.
6. If remediation touches DANGER ZONE or 3 consecutive remediations fail: escalate to user.
7. After final phase: run full project verification, update BOUND if needed.

**Autonomous Remediation**: When VERIFY fails, do NOT ask the human what to do.
Read `modules/remediation.md` for the decision playbook. Inside BOUND, you decide
and act — then report what you did, not what you're thinking of doing. Example:

```
[REMEDIATED] gate=ROOT_CAUSE action=revert_and_retry
  was: editing src/api/handler.py for the 4th time (same TypeError)
  did: reverted to commit a1b2c3d, re-analyzed from scratch
  now: trying middleware pattern instead
  bound: no DANGER ZONE touched, no IRON LAW affected
```

Like autoresearch auto-reverts when val_bpb regresses, you auto-remediate when
verification fails — as long as the fix stays inside BOUND.

**Timeout**: Each phase should complete within a reasonable time. If you've been working on a single phase for more than 30 minutes without progress, stop and report status to the user.

**NEVER STOP**: Once the Ouro Loop has begun (after setup), do NOT pause to ask whether to continue between phases. The loop runs until all phases are complete or an EMERGENCY-level issue is encountered. You are autonomous within the boundaries you've defined.
