# Requirements Traceability

This initial matrix tracks M1. The complete functional, security, and release criteria remain those in `docs/specifications/WORLDWEAVE_M0/`; an item marked later is still required before 1.0.

| Requirement | M1 implementation | Verification | State |
|---|---|---|---|
| FR-AUTH-01 account registration policy | FastAPI registration endpoint; `bootstrap_only`, `open`, and `closed` modes | `backend/tests/test_auth.py` | Implemented; tests pass |
| FR-AUTH-02 login | Argon2id credential verification and generic credential errors | `backend/tests/test_auth.py` | Implemented; tests pass |
| FR-AUTH-03 revocable sessions | Opaque session cookie, hashed server-side token, logout revocation and expiry | `backend/tests/test_auth.py` | Implemented; tests pass |
| FR-AUTH-04 multi-universe membership | Universe membership model | M3 | Not started |
| FR-AUTH-05 membership or explicit public-read access | Tenant authorization policy | M3 | Not started |
| NFR-OPS-01 health/readiness and structured logs | `/api/healthz`, `/api/readyz`, request IDs, JSON logs | `backend/tests/test_health.py`; running preview returned 200 for both endpoints | Implemented; verified |
| NFR-REL-01 durable committed writes | PostgreSQL-backed sessions and users | Clean PostgreSQL migration and restart test | In progress |
| M1 migration from empty database | Alembic `0001_identity` | Development migration applied; clean PostgreSQL workflow is defined but not run | Applied in development; CI pending |
| M1 local self-hosted startup | Compose, Postgres, FastAPI, Caddy, Windows scripts | `docker compose config --quiet` passes; Docker Desktop clean-start test unavailable | Authored; runtime pending |
| All M2–M9 functional and security requirements | See normative M0 requirements and roadmap | Milestone-specific tests and release E2E | Not started |
