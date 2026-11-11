# Product Specification

## 1. Product statement

WORLDWEAVE is a collaborative worldbuilding workspace for creating, structuring, exploring, and maintaining fictional universes. It combines an extensible encyclopedia, narrative documents, maps, custom calendars and timelines, a relationship graph, and collaborative editorial workflows.

It is not a generic note-taking app, a public wiki clone, or an AI writing assistant.

## 2. Product goals

- Let a team create and maintain one or more independent fictional universes.
- Represent world knowledge as typed entities with explicit, navigable relationships.
- Support long-form writing that references canonical world entities without duplicating their data.
- Represent fictional geography using user-supplied maps and arbitrary coordinate systems.
- Represent fictional time using custom calendars and eras.
- Support controlled collaboration, review, comments, version history, and simultaneous document editing.
- Keep data portable through documented Markdown and asset export.
- Be deployable and operable by a self-hosting administrator.

## 3. Non-goals for v1.0

- AI generation, AI chat, agents, RAG, embeddings, vector search.
- Public social network, marketplace, discovery directory, or public comments.
- Native mobile apps.
- Offline-first multi-device synchronization.
- Full GIS, routing, terrain generation, or procedural map creation.
- Full project management suite.
- Real-time co-editing of every structured entity form. Realtime CRDT editing is required for long-form documents; structured entities use optimistic concurrency and revision history.
- Arbitrary plugin execution or user-installed server code.
- End-to-end encryption. The self-hosted server is trusted with plaintext content.
- Notion or Wiki.js runtime dependency.

## 4. Primary personas

### Universe owner
Creates universes, configures settings, invites collaborators, assigns roles, manages exports and backups.

### Administrator
Manages members, categories, content policy, and workspace configuration within delegated authority.

### Editor
Creates and edits canonical content, reviews submissions, and manages narrative documents.

### Contributor
Creates drafts and proposes changes. Cannot publish protected canonical changes without approval when review is enabled.

### Viewer
Reads content they are authorized to see and may participate in discussions only if granted comment permission.

## 5. Information architecture

Top-level application:
- Home / workspace switcher
- Universe overview
- Codex
- Chronicle
- Atlas
- Chronos
- Nexus
- Society
- Search
- Settings

Each universe has its own navigation and context. Global account settings are separate from universe settings.

### Universe overview
Shows universe identity, recent activity, recently edited entries, quick actions, member presence, and configurable summary widgets. Counts are computed from authorized data, not hardcoded.

### Codex
Extensible typed records:
- Characters
- Places
- Peoples/species
- Organizations
- Creatures
- Items/artifacts
- Religions/deities
- Magic systems
- Technologies
- Concepts
- User-defined types

Every entity has a stable ID, type, title, slug, summary, body, optional cover/media, tags, status, visibility, author, timestamps, and revision metadata. Type-specific fields are schema-defined and validated.

### Chronicle
Hierarchical narrative workspace:
- Collections / projects
- Works
- Parts / books
- Chapters
- Scenes
- Notes and reference documents

Documents support rich text, Markdown import/export, entity mentions/links, comments, version history, and collaborative editing.

### Atlas
Supports multiple maps per universe, uploaded image assets, arbitrary coordinate systems, markers, marker categories, optional region overlays, and links to Codex entities. A map's coordinates are relative to its source image, normalized to a stable 0..1 coordinate space. Do not assume latitude/longitude.

### Chronos
Supports user-defined calendars:
- calendar name and description;
- year length and ordered months;
- days per month;
- optional weekdays;
- eras and epoch offset;
- date precision rules;
- events with start/end dates;
- uncertain or approximate dates;
- links to entities and documents.

The initial date engine must support exact dates and date ranges in the configured calendar. Complex astronomical cycles and arbitrary calendar scripting are out of scope.

### Nexus
Interactive graph of entities and their relationships. Supports filtering by type and relation, search, focus node, neighborhood depth, and navigation to entity pages. Graph layout is a visualization, not the source of truth.

### Society
Member invitations, roles, per-resource permissions, review queues, comments, notifications, activity feed, and audit history.

## 6. Functional requirements

### Account and access
- FR-AUTH-01: Users can register or accept an invitation according to instance registration policy.
- FR-AUTH-02: Users can log in, log out, and recover access using configured email delivery or an administrator recovery path.
- FR-AUTH-03: Sessions are revocable.
- FR-AUTH-04: Users can belong to multiple universes with different roles.
- FR-AUTH-05: No user may access a universe without membership or an explicit public-read policy.

### Universe management
- FR-UNI-01: Owner can create, update, archive, and export a universe.
- FR-UNI-02: Universe IDs are globally unique and immutable.
- FR-UNI-03: Every universe-owned record carries a universe ID.
- FR-UNI-04: Cross-universe references are prohibited in v1.0.
- FR-UNI-05: Universe deletion requires typed confirmation and a recoverable backup/export recommendation.

