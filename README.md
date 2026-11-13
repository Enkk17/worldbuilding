# WORLDWEAVE

WORLDWEAVE is a collaborative, self-hostable workspace for building structured fictional universes. Its M0 product and technical specifications are preserved in [`docs/specifications/WORLDWEAVE_M0/`](docs/specifications/WORLDWEAVE_M0/).

## Current release status

Milestones M1 through M9 are implemented: identity and sessions, universes and roles, Codex entities and the Nexus graph, Chronicle documents with realtime collaboration, Atlas maps, Chronos calendars and timelines, unified full-text search, portable import/export, and release hardening. See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) and [`docs/MILESTONE_ACCEPTANCE.md`](docs/MILESTONE_ACCEPTANCE.md). The default Compose configuration targets local loopback use, not a hardened public deployment.

## Run on Windows 10/11

1. Install Docker Desktop and wait until it reports that the engine is running.
2. Extract this repository to `K:\WORLDWEAVE_M0` (or another local folder).
3. Open PowerShell in that folder and run:

   ```powershell
   .\Avvia-WORLDWEAVE.ps1
   ```

   The script creates a private `.env` file with a random database password when needed, starts the containers, waits for the API readiness check, and opens `http://localhost:8080`.
4. Register the first account. By default, registration is then limited to that initial account (`REGISTRATION_MODE=bootstrap_only`).

Stop the app with `.\Ferma-WORLDWEAVE.ps1`. This does not delete the database volume. Create a database and media backup with `.\Backup-WORLDWEAVE.ps1`. Restore with `.\Ripristina-WORLDWEAVE.ps1 .\backups\<file>.dump .\backups\<media>.tar`; restore verifies the SHA-256 sidecars, requires typing `RESTORE WORLDWEAVE`, and replaces the current database. See [`docs/BACKUP_RESTORE.md`](docs/BACKUP_RESTORE.md).

## Development checks

```bash
pnpm install --frozen-lockfile
pnpm run typecheck
uv sync --locked
uv run --locked python -m pytest
```

The API uses PostgreSQL through `DATABASE_URL`; local development can use the Docker Compose database or another PostgreSQL instance. `uv.lock` and `pnpm-lock.yaml` pin resolved dependencies.

## Architecture and operations

- [Architecture](docs/ARCHITECTURE.md)
- [Database](docs/DATABASE.md)
- [API](docs/API.md)
- [Security](docs/SECURITY.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Backup and restore](docs/BACKUP_RESTORE.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Requirements traceability](docs/REQUIREMENTS_TRACEABILITY.md)
- [Milestone acceptance](docs/MILESTONE_ACCEPTANCE.md)

## Fonts

The interface bundles Instrument Serif, DM Sans, and DM Mono locally through Fontsource. The app does not need an external font CDN to render its typography.
