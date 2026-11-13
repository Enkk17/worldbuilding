# WORLDWEAVE

WORLDWEAVE is a self-hostable collaborative workspace for creating and organizing fictional universes. The M0 specification pack is the product and architecture source of truth in `docs/specifications/WORLDWEAVE_M0/`.

## Run & Operate

- `pnpm --filter @workspace/worldweave run dev` — run the React/Vite web artifact (managed workflow supplies `PORT` and `BASE_PATH`)
- `uv sync --locked` — install the pinned Python environment
- `uv run --locked alembic -c backend/alembic.ini upgrade head` — apply FastAPI database migrations
- `uv run --locked python -m pytest` — run backend tests
- `pnpm run typecheck` — typecheck all workspace TypeScript
- `pnpm --filter @workspace/api-spec run codegen` — regenerate client and validation types from OpenAPI
- Required backend env: `DATABASE_URL`; local self-hosting settings are in `.env.example`
- Standalone Windows scripts: `Avvia-WORLDWEAVE.ps1`, `Ferma-WORLDWEAVE.ps1`, `Backup-WORLDWEAVE.ps1`, `Ripristina-WORLDWEAVE.ps1`

## Stack

- Web: React, strict TypeScript, Vite, Tailwind CSS, TanStack Query, Wouter, React Hook Form, Zod
- API: Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2.x, Alembic, PostgreSQL
- Python dependency lock: `pyproject.toml` and `uv.lock`
- TypeScript API contract: `lib/api-spec/openapi.yaml`, generated client in `lib/api-client-react`, generated schemas in `lib/api-zod`
- Self-hosted runtime: Docker Compose, PostgreSQL, Caddy

## Where things live

- `artifacts/worldweave/` — web UI
- `backend/core/` — database, settings, security, errors, rate limit
- `backend/modules/identity/` — account and session flows
- `backend/migrations/` — Alembic schema history
- `backend/tests/` — direct Python tests
- `infra/` — Docker build and Windows operations scripts
- `docs/` — user, operations, architecture, traceability, and status documentation
- `docs/specifications/WORLDWEAVE_M0/` — preserved normative source specifications

## Architecture decisions

- Preserve the M0 modular-monolith and self-hosted architecture; do not replace FastAPI/SQLAlchemy with the workspace's starter Express/Drizzle service.
- Use PostgreSQL as the authoritative store; Markdown remains the interchange format.
- Use UUIDv4 consistently, bootstrap-only signup by default, and server-side sessions with hashed opaque tokens.
- No AI, embeddings, vector database, analytics, or mandatory SaaS service in v1.0.

## Product

WORLDWEAVE covers universe and Society management, the Codex encyclopedia, Chronicle documents, Nexus relation graphs, Atlas maps, Chronos calendars/timelines, collaboration, and portable import/export. Milestones M1 through M9 are implemented; see `docs/IMPLEMENTATION_STATUS.md`.

## User preferences

No separate preferences recorded.

## Gotchas

- The API artifact route is `/api`; API endpoints use `/api/v1`. Keep the OpenAPI base `/api` and do not change `info.title` from `Api`.
- After OpenAPI changes, regenerate client and Zod code before using new hooks or schemas.
- API mutations require `ww_csrf`; the generated `custom-fetch` reads the CSRF cookie and sends the header.
- Do not expose the local HTTP Compose deployment publicly. Configure HTTPS and `COOKIE_SECURE=true` before public access.
- The normal stop script preserves the database volume; restore is destructive and requires a typed confirmation.

## Pointers

- M0 source requirements: `docs/specifications/WORLDWEAVE_M0/`
- Current milestone gates: `docs/MILESTONE_ACCEPTANCE.md`
- Workspace conventions: `.local/skills/pnpm-workspace/SKILL.md`
