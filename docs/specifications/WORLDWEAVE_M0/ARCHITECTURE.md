# Technical Architecture

## 1. Architecture style

Use a **modular monolith** with explicit domain boundaries. Deploy the web application, API, database, and supporting infrastructure as containers. Do not split modules into microservices in v1.0.

The backend is the authority for business rules, authorization, validation, and persistence. The frontend must not be trusted to enforce permissions.

## 2. Technology baseline

### Frontend
- React
- TypeScript (`strict: true`)
- Vite
- Tailwind CSS
- shadcn/ui components, customized rather than copied as an unmodified theme
- TanStack Query for server state
- React Router for routing
- React Hook Form + Zod for forms and client-side schema feedback
- TipTap for rich-text editing
- Yjs for collaborative document state
- Cytoscape.js for graph visualization
- Leaflet for image-based maps using CRS.Simple or an equivalent normalized image coordinate adapter
- Vitest + Testing Library; Playwright for E2E

### Backend
- Python
- FastAPI
- Pydantic for request/response schemas
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- pytest
- WebSocket endpoint(s) for collaboration and presence
- Yjs-compatible collaboration protocol. Select and document a maintained server implementation during M1 technical spike; do not invent a proprietary CRDT protocol.

### Infrastructure
- Docker Compose
- PostgreSQL
- Redis only for shared ephemeral coordination/cache when needed; it is not the system of record
- Filesystem storage in local deployment; define an S3-compatible storage adapter for future portability
- Reverse proxy (Caddy or Nginx) for TLS termination
- SMTP adapter is configurable and optional for local development; invitation delivery must have a copyable link fallback.

Do not pin unverified "latest" versions in this spec. At project initialization, choose mutually compatible stable releases, pin exact versions in lockfiles/images, and record them.

## 3. Repository and package boundaries

Recommended monorepo:
- `apps/web`: React client
- `apps/api`: FastAPI entry point and dependency wiring
- `packages/ui`: shared visual components
- `packages/editor`: editor extensions and entity-reference behavior
- `packages/contracts`: generated or shared API types; generated OpenAPI client is preferred
- `packages/graph`: graph presentation adapters
- `packages/map`: map presentation adapters
- `backend/modules/*`: domain modules
- `backend/core/*`: database, auth, permissions, storage, events, configuration
- `infra/*`: Docker, reverse proxy, backup scripts
- `docs/*`: normative specs and ADRs

Python dependencies should be managed separately from JavaScript dependencies (for example, `uv` for Python and `pnpm` for JS). A workspace orchestrator is optional; do not add tooling without a clear need.

## 4. Backend module boundaries

Each domain module owns:
- domain models or ORM mappings;
- schemas;
- repository functions;
- service/use-case functions;
- API routers;
- tests.

Modules must not directly manipulate another module's tables except through an explicitly documented shared transaction/service boundary. Cross-module workflows should call application services, not import private internals.

Suggested modules:
- identity
- universes
- membership
- codex
- relations
- documents
- collaboration
- atlas
- chronos
- comments
- revisions
- search
- imports_exports
- audit

## 5. Data flow

1. Browser sends request with secure session.
2. API authenticates session.
3. Authorization layer resolves user membership and resource permissions.
4. Pydantic validates request.
5. Application service enforces domain invariants.
6. Repository persists within transaction.
7. Audit event is written in the same transaction for relevant mutations.
8. API returns a typed response.
9. Frontend updates or invalidates relevant queries.

Do not let route handlers become business-logic containers.

## 6. API design

- Prefix: `/api/v1`
- JSON REST for ordinary operations.
- WebSocket for Yjs synchronization and ephemeral presence.
- OpenAPI is generated from FastAPI and treated as the contract.
- Use UUIDv7 or UUIDv4 consistently; select one in ADR before migrations. Never use slugs as primary keys.
- Timestamps stored in UTC; display localized in client.
- Pagination uses cursor pagination for activity and large collections; offset pagination may be used for bounded administrative tables.
- Errors use a consistent envelope with stable machine-readable `code`, human-readable `message`, optional `details`, and `request_id`.
- Use HTTP status codes correctly.
- Mutating endpoints support idempotency where retries could duplicate side effects (invites, imports, submissions).
- Concurrency-sensitive structured updates require `If-Match`/version number or equivalent.

## 7. Authentication

Prefer server-side sessions:
- opaque random session token in Secure, HttpOnly, SameSite cookie;
- only a hash of the token stored server-side;
- rotation on login and privilege changes;
- revocation on logout/password change;
- CSRF protection for cookie-authenticated unsafe requests;
- Argon2id password hashing;
- rate limiting on login and recovery;
- no password or session token in logs.

Email is optional in development. Production recovery requires configured SMTP or documented administrator recovery.

## 8. Authorization

Authorization is deny-by-default. Use RBAC for universe-level roles plus explicit resource-level grants where required. Every query is scoped by universe ID and authorized visibility. See `PERMISSIONS.md`.

## 9. Storage

PostgreSQL is authoritative for structured entities, relationships, metadata, document revisions, and collaboration snapshots. Markdown is the portable representation for export/import and optional local vault workflows. See `STORAGE_AND_IMPORT_EXPORT.md`.

Binary assets live in a storage adapter with metadata in PostgreSQL. Never store large image binaries in ordinary relational rows.

## 10. Realtime

Use Yjs for document editing, with durable persistence and authorization checks before joining a document room. Presence is ephemeral. Structured entity forms use optimistic concurrency, not CRDT.

Realtime messages must never bypass document permissions. Re-check access on connection and on permission changes; revoke active room access when membership/permissions are removed.

## 11. Search

v1.0 uses PostgreSQL full-text search and indexed metadata. No vector database or semantic search. Search queries must be scoped to authorized universes and records.

## 12. Observability

- JSON structured logs.
- Request correlation ID.
- Health endpoint and readiness endpoint.
- Metrics may be exposed locally, but no external telemetry by default.
- Redact credentials, cookies, invite tokens, and document content from logs.
- Audit log is separate from operational logs.

## 13. Performance and scale

Optimize after measurement. Use indexes, pagination, query plans, caching only where justified, and graph depth limits. Avoid N+1 queries. Do not introduce distributed infrastructure prematurely.

## 14. Security boundaries

- Validate uploads by size, MIME sniffing, and safe file handling.
- Store uploads outside executable web roots.
- Prevent path traversal.
- Use CSRF protection, secure headers, rate limits, and input validation.
- Render rich text through a safe schema; sanitize any HTML output.
- Avoid arbitrary HTML and script execution in content.
- Apply database least privilege.
- Use migrations, not manual schema edits.

## 15. Engineering constraints

- No AI functionality in v1.0.
- No mandatory cloud account.
- No external analytics by default.
- No microservices.
- No frontend-only authorization.
- No unbounded graph traversal.
- No unversioned schema changes.
- No destructive migration without backup and rollback/forward-recovery plan.