### Codex
- FR-COD-01: Authorized users can create, read, update, archive, and restore entities.
- FR-COD-02: Administrators can define entity types and validated custom fields.
- FR-COD-03: Entities support tags, media, body content, status, and visibility.
- FR-COD-04: Users can create typed directed relationships between entities.
- FR-COD-05: Relationship types define allowed source and target entity types, directionality, and inverse label.
- FR-COD-06: Entity detail pages show incoming and outgoing relationships.
- FR-COD-07: Updates use optimistic concurrency to prevent silent overwrite.
- FR-COD-08: Slugs are unique within a universe and entity type; IDs remain canonical.

### Chronicle
- FR-DOC-01: Users can create hierarchical documents.
- FR-DOC-02: Documents support headings, lists, quotes, tables, links, images, and entity references.
- FR-DOC-03: Entity references resolve to canonical entity IDs, not title text alone.
- FR-DOC-04: Users can view and restore prior versions subject to permission.
- FR-DOC-05: Multiple users can edit a document simultaneously.
- FR-DOC-06: Document content is stored durably and can be exported to Markdown.
- FR-DOC-07: Comments can be anchored to a document or a selected text range where supported.

### Atlas
- FR-MAP-01: Users can create maps and upload/replace map images.
- FR-MAP-02: Users can add, move, edit, categorize, and delete markers.
- FR-MAP-03: Markers may link to Codex entities.
- FR-MAP-04: Marker positions remain correct after image resize or viewport changes.
- FR-MAP-05: Maps support visibility and permission checks.

### Chronos
- FR-TIME-01: Users can define calendars and eras.
- FR-TIME-02: Users can create dated and approximate events.
- FR-TIME-03: Events can reference entities and documents.
- FR-TIME-04: Timeline supports filtering, zoom, and overlapping events.
- FR-TIME-05: Date validation uses the selected calendar, not Gregorian assumptions.

### Nexus
- FR-GRAPH-01: Graph nodes represent entities and edges represent explicit relations.
- FR-GRAPH-02: Users can filter by entity type and relation type.
- FR-GRAPH-03: Users can focus a node and choose neighborhood depth.
- FR-GRAPH-04: Graph queries respect permissions and never leak hidden nodes or edges.
- FR-GRAPH-05: Graph is derived from authorized database records.

### Society and review
- FR-COL-01: Owners/admins can invite and remove members.
- FR-COL-02: Roles and resource permissions are enforced server-side.
- FR-COL-03: Review-enabled content can be submitted as a proposal.
- FR-COL-04: Authorized reviewers can approve, reject, or request changes.
- FR-COL-05: Every decision is recorded in the audit log.
- FR-COL-06: Comments and notifications respect visibility rules.
- FR-COL-07: User presence is ephemeral and not treated as audit evidence.

### Search and portability
- FR-SEARCH-01: Full-text search spans authorized entities and documents.
- FR-SEARCH-02: Search results expose type, title, summary, and navigation target.
- FR-IO-01: Universe export includes manifest, structured data, Markdown documents, and referenced assets.
- FR-IO-02: Import validates schema and reports conflicts before mutation.
- FR-IO-03: Export/import preserves stable IDs and relationships.
- FR-IO-04: Markdown WikiLinks are portable and resolve to stable IDs through metadata/frontmatter.

## 7. Non-functional requirements

- NFR-SEC-01: Authorization is enforced in the backend for every protected operation.
- NFR-SEC-02: Tenant isolation is tested at repository/service/API layers.
- NFR-REL-01: A committed write is durable according to PostgreSQL guarantees.
- NFR-REL-02: Backup and restore are documented and tested.
- NFR-PERF-01: Normal page/API operations should target p95 under 500 ms on a modest self-hosted deployment, excluding uploads, exports, and complex graph queries.
- NFR-PERF-02: Pagination is mandatory for potentially unbounded lists.
- NFR-UX-01: Core flows work at desktop and tablet widths; mobile supports reading and basic editing.
- NFR-ACC-01: Keyboard navigation, visible focus, semantic controls, and WCAG 2.2 AA-oriented contrast are required.
- NFR-PORT-01: User data can be exported without proprietary lock-in.
- NFR-OPS-01: Health/readiness endpoints and structured logs are available.
- NFR-PRIV-01: No analytics or telemetry is enabled by default.

## 8. Product acceptance

A complete v1.0 must satisfy all FR and NFR requirements marked in the release scope, pass the test strategy, have an operator guide, and demonstrate a successful backup restore on a clean deployment.
