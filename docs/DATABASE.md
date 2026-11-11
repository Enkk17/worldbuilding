# Database

## Authority and conventions

PostgreSQL is the authoritative store. IDs are opaque UUIDv4 values. Timestamps represent UTC instants. Every future universe-owned table must include `universe_id`; composite constraints or service checks must prevent cross-universe references.

## M1 schema

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

Session cookie values and passwords are never stored in plaintext. Expired or revoked sessions are rejected server-side. The M1 schema migration is reversible.

## Migrations

Alembic migrations are in `backend/migrations/versions/`. Run:

```bash
uv run --locked alembic -c backend/alembic.ini upgrade head
uv run --locked alembic -c backend/alembic.ini downgrade base
```

The downgrade removes only M1 identity tables; do not use it against a database containing user data without a separate backup and explicit operator approval.

## Planned domain model

The normative future model—including universes, memberships, invitations, Codex entities and relations, documents and revisions, map assets, calendars, timeline events, comments, proposals, activity, and audit logs—is specified in `docs/specifications/WORLDWEAVE_M0/DATABASE.md`. Those tables have not been created in M1.
