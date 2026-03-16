# Project: FinanceApp — Financial Gaming Platform

## Overview

Real-money gaming platform with wallet management, bet settlement, and withdrawal processing.
Handles USD transactions with penny-level precision. PCI-DSS adjacent.

## BOUND

### DANGER ZONES

- `src/wallet/balance.py` — User balance calculations. Off-by-one = real money lost.
- `src/settlement/engine.py` — Bet settlement logic. Complex state machine with 7 states.
- `src/withdrawal/processor.py` — Withdrawal pipeline. Touches external payment APIs.
- `migrations/` — Database schema. Production rollbacks are expensive and risky.
- `src/auth/session.py` — Session management. Token handling, expiry, refresh.

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
- All withdrawals require at least 2 state transitions: PENDING → APPROVED → PROCESSED
- All API responses include `request_id` for audit trail
- Settlement engine state transitions are logged to immutable audit table
- Test coverage for financial modules never drops below 95%
- All database migrations have both `up()` and `down()` methods

## Architecture

- Python/FastAPI backend, PostgreSQL database
- Event-sourced balance tracking (append-only ledger + materialized balance)
- Settlement engine uses state machine pattern with explicit transition guards

## Development Workflow

### Test
```bash
pytest tests/financial/ -v --cov=src/wallet,src/settlement,src/withdrawal --cov-fail-under=95
```

### Verify Balance Integrity
```bash
python scripts/verify_ledger.py --check-consistency
```
