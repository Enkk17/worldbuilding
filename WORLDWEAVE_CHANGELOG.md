# WORLDWEAVE Changelog

All notable changes, architectural decisions, and verification records for WORLDWEAVE.

## [Unreleased] - 2026-11-12

### Milestone M5: Collaborazione realtime
- Added `document_collab_snapshots`, ordered `document_collab_updates`, and `documents.collab_generation` (migration `0004_collaboration_m5`).
- Implemented HMAC-SHA256 collaboration tickets bound to user, session, universe, document, and generation with short TTL.
- Implemented a custom Yjs WebSocket protocol: sync/awareness framing, binary control channel, commit-before-ack durability, read-only write rejection, live membership revalidation, idle room shutdown, verified snapshot compaction, and awareness replay for late joiners.
- Added server-side TipTap JSON projection and checkpoint revisions; revision restore invalidates the CRDT generation and stale tickets close with `4001`.
- Guarded REST content writes with `409 collaboration_content_conflict` once collaboration state exists.
- Built the frontend Yjs provider and TipTap collaboration integration with durable status, collaborator count, reconnect, permission updates, and reset handling.
- Added 14 collaboration regression tests; full backend suite green.

### Milestone M4: Editor Rich Text e cross-linking (Chronicle)
- Added hierarchical documents, revisions, comments, and entity-link indexing (migration `0003_chronicle_m4`).
- Implemented canonical TipTap JSON validation, Markdown snapshots, SHA-backed revisions, WikiLinks (`[[Label|ww:UUID]]`), recursive soft delete, revision restore, and optimistic concurrency.
- Built the Chronicle tree, rich-text editor, entity mention picker, comments, and revision history UI.
- Added conversion fixtures for the Yjs bridge and comprehensive document/comment tests.

### Milestone M3: Entità e Knowledge Graph (Codex & Nexus)
- Implemented entity types, custom fields, entities, tags, relations, and typed relation constraints.
- Added shared visibility policy and tenant-safe filtering across list/detail/graph endpoints.
- Added Nexus graph query with focus node, bounded depth, and type filters.
- Built the Codex directory, entity detail panel, custom fields editor, relation management, and graph visualizer.
- Added tests for validation, permissions, cross-universe isolation, and optimistic concurrency.


### Milestone M2: Gestione Mondi e Permessi (Universes & Society)
- **Data Architecture**:
  - Implemented `Universe`, `UniverseMember`, `Invitation`, `AuditLog`, `ActivityEvent` models in `backend/core/models.py`.
  - Added Alembic migration `0002_core_worldweave.py` covering Universes, Society, and remaining domain models.
- **Security & Authorization**:
  - Implemented `backend/core/permissions.py` defining full 5-role RBAC (`owner`, `admin`, `editor`, `contributor`, `viewer`) and action hierarchy.
  - Added `can_manage_member` enforcement to prevent privilege escalation.
  - Enforced strict tenant isolation returning 404 for unauthorized universe lookups to prevent tenant sniffing.
- **Backend API**:
  - Implemented `backend/modules/universes` router and service with full Universe CRUD, archiving, membership listings, role updates, member removal, invitation issuance, and invitation acceptance.
  - Implemented audit trail logger and activity feed.
- **Frontend & UX**:
  - Regenerated Orval React Query client hooks from updated `lib/api-spec/openapi.yaml`.
  - Built Universe portfolio in `AccountHome` with "+ New Universe" creation workflow and role badges.
  - Created `UniverseDetail.tsx` providing Overview, Society & Member Management, Audit Log ledger, and Universe Settings.
  - Solved cross-platform build dependencies (`@rollup/rollup-win32-x64-msvc`, `@esbuild/win32-x64`, `lightningcss-win32-x64-msvc`, `@tailwindcss/oxide-win32-x64-msvc`).
- **Verification**:
  - 17 unit and integration tests passing in `backend/tests/`.
  - Full TypeScript workspace typecheck passing across all packages.
  - Production Vite bundle builds cleanly in 6.27s.

### Milestone M1: Foundation
- Validated baseline FastAPI application, session store, security headers, and health checks.
- Monorepo tooling and Python 3.13 configuration.
