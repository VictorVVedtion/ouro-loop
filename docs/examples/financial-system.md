# Example: Financial System

This example shows how Ouro Loop's BOUND system applies to a real-money gaming platform with wallet management, bet settlement, and withdrawal processing. The BOUND definition protects balance calculations, the settlement state machine, withdrawal pipelines, database migrations, and session management — areas where bugs translate directly to monetary loss, regulatory violations, or user fund exposure.

---

## Project Overview

| | |
|---|---|
| **Project** | FinanceApp — Financial Gaming Platform |
| **Language** | Python/FastAPI, PostgreSQL |
| **Architecture** | Event-sourced balance tracking (append-only ledger + materialized balance), state machine settlement engine |
| **Domain** | Real-money gaming, wallet management, PCI-DSS adjacent |

---

## BOUND Definition

### DANGER ZONES

| Path | Risk |
|------|------|
| `src/wallet/balance.py` | User balance calculations. Off-by-one = real money lost. |
| `src/settlement/engine.py` | Bet settlement logic. Complex state machine with 7 states. |
| `src/withdrawal/processor.py` | Withdrawal pipeline. Touches external payment APIs. |
| `migrations/` | Database schema. Production rollbacks are expensive and risky. |
| `src/auth/session.py` | Session management. Token handling, expiry, refresh. |

### NEVER DO

- Never modify balance calculation logic without explicit paired review
- Never skip decimal precision checks (always use Decimal, never float for money)
- Never delete or rename migration files — only add new ones
- Never bypass the withdrawal approval queue, even for testing
- Never log or expose full credit card numbers, even in debug mode
- Never disable rate limiting on financial endpoints
- Never commit with failing financial test suite

### IRON LAWS

- All monetary values use `Decimal` with 2-digit precision, never `float`
- All balance changes are atomic: debit and credit in a single transaction
- All withdrawals require at least 2 state transitions: PENDING -> APPROVED -> PROCESSED
- All API responses include `request_id` for audit trail
- Settlement engine state transitions are logged to immutable audit table
- Test coverage for financial modules never drops below 95%
- All database migrations have both `up()` and `down()` methods

---

## Development Workflow

```bash
# Run financial test suite with coverage enforcement
pytest tests/financial/ -v --cov=src/wallet,src/settlement,src/withdrawal --cov-fail-under=95

# Verify balance integrity
python scripts/verify_ledger.py --check-consistency
```

---

## What the BOUND Teaches

This financial system BOUND demonstrates several patterns specific to money-handling software:

### Decimal Precision as an IRON LAW

The rule "All monetary values use `Decimal` with 2-digit precision, never `float`" is the single most important constraint for any financial system. Floating point arithmetic introduces rounding errors that accumulate over millions of transactions. By declaring this as an IRON LAW, the verification gate checks every monetary operation for type compliance — the agent physically cannot introduce `float` in financial code without triggering a gate failure.

### Atomic Balance Operations

The IRON LAW "All balance changes are atomic: debit and credit in a single transaction" prevents a class of bugs where a debit succeeds but the corresponding credit fails (or vice versa), leaving the system in an inconsistent state. This is verified at the database transaction level.

### State Machine Discipline

The settlement engine uses an explicit state machine with 7 states and guarded transitions. The IRON LAW requiring all state transitions to be logged to an immutable audit table provides a forensic trail — if a bet is settled incorrectly, the full state history can be reconstructed.

### Migration Safety

Database migrations in production systems are effectively irreversible operations. The NEVER DO rules ("never delete or rename migration files") and IRON LAW ("all migrations have both `up()` and `down()` methods") ensure that schema changes can be rolled back and that the migration history remains intact.

### Coverage as a Gate

The 95% test coverage threshold for financial modules is an IRON LAW, not a suggestion. The verification gate checks coverage after every phase. If coverage drops below 95%, the gate fails and the agent must add tests before proceeding — it cannot skip coverage for expediency.

---

## Applicable Domains

This BOUND pattern applies broadly to any system handling financial transactions:

- Payment processing platforms
- Banking and fintech applications
- E-commerce order and refund systems
- Cryptocurrency exchanges and wallets
- Insurance claim processing
- Payroll and accounting systems

The specific file paths change, but the constraint patterns remain: Decimal precision, atomic operations, immutable audit trails, migration safety, and high test coverage thresholds.
