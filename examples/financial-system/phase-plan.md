# Phase Plan: Add Multi-Currency Support

## Meta

- **Complexity**: Architectural
- **Total Phases**: 5
- **BOUND Interaction**: Inside DANGER ZONE (wallet, settlement)
- **Estimated Effort**: 2-3 days

## Task Summary

Add EUR and GBP support alongside existing USD. Users can hold multiple
currency balances. Bets are settled in the currency they were placed in.
No cross-currency conversion in v1.

## Core Metric

All existing USD financial tests pass + new multi-currency tests at 95% coverage.

---

## Phase 1: Database Schema — CRITICAL

**Entry criteria:**
- [x] BOUND reviewed — DANGER ZONE: migrations/, wallet/
- [x] All existing tests pass (247/247)

**Scope:**
- `migrations/0042_add_currency_column.py` — add currency field to balance table
- `src/wallet/models.py` — add currency enum, update Balance model

**Exit criteria:**
- [x] Migration runs forward and backward successfully
- [x] Existing USD balances default correctly
- [x] No data loss on rollback

**Verification:**
```bash
python manage.py migrate && python manage.py migrate 0041 && python manage.py migrate
pytest tests/financial/test_migrations.py -v
```

---

## Phase 2: Balance Logic — CRITICAL

**Entry criteria:**
- [x] Phase 1 verified

**Scope:**
- `src/wallet/balance.py` — currency-aware balance operations
- `tests/financial/test_balance.py` — multi-currency test cases

**Exit criteria:**
- [x] Balance operations are currency-scoped
- [x] Cross-currency operations raise explicit error (not silent wrong result)
- [x] All Decimal precision IRON LAWS hold for all currencies

---

## Phase 3: Settlement Engine — HIGH

**Entry criteria:**
- [x] Phase 2 verified

**Scope:**
- `src/settlement/engine.py` — currency field in settlement flow
- `tests/financial/test_settlement.py` — currency-aware settlement tests

**Exit criteria:**
- [x] Bets settle in their original currency
- [x] State machine transitions log currency
- [x] Audit table includes currency field

---

## Phase 4: API Layer — HIGH

**Entry criteria:**
- [x] Phase 3 verified

**Scope:**
- `src/api/wallet_endpoints.py` — currency parameter in balance endpoints
- `src/api/bet_endpoints.py` — currency in bet placement

**Exit criteria:**
- [x] API accepts currency parameter
- [x] Backwards compatible — USD default when currency omitted
- [x] request_id present in all responses (IRON LAW)

---

## Phase 5: Integration Tests — MEDIUM

**Entry criteria:**
- [x] Phases 1-4 verified individually

**Scope:**
- `tests/integration/test_multi_currency_flow.py` — end-to-end flow
- Documentation updates

**Exit criteria:**
- [x] Full flow: deposit EUR → place bet in EUR → settle → withdraw EUR
- [x] Coverage >= 95% on all financial modules
- [x] No existing test regressions

---

## Autonomous Discovery & Remediation Log

| Phase | Discovery / Trigger | Action Taken (Autonomous) | Verification |
|-------|---------------------|---------------------------|--------------|
| 1 | PostgreSQL ENUM requires special migration handling | Phase 1 scope | Added custom migration step |
| 2 | VERIFY Failed: Existing balance helper function assumes single currency, causing test failures. | Consulted `remediation.md`. Issue is inside DANGER ZONE (`wallet/balance.py`), but does not violate IRON LAWS (no float conversion). Autonomously refactored the helper function to accept a `currency` parameter with a default to USD for backwards compatibility. | All balance tests pass. Precision maintained. |
| 3 | Audit table index needs currency | Phase 3 scope | Added index migration |
