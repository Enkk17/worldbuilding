# Backup and Restore

## What a backup contains

WORLDWEAVE keeps its state in two places:

- **PostgreSQL** (named volume `worldweave_postgres`): all relational data, including universes, members, Codex entities and relations, Chronicle documents and revisions, Atlas maps, Chronos calendars and events, import jobs, and the realtime update/snapshot logs.
- **Media assets** (named volume `worldweave_media`, mounted at `MEDIA_ROOT`): user-uploaded images and files referenced by the database.

A complete backup covers both. A database dump alone is not sufficient once assets exist.

## Creating a backup

Run the backup script from the repository root:

```powershell
.\Backup-WORLDWEAVE.ps1
```

The script writes both artifacts under `backups/` with a shared timestamp, and a SHA-256 sidecar next to each:

- `backups\worldweave-YYYYMMDD-HHMMSS.dump` — PostgreSQL custom-format dump (`pg_dump -Fc`).
- `backups\worldweave-media-YYYYMMDD-HHMMSS.tar` — the media volume archive.
- `*.sha256` — SHA-256 sidecars for each artifact.

The media root is read from `MEDIA_ROOT` in `.env` (default `/var/lib/worldweave/media`).

## Restoring

Stop writes, then run the restore script with the dump and, optionally, the media archive:

```powershell
.\Ripristina-WORLDWEAVE.ps1 .\backups\worldweave-YYYYMMDD-HHMMSS.dump `
  .\backups\worldweave-media-YYYYMMDD-HHMMSS.tar
```

The script verifies each artifact against its SHA-256 sidecar (and refuses to restore on a mismatch), warns that the current database is replaced, requires the typed confirmation `RESTORE WORLDWEAVE`, stops the API, restores the database with `pg_restore --clean --if-exists --exit-on-error`, restores the media volume when supplied, then restarts the API.

**Restore replaces the current database.** Make a fresh backup first, verify the selected files and checksums, and never use a dump from an untrusted source.

## Recovery targets

- **RPO** (maximum acceptable data loss): the interval between backups. Schedule backups at least daily for active use.
- **RTO** (maximum acceptable downtime): the time to run the restore script plus a verification pass; typically a few minutes for a single-host deployment.

Document your actual schedule and measured restore time for your deployment.

## Encryption and retention

- Store backups on encrypted media and restrict access; a dump contains all user data.
- Keep several generations and at least one off-host copy.
- Test a restore periodically; an untested backup is not a backup.

## Verified drill

The restore procedure was exercised against PostgreSQL: seed a database, `pg_dump -Fc`, drop and recreate the database, `pg_restore --exit-on-error`, then verify through the API that the restored universe, entities, and document content were intact (`3` entities and `1` document with its text restored). The media volume archive and its checksum sidecar follow the same pattern.

The seed step uses `backend/tests/seed_backup_drill.py`, which writes a small dataset through the real service layer:

```bash
DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/worldweave" \
  uv run --locked python -m backend.tests.seed_backup_drill
```

The script is idempotent: it registers the drill account on first run and signs in on later runs.

## Note on Markdown export

The user-facing Markdown export (Milestone 8) is a portability feature, not an operational backup. It does not capture sessions, audit logs, or the realtime update log. Use the database and media backups for recovery.
