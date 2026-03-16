# AI BOUND Definitions: Django/DRF Web Application

This file defines the strict operational boundaries (BOUNDs), workflows, and danger zones for AI assistants and contributors working on this Django REST Framework repository.

## DANGER ZONES (Strict Boundaries)
The following areas are critical. **DO NOT** make autonomous architectural changes, bypass validations, or execute scripts related to these areas without explicit, step-by-step user confirmation.

### 1. Authentication & Authorization
* **Permission Classes:** NEVER remove or bypass DRF permission classes (e.g., `IsAuthenticated`, `IsAdminUser`) on views or viewsets.
* **Cryptography:** DO NOT implement custom password hashing or encryption. Always rely on Django's built-in `make_password` and standard authentication backends.
* **Token Management:** Do not alter JWT/Token expiration times or refresh logic without explicit instruction. 
* **Secrets:** NEVER log, expose, or hardcode environment variables, API keys, or database credentials.

### 2. Payments & Billing
* **Webhooks:** DO NOT modify payment gateway (e.g., Stripe, PayPal) webhook verification logic or signature checks.
* **Data Privacy:** NEVER write logging statements that capture Personally Identifiable Information (PII), Primary Account Numbers (PAN), or sensitive customer data.
* **State Changes:** Modifications to subscription states, balances, or payout logic require rigorous manual review. Do not bypass state machine transitions.

### 3. Database Migrations & Schema
* **Immutable History:** DO NOT edit or delete existing migration files that have already been merged into the `main` branch.
* **Destructive Operations:** Pause and request confirmation before generating migrations that involve `RemoveField`, `DeleteModel`, or dropping tables.
* **Faking:** NEVER suggest or run `python manage.py migrate --fake` unless explicitly ordered by the user to fix a broken state.

---

## Standard Development Boundaries (Soft Bounds)

### Django & DRF Conventions
* **Fat Models, Skinny Views:** Keep business logic in models or dedicated service layers, not in DRF Views or Serializers.
* **Query Optimization:** Always check for N+1 query problems. Use `select_related()` for foreign keys and `prefetch_related()` for many-to-many/reverse foreign key relationships.
* **Serializers:** Do not use `depth = ...` in `ModelSerializer` classes for write operations. Explicitly define nested serializers to maintain validation control.

### Testing Commands
* Always run tests for the specific app you are modifying before proposing a final solution.
* Command: `python manage.py test <app_name> --keepdb`

### Code Style
* Follow PEP 8 guidelines.
* Use `black` for formatting and `flake8` for linting.
