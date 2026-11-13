# API

## Contract and conventions

`lib/api-spec/openapi.yaml` is the OpenAPI source of truth for the client contract. The FastAPI application also serves a live schema at `/api/openapi.json` and interactive docs at `/api/docs`. Rebuild generated client and Zod schemas after edits:

```bash
pnpm --filter @workspace/api-spec run codegen
```

The wire format uses snake_case, opaque UUID strings, ISO 8601 UTC timestamps, and stable error envelopes:

```json
{
  "error": {
    "code": "authentication_required",
    "message": "Authentication is required.",
    "details": {},
    "request_id": "..."
  }
}
```

Authentication uses the `ww_session` cookie. Unsafe authenticated requests must also send the `X-CSRF-Token` header matching the `ww_csrf` cookie.

## Health

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| GET | `/api/healthz` | No | Process health |
| GET | `/api/readyz` | No | Database readiness |

## Identity

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register` | Register under the instance policy and start a session |
| POST | `/api/v1/auth/login` | Verify credentials and start a session |
| POST | `/api/v1/auth/logout` | Revoke the current session |
| GET | `/api/v1/auth/me` | Return the current account |

## Universes, membership, and invitations

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/universes` | List universes the caller can access |
| POST | `/api/v1/universes` | Create a universe |
| GET | `/api/v1/universes/{universe_id}` | Read a universe |
| PATCH | `/api/v1/universes/{universe_id}` | Update a universe |
| POST | `/api/v1/universes/{universe_id}/archive` | Archive a universe |
| POST | `/api/v1/universes/{universe_id}/unarchive` | Unarchive a universe |
| POST | `/api/v1/universes/{universe_id}/transfer-ownership` | Transfer ownership |
| GET | `/api/v1/universes/{universe_id}/members` | List members |
| PATCH | `/api/v1/universes/{universe_id}/members/{target_user_id}` | Change a member role |
| DELETE | `/api/v1/universes/{universe_id}/members/{target_user_id}` | Remove a member |
| GET | `/api/v1/universes/{universe_id}/invitations` | List invitations |
| POST | `/api/v1/universes/{universe_id}/invitations` | Invite a member |
| DELETE | `/api/v1/universes/{universe_id}/invitations/{invitation_id}` | Revoke an invitation |
| POST | `/api/v1/invitations/{token}/accept` | Accept an invitation |
| GET | `/api/v1/universes/{universe_id}/activity` | Read the activity feed |
| GET | `/api/v1/universes/{universe_id}/audit-logs` | Read audit logs |

## Codex (entities, relations, Nexus)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/universes/{universe_id}/entity-types` | List entity types |
| POST | `/api/v1/universes/{universe_id}/entity-types` | Create an entity type |
| PATCH | `/api/v1/universes/{universe_id}/entity-types/{type_id}` | Update an entity type |
| GET | `/api/v1/universes/{universe_id}/entities` | List entities |
| POST | `/api/v1/universes/{universe_id}/entities` | Create an entity |
| GET | `/api/v1/universes/{universe_id}/entities/{entity_id}` | Read an entity |
| PATCH | `/api/v1/universes/{universe_id}/entities/{entity_id}` | Update an entity |
| DELETE | `/api/v1/universes/{universe_id}/entities/{entity_id}` | Delete an entity |
| POST | `/api/v1/universes/{universe_id}/entities/{entity_id}/restore` | Restore an entity |
| GET | `/api/v1/universes/{universe_id}/entities/{entity_id}/relations` | List an entity's relations |
| GET | `/api/v1/universes/{universe_id}/entities/{entity_id}/documents` | List documents linking to an entity |
| GET | `/api/v1/universes/{universe_id}/relation-types` | List relation types |
| POST | `/api/v1/universes/{universe_id}/relation-types` | Create a relation type |
| POST | `/api/v1/universes/{universe_id}/relations` | Create a relation |
| DELETE | `/api/v1/universes/{universe_id}/relations/{relation_id}` | Delete a relation |
| GET | `/api/v1/universes/{universe_id}/graph` | Read the Nexus graph |

