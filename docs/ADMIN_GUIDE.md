# Administrator Guide

## Initial administrator account

The first account created in a fresh database is the bootstrap account. Within a universe, the creator is the owner and can grant the `admin` role to other members. Only an owner can transfer ownership.

## Registration policy

Set `REGISTRATION_MODE` in `.env`:

- `bootstrap_only` (default): permit only the first account; use this for a private installation.
- `open`: permit ongoing self-registration.
- `closed`: disable self-registration.

After changing `.env`, restart with `docker compose up -d --force-recreate api`. Keep the `.env` file private.

## Members, roles, and invitations

Manage members from a universe's Society tab or the membership endpoints. The five roles and their capabilities are described in `docs/USER_GUIDE.md`; the authoritative permission matrix is in `backend/core/permissions.py`.

- Invite members by email and role. Invitations are bound to the invited address and can be revoked before acceptance.
- An actor cannot change the role of, or remove, a peer or a superior.
- The owner cannot be removed; transfer ownership explicitly instead.
- Deleting a universe is a separate, higher-risk action than archiving it.

## Audit and activity

Read the universe activity feed and audit log through the API (`/activity`, `/audit-logs`) or the administration views. The audit log records membership, ownership, and content changes.

## Service checks

- `http://localhost:8080/api/healthz` confirms that the API process is running.
- `http://localhost:8080/api/readyz` confirms that PostgreSQL is reachable.
- `docker compose ps` shows container status.
- `docker compose logs --tail 100 api` and `docker compose logs --tail 100 db` show service logs. API logs do not include request bodies or credentials.

## Backup and recovery

Backups cover both the PostgreSQL database and the media asset volume. See `docs/BACKUP_RESTORE.md` for the procedures, the checksum sidecars, and the verified restore drill.

## Operational limits

- Run a single API worker. The rate limiter and the realtime room manager keep state in-process; multiple workers require shared state (external rate-limit store, sticky routing, or pub/sub).
- The default Compose configuration binds to loopback. Review `docs/DEPLOYMENT.md` before exposing the service publicly.
