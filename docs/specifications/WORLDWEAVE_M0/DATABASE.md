# Database and Domain Model

## 1. Principles

- PostgreSQL is the authoritative system of record.
- Every universe-owned row is scoped by `universe_id`.
- IDs are stable opaque UUIDs; slugs and titles are mutable presentation identifiers.
- Use foreign keys and database constraints wherever possible.
- Soft deletion is used for user-facing content where restore is expected; hard deletion is an explicit retention/admin operation.
- All mutable records include `created_at`, `updated_at`, and actor metadata where relevant.
- Store timestamps in UTC.
- Do not place the entire universe in one JSON document.

## 2. Core entities

### Identity and tenancy
- `users(id, email, password_hash, display_name, status, created_at, updated_at)`
- `sessions(id, user_id, token_hash, expires_at, revoked_at, created_at)`
- `universes(id, owner_user_id, name, slug, description, cover_asset_id, settings_json, status, created_at, updated_at)`
- `universe_members(id, universe_id, user_id, role, status, invited_by, joined_at, created_at)`
- `invitations(id, universe_id, email, role, token_hash, expires_at, accepted_at, created_by)`

Unique constraints:
- user email normalized and unique;
- universe slug unique per owner or globally according to routing choice; choose and document one before M1;
- one membership per `(universe_id, user_id)`;
- one active invitation token hash.

### Codex
- `entity_types(id, universe_id, key, name, description, schema_json, icon, color, is_system, created_at, updated_at)`
- `entities(id, universe_id, entity_type_id, title, slug, summary, body_document_id, status, visibility, created_by, updated_by, version, created_at, updated_at, deleted_at)`
- `entity_relations(id, universe_id, source_entity_id, relation_type_id, target_entity_id, attributes_json, created_by, created_at, updated_at, deleted_at)`
- `relation_types(id, universe_id, key, label, inverse_label, description, allowed_source_types, allowed_target_types, is_directional, is_symmetric, created_at)`
- `entity_field_values` is optional only if JSONB validation becomes insufficient; start with validated JSONB `custom_fields` on entities.
- `tags(id, universe_id, name, slug)`
- `entity_tags(entity_id, tag_id)`

Entity custom field schema must support a bounded set of types: text, long_text, number, boolean, date, enum, multi_enum, URL, and entity reference. Do not support arbitrary executable formulas in v1.0.

### Documents
- `documents(id, universe_id, parent_id, document_type, title, slug, status, visibility, created_by, updated_by, version, created_at, updated_at, deleted_at)`
- `document_revisions(id, document_id, revision_number, content_json, markdown_snapshot, created_by, created_at, change_summary)`
- `document_collab_snapshots(id, document_id, ydoc_state, state_vector, created_at)`
- `document_collab_updates(id, document_id, update_blob, client_id, created_at)`
- `document_entity_links(id, document_id, entity_id, anchor_json, link_kind)`

TipTap JSON is the editor document representation. Markdown snapshots are generated for portability. Yjs updates/snapshots support live collaboration. A single canonical persistence path must be documented in the collaboration ADR and tested for crash recovery.

### Atlas
- `maps(id, universe_id, title, description, image_asset_id, coordinate_system, width, height, created_by, updated_at, version, created_at)`
- `map_markers(id, map_id, universe_id, title, description, x_norm, y_norm, marker_type, linked_entity_id, style_json, created_by, updated_at)`
- `map_regions(id, map_id, universe_id, title, geometry_json, linked_entity_id, style_json)`

Marker coordinates are normalized floats in [0,1] relative to original image bounds. Reject out-of-range values. Region geometry uses a documented normalized coordinate representation.

### Chronos
- `calendars(id, universe_id, name, description, config_json, created_at, updated_at)`
- `eras(id, calendar_id, name, start_day_index, description)`
- `timeline_events(id, universe_id, calendar_id, title, description, start_date_json, end_date_json, date_precision, uncertainty_json, linked_entity_id, linked_document_id, created_by, updated_at)`

Use a calendar engine/service to convert structured custom dates to a comparable internal day index where the calendar definition permits it. Do not store only formatted date strings. Calendar configuration is versioned; changing a calendar must not silently reinterpret historical events.

### Society and workflow
- `comments(id, universe_id, target_type, target_id, parent_comment_id, body, anchor_json, created_by, created_at, edited_at, deleted_at)`
- `revision_proposals(id, universe_id, target_type, target_id, base_version, proposed_payload, status, submitted_by, reviewed_by, reviewed_at, decision_note, created_at)`
- `activity_events(id, universe_id, actor_user_id, event_type, target_type, target_id, metadata_json, created_at)`
- `audit_logs(id, universe_id, actor_user_id, action, target_type, target_id, before_hash, after_hash, request_id, created_at)`

### Assets
- `assets(id, universe_id, storage_key, original_filename, mime_type, byte_size, checksum_sha256, width, height, uploaded_by, created_at, deleted_at)`

## 3. Important invariants

1. Every relationship source and target belongs to the same universe as the relationship.
2. A marker's linked entity belongs to the same universe as its map.
3. A timeline event's linked entity/document belongs to the same universe.
4. A document parent belongs to the same universe.
5. A user must be an active member or have explicit public access before reading universe content.
6. A relation type must allow the source and target entity types.
7. Entity slug uniqueness is enforced within the defined scope.
8. A version increment occurs atomically with a structured entity update.
9. Audit records for sensitive mutations are committed in the same transaction as the mutation.
10. Soft-deleted entities are excluded from normal search and graph results.

Use composite foreign keys or service-level invariant checks plus database constraints where practical. Add tests that attempt cross-universe references.

## 4. Indexing

At minimum:
- index all `universe_id` columns;
- composite indexes for `(universe_id, status)` and `(universe_id, updated_at)`;
- unique indexes for scoped slugs;
- indexes on relation source and target IDs;
- GIN indexes for JSONB only for queried paths;
- PostgreSQL full-text indexes for entity/document title, summary, and body text;
- indexes for timeline date ordering and map marker lookup.

Do not add speculative indexes without query evidence.

## 5. Migrations

- Alembic owns schema changes.
- Every migration has upgrade and downgrade where safely possible.
- Destructive data transformations require a backup and documented recovery.
- Seed system entity types and relation types through repeatable, idempotent seed routines.
- CI must create a clean database, apply all migrations, run tests, and validate migration head.
