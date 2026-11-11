# Security

## M1 controls

- Passwords are hashed with Argon2id; raw passwords are not logged or stored.
- Session identifiers are cryptographically random, opaque, revocable, time-limited, and stored only as SHA-256 hashes.
- Auth cookies use HttpOnly and SameSite=Lax; `COOKIE_SECURE` controls the Secure flag. It defaults on outside explicit development mode.
- Logout and other authenticated mutations require a double-submit CSRF token whose hash is stored with the session. Login and registration reject cross-site fetch metadata and mismatched Origin headers.
- Login and registration have a per-process sliding-window rate limit. It is designed for the single API process in this milestone.
- Input validation uses Pydantic; error responses do not expose submitted values or stack traces.
- Logs include request IDs, method, path, status, and duration only. They omit query strings, request bodies, cookies, and credentials.
- Docker's local web port is bound to loopback; the database is not exposed on the host.

## Operational settings

Keep `.env` private. It is ignored by Git. For a public deployment, configure HTTPS through Caddy, set `COOKIE_SECURE=true`, restrict registration, protect backups, and review network access before exposing the service.

## Remaining release security work

M1 is not a security-complete release. Required future work includes per-universe authorization and isolation, invitation tokens, password recovery, broader rate limits, upload validation and path safety, stored-XSS protections, audit coverage, search/graph leakage tests, WebSocket room authorization and revocation, and a full security test pass. Do not expose unfinished data modules publicly.
