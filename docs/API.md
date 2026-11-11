# API

## Contract and conventions

`lib/api-spec/openapi.yaml` is the OpenAPI source of truth for the current M1 client contract. Rebuild generated client and Zod schemas after edits:

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

## M1 endpoints

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| GET | `/api/healthz` | No | Process health |
| GET | `/api/readyz` | No | Database readiness |
| POST | `/api/v1/auth/register` | No | Register under instance policy and start a session |
| POST | `/api/v1/auth/login` | No | Verify credentials and start a session |
| POST | `/api/v1/auth/logout` | Session + CSRF | Revoke the current session |
| GET | `/api/v1/auth/me` | Session | Return the current account |

Registration policy is controlled by `REGISTRATION_MODE`: `bootstrap_only` allows the first account only, `open` allows further registrations, and `closed` disables registration.

## Sessions and errors

Authentication uses `ww_session` (Secure where configured, HttpOnly, SameSite=Lax). Unsafe authenticated requests also require the `X-CSRF-Token` header to match the non-HttpOnly `ww_csrf` cookie and its stored hash. The generated browser fetcher adds the header for mutating requests.

Request bodies are validated by Pydantic. Validation errors do not return submitted values. Unhandled exceptions return a generic 500 response without stack traces. The response `X-Request-ID` matches the error envelope request ID.

## Future endpoint groups

The full M0 inventory for universes, membership, Codex, Chronicle, collaboration, Atlas, Chronos, Nexus/search, and import/export remains required before v1.0. Those routes are not represented as complete in M1.
