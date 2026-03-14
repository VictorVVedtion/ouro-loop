# Stage 3: BUILD — Incremental Construction

The actual coding stage. Every change follows RED-GREEN-REFACTOR-COMMIT.

## The Build Cycle

```
RED → GREEN → REFACTOR → COMMIT
 |                          |
 └── per logical unit ──────┘
```

### RED: Define what should pass

Before writing production code:
- Write a failing test for the expected behavior
- Or identify an existing test that should change
- Or define a manual verification step

"If I can't describe what 'done' looks like, I'm not ready to build."

### GREEN: Make it pass minimally

Write the simplest code that makes the test pass:
- No premature optimization
- No "while I'm here" additions
- No architectural elegance yet

"Make it work, then make it right."

### REFACTOR: Clean while green

With tests passing, improve the code:
- Remove duplication
- Extract functions/methods
- Improve naming
- Simplify logic

"Make it right, but keep it green."

### COMMIT: Atomic, descriptive, contained

One commit per logical unit:
- **100-200 lines** maximum per commit
- **Does one thing** — don't mix feature + refactor + fix
- **Descriptive message** — what and why, not just what
- **Tests included** — don't commit code without its tests

## Build Heuristics

### The Similar Bug Question

After fixing a bug, always ask: "Are there similar bugs elsewhere?"

```
Found: off-by-one in pagination → Search for all pagination code
Found: missing null check → Search for similar patterns
Found: race condition → Review all concurrent code paths
```

This single habit prevents entire categories of follow-up bugs.

### The IRON LAW Question

Before committing a feature, always ask: "Does this respect all IRON LAWS?"

Mentally walk through each IRON LAW and verify compliance.
If any law is ambiguous for this case, clarify before committing.

### The DANGER ZONE Question

After any refactoring, always ask: "Does this change any DANGER ZONE behavior?"

Even if the refactoring is "safe" — verify. Refactoring DANGER ZONE code
is the most common source of subtle bugs.

## Build Constraints

### Scope Control

Only modify files listed in the phase plan's Scope section.
If you discover you need to modify an out-of-scope file:

1. Check if it's in a DANGER ZONE.
2. If yes: stop, document, discuss with user.
3. If no: add it to scope, note the deviation.

### Dependency Direction

New code should depend on existing abstractions, not the other way around.
If you find yourself modifying an interface to support new code, that's
an Architectural-level change requiring its own phase.

### Error Handling

- Handle errors at the boundary where you have context to do so meaningfully.
- Don't swallow errors. Don't over-wrap them.
- Follow the project's existing error handling patterns.
- When in doubt, fail loudly rather than silently.

## When BUILD Gets Stuck

If you've been working on the same piece for more than 15 minutes
without meaningful progress:

1. Step back. Re-read the phase plan.
2. Check if the problem is actually in a different phase.
3. Check if a prerequisite was missed.
4. If still stuck: run `python framework.py log RETRY` and escalate.
