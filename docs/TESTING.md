# Testing

## Running the checks

```bash
pnpm run typecheck
uv sync --locked
uv run --locked python -m pytest
POSTGRES_PASSWORD=validation-only docker compose config --quiet
```

Apply migrations against a real PostgreSQL database to exercise the PostgreSQL-only paths (full-text search indexes, `concat_ws` immutability, and so on):

```bash
DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/worldweave" \
  uv run --locked alembic -c backend/alembic.ini upgrade head
```

## Suite layout

| Suite | Scope |
|---|---|
| `backend/tests/test_auth.py` | Registration policy, login, session rotation and revocation, CSRF |
| `backend/tests/test_health.py` | `/api/healthz`, `/api/readyz`, structured logging |
| `backend/tests/test_universes.py`, `test_universe_security.py` | Universe CRUD, RBAC, invitations, cross-universe isolation |
| `backend/tests/test_codex.py`, `test_codex_validation.py`, `test_codex_visibility.py` | Entities, custom fields, relations, visibility |
| `backend/tests/test_chronicle.py` | Documents, revisions, comments, contributor workflow |
| `backend/tests/test_collaboration.py` | Realtime tickets, durability, permissions, compaction |
| `backend/tests/test_atlas_chronos.py` | Maps, markers, regions, assets, calendars, timeline events |
| `backend/tests/test_search.py` | Unified, permission-filtered search |
| `backend/tests/test_import_export.py` | Export bundles and import validation/execution |
| `backend/tests/test_release_e2e.py` | Ten release end-to-end scenarios (M9) |
| `backend/tests/test_security_audit.py` | Cross-cutting security audit (M9) |

## Release end-to-end scenarios

`backend/tests/test_release_e2e.py` walks the full HTTP surface with a file-backed SQLite database so the HTTP and WebSocket threads share one store. It covers:

1. An owner creates a universe and invites an editor, a contributor, and a viewer.
2. A viewer cannot mutate an entity even by direct API request.
3. A contributor submits a draft; an editor reviews and publishes it.
4. Two editors co-edit a chapter and both clients converge.
5. An acknowledged update survives a server restart.
6. A map marker links to a location entity and stays at its normalized position after the map is resized.
7. A custom (non-Gregorian) calendar orders events by continuous day index.
8. The Nexus graph hides private nodes and their edges from a viewer.
9. An exported bundle imports into a clean universe without broken links.
10. An export bundle is internally integrity-verifiable (checksums match contents).

## Security audit

`backend/tests/test_security_audit.py` asserts the release security properties: unauthenticated access rejection, session revocation, cross-universe id substitution, search and graph leakage, role escalation, viewer mutation across every resource family, WebSocket room authorization, upload path/MIME/size safety, stored-XSS link and node rejection, CSRF enforcement, invitation token binding and non-reuse, and import archive safety.

## Cross-environment checks not run by pytest

- Realtime convergence and restart durability were verified against a live `uvicorn` server backed by PostgreSQL, not only in-process.
- The backup/restore drill was executed against PostgreSQL with `pg_dump -Fc`, a database wipe, and `pg_restore --exit-on-error`, followed by API-level verification of the restored rows.

## Acceptance evidence

Record exact command outcomes in `docs/MILESTONE_ACCEPTANCE.md`. A source file or a successful typecheck alone does not complete a milestone.
