# Stage 0: BOUND — Define Boundaries

The foundation of Ouro Loop. Before writing any code, define what must never break.

## Why Boundaries First

Most development failures aren't from bad code — they're from breaking something
that should have been sacred. A junior dev drops a migration file. A refactor
silently changes a financial calculation. A "quick fix" disables a security check.

BOUND prevents these by making constraints explicit before work begins.

## The Three BOUND Elements

### DANGER ZONES

Modules or areas where a wrong change has severe, hard-to-reverse consequences.

**How to identify:**
- What handles money, credentials, or user data?
- What has complex state machines or business logic?
- What has no tests but is critical?
- What would cause an incident if changed incorrectly?

**Format in CLAUDE.md:**
```markdown
## BOUND

### DANGER ZONES
- `src/payments/calculator.py` — financial calculations, penny-level precision required
- `src/auth/` — authentication flow, session management
- `migrations/` — database schema changes, irreversible in production
```

### NEVER DO

Absolute prohibitions. These are not guidelines — they are hard stops.

**How to define:**
- What actions have caused incidents before?
- What shortcuts are tempting but dangerous?
- What requires human oversight by policy?

**Format:**
```markdown
### NEVER DO
- Never modify payment calculation logic without explicit user approval
- Never delete or rename migration files
- Never disable CSRF protection, even in development
- Never commit secrets or API keys
- Never bypass the rate limiter
```

### IRON LAWS

Invariants that must always hold, verifiable by automated checks.

**How to define:**
- What properties must every API endpoint have?
- What database constraints are non-negotiable?
- What code quality rules are absolute?

**Format:**
```markdown
### IRON LAWS
- All API responses include `request_id` header
- All database migrations are reversible (have both up and down)
- All user-facing errors return structured JSON, never raw exceptions
- Test coverage never drops below 80%
- No function exceeds 50 lines
```

## BOUND Discovery Process

1. **Read existing CLAUDE.md** — check if BOUND already exists.
2. **Scan for risk indicators** — look for files with "payment", "auth", "migration", "secret" in names.
3. **Check git history** — look for reverted commits, hotfixes, incident-related changes.
4. **Ask the user** — "What would keep you up at night if I changed it?"
5. **Document** — write BOUND section in CLAUDE.md.
6. **Validate** — read it back to the user for confirmation.

## BOUND Evolution

BOUND is not static. It evolves through the LOOP stage:
- New DANGER ZONES are discovered during development.
- New NEVER DO rules emerge from near-misses.
- IRON LAWS are added when invariants are identified.
- IRON LAWS are relaxed only with explicit user approval and documented reasoning.

## Complexity Routing

BOUND definitions also inform complexity routing in the PLAN stage:

| BOUND interaction | Minimum complexity |
|-------------------|-------------------|
| No DANGER ZONE touched | Trivial or Simple |
| Adjacent to DANGER ZONE | Simple or Complex |
| Inside DANGER ZONE | Complex |
| Modifies IRON LAW | Architectural |