## Chronicle (documents, revisions, comments)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/universes/{universe_id}/documents` | List documents |
| POST | `/api/v1/universes/{universe_id}/documents` | Create a document |
| GET | `/api/v1/universes/{universe_id}/documents/tree` | Read the document tree |
| GET | `/api/v1/universes/{universe_id}/documents/{document_id}` | Read a document |
| PATCH | `/api/v1/universes/{universe_id}/documents/{document_id}` | Update a document |
| DELETE | `/api/v1/universes/{universe_id}/documents/{document_id}` | Delete a document |
| POST | `/api/v1/universes/{universe_id}/documents/{document_id}/restore` | Restore a document |
| GET | `/api/v1/universes/{universe_id}/documents/{document_id}/revisions` | List revisions |
| GET | `/api/v1/universes/{universe_id}/documents/{document_id}/revisions/{revision_id}` | Read a revision |
| POST | `/api/v1/universes/{universe_id}/documents/{document_id}/restore/{revision_id}` | Restore a revision |
| GET | `/api/v1/universes/{universe_id}/documents/{document_id}/comments` | List comments |
| POST | `/api/v1/universes/{universe_id}/documents/{document_id}/comments` | Create a comment |
| PATCH | `/api/v1/universes/{universe_id}/documents/{document_id}/comments/{comment_id}` | Update a comment |
| DELETE | `/api/v1/universes/{universe_id}/documents/{document_id}/comments/{comment_id}` | Delete a comment |
| GET | `/api/v1/universes/{universe_id}/documents/{document_id}/links` | List entity links |
| GET | `/api/v1/universes/{universe_id}/documents/{document_id}/collaboration-ticket` | Issue a realtime ticket |
| WS | `/api/v1/collaboration/documents/{document_id}` | Realtime collaboration channel |

## Atlas (maps, markers, regions, assets)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/universes/{universe_id}/maps` | List maps |
| POST | `/api/v1/universes/{universe_id}/maps` | Create a map |
| GET | `/api/v1/universes/{universe_id}/maps/{map_id}` | Read a map |
| PATCH | `/api/v1/universes/{universe_id}/maps/{map_id}` | Update a map |
| DELETE | `/api/v1/universes/{universe_id}/maps/{map_id}` | Delete a map |
| GET | `/api/v1/universes/{universe_id}/maps/{map_id}/markers` | List markers |
| POST | `/api/v1/universes/{universe_id}/maps/{map_id}/markers` | Create a marker |
| PATCH | `/api/v1/universes/{universe_id}/maps/{map_id}/markers/{marker_id}` | Update a marker |
| DELETE | `/api/v1/universes/{universe_id}/maps/{map_id}/markers/{marker_id}` | Delete a marker |
| GET | `/api/v1/universes/{universe_id}/maps/{map_id}/regions` | List regions |
| POST | `/api/v1/universes/{universe_id}/maps/{map_id}/regions` | Create a region |
| PATCH | `/api/v1/universes/{universe_id}/maps/{map_id}/regions/{region_id}` | Update a region |
| DELETE | `/api/v1/universes/{universe_id}/maps/{map_id}/regions/{region_id}` | Delete a region |
| POST | `/api/v1/universes/{universe_id}/assets` | Upload an asset |
| GET | `/api/v1/universes/{universe_id}/assets/{asset_id}` | Download an asset |

## Chronos (calendars, eras, timeline events)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/universes/{universe_id}/calendars` | List calendars |
| POST | `/api/v1/universes/{universe_id}/calendars` | Create a calendar |
| GET | `/api/v1/universes/{universe_id}/calendars/{calendar_id}` | Read a calendar |
| PATCH | `/api/v1/universes/{universe_id}/calendars/{calendar_id}` | Update a calendar |
| GET | `/api/v1/universes/{universe_id}/calendars/{calendar_id}/eras` | List eras |
| POST | `/api/v1/universes/{universe_id}/calendars/{calendar_id}/eras` | Create an era |
| PATCH | `/api/v1/universes/{universe_id}/calendars/{calendar_id}/eras/{era_id}` | Update an era |
| DELETE | `/api/v1/universes/{universe_id}/calendars/{calendar_id}/eras/{era_id}` | Delete an era |
| GET | `/api/v1/universes/{universe_id}/timeline-events` | List timeline events |
| POST | `/api/v1/universes/{universe_id}/timeline-events` | Create a timeline event |
| GET | `/api/v1/universes/{universe_id}/timeline-events/{event_id}` | Read a timeline event |
| PATCH | `/api/v1/universes/{universe_id}/timeline-events/{event_id}` | Update a timeline event |
| DELETE | `/api/v1/universes/{universe_id}/timeline-events/{event_id}` | Delete a timeline event |

## Search

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/universes/{universe_id}/search` | Unified, permission-filtered search over entities, documents, and timeline events |

## Import and export

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/universes/{universe_id}/exports` | Create and download an export bundle |
| GET | `/api/v1/universes/{universe_id}/imports` | List import jobs |
| POST | `/api/v1/universes/{universe_id}/imports/validate` | Validate a bundle without writing |
| POST | `/api/v1/universes/{universe_id}/imports` | Execute an import |

## Errors

Request bodies are validated by Pydantic. Validation errors do not return submitted values. Unhandled exceptions return a generic 500 response without stack traces. The response `X-Request-ID` matches the error envelope request ID. Authorization failures return `403` for a known universe and `404` for a universe the caller cannot see.
