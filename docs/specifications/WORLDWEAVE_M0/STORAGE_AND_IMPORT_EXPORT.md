# Storage, Markdown, Import/Export, and Backup

## 1. Hybrid storage decision

PostgreSQL is the authoritative source of truth for:
- structured Codex entities and relationships;
- universe configuration;
- users and memberships;
- document metadata and revisions;
- collaboration state/snapshots;
- maps, markers, calendars, events;
- comments, proposals, and audit records.

Markdown is the portable content representation and interchange format. It is not a second independently editable canonical database.

The application may export a universe to a directory that can be opened in Obsidian or another Markdown editor. Changes made outside WORLDWEAVE are imported through an explicit validation/import workflow.

## 2. Markdown format

Each exported document/entity has:
- Markdown body;
- YAML frontmatter;
- stable WORLDWEAVE ID;
- type;
- title;
- slug;
- universe export identifier;
- schema version;
- linked entity IDs where relevant.

Example:

---
worldweave_id: "UUID"
universe_id: "UUID"
kind: "entity"
entity_type: "character"
title: "Arielle"
slug: "arielle"
schema_version: 1
---

# Arielle

Character description...

Links should use stable IDs in metadata and readable WikiLink syntax where possible. Titles alone are not reliable identifiers.

## 3. Export package

Suggested structure:

worldweave-export/
  manifest.json
  universe.json
  entities/
    characters/
    locations/
    organizations/
  documents/
    works/
    chapters/
  maps/
    maps.json
  timelines/
    calendars.json
    events.json
  assets/
  checksums.sha256

Export must include:
- schema version;
- universe ID;
- export timestamp;
- stable entity/document IDs;
- relationships;
- referenced assets;
- checksums;
- warnings for unsupported content.

## 4. Import workflow

1. Upload/select export package.
2. Validate archive safety and size.
3. Parse manifest and schema version.
4. Validate all IDs, references, relation constraints, and asset checksums.
5. Produce dry-run report: create/update/skip/conflict/error.
6. User selects conflict policy.
7. Execute import in a transaction or resumable job.
8. Record import job and audit event.
9. Verify counts and references.

Never execute an import just because a file was uploaded. Import is an explicit user action.

## 5. Obsidian compatibility

- Export folders and Markdown files should open as an Obsidian vault.
- Use readable filenames and `[[WikiLinks]]`.
- Preserve stable IDs in frontmatter.
- Provide an optional `.obsidian`-free export by default; do not overwrite user-specific vault configuration.
- Round-trip import must detect duplicate IDs and changed records.
- Do not promise perfect fidelity for arbitrary Obsidian plugins or unsupported embeds.

## 6. Notion and Wiki.js

They are optional future import/export adapters, not runtime dependencies. Scope them after the core Markdown round-trip format is stable. Respect each platform's export format and API constraints.

## 7. Assets

- Store binary data outside PostgreSQL.
- Use opaque storage keys; never trust user-supplied paths.
- Record SHA-256 checksum, MIME type, byte size, dimensions, uploader, and universe.
- Validate actual file type rather than trusting extension.
- Generate thumbnails asynchronously if needed.
- Enforce configurable upload limits.
- Prevent cross-universe asset access.

## 8. Backup and restore

A backup includes:
- PostgreSQL logical backup or tested physical backup strategy;
- asset storage;
- configuration secrets backed up separately and securely;
- version/manifest metadata.

Document:
- backup cadence;
- retention;
- encryption at rest for backup files where available;
- restore procedure;
- restore to clean deployment;
- integrity verification.

A release cannot pass without a successful restore drill. Export is not a substitute for operational backup, and backup is not a substitute for user-facing export.
