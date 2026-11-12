# WORLDWEAVE Task Tracker

## Milestone M2: Gestione Mondi e Permessi (Universes & Society) — COMPLETE

### M2 Tasks Breakdown
- [x] **M2.1 Data Models & Schemas**
  - [x] Add `Universe`, `UniverseMember`, `Invitation`, `AuditLog`, `ActivityEvent` models in `backend/core/models.py`.
  - [x] Add Alembic migration `0002_core_worldweave.py` for universe & membership tables.
  - [x] Define Pydantic request & response schemas in `backend/modules/universes/schemas.py`.
- [x] **M2.2 Authorization & RBAC Policies**
  - [x] Implement `backend/core/permissions.py` with roles (`owner`, `admin`, `editor`, `contributor`, `viewer`) and actions.
  - [x] Implement permission matrix and hierarchical management authority (`can_manage_member`).
  - [x] Implement cross-universe tenant protection (`check_universe_access`, 404 anti-leak responses).
- [x] **M2.3 Service & Endpoints Implementation**
  - [x] Universe CRUD: `GET /api/v1/universes`, `POST /api/v1/universes`, `GET /api/v1/universes/{id}`, `PATCH /api/v1/universes/{id}`, `POST /api/v1/universes/{id}/archive`.
  - [x] Member management: `GET /api/v1/universes/{id}/members`, `PATCH /api/v1/universes/{id}/members/{user_id}`, `DELETE /api/v1/universes/{id}/members/{user_id}`.
  - [x] Invitations: `POST /api/v1/universes/{id}/invitations`, `POST /api/v1/invitations/{token}/accept`.
  - [x] Audit logs: `GET /api/v1/universes/{id}/audit-logs`.
  - [x] Activity events: `GET /api/v1/universes/{id}/activity`.
- [x] **M2.4 Automated Testing**
  - [x] Test universe creation, listing, updating, slug uniqueness, and archiving.
  - [x] Test role matrix: Owner vs Admin vs Editor vs Contributor vs Viewer.
  - [x] Test cross-universe isolation (attempting access with non-member session).
  - [x] Test invitation generation, expiration, acceptance, and duplicate rejection.
  - [x] Test audit trail creation on universe mutation and member role changes.
  - [x] 17 pytest tests pass with 0 failures.
- [x] **M2.5 Frontend Integration**
  - [x] Updated OpenAPI contract in `lib/api-spec/openapi.yaml` and generated Orval hooks.
  - [x] Added Universe cards, "+ New Universe" creation form in `AccountHome`.
  - [x] Implemented comprehensive `UniverseDetail.tsx` page with Overview, Society & Members, Audit Trail, and Settings tabs.
  - [x] Frontend builds cleanly (`vite build` in 6.27s) and passes `tsc` typecheck.

---

## Current Focus: M3 — Entità e Knowledge Graph (Codex & Nexus)

### M3 Tasks Breakdown
- [ ] **M3.1 Codex Schemas & System Seed Types**
  - [ ] Add system default entity types (Characters, Places, Peoples, Organizations, Creatures, Items, Religions, Magic Systems, Technologies, Concepts).
  - [ ] Support custom field schema definitions (text, long_text, number, boolean, date, enum, multi_enum, URL, entity reference).
- [ ] **M3.2 Codex Backend Service & Routers**
  - [ ] `GET/POST /api/v1/universes/{id}/entity-types`
  - [ ] `PATCH /api/v1/universes/{id}/entity-types/{type_id}`
  - [ ] `GET/POST /api/v1/universes/{id}/entities` (with filters, pagination, optimistic locking `version`)
  - [ ] `GET/PATCH/DELETE /api/v1/universes/{id}/entities/{entity_id}` (soft-delete with `deleted_at`, optimistic locking conflict 409)
  - [ ] `POST /api/v1/universes/{id}/entities/{entity_id}/restore`
  - [ ] Directed relations: `POST /api/v1/universes/{id}/relations`, `DELETE /api/v1/universes/{id}/relations/{relation_id}`, `GET /api/v1/universes/{id}/entities/{entity_id}/relations`
  - [ ] Type compatibility validation (source and target entity types must match `allowed_source_types` / `allowed_target_types`).
- [ ] **M3.3 Nexus Graph API**
  - [ ] `GET /api/v1/universes/{id}/graph` with `focus_entity_id`, bounded `depth` (1..3), type filters, and tenant-safe scoping.
- [ ] **M3.4 Automated Testing**
  - [ ] Unit & integration tests for entity CRUD, custom fields validation, slug uniqueness per type, optimistic concurrency conflict (409), soft delete and restore.
  - [ ] Relation constraint enforcement (reject cross-universe relations, reject incompatible entity types).
  - [ ] Graph query filtering and depth traversal tests.
- [ ] **M3.5 Frontend Codex & Nexus UI**
  - [ ] Codex directory view: filter by entity type, status, tag; search bar; "+ New Entity" dialog.
  - [ ] Entity Detail page: custom fields renderer/editor, incoming & outgoing relations panel, revision history.
  - [ ] Nexus Graph view: interactive node-link graph visualization with focus, depth control, and filters.
- [ ] **M3.6 Verification & Milestone Sign-off**
  - [ ] Run backend tests.
  - [ ] Run frontend typecheck and build.

---

### Backlog: Upcoming Milestones
- **M4**: Editor Rich Text e cross-linking (Chronicle documents, TipTap, WikiLinks, comments, revisions)
- **M5**: Collaborazione realtime (Yjs collaboration tickets, WebSockets, snapshot compaction, presence)
- **M6**: Timeline e mappe (Atlas maps, markers, regions; Chronos custom calendars, eras, events)
- **M7**: Full-text Search (Unified search engine, multi-resource query, search UI)
- **M8**: Import/Export (Portable universe bundle export, schema validation, import pipeline)
- **M9**: Release 1.0 (Hardening, full regression, operational backup/restore drills, final release)
