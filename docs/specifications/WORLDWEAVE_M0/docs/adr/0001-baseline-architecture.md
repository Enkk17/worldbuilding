# ADR 0001 — Modular Monolith and Technology Baseline

- Status: Accepted baseline
- Date: 2026-11-10

## Context
WORLDWEAVE is a greenfield collaborative worldbuilding application. It needs a rich frontend, structured domain model, realtime document editing, and self-hosted operation. The project must remain maintainable for a small team.

## Decision
Use a modular monolith:
- React + TypeScript + Vite frontend;
- FastAPI backend;
- PostgreSQL;
- SQLAlchemy and Alembic;
- TipTap for editing;
- Yjs for document collaboration;
- Cytoscape.js for graph visualization;
- Leaflet for custom image maps;
- Docker Compose for deployment.

Redis is optional infrastructure for ephemeral coordination/cache, not a source of truth. No microservices in v1.0.

## Consequences
Positive:
- fewer operational components;
- clear domain boundaries;
- easier local development;
- simpler transactions and authorization.

Trade-offs:
- module boundaries require discipline;
- future extraction requires explicit contracts;
- a single backend release unit may eventually need scaling.

## Alternatives considered
- Microservices: rejected as premature operational complexity.
- Wiki.js as core: rejected because the product requires custom structured entities, permissions, maps, timelines, and collaborative workflows.
- Notion as data store: rejected due to platform dependency and insufficient control.
