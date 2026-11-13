# Security

## Authentication and sessions

- Passwords are hashed with Argon2id; raw passwords are never logged or stored.
- Session identifiers are cryptographically random, opaque, revocable, time-limited, and stored only as SHA-256 hashes.
- Auth cookies use HttpOnly and SameSite=Lax; `COOKIE_SECURE` controls the Secure flag and defaults on outside explicit development mode.
- Logout and other authenticated mutations require a double-submit CSRF token whose hash is stored with the session. Login and registration reject cross-site fetch metadata and mismatched Origin headers.
- Login and registration use a per-process sliding-window rate limit. It targets the single API process in the current deployment.

## Authorization and tenant isolation

- Authorization is centralized in `backend/core/permissions.py` with five ranked roles (`owner`, `admin`, `editor`, `contributor`, `viewer`). An actor cannot manage a peer or a superior.
- Every universe-owned row carries `universe_id`; services reject cross-universe references. Substituting another universe's identifier in a path returns not-found rather than leaking data.
- Private content is filtered by `backend/core/visibility.py` for reads, search results, and the Nexus graph.

## Input, uploads, and stored content

- Request bodies are validated by Pydantic; error responses do not expose submitted values or stack traces.
- Asset uploads enforce a maximum size, verify the declared MIME type against the file content, and store SHA-256 checksums.
- Chronicle content and Markdown rendering sanitize HTML: script-bearing links and unsafe nodes are rejected or stripped before storage and rendering.
- Import archives are validated for schema version, checksums, archive path safety (no absolute paths or traversal), and reference integrity before any write.
- Unhandled exceptions return a generic 500 response without stack traces. The response `X-Request-ID` matches the error envelope request ID.

## Logging and operations

- Logs include request IDs, method, path, status, and duration only. They omit query strings, request bodies, cookies, and credentials.
- Docker's local web port binds to loopback; PostgreSQL is not exposed on the host.
- Keep `.env` private. It is ignored by Git. For a public deployment, configure HTTPS through Caddy, set `COOKIE_SECURE=true`, restrict registration, protect backups, and review network access before exposing the service.

## Verification

- `backend/tests/test_security_audit.py` asserts the release security properties: unauthenticated access rejection, session revocation, cross-universe id substitution, search and graph leakage, role escalation, viewer mutation across every resource family, WebSocket room authorization, upload path/MIME/size safety, stored-XSS link and node rejection, CSRF enforcement, invitation token binding and non-reuse, and import archive safety.
- `backend/tests/test_universe_security.py`, `test_codex_visibility.py`, and `test_collaboration.py` cover tenant isolation, visibility, and realtime authorization.

## Known operational limits

- The rate limiter and the realtime room manager are per-process; run a single API worker until shared state (external rate-limit store, sticky routing, or pub/sub) is added.
- The Compose defaults target local loopback use, not a hardened public deployment; review the deployment guide before exposing the service.
