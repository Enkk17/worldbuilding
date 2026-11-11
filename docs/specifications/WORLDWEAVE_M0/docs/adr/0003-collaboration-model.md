# ADR 0003 — CRDT Documents and Optimistic Entity Updates

- Status: Accepted baseline, implementation spike required
- Date: 2026-11-10

## Context
Multiple users must work together. Long-form documents benefit from simultaneous editing, while arbitrary structured entity forms have validation and business invariants that are not suitable for naive CRDT merging.

## Decision
- Use Yjs for Chronicle document editing.
- Persist updates and snapshots durably.
- Use application-level revisions for checkpoints and restore.
- Use optimistic concurrency for structured Codex entities.
- Use server-side permission checks for every realtime room.

## Consequences
- A maintained Yjs-compatible server implementation must be selected and proven in a spike.
- Acknowledgement must follow durable persistence.
- Realtime permission revocation and recovery are release-blocking tests.
- Entity conflicts are explicit 409 responses, not silent overwrites.
