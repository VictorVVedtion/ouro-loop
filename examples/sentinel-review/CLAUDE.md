# Example: Python Web App — Sentinel Review

This is an example CLAUDE.md showing how Sentinel integrates with a Python project.

## BOUND

### DANGER ZONES
- `core/auth/` — authentication module, any change requires security review
- `core/payments/` — payment processing, PCI-DSS compliance required
- `migrations/` — database migrations, irreversible in production
- `config/secrets.py` — contains secret key references

### NEVER DO
- Never commit secrets, API keys, or credentials
- Never modify migrations that have been applied to production
- Never disable CSRF protection
- Never use raw SQL without parameterized queries
- Never push to main/master directly

### IRON LAWS
- All endpoints must have authentication
- All user input must be validated and sanitized
- Database queries must use the ORM (no raw SQL except in `core/db/raw.py`)
- Every model change must have a corresponding migration
- Test coverage must stay above 80%

## Commands

```bash
# Build
pip install -e .

# Test
python -m pytest tests/ -v --cov=core --cov-fail-under=80

# Lint
ruff check . && mypy core/
```

## Architecture

```
core/
  auth/       — Authentication (JWT + sessions)
  payments/   — Stripe integration
  api/        — REST endpoints
  models/     — SQLAlchemy models
  db/         — Database utilities
tests/        — pytest test suite
migrations/   — Alembic migrations
config/       — Settings and secrets
```
