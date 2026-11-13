# WORLDWEAVE Task Tracker

All milestones M1–M9 are complete and verified. Per-milestone evidence is in `docs/MILESTONE_ACCEPTANCE.md`; module status is in `docs/IMPLEMENTATION_STATUS.md`.

## M1 — Foundation — COMPLETE
- [x] FastAPI application, settings, database, error envelope, structured logging.
- [x] Identity: registration policy, Argon2id login, revocable sessions, CSRF.
- [x] Health/readiness endpoints; Docker Compose, Caddy, Windows scripts.
- [x] `backend/tests/test_auth.py`, `test_health.py`.

## M2 — Universes & Society — COMPLETE
- [x] `Universe`, `UniverseMember`, `Invitation`, `AuditLog`, `ActivityEvent` models (migration `0002`).
- [x] `backend/core/permissions.py`: five ranked roles and the action matrix.
- [x] Tenant isolation with 404 anti-leak responses; ownership transfer; archive/unarchive.
- [x] Membership, invitations, audit logs, activity feed.
- [x] `backend/tests/test_universes.py`, `test_universe_security.py`.

## M3 — Codex & Nexus — COMPLETE
- [x] Entity types, custom fields, entities (soft delete + optimistic concurrency), tags, typed relations.
- [x] Relation type compatibility constraints; cross-universe rejection.
- [x] Nexus graph endpoint with focus node, bounded depth, and type filters.
- [x] `backend/tests/test_codex.py`, `test_codex_validation.py`, `test_codex_visibility.py`.

## M4 — Chronicle — COMPLETE
- [x] Hierarchical documents, revisions, comments, entity-link indexing (migration `0003`).
- [x] TipTap JSON validation, Markdown snapshots, WikiLinks, revision restore.
- [x] `backend/tests/test_chronicle.py`.

## M5 — Realtime Collaboration — COMPLETE
- [x] `document_collab_updates`, `document_collab_snapshots`, `collab_generation` (migration `0004`).
- [x] HMAC tickets; Yjs WebSocket protocol; commit-before-ack; snapshot compaction; awareness replay.
- [x] `backend/tests/test_collaboration.py`.

## M6 — Atlas & Chronos — COMPLETE
- [x] Maps, markers, regions, assets with SHA-256 checksums (migration `0005`).
- [x] Normalized [0,1] coordinates; markers/regions linked to Codex entities.
- [x] Custom calendar engine (variable months, leap rules, eras) with day-index conversion; timeline events.
- [x] `backend/tests/test_atlas_chronos.py`.

## M7 — Full-text Search — COMPLETE
- [x] GIN expression indexes `ix_entities_search_fts`, `ix_documents_search_fts`, `ix_timeline_events_search_fts` (migration `0006`).
- [x] Replaced non-immutable `concat_ws` indexes; query expression aligned to the index.
- [x] Unified, permission-filtered search with snippet highlighting.
- [x] `backend/tests/test_search.py`.

## M8 — Import/Export — COMPLETE
- [x] Import job ledger (migration `0007`).
- [x] Portable ZIP bundles with `manifest.json`, `universe.json`, JSON indexes, Markdown, assets, `checksums.sha256`.
- [x] Import validation (schema, checksums, path safety, references) and execution with conflict policy.
- [x] `backend/tests/test_import_export.py`.

## M9 — Release 1.0 Hardening — COMPLETE (VERIFIED)
- [x] Release E2E suite: ten scenarios (`backend/tests/test_release_e2e.py`).
- [x] Security audit suite: `18 passed` (`backend/tests/test_security_audit.py`).
- [x] Full backend suite: `115 passed`.
- [x] Realtime convergence and restart durability verified against live `uvicorn` + PostgreSQL.
- [x] Backup/restore drill verified on PostgreSQL (`pg_dump -Fc`, wipe, `pg_restore`, API integrity check).
- [x] Operational scripts extended for the media volume with SHA-256 sidecar verification.
- [x] Production web build and TypeScript typecheck pass; clean-database migration applies.
- [x] Documentation synchronized (README, guides, API, database, testing, deployment, backup/restore, traceability).

## Outstanding operator gates
- [ ] Confirm GitHub Actions CI passes on the next push against its clean PostgreSQL service.
- [ ] Run the clean start/stop/backup/restore drill on a Windows Docker Desktop host.
