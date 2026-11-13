# Implementation Status

Updated: 2026-11-12

## M0 — Baseline
- **Status**: COMPLETE & FROZEN.
- Evidence: All M0 specifications preserved in `docs/specifications/WORLDWEAVE_M0/`.

## M1 — Foundation
- **Status**: COMPLETE & VERIFIED.
- React/Vite artifact and account-entry screens: implemented and verified.
- FastAPI core, account/session models, Argon2id, revocable hashed sessions, CSRF checks, health & readiness endpoints, structured logging: implemented and verified.
- Docker Compose and Windows start/stop/backup/restore scripts: operational.
- Automated auth/security tests pass.

## M2 — Gestione Mondi e Permessi (Universes & Society)
- **Status**: COMPLETE & VERIFIED.
- Relational schema and Alembic migration `0002_core_worldweave.py`.
- Universe CRUD, archiving, Society & Memberships, hierarchical RBAC (`owner`, `admin`, `editor`, `contributor`, `viewer`), invitations, audit logs, and activity feed.
- Hardened with CSRF enforcement on unsafe methods, email-bound invitations, archived-universe read-only enforcement, owner transfer, and SHA-256 audit hashes.
- Anti-leak cross-universe tenant protection (404 on unpermitted universe access).
- Frontend Universe list, creation modal, and `UniverseDetail` multi-tab interface.

## M3 — Entità e Knowledge Graph (Codex & Nexus)
- **Status**: COMPLETE & VERIFIED.
- Entity types (10 system seeds), custom-field schemas, entities with slugs and optimistic concurrency, soft delete/restore, typed relations with source/target constraints, and tenant-safe Nexus graph query (depth 1–3).
- Shared visibility policy in `backend/core/visibility.py`: privileged roles see all; contributors see universe/restricted/draft plus their own private records; viewers see universe records and their own private records.
- Frontend Codex directory, entity detail panel, custom fields, relation management, and Nexus graph visualizer.
- Covered by pytest suites for CRUD, validation, permissions, concurrency, and cross-universe isolation.

## M4 — Editor Rich Text e cross-linking (Chronicle)
- **Status**: COMPLETE & VERIFIED.
- Migration `0003_chronicle_m4`; hierarchical documents, revisions, comments, and entity-link indexing.
- Canonical TipTap JSON with bounded node vocabulary; Markdown serializer; `[[Label|ww:UUID]]` WikiLinks; SHA-backed revisions; atomic optimistic updates; recursive soft delete; restore-as-new-revision.
- Frontend Chronicle tree, TipTap editor, entity mention picker, comments, and revision history.

## M5 — Collaborazione realtime
- **Status**: COMPLETE & VERIFIED.
- Migration `0004_collaboration_m5`; `document_collab_snapshots` and ordered `document_collab_updates`.
- HMAC-SHA256 tickets (`wwc1`) bound to user, session, universe, document, and `collab_generation`; short TTL.
- Custom Yjs WebSocket protocol with commit-before-ack durability, per-message authorization, read-only rejection, server-side TipTap JSON materialization, checkpoint revisions, verified snapshot compaction, and awareness replay.
- Revision restore and invalid CRDT projections reset the generation; stale tickets are rejected with close code `4001`.
- Frontend provider (`collaboration-provider.ts`) with ticket fetch per connection, sync/awareness protocols, durable acknowledgements, heartbeat, exponential reconnect, and editor rebuild on reset.
- REST content edits are rejected with `409 collaboration_content_conflict` once collaboration state exists; metadata edits retain optimistic concurrency.
- Regression suite `backend/tests/test_collaboration.py` covers conversion fixtures, tickets, durability, permissions, tenant isolation, compaction, idle recovery, revocation, REST guard, generation reset, and awareness replay.
- **Operational limit**: the room manager is in-process. Run a single API worker until sticky room routing or external pub/sub is implemented.

## M6 — Timeline e mappe (Atlas & Chronos)
- **Status**: COMPLETE & VERIFIED.
- Migration `0005_atlas_chronos_m6`; maps, markers, regions, and assets with SHA-256 checksums.
- Normalized [0,1] marker coordinates are independent of map dimensions; markers and regions link to Codex entities.
- Custom calendar engine: variable months, days per month, leap rules, weekdays, eras, and conversion between calendar dates and a continuous day index.
- Timeline events with exact/approximate dates and links to entities and documents.
- Frontend Atlas viewer (pan/zoom, markers, regions) and Chronos timeline visualizer.

## M7 — Full-text Search
- **Status**: COMPLETE & VERIFIED.
- Migration `0006_search_m7`; GIN expression indexes for entities, documents, and timeline events.
- The index expressions use immutable `coalesce`/`||` concatenations over `::text`; the previous `concat_ws` form is `STABLE`, not `IMMUTABLE`, and failed to apply on PostgreSQL.
- Unified, permission-filtered search across entities, documents, and events with snippet highlighting.
- The service query expression matches the index expression, so `EXPLAIN` confirms `ix_entities_search_fts` is used (Bitmap Heap Scan).
- Frontend Ctrl/⌘K command palette in the Universe workspace.

## M8 — Import/Export
- **Status**: COMPLETE & VERIFIED.
- Migration `0007_import_export_m8`; portable ZIP bundles: `entities/{type_key}/{slug}.md`, `documents/{document_type}/{slug}.md`, `assets/{asset_id}{suffix}`, JSON indexes, `manifest.json`, `universe.json`, and `checksums.sha256`.
- Import validates schema version, checksums, archive path safety, and reference integrity, then restores entities, relations, documents, maps, markers, regions, and calendars with a configurable conflict policy. Import requires an elevated role.

## M9 — Release 1.0 Hardening
- **Status**: COMPLETE & VERIFIED.
- Release E2E suite (`backend/tests/test_release_e2e.py`) covers the ten release scenarios: role roster, viewer mutation rejection, contributor-to-editor review, two-editor realtime convergence, restart durability, viewport-invariant marker links, custom-calendar ordering, Nexus visibility, export/import round-trip, and integrity-verifiable bundles.
- Security audit suite (`backend/tests/test_security_audit.py`) covers unauthenticated access, session revocation, cross-universe id substitution, search/graph leakage, role escalation, viewer mutation, room authorization, upload path/MIME/size safety, stored-XSS link and node rejection, CSRF, invitation binding, and import safety.
- Backup/restore drill executed against PostgreSQL: `pg_dump -Fc`, database wipe, `pg_restore`, and API-level integrity verification of restored rows.
- Operational scripts back up and restore the media asset volume alongside the database, with SHA-256 sidecar verification.
- Production web build and TypeScript typecheck pass; clean-database migrations apply with FTS indexes present.
