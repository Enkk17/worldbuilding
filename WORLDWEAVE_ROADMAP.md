# WORLDWEAVE Master Roadmap (M0–M9)

## Strategy
Deliver a complete v1.0 self-hostable collaborative worldbuilding platform adhering to `docs/specifications/WORLDWEAVE_M0/`.
No mocks, no placeholders. Hard quality gates between milestones.

---

### M0: Baseline e specifiche
- **Deliverables**: Product specifications, Database schema, API specification, Permissions matrix, Collaboration ADR, Design system tokens, Test strategy.
- **Status**: **COMPLETE (VERIFIED)**. Specifications preserved in `docs/specifications/WORLDWEAVE_M0/`.

---

### M1: Foundation
- **Deliverables**:
  - FastAPI modular application core (`backend/core`, `backend/modules/identity`).
  - PostgreSQL database engine + SQLite compatibility for tests.
  - Argon2id password hashing + session management with cryptographic hashing.
  - Alembic migrations framework (`backend/migrations`).
  - Auth endpoints (`/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`).
  - Health & readiness endpoints (`/healthz`, `/readyz`).
  - Structured JSON logging with request IDs and security headers.
  - Windows operational scripts (`Avvia-WORLDWEAVE.ps1`, `Ferma-WORLDWEAVE.ps1`, `Backup-WORLDWEAVE.ps1`, `Ripristina-WORLDWEAVE.ps1`).
  - Automated test suite (13 passing pytest tests).
- **Status**: **COMPLETE (VERIFIED)**.

---

### M2: Gestione mondi e permessi (Universes & Society)
- **Deliverables**:
  - Universe schema (`universes`, `universe_members`, `invitations`, `audit_logs`).
  - Universe CRUD endpoints (`GET/POST /universes`, `GET/PATCH /universes/{id}`, `POST /universes/{id}/archive`).
  - Society & Membership management (`GET /universes/{id}/members`, `PATCH/DELETE /universes/{id}/members/{user_id}`).
  - Invitations system (`POST /universes/{id}/invitations`, `POST /invitations/{token}/accept`).
  - Role-Based Access Control (Owner, Administrator, Editor, Contributor, Viewer) + authorization dependency.
  - Cross-universe access isolation checks.
  - Audit logging of membership, roles, and universe settings changes.
  - Frontend Universe switcher, Universe creation modal, Universe settings, and Society management dashboard.
- **Status**: **COMPLETE (VERIFIED)**. Hardened with CSRF enforcement, email-bound invitations, archived-universe read-only mode, owner transfer, and SHA-256 audit hashes.

---

### M3: Entità e Knowledge Graph (Codex & Nexus)
- **Deliverables**:
  - Codex schema: `entity_types`, `entities`, `relation_types`, `entity_relations`, `tags`, `entity_tags`.
  - Default system entity types (Characters, Places, Peoples, Organizations, Creatures, Items, Religions, Magic Systems, Technologies, Concepts).
  - Custom field schemas (text, long_text, number, boolean, date, enum, multi_enum, URL, entity reference).
  - Entity CRUD with slugs and optimistic concurrency (`version` checks, conflict 409).
  - Soft deletion and restoration (`POST .../restore`).
  - Directed typed relations with type constraint validation (allowed source/target types) and inverse labels.
  - Nexus Graph API (`GET /universes/{id}/graph`) with focus node, depth bounds (1..3), type filters, and tenant-safe scoping.
  - Frontend Codex directory, Entity detail views, Custom fields editor, and Nexus interactive Graph visualizer.
- **Status**: **COMPLETE (VERIFIED)**. Shared visibility policy, filters, custom-field validation, graph depth bounds, and tenant isolation covered by tests.

---

### M4: Editor Rich Text e cross-linking (Chronicle)
- **Deliverables**:
  - Chronicle schema: `documents`, `document_revisions`, `document_entity_links`, `comments`.
  - Hierarchical document structure (Collections, Works, Parts, Chapters, Scenes, Notes).
  - TipTap rich text schema, Markdown serializer/deserializer roundtrip.
  - Canonical Entity mentions (`document_entity_links`) resolving to immutable entity IDs.
  - Revision history tracking and revision restore endpoint (`POST .../restore/{revision_id}`).
  - Inline and document-level comments (`POST/GET .../comments`).
  - Frontend Chronicle navigation tree, TipTap rich text editor, entity auto-complete mention plugin, comments sidebar.
