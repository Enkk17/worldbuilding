# Implementation Decisions

## Accepted M0 decisions

- Use a modular monolith, not microservices.
- PostgreSQL is authoritative; Markdown is portable import/export, not a second canonical store.
- Use the specified React/TypeScript and FastAPI/Python stack.
- Exclude AI, embeddings, vector search, analytics, and mandatory SaaS services.

## M1 implementation choices

1. **UUIDv4 for opaque identifiers.** M0 allows UUIDv4 or UUIDv7 but requires one consistent choice before migrations. UUIDv4 is available in Python's standard library and maps directly to PostgreSQL UUID.
2. **Bootstrap-only public registration by default.** The first account can initialize an installation; subsequent signup is disabled unless the operator deliberately enables `open`.
3. **Opaque server-side sessions.** Random session tokens and CSRF tokens are only stored as SHA-256 hashes; passwords use Argon2id.
4. **Single-process rate limiter in M1.** The initial application has one API process. If deployment becomes multi-instance, replace this with shared ephemeral coordination before scaling.
5. **Reuse the API artifact route for FastAPI.** The project template's API artifact is configured to serve the Python service so the preview path remains `/api`; the actual domain logic and data access live in FastAPI, not the starter Express code.
6. **Docker development uses separate migration and API services.** Migration runs only after PostgreSQL is healthy and API startup waits for migration success.

## Decisions still required

The M0 pack says to request a decision for ambiguous requirements. Any unresolved design choices affecting authorization, document collaboration persistence, import conflict policy, calendar semantics, or resource visibility must be written here and resolved before their milestone gate.
