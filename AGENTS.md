# AGENTS.md — WORLDWEAVE Autonomous Engineering

## Roles and Responsibilities
- **Senior Software Architect**: Enforces domain boundaries, PostgreSQL data model invariants, zero-trust RBAC/tenant isolation, and modular architecture.
- **Lead Developer**: Implements backend FastAPI routers, SQLAlchemy 2.0 async/sync models, Alembic migrations, frontend React components, TanStack Query hooks, and responsive UX.
- **QA Engineer**: Writes comprehensive pytest suites for auth, permissions, cross-universe isolation, optimistic concurrency, and validation; runs automated typecheck and builds.
- **Release Manager**: Tracks progress through M0–M9, maintains documentation, updates changelogs, and guarantees reproducible local deployment and backup/restore.

## Active Directives
1. Autonomous execution: no pauses for permission on planned tasks; progress milestone by milestone.
2. Complete implementation: zero mock or placeholder implementations.
3. Tenant isolation: every universe-owned record is strictly validated against its `universe_id`. No cross-universe references allowed.
4. Testing: execute and verify automated tests after every significant component.
5. Living documentation: maintain `AGENTS.md`, `WORLDWEAVE_ROADMAP.md`, `WORLDWEAVE_TASKS.md`, `docs/IMPLEMENTATION_STATUS.md`, and `WORLDWEAVE_CHANGELOG.md`.

## Milestone Roadmap Summary
- **M0**: Baseline & specifications (Completed / Frozen)
- **M1**: Foundation (Architecture, Auth, Sessions, Health, CI, Docker Compose) — Validated
- **M2**: Gestione mondi e permessi (Universes, Society, Roles, Memberships, Invitations, Audit)
- **M3**: Entità e Knowledge Graph (Codex entities, Custom Fields, Relations, Nexus Graph API & UI)
- **M4**: Editor Rich Text e cross-linking (Chronicle documents hierarchy, TipTap, WikiLinks, Comments, Revisions)
- **M5**: Collaborazione realtime (Yjs / WebSocket collaboration tickets, durable sync, snapshots)
- **M6**: Timeline e mappe (Atlas maps/markers/regions + Chronos custom calendars/eras/events)
- **M7**: Full-text Search (Unified PostgreSQL/SQLite FTS, multi-resource search UI)
- **M8**: Import/Export (Zip archive bundles, Markdown frontmatter WikiLinks, validator & execution)
- **M9**: Release 1.0 (Hardening, full regression, backup/restore drills, documentation)
