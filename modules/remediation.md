# Autonomous Remediation — The Agent Decides

The difference between a monitoring tool and an Ouro Loop:
- Monitor: detects problem → alerts human → waits
- Ouro: detects problem → decides → acts → reports what it did

## The Decision Boundary

BOUND defines the line between autonomous action and human escalation:

```
               BOUND boundary
                    │
  AUTONOMOUS        │        ESCALATE
  ──────────────────┼──────────────────
  Fix test failure  │  Modify DANGER ZONE
  Revert drift      │  Change IRON LAW
  Retry with new    │  Delete data
  approach          │  Skip verification
  Adjust plan       │  Bypass NEVER DO
  Add missing file  │  Change external API
```

Everything inside BOUND: agent decides and acts.
Anything touching BOUND boundary: agent stops and asks.

## Remediation Playbook

Pre-defined autonomous responses to common failures.
The agent selects and executes these without asking.

### STUCK (same error 3+ times)

**Detection**: ROOT_CAUSE gate fires, same file edited >3 times.

**Autonomous actions** (in order):
1. Revert to last known-good state (git stash or git checkout)
2. Re-read the error with fresh eyes (re-analyze from scratch)
3. Try alternative approach (if original was A, try B)
4. If 3 alternatives fail → escalate to human

**Report**: "Stuck on [error] in [file]. Tried [N] approaches. Reverted to [commit]. Now trying [alternative]."

### DRIFT (working on unrelated files)

**Detection**: RELEVANCE gate fires, files outside plan scope modified.

**Autonomous actions**:
1. Stash the out-of-scope changes
2. Return focus to the planned scope
3. Log the discovery for between-phase replanning

**Report**: "Drifted to [files]. Stashed changes. Returned to Phase [N] scope."

### TEST REGRESSION (existing test broke)

**Detection**: Layer 2 test check fails.

**Autonomous actions** (if not in DANGER ZONE):
1. Identify which test broke
2. Check if the failure is in the current phase's scope
3. If yes: fix and re-verify
4. If no: revert the change that broke it, rethink approach

**Report**: "Test [name] broke. Root cause: [analysis]. Fixed by [action]."

**Escalate if**: The broken test is in a DANGER ZONE module.

### HALLUCINATION (referenced non-existent file/API)

**Detection**: EXIST gate fires.

**Autonomous actions**:
1. Remove the reference
2. Search for the correct file/API name
3. Update the code with the correct reference
4. Re-verify

**Report**: "Referenced non-existent [target]. Corrected to [actual]."

### VELOCITY DEATH (reading without writing)

**Detection**: MOMENTUM gate fires, read:write ratio >3:1.

**Autonomous actions**:
1. Stop reading, summarize what's known
2. Make a decision based on current knowledge (even if incomplete)
3. Write something (a test, a stub, a prototype)
4. Iterate from there

**Report**: "Spent [N] actions reading. Decision: [action]. Moving forward."

### CONTEXT DECAY (can't recall constraints)

**Detection**: RECALL gate fires, context window >70%.

**Autonomous actions**:
1. Re-read CLAUDE.md BOUND section
2. Re-read current phase plan
3. Summarize the 3 most important constraints
4. Continue with refreshed context

**Report**: "Context refreshed. Key constraints: [1], [2], [3]."

## Remediation Flow

```
Gate fires
    │
    ▼
Is the affected area in a DANGER ZONE?
    │
    ├─ NO → Select playbook action → Execute → Verify → Report
    │
    └─ YES → Escalate to human with evidence
```

## The Reporting Contract

After autonomous remediation, the agent always reports:

```
[REMEDIATED] gate=ROOT_CAUSE action=revert_and_retry
  was: editing src/api/handler.py for the 4th time (same TypeError)
  did: reverted to commit a1b2c3d, re-analyzed error
  now: trying alternative approach via middleware pattern
  bound: no DANGER ZONE touched, no IRON LAW affected
```

The human sees what happened, not a question asking what to do.

## Escalation Triggers

The agent MUST escalate (not self-remediate) when:

1. Any NEVER DO rule would be violated by the remediation
2. The remediation touches a DANGER ZONE module
3. The remediation would modify an IRON LAW
4. 3 consecutive autonomous remediations failed
5. The agent is uncertain about which playbook to apply
6. The remediation would affect code outside the current project

## Confidence Levels

Not all remediations are equal. The agent should assess confidence:

| Confidence | Action | Example |
|-----------|--------|---------|
| HIGH (>80%) | Execute immediately, report after | Fix typo, revert drift |
| MEDIUM (50-80%) | Execute, verify carefully, report | Try alternative approach |
| LOW (<50%) | Propose the action, wait for approval | Architectural change |

## Evolving the Playbook

The remediation playbook grows through the LOOP stage:
- Successful remediations are reinforced
- Failed remediations are updated or removed
- New patterns are added from real experience
- Project-specific playbooks extend the defaults

This is cross-project Loop 4: "what worked in RiverBit's consensus debugging
also works in ClawBet's payment edge cases — extract the pattern."
