# WORLDWEAVE Architecture

## Baseline

WORLDWEAVE follows the normative M0 baseline: one modular monolith, React + strict TypeScript + Vite in the browser, FastAPI + Pydantic + SQLAlchemy + Alembic on the server, and PostgreSQL as the authoritative store. The complete baseline and accepted ADRs are in `docs/specifications/WORLDWEAVE_M0/`.

The workspace is a pnpm monorepo for the web artifact and the generated TypeScript API client. Python dependencies are managed with `uv`. The WORLDWEAVE API service runs the FastAPI application. Self-hosted deployment uses Docker Compose, PostgreSQL, and Caddy.

## Module boundaries

```text
artifacts/worldweave/       React/Vite application (all universe modules)
backend/core/               Settings, database, models, permissions, visibility, errors, security, rate limiting
backend/modules/identity/   Registration, login, account, sessions
backend/modules/universes/  Universes, membership, roles, invitations, ownership, audit and activity
backend/modules/codex/      Entity types, entities, relations, Nexus graph
backend/modules/chronicle/  Document tree, rich content, revisions, comments, entity links
backend/modules/collaboration/  Yjs realtime rooms, tickets, persistence, compaction
backend/modules/atlas/      Maps, markers, regions, assets
backend/modules/chronos/    Calendars, eras, timeline events
backend/modules/search/     Unified permission-filtered search
backend/modules/exports/    Import/export bundles and job ledger
backend/migrations/         Alembic schema history
backend/tests/              Direct pytest coverage
lib/api-spec/               OpenAPI contract source
lib/api-client-react/       Generated React Query client
lib/api-zod/                Generated validation types
infra/                      Caddy, Docker, and Windows operations scripts
docs/specifications/        The received M0 specification pack
```

## Authorization model

Authorization is centralized in `backend/core/permissions.py`. Five roles exist: `owner`, `admin`, `editor`, `contributor`, and `viewer`, ranked `50/40/30/20/10`. Each role maps to a set of `Action` values (for example `entity.update`, `document.review`, `import.execute`). Services call `has_permission(role, action)` and use `ROLE_RANK` to prevent an actor from managing a peer or a superior. Visibility (public vs private content) is applied on top of roles by `backend/core/visibility.py`.

## Request lifecycle

1. A same-origin browser request reaches Caddy and is routed to the API for `/api/*`.
2. Middleware assigns a request ID, enforces CSRF for unsafe `/api/v1` requests, and logs method, path, status, and duration.
3. FastAPI resolves the session, then the service layer resolves the caller's role for the target universe and checks the required `Action`.
4. SQLAlchemy performs parameterized queries against PostgreSQL; every universe-owned row carries `universe_id` and cross-universe references are rejected.
5. Errors use a stable envelope with a request ID; logs omit query strings, bodies, cookies, and credential values.

## Realtime collaboration

Each document room loads a Yjs document, applies stored updates in order, and broadcasts further updates to connected clients. Updates are acknowledged only after they are durably stored. Idle rooms compact the update log into a verified snapshot. The room manager is in-process, so a single API worker must be used until sticky routing or external pub/sub is added.

## Configuration and migration

`DATABASE_URL` is required; the application does not fall back to an in-memory or local database. Alembic owns schema changes. Compose runs a separate one-shot migration container before the API starts. PostgreSQL-only behavior (full-text search indexes, `IMMUTABLE` index expressions) is exercised against a real PostgreSQL database.

## Delivered milestones

M1 through M9 are implemented: identity, universes and roles, Codex and Nexus, Chronicle, realtime collaboration, Atlas, Chronos, search, and import/export, plus release hardening. See `docs/IMPLEMENTATION_STATUS.md` for the module-level status.
