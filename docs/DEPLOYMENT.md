# Deployment

## Supported target

The intended standalone target is Windows 10/11 with Docker Desktop and Docker Compose. Extract the repository to a local path such as `K:\WORLDWEAVE`. Start with the root script:

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
- `COOKIE_SECURE`: enable the Secure cookie attribute for HTTPS
- `MEDIA_ROOT`: container path for uploaded media (backed by the `worldweave_media` volume)
- `MAX_ASSET_BYTES`: maximum upload size (default 10485760)
- `WORLDWEAVE_DOMAIN`: Caddy site address; `:80` is the local HTTP default
- `HTTP_BIND_ADDRESS` / `HTTP_PORT` and `HTTPS_BIND_ADDRESS` / `HTTPS_PORT`: local defaults bind only loopback; set the public host to the intended interfaces and standard ports when deliberately enabling HTTPS

For a domain deployment, set a domain in `WORLDWEAVE_DOMAIN`, set `COOKIE_SECURE=true`, and adjust both host port bindings and firewall rules deliberately. Caddy can obtain and renew public certificates when it is given a real domain and reachable ports 80 and 443.

## Service lifecycle

Compose starts PostgreSQL, waits for its health check, applies Alembic migrations through a one-shot service, starts FastAPI, then starts Caddy. PostgreSQL data lives in the named `worldweave_postgres` volume; uploaded media lives in `worldweave_media`; Caddy state uses separate named volumes.

## Upgrades

1. Back up the database and media volumes (see `docs/BACKUP_RESTORE.md`).
2. Pull the new revision.
3. Run `docker compose up -d --build`. The one-shot `migrate` service applies new Alembic revisions before the API starts.

Migrations apply forward automatically. Verify `/api/readyz` after an upgrade and confirm the running revision with `alembic current`.

## Operational limits

- Run a single API worker. The rate limiter and the realtime room manager keep state in-process.
- The default Compose file is optimized for local loopback use, not a hardened public deployment. Review TLS, network exposure, and registration policy before exposing the service.

## Current scope

Milestones M1 through M9 are delivered: identity, universes and roles, Codex and Nexus, Chronicle, realtime collaboration, Atlas, Chronos, search, and import/export, plus release hardening. See `docs/IMPLEMENTATION_STATUS.md` and `docs/MILESTONE_ACCEPTANCE.md`.
