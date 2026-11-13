# Database

## Authority and conventions

PostgreSQL is the authoritative store. IDs are opaque UUIDv4 values. Timestamps represent UTC instants. Every universe-owned table includes `universe_id`, and composite constraints or service checks prevent cross-universe references.

## Schema by milestone

The full model is specified in `docs/specifications/WORLDWEAVE_M0/DATABASE.md`. The implemented Alembic history is:

| Revision | Scope |
|---|---|
| `0001_identity` | `users`, `sessions` |
| `0002_core_worldweave` | Universes, memberships, invitations, Codex, Chronicle, Atlas, and Chronos core tables |
| `0003_chronicle_m4` | Chronicle revision sources, slugs, comment lookup indexes |
| `0004_collaboration_m5` | Ordered Yjs updates and verified snapshots |
| `0005_atlas_chronos_m6` | Atlas and Chronos tables brought to their M6 model shape |
| `0006_search_m7` | PostgreSQL full-text search GIN expression indexes |
| `0007_import_export_m8` | Import job ledger |

The current head is `0007_import_export_m8`.

## Identity tables

### `users`

- `id`: UUID primary key
- `email`: normalized unique email, maximum 254 characters
- `password_hash`: Argon2id encoded password hash
- `display_name`: account display label
- `status`: account state (`active` at registration)
- `created_at`, `updated_at`: timezone-aware timestamps

### `sessions`

- `id`: UUID primary key
- `user_id`: foreign key to `users`, cascade on account deletion
- `token_hash`: unique SHA-256 hash of the opaque `ww_session` cookie
- `csrf_hash`: SHA-256 hash used to validate unsafe requests
- `created_at`, `expires_at`, `revoked_at`: session lifecycle timestamps

Session cookie values and passwords are never stored in plaintext. Expired or revoked sessions are rejected server-side.

## Full-text search indexes

`0006_search_m7` creates GIN expression indexes `ix_entities_search_fts`, `ix_documents_search_fts`, and `ix_timeline_events_search_fts`. The expressions use immutable `coalesce`/`||` concatenations over `::text`; `concat_ws` is `STABLE`, not `IMMUTABLE`, and cannot be indexed. The service query expression matches the index expression so the planner uses the index.

## Realtime tables

`document_collab_updates` stores ordered Yjs updates per document, and `document_collab_snapshots` stores compacted, verified snapshots. Updates are acknowledged only after they are durably stored.

## Migrations

Alembic migrations are in `backend/migrations/versions/`. Run:

```bash
uv run --locked alembic -c backend/alembic.ini upgrade head
uv run --locked alembic -c backend/alembic.ini downgrade base
```

Migrations apply forward automatically through the Compose `migrate` service. Always back up the database before a downgrade; a downgrade removes the tables for the reverted revisions.
