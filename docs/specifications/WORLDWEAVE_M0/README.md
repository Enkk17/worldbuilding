# WORLDWEAVE — M0 Product & Technical Specification Pack

**Version:** 1.0  
**Status:** Baseline for implementation planning  
**Date:** 2026-11-10  
**Product:** Collaborative, self-hostable worldbuilding platform  
**Release target:** Complete v1.0 (not an MVP)  
**AI in v1.0:** Explicitly out of scope

## Purpose

This repository is the implementation baseline for WORLDWEAVE. It defines product scope, architecture, domain model, API conventions, authorization, collaboration, storage, UX, testing, deployment, and delivery gates.

Agents must read these documents before changing code. The specifications are normative unless a documented Architecture Decision Record (ADR) supersedes them.

## Product decisions

- Greenfield project; do not assume or import code from an earlier application.
- Multi-user collaboration across isolated universes.
- Fantasy editorial visual identity; usability and accessibility take priority over decorative effects.
- Complete v1.0 release target, delivered through gated milestones.
- Hybrid content storage: PostgreSQL is authoritative for structured data and document metadata/content revisions; Markdown is the portable interchange format and may be exported to a local filesystem vault.
- No AI features, AI services, vector database, embeddings, or model runtime in v1.0.
- Self-hosted deployment through Docker Compose; no mandatory external SaaS dependency.
- Modular monolith, not microservices.

## Document map

| File | Authority |
|---|---|
| `PRODUCT.md` | Product vision, personas, scope and functional requirements |
| `ARCHITECTURE.md` | System boundaries, stack, runtime and engineering rules |
| `DATABASE.md` | Domain model, invariants and data lifecycle |
| `API_SPEC.md` | API conventions and initial endpoint contract |
| `PERMISSIONS.md` | Roles, authorization and isolation rules |
| `COLLABORATION.md` | Realtime editing, revisions and conflict handling |
| `STORAGE_AND_IMPORT_EXPORT.md` | Markdown, assets, import/export and backups |
| `DESIGN_SYSTEM.md` | UX, visual identity, navigation and accessibility |
| `TEST_STRATEGY.md` | Verification strategy and release gates |
| `ROADMAP.md` | Milestones, dependencies and acceptance criteria |
| `adr/0001-baseline-architecture.md` | Accepted architectural baseline |
| `adr/0002-content-storage.md` | Hybrid storage decision |
| `adr/0003-collaboration-model.md` | Collaborative editing decision |

## Instructions for AI agents

1. Read the entire document pack before implementation.
2. Treat this pack as the baseline contract. Do not silently reinterpret requirements.
3. Do not invent endpoints, fields, permissions, or domain concepts that conflict with these specifications.
4. If a requirement is ambiguous, write a short proposal and request a decision rather than guessing.
5. Any architecture change requires an ADR with context, alternatives, decision, consequences, migration impact, and tests.
6. Keep API schemas, database migrations, frontend types, and tests aligned.
7. Never mark a milestone complete because code merely compiles. Use the acceptance criteria and attach test evidence.
8. Do not introduce AI functionality into v1.0.
9. Do not add external paid dependencies or telemetry by default.
10. Do not perform destructive database, filesystem, or Git operations without explicit authorization.

## Definition of ready

A task is ready only when it has:
- a clear user outcome;
- a module owner;
- affected API and data contracts identified;
- permission implications identified;
- acceptance criteria;
- test expectations;
- migration and rollback considerations where applicable.

## Definition of done

A task is done only when:
- implementation matches the accepted contract;
- automated tests pass;
- authorization and tenant isolation are tested where relevant;
- migrations are reversible or have a documented forward-recovery plan;
- UI states include loading, empty, error, and success;
- accessibility and responsive behavior are checked;
- documentation is updated;
- no secrets or user content are logged.
