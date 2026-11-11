# ADR 0002 — Hybrid Database and Markdown Storage

- Status: Accepted baseline
- Date: 2026-11-10

## Context
Users need structured relations and collaborative editing while retaining portability and compatibility with Markdown tools such as Obsidian.

## Decision
PostgreSQL is authoritative for structured records, metadata, document revisions, and collaboration persistence. Markdown is the portable interchange/export format and an explicitly validated import path. Exported vaults may be edited externally and re-imported through a conflict-aware workflow.

## Consequences
- No two-way filesystem sync in the initial implementation.
- Markdown exports carry stable IDs in frontmatter.
- Import must validate and report conflicts before mutation.
- Notion and Wiki.js are optional future adapters, not runtime dependencies.
- User-facing export and operational backup are separate features.
