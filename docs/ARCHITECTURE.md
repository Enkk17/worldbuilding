# WORLDWEAVE Architecture

## Baseline

WORLDWEAVE follows the normative M0 baseline: one modular monolith, React + strict TypeScript + Vite in the browser, FastAPI + Pydantic + SQLAlchemy + Alembic on the server, and PostgreSQL as the authoritative store. The complete baseline and accepted ADRs are in `docs/specifications/WORLDWEAVE_M0/`.

The Replit workspace is a pnpm monorepo for the web artifact and generated TypeScript API client. Python dependencies are managed with `uv`. The WORLDWEAVE API service runs the FastAPI application; the former Express starter implementation is not part of the WORLDWEAVE request path. Self-hosted deployment uses Docker Compose, PostgreSQL, and Caddy.

## Current module boundaries

```text
artifacts/worldweave/       React/Vite account-entry UI
backend/core/               Settings, database, sessions, errors, security
backend/modules/identity/   Registration, login, account, session use cases
backend/migrations/         Alembic schema history
backend/tests/              Direct pytest coverage
lib/api-spec/               OpenAPI contract source
lib/api-client-react/       Generated React Query client
lib/api-zod/                Generated validation types
infra/                      Caddy, Docker, and Windows operations scripts
docs/specifications/        The received M0 specification pack
```

## Request lifecycle

1. A same-origin browser request reaches Caddy and is routed to the API for `/api/*`.
2. FastAPI validates the request and applies account/session rules.
3. SQLAlchemy performs a parameterized query or transaction against PostgreSQL.
4. Sensitive auth mutations write only password hashes, session token hashes, CSRF token hashes, and timestamps.
5. API errors use a stable envelope with a request ID; request logs omit query strings, bodies, cookies, and credential values.

## Configuration and migration

`DATABASE_URL` is required; the application intentionally does not fall back to an in-memory or local database. Alembic owns schema changes. Development startup applies the current migration before serving; Compose runs a separate one-shot migration container before the API starts.

## M1 decisions and boundaries

- IDs use UUIDv4 consistently.
- Email addresses are normalized to lowercase and globally unique.
- Initial self-hosted registration is bootstrap-only by default; `open` and `closed` modes are configurable.
- Sessions use opaque random cookie values; only SHA-256 hashes are stored in PostgreSQL. Passwords use Argon2id.
- A single-process sliding-window limiter protects login and registration in M1. Multi-instance coordination and broader security controls remain release work.
- Replit's build environment runs the same FastAPI app, but Windows Docker Compose is the intended self-hosted deployment path.

## Not yet implemented

Universe, membership, Codex, Chronicle, Nexus, Atlas, Chronos, review, imports/exports, realtime collaboration, asset storage, and release operations are future milestone scope. The UI does not present those modules as working features yet.
