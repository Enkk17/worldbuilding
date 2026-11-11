# Collaboration, Revisions, and Conflict Handling

## 1. Scope

Realtime concurrent editing is required for Chronicle documents in v1.0. Structured Codex entities use optimistic concurrency and revision history. Do not attempt to CRDT-merge arbitrary JSON entity forms in v1.0.

## 2. Document editing model

- TipTap provides the editor experience.
- Yjs provides shared CRDT document state.
- A maintained Yjs-compatible server implementation handles synchronization.
- Server checks document permission before allowing room access.
- Durable Yjs state is persisted to PostgreSQL snapshots and update records, with compaction.
- TipTap JSON snapshots are produced for application-level rendering and version history.
- Markdown is generated for portable export.

Before implementation, the team must complete a technical spike proving:
1. two browser clients can edit concurrently;
2. disconnect/reconnect converges;
3. server restart does not lose acknowledged edits;
4. unauthorized users cannot join;
5. document revisions can be restored safely;
6. the chosen Yjs server implementation is maintained and compatible with the client.

## 3. Persistence and durability

A server acknowledgement must only be sent after the update is durably accepted according to the chosen persistence strategy. Define update batching and flush guarantees explicitly. A periodic snapshot compacts older updates but must not discard data before a verified snapshot exists.

Store:
- Yjs update log;
- state vector;
- compacted snapshot;
- application-level document revision;
- actor and timestamp metadata for revisions.

Avoid unbounded update-log growth. Implement snapshot/compaction thresholds and monitoring.

## 4. Revision semantics

A revision is a named, durable checkpoint of a document state, not every keystroke.

Create revisions:
- on explicit save/checkpoint;
- on publish/review decision;
- before restore;
- on configured periodic checkpoints if needed.

Revision metadata:
- revision number;
- author;
- timestamp;
- optional summary;
- content snapshot;
- source (manual, publish, restore, import).

Restoring a revision creates a new revision based on the old snapshot. It does not erase later history.

## 5. Structured entity conflicts

Each entity has an integer version. Update includes expected version. If the stored version differs:
- return `409 version_conflict`;
- include current version and safe metadata;
- frontend presents reload/compare/reapply options;
- do not overwrite silently.

## 6. Presence and awareness

Presence may show active collaborators and cursors/selections where supported. Presence is ephemeral, may be stale, and must never be used as evidence of authorship or audit history.

Do not broadcast document content to users lacking read permission. Do not put private content in presence metadata.

## 7. Review workflow

Contributors can submit a proposal. Proposal records the base revision/version and proposed changes. Reviewer can approve, reject, or request changes. Approval applies changes only if the base version is still valid or a reconciliation is completed.

## 8. Operational failure cases

Test:
- client disconnect during edit;
- server restart;
- duplicate update delivery;
- stale client;
- permission revoked mid-session;
- document deleted while open;
- snapshot failure;
- compaction interrupted;
- concurrent restore and edit.

Provide a clear UI state when offline or disconnected. Do not claim changes are saved until the server confirms durability.
