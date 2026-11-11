# Deployment

## Supported target

The intended standalone target is Windows 10/11 with Docker Desktop and Docker Compose. Extract the repository to `K:\WORLDWEAVE_M0` (or another local path). Start with the root script:

```powershell
.\Avvia-WORLDWEAVE.ps1
```

The script verifies Docker and Compose, creates `.env` with a random hexadecimal database password if it is missing or still contains the template marker, validates Compose configuration, builds and starts the services, waits for `/api/readyz`, and opens the browser.

The web service is available at `http://localhost:8080`. Compose binds it to `127.0.0.1`; PostgreSQL and FastAPI are only reachable inside the Compose network. The first account is available under the default `bootstrap_only` policy.

## Stop and restart

```powershell
.\Ferma-WORLDWEAVE.ps1
docker compose up -d
```

Normal shutdown uses `docker compose down` without `--volumes`, so PostgreSQL data is preserved.

## Environment

Copying `.env.example` is optional; the startup script creates `.env` automatically. Important values:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: local database initialization
- `REGISTRATION_MODE`: `bootstrap_only`, `open`, or `closed`
- `SESSION_TTL_DAYS`: session lifetime
- `COOKIE_SECURE`: enable Secure cookie attribute for HTTPS
- `WORLDWEAVE_DOMAIN`: Caddy site address; `:80` is the local HTTP default
- `HTTP_BIND_ADDRESS` / `HTTP_PORT` and `HTTPS_BIND_ADDRESS` / `HTTPS_PORT`: local defaults bind only loopback; set the public host to the intended interfaces and standard ports when deliberately enabling HTTPS

For a domain deployment, set a domain in `WORLDWEAVE_DOMAIN`, set `COOKIE_SECURE=true`, and adjust both host port bindings and firewall rules deliberately. Caddy can obtain and renew public certificates when it is given a real domain and reachable ports 80 and 443. The current Compose file is optimized for local loopback use, not a hardened public deployment.

## Service lifecycle

Compose starts PostgreSQL, waits for its health check, applies Alembic migrations through a one-shot service, starts FastAPI, then starts Caddy. PostgreSQL data lives in the named `worldweave_postgres` volume. Caddy state uses separate named volumes.

## Current deployment limitations

The current build is M1. Registration and session flows exist, but the worldbuilding modules, invitations, full production TLS/networking guide, asset storage, and release hardening remain incomplete. Do not treat this as a public production release.