- **Status**: **COMPLETE (VERIFIED)**. Migration `0003_chronicle_m4`; canonical TipTap JSON, bounded node vocabulary, SHA-backed revisions, Markdown snapshots, WikiLinks, recursive soft delete, and restore-as-new-revision.

---

### M5: Collaborazione realtime
- **Deliverables**:
  - Realtime collaboration schema: `document_collab_snapshots`, `document_collab_updates`.
  - Ticket issuance endpoint (`GET .../collaboration-ticket`) with short-lived cryptographically signed token.
  - WebSocket collaboration endpoint (`WS /api/v1/collaboration/documents/{document_id}`).
  - Yjs durable update storage, state vector exchanges, and periodic snapshot compaction.
  - Ephemeral presence awareness (cursors, active user indicators).
  - Disconnect/reconnect handling and write permissions enforcement.
  - Frontend Yjs provider integration with TipTap editor.
- **Status**: **COMPLETE (VERIFIED)**. Migration `0004_collaboration_m5`; HMAC tickets bound to user/session/universe/document/generation, durable commit-before-ack, server-side TipTap projection, guarded compaction, awareness replay, and live permission revocation. **Operational limit**: the room manager is in-process, so the deployment must run a single API worker until sticky routing or pub/sub is introduced.

---

### M6: Timeline e mappe (Atlas & Chronos)
- **Deliverables**:
  - Atlas schema: `maps`, `map_markers`, `map_regions`, `assets`.
  - Asset upload and storage for map backgrounds with SHA256 checksums.
  - Normalized coordinate system [0, 1] invariant to viewport/scaling.
  - Map markers CRUD linked to Codex entities, categories, and styling.
  - Map regions polygon overlays.
  - Chronos schema: `calendars`, `eras`, `timeline_events`.
  - Custom calendar engine: variable months, days per month, leap rules, weekdays, eras.
  - Conversion between calendar dates and continuous internal day index.
  - Timeline events CRUD with exact and approximate dates, links to entities/documents.
  - Frontend interactive Atlas viewer (pan/zoom, markers, popups) and Chronos timeline visualizer.
- **Status**: **QUEUED**.

---

### M7: Full-text Search
- **Deliverables**:
  - PostgreSQL `tsvector` + `to_tsquery` indexing (with fallback SQL `LIKE` / token matching for test environments).
  - Multi-resource search covering Codex Entities, Chronicle Documents, and Chronos Events.
  - Unified search endpoint (`GET /universes/{id}/search?q=...&types=...`).
  - Highlighting / snippet extraction and permission filtering.
  - Frontend Command Palette (`Ctrl+K` / `Cmd+K`) and dedicated search page with type filters.
- **Status**: **QUEUED**.

---

### M8: Import/Export
- **Deliverables**:
  - Export package specification: ZIP bundle containing `manifest.json`, universe metadata, entity schemas, JSON records, markdown documents with YAML frontmatter and WikiLinks, and media assets.
  - Export creation endpoint (`POST /universes/{id}/exports`) generating downloadable bundle.
  - Import validation endpoint (`POST /imports/validate`) validating schema, version, reference integrity, and reporting conflicts.
  - Import execution endpoint (`POST /universes/{id}/imports`) restoring entities, relations, documents, maps, and calendars while preserving IDs.
  - Frontend Export modal and Import wizard with validation review.
- **Status**: **QUEUED**.

---

### M9: Release 1.0 Hardening
- **Deliverables**:
  - Full automated end-to-end regression test suite.
  - Cross-universe security audit tests.
  - Backup and restore drill verification.
  - Updated User Guide, Administrator Guide, and API documentation.
  - Production build verification and release package sign-off.
- **Status**: **QUEUED**.
