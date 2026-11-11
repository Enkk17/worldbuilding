# API Contract Baseline

## 1. General

Base path: `/api/v1`

All endpoints require authentication unless explicitly marked public. Every universe-scoped endpoint verifies membership and resource authorization.

Response conventions:
- JSON objects use `snake_case` on the wire.
- IDs are opaque UUID strings.
- Dates/times use ISO 8601; timestamps are UTC.
- Lists are paginated.
- Errors: `{ "error": { "code": "stable_code", "message": "Human-readable message", "details": {}, "request_id": "..." } }`
- Never return internal stack traces.

## 2. Initial endpoint inventory

### Authentication
- `POST /auth/register` — registration according to instance policy.
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/recovery/request`
- `POST /auth/recovery/complete`

### Universes and members
- `GET /universes`
- `POST /universes`
- `GET /universes/{universe_id}`
- `PATCH /universes/{universe_id}`
- `POST /universes/{universe_id}/archive`
- `GET /universes/{universe_id}/members`
- `POST /universes/{universe_id}/invitations`
- `POST /invitations/{token}/accept`
- `PATCH /universes/{universe_id}/members/{user_id}`
- `DELETE /universes/{universe_id}/members/{user_id}`

### Codex
- `GET /universes/{universe_id}/entity-types`
- `POST /universes/{universe_id}/entity-types`
- `PATCH /universes/{universe_id}/entity-types/{type_id}`
- `GET /universes/{universe_id}/entities`
- `POST /universes/{universe_id}/entities`
- `GET /universes/{universe_id}/entities/{entity_id}`
- `PATCH /universes/{universe_id}/entities/{entity_id}`
- `DELETE /universes/{universe_id}/entities/{entity_id}`
- `POST /universes/{universe_id}/entities/{entity_id}/restore`
- `GET /universes/{universe_id}/entities/{entity_id}/relations`
- `POST /universes/{universe_id}/relations`
- `DELETE /universes/{universe_id}/relations/{relation_id}`

### Chronicle
- `GET /universes/{universe_id}/documents`
- `POST /universes/{universe_id}/documents`
- `GET /universes/{universe_id}/documents/{document_id}`
- `PATCH /universes/{universe_id}/documents/{document_id}`
- `GET /universes/{universe_id}/documents/{document_id}/revisions`
- `POST /universes/{universe_id}/documents/{document_id}/restore/{revision_id}`
- `POST /universes/{universe_id}/documents/{document_id}/comments`
- `GET /universes/{universe_id}/documents/{document_id}/comments`

### Collaboration
- `GET /universes/{universe_id}/documents/{document_id}/collaboration-ticket`
- `WS /api/v1/collaboration/documents/{document_id}`

The ticket endpoint returns a short-lived, single-purpose connection ticket. Do not place long-lived session credentials in WebSocket query strings.

### Atlas
- `GET/POST /universes/{universe_id}/maps`
- `GET/PATCH/DELETE /universes/{universe_id}/maps/{map_id}`
- `GET/POST /universes/{universe_id}/maps/{map_id}/markers`
- `PATCH/DELETE /universes/{universe_id}/maps/{map_id}/markers/{marker_id}`
- `GET/POST /universes/{universe_id}/maps/{map_id}/regions`

### Chronos
- `GET/POST /universes/{universe_id}/calendars`
- `GET/PATCH /universes/{universe_id}/calendars/{calendar_id}`
- `GET/POST /universes/{universe_id}/timeline-events`
- `GET/PATCH/DELETE /universes/{universe_id}/timeline-events/{event_id}`

### Nexus and search
- `GET /universes/{universe_id}/graph`
- `GET /universes/{universe_id}/search?q=...`
- `GET /universes/{universe_id}/activity`

### Import/export
- `POST /universes/{universe_id}/exports`
- `GET /universes/{universe_id}/exports/{export_id}`
- `POST /imports/validate`
- `POST /universes/{universe_id}/imports`

## 3. Contract details

### Entity update
`PATCH` requires a version precondition (`If-Match` ETag or explicit `expected_version`). If the version differs, return `409 version_conflict` with current version metadata. Never silently last-write-wins structured entity edits.

### Pagination
List endpoints accept:
- `limit` with a server-enforced maximum;
- `cursor` for cursor-based pagination;
- documented filter and sort parameters.

### Graph query
Graph endpoint requires bounded parameters:
- `focus_entity_id` optional;
- `depth` default 1, maximum 3 initially;
- `entity_type_ids` optional;
- `relation_type_ids` optional;
- `limit` bounded.

The response includes only authorized entities and relationships.

### Import/export jobs
Large exports/imports are asynchronous jobs. Job status is queryable and errors are machine-readable. Import validation is a separate non-mutating phase.

## 4. API quality requirements

- Generate OpenAPI in CI.
- Generate TypeScript client types from OpenAPI; do not maintain duplicate handwritten API contracts.
- Add request/response examples for every endpoint group.
- Test authorization for each endpoint.
- Validate pagination bounds, payload size, and query complexity.
- Use idempotency keys for import creation and invitation operations where retries are possible.
- API version changes must be deliberate and documented.
