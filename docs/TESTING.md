# Testing

## M1 checks

```bash
pnpm run typecheck
uv sync --locked
uv run --locked python -m pytest
POSTGRES_PASSWORD=validation-only docker compose config --quiet
```

The current run passes 13 Python tests covering registration policy, login errors and session rotation, session revocation, CSRF, validation/error envelopes, readiness, password/token hashing, and rate-limit window behavior.

The auth tests use SQLite for fast service-level checks. Alembic was applied to the development PostgreSQL database, and the GitHub Actions workflow defines a clean PostgreSQL migration check but has not run yet. Full browser E2E, multi-user role tests, and the Docker backup-restore drill remain release gates; do not count them as passing until actually run against their target environments.

## Acceptance evidence

Record exact command outcomes in `docs/MILESTONE_ACCEPTANCE.md`. A source file or a successful typecheck alone does not complete a milestone.
