# Test Strategy and Quality Gates

## 1. Test pyramid

### Unit tests
- domain validation;
- calendar calculations;
- slug and schema validation;
- permission policy functions;
- Markdown serialization;
- map coordinate transforms;
- relation constraints.

### Integration tests
- repositories and PostgreSQL;
- transactions and audit events;
- auth/session lifecycle;
- tenant isolation;
- import/export round trips;
- Yjs persistence and recovery;
- storage adapter.

### Frontend component tests
- forms and validation;
- loading/empty/error states;
- permission-aware controls;
- editor entity references;
- keyboard interactions.

### E2E tests
- registration/login;
- create universe;
- invite collaborator;
- role enforcement;
- create entity and relation;
- create/edit document;
- two-client collaborative editing;
- create map and marker;
- create custom calendar and event;
- graph navigation;
- export/import round trip;
- backup restore smoke test.

## 2. Security tests

Mandatory:
- cross-universe ID substitution;
- unauthenticated API access;
- revoked session reuse;
- role escalation;
- viewer mutation attempts;
- unauthorized document room join;
- permission revocation during realtime session;
- upload path traversal;
- spoofed MIME type;
- oversized upload;
- stored XSS through rich text and Markdown;
- CSRF where cookie sessions are used;
- invitation token reuse/expiry;
- search and graph information leakage.

## 3. Collaboration tests

- concurrent insertions converge;
- reconnect catches up;
- duplicated updates are idempotent;
- acknowledged updates survive process restart;
- snapshot compaction preserves state;
- permission revocation disconnects or blocks subsequent updates;
- restore creates a new revision and does not erase history.

## 4. Quality gates

A milestone cannot be accepted unless:
- lint/type checks pass;
- unit and integration tests pass;
- relevant E2E tests pass;
- migrations apply on a clean database;
- API schema generation succeeds;
- no critical/high security findings remain unresolved;
- docs and ADRs are updated;
- acceptance evidence is recorded.

## 5. Performance checks

Use realistic seeded data:
- 10,000 entities;
- 50,000 relations;
- 2,000 documents;
- 100,000 timeline events (for query/index testing, not necessarily browser rendering).

Measure list/search/graph/timeline endpoints. Apply pagination and bounded graph traversal. Do not require the browser to render the entire universe graph at once.

## 6. Release test scenarios

1. Owner creates universe and invites Editor, Contributor, Viewer.
2. Viewer cannot change an entity even by direct API request.
3. Contributor submits a proposal; Editor reviews it.
4. Two editors co-edit a chapter; both see converged content.
5. A server restart occurs; acknowledged chapter content remains.
6. A map marker links to a location entity and remains correctly positioned after viewport changes.
7. A custom calendar with non-Gregorian month lengths sorts events correctly.
8. Nexus displays only permitted nodes and relations.
9. Universe export is imported into a clean test universe without broken links.
10. Backup is restored on a clean host and passes integrity checks.
