# Milestone Acceptance

No milestone is complete based on planned work alone. Update each item only with evidence from an actual run.

## M0 — Product and architecture baseline

- [x] Supplied M0 documentation and all three ADRs reviewed.
- [x] Source specification pack retained under `docs/specifications/WORLDWEAVE_M0/`.
- [x] Architecture remains modular monolith; no AI features or external SaaS requirement added.

## M1 — Foundation

- [x] React/Vite account access and first-run account landing implemented.
- [x] FastAPI auth/health contract and generated client implemented.
- [x] PostgreSQL SQLAlchemy models and Alembic migration authored.
- [x] Docker Compose and Windows operation scripts authored.
- [x] Python auth, session, error-envelope, security, and health tests pass (13 tests).
- [x] Workspace TypeScript typecheck passes.
- [x] Web production build passes.
- [x] Alembic migration applies to the development PostgreSQL database from the pre-M1 state.
- [x] API health/readiness verified against the running service (both returned HTTP 200).
- [x] Docker Compose syntax validates.
- [ ] GitHub Actions CI completes successfully, including migration against its clean PostgreSQL service.
- [ ] Docker Desktop clean start, stop-with-data-preserved, backup, and restore drill completed.
- [x] M1 documentation and requirement evidence updated with current verification results and remaining gates.

## M2–M5

Milestones M2 through M9 are recorded in `docs/IMPLEMENTATION_STATUS.md` and `WORLDWEAVE_ROADMAP.md`. Their per-milestone test suites are `test_universes.py`, `test_universe_security.py`, `test_codex*.py`, `test_chronicle.py`, and `test_collaboration.py`. The evidence below was produced by actual runs, not by planning.

## M6 — Atlas & Chronos

- [x] Migration `0005_atlas_chronos_m6` applies to a clean PostgreSQL database.
- [x] Asset upload stores SHA-256 checksums; spoofed MIME types are rejected by content inspection.
- [x] Marker coordinates stay in normalized [0,1] after map dimensions change.
- [x] Custom calendar sorts events by continuous day index.
- [x] `backend/tests/test_atlas_chronos.py` passes.

## M7 — Full-text Search

- [x] Migration `0006_search_m7` applies to a clean PostgreSQL database.
- [x] GIN expression indexes `ix_entities_search_fts`, `ix_documents_search_fts`, and `ix_timeline_events_search_fts` exist after migration.
- [x] The earlier `concat_ws` expression indexes were replaced because `concat_ws` is `STABLE`, not `IMMUTABLE`, and the migration failed on PostgreSQL.
- [x] `EXPLAIN` confirms the service query uses `ix_entities_search_fts` (Bitmap Heap Scan).
- [x] `backend/tests/test_search.py` passes; search results are permission-filtered.

## M8 — Import/Export

- [x] Migration `0007_import_export_m8` applies to a clean PostgreSQL database.
- [x] Export bundle contains `manifest.json`, `universe.json`, `checksums.sha256`, JSON indexes, and per-record Markdown.
- [x] Bundle checksums verify against the archive contents.
- [x] Import round-trip into a clean universe preserves relations without broken links.
- [x] `backend/tests/test_import_export.py` and `backend/tests/test_release_e2e.py` pass.

## M9 — Release 1.0 Hardening

- [x] Full backend suite passes: `115 passed` (`uv run --locked python -m pytest`).
- [x] Release E2E suite passes: ten scenarios in `backend/tests/test_release_e2e.py`.
- [x] Security audit suite passes: `18 passed` in `backend/tests/test_security_audit.py`.
- [x] Realtime convergence verified between two independent WebSocket clients against a live `uvicorn` server on PostgreSQL.
- [x] Durability verified: an acknowledged update survived a full server restart.
- [x] Backup/restore drill executed against PostgreSQL: `pg_dump -Fc`, database wipe, `pg_restore --exit-on-error`, and API-level verification of restored rows (`3` entities, `1` document, content intact).
- [x] Operational scripts extended to back up and restore the media asset volume with SHA-256 sidecar verification.
- [x] TypeScript workspace typecheck passes (`pnpm run typecheck`).
- [x] Production web build passes (`pnpm --filter @workspace/worldweave run build`).
- [x] `docker compose config --quiet` validates.
- [x] Clean-database migration applies and `alembic current` reports `0007_import_export_m8 (head)`.
- [ ] GitHub Actions CI completed successfully against its clean PostgreSQL service. (Workflow is defined; confirm on the next push.)
- [ ] Docker Desktop clean start/stop/backup/restore on Windows. (Scripts are authored and the drill was executed against PostgreSQL; the Windows-host run remains an operator gate.)
