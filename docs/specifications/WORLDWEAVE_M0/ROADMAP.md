# Roadmap and Milestone Acceptance

## Delivery strategy

Target is a complete v1.0, not an MVP. Deliver incrementally with hard gates. Do not start dependent modules before their contracts stabilize.

## M0 — Product and architecture baseline
Deliver:
- approved product scope;
- architecture and domain boundaries;
- initial schema and API contract;
- authorization model;
- collaboration/storage decisions;
- design direction;
- test and release strategy;
- ADRs.

Acceptance:
- all documents reviewed;
- contradictions resolved;
- unresolved decisions listed with owner and due milestone;
- agents can derive bounded implementation tasks without inventing core contracts.

## M1 — Foundation
Deliver:
- monorepo;
- local development setup;
- Docker Compose;
- React shell and FastAPI app;
- PostgreSQL and Alembic;
- CI;
- auth/session baseline;
- health/readiness endpoints;
- structured logs.

Acceptance:
- clean clone can start using documented steps;
- migrations run from empty database;
- CI passes;
- session lifecycle works;
- no secret committed.

## M2 — Design system and application shell
Deliver:
- fantasy design tokens;
- dark and light themes;
- responsive shell;
- navigation;
- command palette;
- common components;
- UI state patterns.

Acceptance:
- visual QA at desktop, tablet, mobile;
- keyboard navigation;
- reduced motion;
- accessible contrast;
- no core route is a dead end.

## M3 — Universe and Society
Deliver:
- universe CRUD;
- memberships;
- invitations;
- roles;
- authorization middleware/policies;
- audit trail;
- resource visibility.

Acceptance:
- all role matrix tests pass;
- cross-universe isolation tests pass;
- invitation expiry/reuse tests pass.

## M4 — Codex
Deliver:
- entity type schemas;
- entity CRUD;
- custom fields;
- tags;
- relation types and relations;
- entity detail pages;
- optimistic concurrency;
- revision history.

Acceptance:
- custom type can be configured without code changes;
- relation constraints enforced;
- stale update returns conflict;
- no cross-universe relation can be created.

## M5 — Chronicle
Deliver:
- document hierarchy;
- TipTap editor;
- entity linking;
- comments;
- revision history;
- Markdown serializer/importer;
- safe rendering.

Acceptance:
- documents round-trip through supported Markdown subset;
- entity links preserve IDs;
- XSS tests pass;
- revision restore preserves history.

## M6 — Nexus
Deliver:
- graph API;
- Cytoscape UI;
- filters;
- focus and bounded depth;
- navigation to entities.

Acceptance:
- graph respects permissions;
- large graphs are bounded/paginated or neighborhood-loaded;
- keyboard/search alternative exists.

## M7 — Atlas and Chronos
Deliver:
- map upload and image-coordinate system;
- markers and regions;
- custom calendar service;
- eras and timeline events;
- filters and linked entities.

Acceptance:
- marker position invariant under zoom/resizing;
- custom calendar tests pass;
- calendar changes do not silently reinterpret dates;
- linked records remain tenant-safe.

## M8 — Realtime collaboration
Deliver:
- Yjs server integration;
- connection tickets;
- room authorization;
- presence;
- durable update persistence;
- snapshot compaction;
- concurrent editing and reconnect UX.

Acceptance:
- two-client convergence tests pass;
- acknowledged updates survive restart;
- permission revocation blocks further writes;
- no unbounded update log.

## M9 — Release hardening
Deliver:
- full regression;
- security review;
- import/export packaging;
- operational backup and restore;
- deployment documentation;
- user guide;
- admin guide;
- release notes.

Acceptance:
- complete E2E suite passes;
- restore drill passes;
- clean deployment succeeds;
- no critical/high unresolved defects;
- all in-scope FR/NFR requirements verified.

## Dependency graph

M0 → M1 → M2  
M1 → M3 → M4 → M6  
M3 → M5 → M8  
M4 → M7  
M3 + M5 → M8  
M2 + M3 + M4 + M5 + M6 + M7 + M8 → M9

M4 and M5 may overlap once M3 and shared API/data conventions are stable. M6 and M7 may overlap after M4 contracts stabilize.

## Change control

Any change to scope, data model, API contract, permission model, or collaboration persistence requires:
1. written change proposal;
2. impact analysis;
3. ADR update where architectural;
4. migration and compatibility plan;
5. approval by product owner;
6. tests updated before implementation is considered complete.
