# Backup and Restore

## Current M1 coverage

M1 stores only identity and session data in PostgreSQL. `.\Backup-WORLDWEAVE.ps1` creates a PostgreSQL custom-format dump under `backups/` and writes a SHA-256 sidecar file. Keep both files protected; database backups contain user data.

```powershell
.\Backup-WORLDWEAVE.ps1
```

To restore, stop writes by using the provided script, which stops the API, requires a typed confirmation, restores the selected dump with `pg_restore --clean`, then restarts the API:

```powershell
.\Ripristina-WORLDWEAVE.ps1 .\backups\worldweave-YYYYMMDD-HHMMSS.dump
```

**Restore replaces the current database.** Make a fresh backup first and verify the selected file and checksum before proceeding. Do not use a dump from an untrusted source.

## Important limitation

There are no user-uploaded assets in M1, so the current backup covers the database only. Before M9, the backup/restore procedure must include binary asset storage, retention and encryption guidance, a clean-host restore drill, integrity checks, and documented recovery targets. User-facing Markdown export is separate and is not an operational backup.
