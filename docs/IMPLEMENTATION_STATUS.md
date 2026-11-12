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

## M6–M9
- **Status**: IN PROGRESS (M6 Atlas & Chronos).
