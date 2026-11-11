# Administrator Guide

## Initial administrator account

The first account created in a fresh database is the bootstrap account. M1 has no universe roles or member-management UI yet; those arrive with the Universe & Society milestone.

## Registration policy

Set `REGISTRATION_MODE` in `.env`:

- `bootstrap_only` (default): permit only the first account; use this for a private installation.
- `open`: permit ongoing self-registration.
- `closed`: disable self-registration.

After changing `.env`, restart with `docker compose up -d --force-recreate api`. Keep the `.env` file private.

## Service checks

- `http://localhost:8080/api/healthz` confirms that the API process is running.
- `http://localhost:8080/api/readyz` confirms that PostgreSQL is reachable.
- `docker compose ps` shows container status.
- `docker compose logs --tail 100 api` and `docker compose logs --tail 100 db` show service logs. API logs do not include request bodies or credentials.

Account recovery, invitation management, audit review, and multi-user role controls are not yet available in M1.
