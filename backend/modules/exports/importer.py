"""Universe import validation and execution (M8).

Import is never implicit: an uploaded archive is parsed, structurally validated,
cross-checked against the target universe, and planned into a per-record report
before anything is written. Execution then applies the same plan inside one
transaction, preserving the stable IDs carried by the bundle.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import (
    Asset,
    Calendar,
    Document,
    DocumentEntityLink,
    DocumentRevision,
    Entity,
    EntityRelation,
    EntityTag,
    EntityType,
    Era,
    ImportJob,
    Map,
    MapMarker,
    MapRegion,
    RelationType,
    Tag,
    TimelineEvent,
    Universe,
    User,
)
from backend.core.permissions import Action
from backend.modules.chronicle.content import (
    ContentValidationError,
    normalize_document_content,
)
from backend.modules.chronicle.markdown import tiptap_to_markdown
from backend.modules.codex.custom_fields import (
    normalize_custom_field_schema,
    validate_custom_field_values,
)
from backend.modules.codex.service import ensure_system_types
from backend.modules.exports.bundle import (
    CHECKSUMS_NAME,
    FORMAT_NAME,
    MANIFEST_NAME,
    SCHEMA_VERSION,
    UNIVERSE_NAME,
    open_archive,
    parse_checksums,
    read_member,
    sha256_hex,
)
from backend.modules.universes.service import (
    check_universe_access,
    record_activity,
    record_audit,
    slugify,
)

CONFLICT_POLICIES = frozenset({"skip", "overwrite", "fail"})
CREATE = "create"
UPDATE = "update"
SKIP = "skip"
CONFLICT = "conflict"
ERROR = "error"


@dataclass
class PlannedAction:
    kind: str
    record_id: str
    label: str
    action: str
    message: str | None = None
    payload: dict[str, Any] | None = None


@dataclass
class ParsedBundle:
    manifest: dict[str, Any]
    universe: dict[str, Any]
    entity_types: list[dict[str, Any]]
    relation_types: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    maps: list[dict[str, Any]]
    calendars: list[dict[str, Any]]
    events: list[dict[str, Any]]
    assets: list[dict[str, Any]]
    source_universe_id: uuid.UUID | None = None
    asset_blobs: dict[str, bytes] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _load_json(payload: bytes, member: str) -> Any:
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(422, "invalid_json_member", f"The archive member '{member}' is not valid JSON.") from exc


def _items(payload: Any, member: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ApiError(422, "invalid_json_member", f"The archive member '{member}' has an unexpected shape.")
    return payload["items"]


def parse_bundle(payload: bytes, *, max_bytes: int) -> ParsedBundle:
    archive = open_archive(payload, max_bytes=max_bytes)
    with archive:
        manifest_bytes = read_member(archive, MANIFEST_NAME)
        manifest = _load_json(manifest_bytes, MANIFEST_NAME)
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_NAME:
            raise ApiError(422, "invalid_manifest", "This archive is not a WORLDWEAVE export bundle.")
        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, int) or schema_version < 1:
            raise ApiError(422, "invalid_manifest", "The bundle declares an invalid schema version.")
        if schema_version > SCHEMA_VERSION:
            raise ApiError(
                422,
                "unsupported_schema_version",
                "This bundle was produced by a newer WORLDWEAVE release than this server supports.",
            )

        universe_bytes = read_member(archive, UNIVERSE_NAME)
        universe = _load_json(universe_bytes, UNIVERSE_NAME)
        if not isinstance(universe, dict):
            raise ApiError(422, "invalid_json_member", "The universe descriptor is malformed.")

        checksums_bytes = read_member(archive, CHECKSUMS_NAME)
        try:
            declared = parse_checksums(checksums_bytes.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ApiError(422, "invalid_checksums", "The checksum index is not valid UTF-8.") from exc

        entries = {
            info.filename: info
            for info in archive.infolist()
            if not info.filename.endswith("/")
        }
        for name, digest in declared.items():
            if name not in entries:
                raise ApiError(422, "checksum_member_missing", f"The archive is missing the checksummed member '{name}'.")
            with archive.open(name) as handle:
                if sha256_hex(handle.read()) != digest:
                    raise ApiError(422, "checksum_mismatch", f"The archive member '{name}' failed its checksum verification.")

        entity_types = _items(_load_json(read_member(archive, "codex/entity-types.json", required=False) or b'{"items": []}', "codex/entity-types.json"), "codex/entity-types.json")
        relation_types = _items(_load_json(read_member(archive, "codex/relation-types.json", required=False) or b'{"items": []}', "codex/relation-types.json"), "codex/relation-types.json")
        relations = _items(_load_json(read_member(archive, "codex/relations.json", required=False) or b'{"items": []}', "codex/relations.json"), "codex/relations.json")
        entities = _items(_load_json(read_member(archive, "entities/index.json", required=False) or b'{"items": []}', "entities/index.json"), "entities/index.json")
        documents = _items(_load_json(read_member(archive, "documents/index.json", required=False) or b'{"items": []}', "documents/index.json"), "documents/index.json")
        maps = _items(_load_json(read_member(archive, "maps/maps.json", required=False) or b'{"items": []}', "maps/maps.json"), "maps/maps.json")
        calendars = _items(_load_json(read_member(archive, "timelines/calendars.json", required=False) or b'{"items": []}', "timelines/calendars.json"), "timelines/calendars.json")
        events = _items(_load_json(read_member(archive, "timelines/events.json", required=False) or b'{"items": []}', "timelines/events.json"), "timelines/events.json")
        assets = _items(_load_json(read_member(archive, "assets/assets.json", required=False) or b'{"items": []}', "assets/assets.json"), "assets/assets.json")

        asset_blobs: dict[str, bytes] = {}
        for record in assets:
            path = record.get("path")
            if not isinstance(path, str) or path not in entries:
                raise ApiError(422, "archive_missing_member", "An asset record references a file missing from the archive.")
            blob = read_member(archive, path)
            if sha256_hex(blob) != record.get("checksum_sha256"):
                raise ApiError(422, "checksum_mismatch", f"The asset '{path}' failed its checksum verification.")
            asset_blobs[path] = blob

    warnings = manifest.get("warnings") if isinstance(manifest.get("warnings"), list) else []
    return ParsedBundle(
        manifest=manifest,
        universe=universe,
        entity_types=entity_types,
        relation_types=relation_types,
        entities=entities,
        relations=relations,
        documents=documents,
        maps=maps,
        calendars=calendars,
        events=events,
        assets=assets,
        source_universe_id=_as_uuid(universe.get("id")),
        asset_blobs=asset_blobs,
        warnings=list(warnings),
    )


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def remap_bundle(bundle: ParsedBundle, target_universe_id: uuid.UUID) -> ParsedBundle:
    """Assign fresh ids when importing a bundle from a different universe.

    WORLDWEAVE ids are globally unique, so a bundle produced elsewhere cannot be
    reinserted verbatim: doing so would collide with the source records. A clone
    therefore mints new ids and rewrites every internal reference so the imported
    graph stays internally consistent. A same-universe round-trip keeps its ids.
    """

    source_id = _as_uuid(bundle.universe.get("id"))
    if source_id is None or source_id == target_universe_id:
        return bundle

    def new_id(value: Any) -> Any:
        parsed = _as_uuid(value)
        if parsed is None:
            return value
        return str(uuid.uuid4())

    entity_map: dict[str, str] = {}
    document_map: dict[str, str] = {}
    calendar_map: dict[str, str] = {}
    asset_map: dict[str, str] = {}

    entities = []
    for record in bundle.entities:
        remapped = dict(record)
        if remapped.get("id") is not None:
            entity_map[str(record["id"])] = new_id(record["id"])
            remapped["id"] = entity_map[str(record["id"])]
        entities.append(remapped)

    documents = []
    for record in bundle.documents:
        remapped = dict(record)
        if remapped.get("id") is not None:
            document_map[str(record["id"])] = new_id(record["id"])
            remapped["id"] = document_map[str(record["id"])]
        documents.append(remapped)
    for remapped in documents:
        if remapped.get("parent_id") is not None:
            remapped["parent_id"] = document_map.get(str(remapped["parent_id"]), remapped["parent_id"])
        if isinstance(remapped.get("linked_entity_ids"), list):
            remapped["linked_entity_ids"] = [
                entity_map.get(str(link), link) for link in remapped["linked_entity_ids"]
            ]

    calendars = []
    for record in bundle.calendars:
        remapped = dict(record)
        if remapped.get("id") is not None:
            calendar_map[str(record["id"])] = new_id(record["id"])
            remapped["id"] = calendar_map[str(record["id"])]
        remapped["eras"] = [dict(era) for era in record.get("eras") or []]
        calendars.append(remapped)

    maps = []
    for record in bundle.maps:
        remapped = dict(record)
        if remapped.get("id") is not None:
            remapped["id"] = new_id(record["id"])
        if remapped.get("image_asset_id") is not None:
            remapped["image_asset_id"] = asset_map.get(str(remapped["image_asset_id"]), remapped["image_asset_id"])
        remapped["markers"] = []
        for marker in record.get("markers") or []:
            new_marker = dict(marker)
            new_marker["id"] = new_id(marker.get("id"))
            if new_marker.get("linked_entity_id") is not None:
                new_marker["linked_entity_id"] = entity_map.get(
                    str(new_marker["linked_entity_id"]), new_marker["linked_entity_id"]
                )
            remapped["markers"].append(new_marker)
        remapped["regions"] = []
        for region in record.get("regions") or []:
            new_region = dict(region)
            new_region["id"] = new_id(region.get("id"))
            if new_region.get("linked_entity_id") is not None:
                new_region["linked_entity_id"] = entity_map.get(
                    str(new_region["linked_entity_id"]), new_region["linked_entity_id"]
                )
            remapped["regions"].append(new_region)
        maps.append(remapped)

    asset_blobs: dict[str, bytes] = {}
    assets = []
    for record in bundle.assets:
        remapped = dict(record)
        if remapped.get("id") is not None:
            asset_map[str(record["id"])] = new_id(record["id"])
            remapped["id"] = asset_map[str(record["id"])]
        old_path = record.get("path")
        if isinstance(old_path, str):
            suffix = Path(old_path).suffix[:16]
            new_path = f"assets/{remapped['id']}{suffix}"
            remapped["path"] = new_path
            if old_path in bundle.asset_blobs:
                asset_blobs[new_path] = bundle.asset_blobs[old_path]
        assets.append(remapped)

    # Re-apply asset ids now that they are known.
    for remapped in maps:
        if remapped.get("image_asset_id") is not None:
            remapped["image_asset_id"] = asset_map.get(str(remapped["image_asset_id"]), remapped["image_asset_id"])

    relations = []
    for record in bundle.relations:
        remapped = dict(record)
        if remapped.get("id") is not None:
            remapped["id"] = new_id(record["id"])
        remapped["source_entity_id"] = entity_map.get(str(record.get("source_entity_id")), record.get("source_entity_id"))
        remapped["target_entity_id"] = entity_map.get(str(record.get("target_entity_id")), record.get("target_entity_id"))
        relations.append(remapped)

    events = []
    for record in bundle.events:
        remapped = dict(record)
        if remapped.get("id") is not None:
            remapped["id"] = new_id(record["id"])
        remapped["calendar_id"] = calendar_map.get(str(record.get("calendar_id")), record.get("calendar_id"))
        if remapped.get("linked_entity_id") is not None:
            remapped["linked_entity_id"] = entity_map.get(
                str(remapped["linked_entity_id"]), remapped["linked_entity_id"]
            )
        if remapped.get("linked_document_id") is not None:
            remapped["linked_document_id"] = document_map.get(
                str(remapped["linked_document_id"]), remapped["linked_document_id"]
            )
        events.append(remapped)

    universe = dict(bundle.universe)
    universe["id"] = str(target_universe_id)

    return ParsedBundle(
        manifest=bundle.manifest,
        universe=universe,
        entity_types=bundle.entity_types,
        relation_types=bundle.relation_types,
        entities=entities,
        relations=relations,
        documents=documents,
        maps=maps,
        calendars=calendars,
        events=events,
        assets=assets,
        source_universe_id=bundle.source_universe_id,
        asset_blobs=asset_blobs,
        warnings=bundle.warnings,
    )


def _existing_id(db: Session, model: Any, record_id: uuid.UUID) -> Any:
    return db.get(model, record_id)


def _resolve_id(
    db: Session,
    model: Any,
    record_id: uuid.UUID,
    universe_id: uuid.UUID,
) -> str:
    """Classify a referenced id: 'ok', 'missing', or 'foreign'."""

    record = db.get(model, record_id)
    if record is None:
        return "missing"
    record_universe = getattr(record, "universe_id", None)
    if record_universe is not None and record_universe != universe_id:
        return "foreign"
    return "ok"


def plan_import(
    db: Session,
    target_universe: Universe,
    bundle: ParsedBundle,
    conflict_policy: str,
) -> list[PlannedAction]:
    if conflict_policy not in CONFLICT_POLICIES:
        raise ApiError(422, "invalid_conflict_policy", "Conflict policy must be skip, overwrite, or fail.")

    universe_id = target_universe.id
    actions: list[PlannedAction] = []

    bundle_entity_type_keys = {record.get("key") for record in bundle.entity_types}
    existing_type_keys = set(
        db.scalars(select(EntityType.key).where(EntityType.universe_id == universe_id)).all()
    )
    known_type_keys = bundle_entity_type_keys | existing_type_keys

    bundle_relation_type_keys = {record.get("key") for record in bundle.relation_types}
    existing_relation_keys = set(
        db.scalars(select(RelationType.key).where(RelationType.universe_id == universe_id)).all()
    )
    known_relation_keys = bundle_relation_type_keys | existing_relation_keys

    imported_entity_ids: set[uuid.UUID] = set()
    for record in bundle.entities:
        record_id = _as_uuid(record.get("id"))
        title = str(record.get("title") or "Untitled")
        if record_id is None:
            actions.append(PlannedAction("entity", "", title, ERROR, "Entity id is not a valid UUID."))
            continue
        type_key = record.get("entity_type")
        if type_key not in known_type_keys:
            actions.append(PlannedAction("entity", str(record_id), title, ERROR, f"Entity type '{type_key}' is not available in the target universe."))
            continue
        existing = _existing_id(db, Entity, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("entity", str(record_id), title, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("entity", str(record_id), title, CONFLICT, "An entity with this id already exists."))
                continue
            action = UPDATE if conflict_policy == "overwrite" else SKIP
            actions.append(PlannedAction("entity", str(record_id), title, action, payload=record))
            imported_entity_ids.add(record_id)
            continue
        actions.append(PlannedAction("entity", str(record_id), title, CREATE, payload=record))
        imported_entity_ids.add(record_id)

    imported_document_ids: set[uuid.UUID] = set()
    for record in bundle.documents:
        record_id = _as_uuid(record.get("id"))
        title = str(record.get("title") or "Untitled")
        if record_id is None:
            actions.append(PlannedAction("document", "", title, ERROR, "Document id is not a valid UUID."))
            continue
        existing = _existing_id(db, Document, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("document", str(record_id), title, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("document", str(record_id), title, CONFLICT, "A document with this id already exists."))
                continue
            action = UPDATE if conflict_policy == "overwrite" else SKIP
            actions.append(PlannedAction("document", str(record_id), title, action, payload=record))
            imported_document_ids.add(record_id)
            continue
        actions.append(PlannedAction("document", str(record_id), title, CREATE, payload=record))
        imported_document_ids.add(record_id)

    imported_calendar_ids: set[uuid.UUID] = set()
    for record in bundle.calendars:
        record_id = _as_uuid(record.get("id"))
        name = str(record.get("name") or "Calendar")
        if record_id is None:
            actions.append(PlannedAction("calendar", "", name, ERROR, "Calendar id is not a valid UUID."))
            continue
        existing = _existing_id(db, Calendar, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("calendar", str(record_id), name, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("calendar", str(record_id), name, CONFLICT, "A calendar with this id already exists."))
                continue
            action = UPDATE if conflict_policy == "overwrite" else SKIP
            actions.append(PlannedAction("calendar", str(record_id), name, action, payload=record))
            imported_calendar_ids.add(record_id)
            continue
        actions.append(PlannedAction("calendar", str(record_id), name, CREATE, payload=record))
        imported_calendar_ids.add(record_id)

    imported_map_ids: set[uuid.UUID] = set()
    for record in bundle.maps:
        record_id = _as_uuid(record.get("id"))
        title = str(record.get("title") or "Map")
        if record_id is None:
            actions.append(PlannedAction("map", "", title, ERROR, "Map id is not a valid UUID."))
            continue
        existing = _existing_id(db, Map, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("map", str(record_id), title, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("map", str(record_id), title, CONFLICT, "A map with this id already exists."))
                continue
            action = UPDATE if conflict_policy == "overwrite" else SKIP
            actions.append(PlannedAction("map", str(record_id), title, action, payload=record))
            imported_map_ids.add(record_id)
            continue
        actions.append(PlannedAction("map", str(record_id), title, CREATE, payload=record))
        imported_map_ids.add(record_id)

    imported_asset_ids: set[uuid.UUID] = set()
    for record in bundle.assets:
        record_id = _as_uuid(record.get("id"))
        label = str(record.get("original_filename") or "asset")
        if record_id is None:
            actions.append(PlannedAction("asset", "", label, ERROR, "Asset id is not a valid UUID."))
            continue
        existing = _existing_id(db, Asset, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("asset", str(record_id), label, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("asset", str(record_id), label, CONFLICT, "An asset with this id already exists."))
                continue
            actions.append(PlannedAction("asset", str(record_id), label, SKIP, "The asset already exists and binary data is never overwritten."))
            imported_asset_ids.add(record_id)
            continue
        actions.append(PlannedAction("asset", str(record_id), label, CREATE, payload=record))
        imported_asset_ids.add(record_id)

    for record in bundle.relations:
        record_id = _as_uuid(record.get("id"))
        label = str(record.get("relation_type") or "relation")
        if record_id is None:
            actions.append(PlannedAction("relation", "", label, ERROR, "Relation id is not a valid UUID."))
            continue
        source_id = _as_uuid(record.get("source_entity_id"))
        target_id = _as_uuid(record.get("target_entity_id"))
        if source_id not in imported_entity_ids or target_id not in imported_entity_ids:
            actions.append(PlannedAction("relation", str(record_id), label, ERROR, "The relation references an entity that is not part of this import."))
            continue
        if record.get("relation_type") not in known_relation_keys:
            actions.append(PlannedAction("relation", str(record_id), label, ERROR, f"Relation type '{record.get('relation_type')}' is not available in the target universe."))
            continue
        existing = _existing_id(db, EntityRelation, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("relation", str(record_id), label, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("relation", str(record_id), label, CONFLICT, "A relation with this id already exists."))
                continue
            action = UPDATE if conflict_policy == "overwrite" else SKIP
            actions.append(PlannedAction("relation", str(record_id), label, action, payload=record))
            continue
        actions.append(PlannedAction("relation", str(record_id), label, CREATE, payload=record))

    for record in bundle.events:
        record_id = _as_uuid(record.get("id"))
        title = str(record.get("title") or "Event")
        if record_id is None:
            actions.append(PlannedAction("timeline_event", "", title, ERROR, "Event id is not a valid UUID."))
            continue
        calendar_id = _as_uuid(record.get("calendar_id"))
        if calendar_id not in imported_calendar_ids:
            actions.append(PlannedAction("timeline_event", str(record_id), title, ERROR, "The event references a calendar that is not part of this import."))
            continue
        linked_entity = _as_uuid(record.get("linked_entity_id"))
        if linked_entity is not None and linked_entity not in imported_entity_ids:
            actions.append(PlannedAction("timeline_event", str(record_id), title, ERROR, "The event links to an entity that is not part of this import."))
            continue
        linked_document = _as_uuid(record.get("linked_document_id"))
        if linked_document is not None and linked_document not in imported_document_ids:
            actions.append(PlannedAction("timeline_event", str(record_id), title, ERROR, "The event links to a document that is not part of this import."))
            continue
        existing = _existing_id(db, TimelineEvent, record_id)
        if existing is not None:
            if existing.universe_id != universe_id:
                actions.append(PlannedAction("timeline_event", str(record_id), title, ERROR, "This id already belongs to another universe."))
                continue
            if conflict_policy == "fail":
                actions.append(PlannedAction("timeline_event", str(record_id), title, CONFLICT, "A timeline event with this id already exists."))
                continue
            action = UPDATE if conflict_policy == "overwrite" else SKIP
            actions.append(PlannedAction("timeline_event", str(record_id), title, action, payload=record))
            continue
        actions.append(PlannedAction("timeline_event", str(record_id), title, CREATE, payload=record))

    # Asset references used by maps must be resolvable inside the target universe.
    for action in actions:
        if action.kind != "map" or action.action in {ERROR, SKIP} or not action.payload:
            continue
        asset_id = _as_uuid(action.payload.get("image_asset_id"))
        if asset_id is not None and asset_id not in imported_asset_ids:
            action.action = ERROR
            action.message = "The map references an image asset that is not part of this import."

    return actions


def summarise(actions: list[PlannedAction]) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {}
    items: list[dict[str, Any]] = []
    errors = 0
    for action in actions:
        bucket = counts.setdefault(action.kind, {CREATE: 0, UPDATE: 0, SKIP: 0, CONFLICT: 0, ERROR: 0})
        bucket[action.action] = bucket.get(action.action, 0) + 1
        if action.action == ERROR:
            errors += 1
        items.append(
            {
                "kind": action.kind,
                "id": action.record_id or None,
                "label": action.label,
                "action": action.action,
                "message": action.message,
            }
        )
    return {"counts": counts, "items": items, "errors": errors, "valid": errors == 0}


def _resolve_entity_type(db: Session, universe_id: uuid.UUID, key: str, cache: dict[str, EntityType]) -> EntityType:
    if key in cache:
        return cache[key]
    record = db.scalar(
        select(EntityType).where(EntityType.universe_id == universe_id, EntityType.key == key)
    )
    if record is None:
        raise ApiError(422, "entity_type_not_found", f"Entity type '{key}' could not be resolved during import.")
    cache[key] = record
    return record


def _resolve_relation_type(db: Session, universe_id: uuid.UUID, key: str, cache: dict[str, RelationType]) -> RelationType:
    if key in cache:
        return cache[key]
    record = db.scalar(
        select(RelationType).where(RelationType.universe_id == universe_id, RelationType.key == key)
    )
    if record is None:
        raise ApiError(422, "relation_type_not_found", f"Relation type '{key}' could not be resolved during import.")
    cache[key] = record
    return record


def _sync_tags(db: Session, universe_id: uuid.UUID, entity_id: uuid.UUID, names: list[str]) -> None:
    db.execute(EntityTag.__table__.delete().where(EntityTag.entity_id == entity_id))
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip()
        if not name:
            continue
        tag_slug = slugify(name)
        if tag_slug in seen:
            continue
        seen.add(tag_slug)
        tag = db.scalar(select(Tag).where(Tag.universe_id == universe_id, Tag.slug == tag_slug))
        if tag is None:
            tag = Tag(id=uuid.uuid4(), universe_id=universe_id, name=name, slug=tag_slug)
            db.add(tag)
            db.flush()
        db.add(EntityTag(entity_id=entity_id, tag_id=tag.id))


def _import_entity_types(db: Session, universe_id: uuid.UUID, bundle: ParsedBundle) -> None:
    existing = {
        record.key: record
        for record in db.scalars(
            select(EntityType).where(EntityType.universe_id == universe_id)
        ).all()
    }
    for record in bundle.entity_types:
        key = record.get("key")
        if not isinstance(key, str) or not key:
            continue
        if key in existing:
            continue
        schema = normalize_custom_field_schema(record.get("schema_json") or {})
        db.add(
            EntityType(
                id=uuid.uuid4(),
                universe_id=universe_id,
                key=key,
                name=str(record.get("name") or key)[:80],
                description=record.get("description"),
                schema_json=schema,
                icon=record.get("icon"),
                color=record.get("color"),
                is_system=bool(record.get("is_system", False)),
            )
        )
    db.flush()


def _import_relation_types(db: Session, universe_id: uuid.UUID, bundle: ParsedBundle) -> None:
    existing = set(
        db.scalars(select(RelationType.key).where(RelationType.universe_id == universe_id)).all()
    )
    for record in bundle.relation_types:
        key = record.get("key")
        if not isinstance(key, str) or not key or key in existing:
            continue
        db.add(
            RelationType(
                id=uuid.uuid4(),
                universe_id=universe_id,
                key=key,
                label=str(record.get("label") or key)[:80],
                inverse_label=record.get("inverse_label"),
                description=record.get("description"),
                allowed_source_types=list(record.get("allowed_source_types") or []),
                allowed_target_types=list(record.get("allowed_target_types") or []),
                is_directional=bool(record.get("is_directional", True)),
                is_symmetric=bool(record.get("is_symmetric", False)),
            )
        )
    db.flush()


def _write_asset_blob(media_root: str, storage_key: str, payload: bytes) -> Path:
    root = Path(media_root).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = (root / storage_key).resolve()
    if destination.parent != root:
        raise ApiError(500, "storage_error", "The asset could not be stored.")
    destination.write_bytes(payload)
    return destination


def execute_import(
    db: Session,
    target_universe: Universe,
    user: User,
    bundle: ParsedBundle,
    actions: list[PlannedAction],
    conflict_policy: str,
    *,
    media_root: str,
    dry_run: bool,
    archive_checksum: str,
    request_id: str | None = None,
) -> ImportJob:
    universe_id = target_universe.id
    written_paths: list[Path] = []
    try:
        if not dry_run:
            ensure_system_types(db, universe_id)
            _import_entity_types(db, universe_id, bundle)
            _import_relation_types(db, universe_id, bundle)

        entity_type_cache: dict[str, EntityType] = {}
        relation_type_cache: dict[str, RelationType] = {}

        # A dry run must validate a bundle whose custom entity/relation types do
        # not exist yet, so resolve schemas from the bundle as well as the DB.
        bundle_entity_schemas = {
            record["key"]: normalize_custom_field_schema(record.get("schema_json") or {})
            for record in bundle.entity_types
            if isinstance(record.get("key"), str) and record.get("key")
        }
        db_entity_schemas = {
            record.key: normalize_custom_field_schema(record.schema_json)
            for record in db.scalars(
                select(EntityType).where(EntityType.universe_id == universe_id)
            ).all()
        }
        combined_entity_schemas = {**bundle_entity_schemas, **db_entity_schemas}
        known_relation_keys = {
            record.get("key") for record in bundle.relation_types if record.get("key")
        } | set(
            db.scalars(
                select(RelationType.key).where(RelationType.universe_id == universe_id)
            ).all()
        )

        for action in actions:
            if action.kind == "asset" and action.action == CREATE and action.payload:
                record = action.payload
                if dry_run:
                    continue
                blob = bundle.asset_blobs.get(record.get("path", ""))
                if blob is None:
                    continue
                storage_key = uuid.UUID(action.record_id).hex
                path = _write_asset_blob(media_root, storage_key, blob)
                written_paths.append(path)
                db.add(
                    Asset(
                        id=uuid.UUID(action.record_id),
                        universe_id=universe_id,
                        storage_key=storage_key,
                        original_filename=str(record.get("original_filename") or "asset")[:255],
                        mime_type=str(record.get("mime_type") or "application/octet-stream")[:100],
                        byte_size=int(record.get("byte_size") or len(blob)),
                        checksum_sha256=str(record.get("checksum_sha256") or sha256_hex(blob)),
                        width=record.get("width"),
                        height=record.get("height"),
                        uploaded_by=user.id,
                    )
                )
        if not dry_run:
            db.flush()

        for action in actions:
            if action.kind != "entity" or not action.payload or action.action in {SKIP, ERROR, CONFLICT}:
                continue
            record = action.payload
            schema = combined_entity_schemas.get(record.get("entity_type"))
            if schema is None:
                raise ApiError(
                    422,
                    "entity_type_not_found",
                    f"Entity type '{record.get('entity_type')}' could not be resolved during import.",
                )
            custom_fields = validate_custom_field_values(
                db, universe_id, schema, record.get("custom_fields") or {}
            )
            if dry_run:
                continue
            entity_type = _resolve_entity_type(db, universe_id, record["entity_type"], entity_type_cache)
            if action.action == CREATE:
                entity = Entity(
                    id=uuid.UUID(action.record_id),
                    universe_id=universe_id,
                    entity_type_id=entity_type.id,
                    title=str(record.get("title") or "Untitled")[:200],
                    slug=str(record.get("slug") or slugify(str(record.get("title") or "entity")))[:200],
                    summary=record.get("summary"),
                    custom_fields=custom_fields,
                    status=str(record.get("status") or "active"),
                    visibility=str(record.get("visibility") or "universe"),
                    created_by=user.id,
                    updated_by=user.id,
                    version=1,
                )
                db.add(entity)
                db.flush()
            else:
                entity = db.get(Entity, uuid.UUID(action.record_id))
                if entity is None:
                    continue
                entity.entity_type_id = entity_type.id
                entity.title = str(record.get("title") or entity.title)[:200]
                entity.summary = record.get("summary")
                entity.custom_fields = custom_fields
                entity.status = str(record.get("status") or entity.status)
                entity.visibility = str(record.get("visibility") or entity.visibility)
                entity.updated_by = user.id
                entity.version += 1
                entity.updated_at = datetime.now(timezone.utc)
            _sync_tags(db, universe_id, entity.id, list(record.get("tags") or []))

        for action in actions:
            if action.kind != "document" or not action.payload or action.action in {SKIP, ERROR, CONFLICT}:
                continue
            record = action.payload
            try:
                content = normalize_document_content(record.get("content_json"))
            except ContentValidationError as exc:
                raise ApiError(
                    422,
                    "invalid_document_content",
                    f"Document '{action.record_id}' has invalid content: {exc.message}",
                ) from exc
            if dry_run:
                continue
            parent_id = _as_uuid(record.get("parent_id"))
            if action.action == CREATE:
                document = Document(
                    id=uuid.UUID(action.record_id),
                    universe_id=universe_id,
                    parent_id=parent_id,
                    document_type=str(record.get("document_type") or "chapter"),
                    title=str(record.get("title") or "Untitled")[:200],
                    slug=str(record.get("slug") or slugify(str(record.get("title") or "document")))[:200],
                    content_json=content,
                    status=str(record.get("status") or "draft"),
                    visibility=str(record.get("visibility") or "universe"),
                    sort_order=int(record.get("sort_order") or 0),
                    created_by=user.id,
                    updated_by=user.id,
                    version=1,
                )
                db.add(document)
                db.flush()
                db.add(
                    DocumentRevision(
                        id=uuid.uuid4(),
                        document_id=document.id,
                        revision_number=1,
                        content_json=content,
                        markdown_snapshot=tiptap_to_markdown(content),
                        change_summary="Imported",
                        source="import",
                        created_by=user.id,
                    )
                )
            else:
                document = db.get(Document, uuid.UUID(action.record_id))
                if document is None:
                    continue
                document.parent_id = parent_id
                document.document_type = str(record.get("document_type") or document.document_type)
                document.title = str(record.get("title") or document.title)[:200]
                document.content_json = content
                document.status = str(record.get("status") or document.status)
                document.visibility = str(record.get("visibility") or document.visibility)
                document.sort_order = int(record.get("sort_order") or document.sort_order)
                document.updated_by = user.id
                document.version += 1
                document.updated_at = datetime.now(timezone.utc)
                db.add(
                    DocumentRevision(
                        id=uuid.uuid4(),
                        document_id=document.id,
                        revision_number=document.version,
                        content_json=content,
                        markdown_snapshot=tiptap_to_markdown(content),
                        change_summary="Imported update",
                        source="import",
                        created_by=user.id,
                    )
                )
            db.execute(
                DocumentEntityLink.__table__.delete().where(DocumentEntityLink.document_id == document.id)
            )
            for linked in record.get("linked_entity_ids") or []:
                linked_id = _as_uuid(linked)
                if linked_id is not None and db.get(Entity, linked_id) is not None:
                    db.add(
                        DocumentEntityLink(
                            id=uuid.uuid4(),
                            document_id=document.id,
                            entity_id=linked_id,
                            link_kind="mention",
                        )
                    )

        for action in actions:
            if action.kind != "relation" or not action.payload or action.action in {SKIP, ERROR, CONFLICT}:
                continue
            record = action.payload
            if record.get("relation_type") not in known_relation_keys:
                raise ApiError(
                    422,
                    "relation_type_not_found",
                    f"Relation type '{record.get('relation_type')}' could not be resolved during import.",
                )
            if dry_run:
                continue
            relation_type = _resolve_relation_type(db, universe_id, record["relation_type"], relation_type_cache)
            if action.action == CREATE:
                db.add(
                    EntityRelation(
                        id=uuid.UUID(action.record_id),
                        universe_id=universe_id,
                        source_entity_id=uuid.UUID(record["source_entity_id"]),
                        relation_type_id=relation_type.id,
                        target_entity_id=uuid.UUID(record["target_entity_id"]),
                        attributes_json=record.get("attributes_json") or {},
                        created_by=user.id,
                    )
                )
            else:
                relation = db.get(EntityRelation, uuid.UUID(action.record_id))
                if relation is None:
                    continue
                relation.relation_type_id = relation_type.id
                relation.source_entity_id = uuid.UUID(record["source_entity_id"])
                relation.target_entity_id = uuid.UUID(record["target_entity_id"])
                relation.attributes_json = record.get("attributes_json") or {}

        for action in actions:
            if action.kind != "map" or not action.payload or action.action in {SKIP, ERROR, CONFLICT}:
                continue
            record = action.payload
            if dry_run:
                continue
            image_asset_id = _as_uuid(record.get("image_asset_id"))
            if action.action == CREATE:
                map_record = Map(
                    id=uuid.UUID(action.record_id),
                    universe_id=universe_id,
                    title=str(record.get("title") or "Map")[:150],
                    description=record.get("description"),
                    image_asset_id=image_asset_id,
                    coordinate_system=str(record.get("coordinate_system") or "normalized"),
                    width=int(record.get("width") or 1920),
                    height=int(record.get("height") or 1080),
                    created_by=user.id,
                    version=1,
                )
                db.add(map_record)
                db.flush()
            else:
                map_record = db.get(Map, uuid.UUID(action.record_id))
                if map_record is None:
                    continue
                map_record.title = str(record.get("title") or map_record.title)[:150]
                map_record.description = record.get("description")
                map_record.image_asset_id = image_asset_id
                map_record.width = int(record.get("width") or map_record.width)
                map_record.height = int(record.get("height") or map_record.height)
                map_record.version += 1
                map_record.updated_at = datetime.now(timezone.utc)
                db.execute(MapMarker.__table__.delete().where(MapMarker.map_id == map_record.id))
                db.execute(MapRegion.__table__.delete().where(MapRegion.map_id == map_record.id))
            for marker in record.get("markers") or []:
                db.add(
                    MapMarker(
                        id=_as_uuid(marker.get("id")) or uuid.uuid4(),
                        map_id=map_record.id,
                        universe_id=universe_id,
                        title=str(marker.get("title") or "Marker")[:150],
                        description=marker.get("description"),
                        x_norm=float(marker.get("x_norm") or 0.0),
                        y_norm=float(marker.get("y_norm") or 0.0),
                        marker_type=str(marker.get("marker_type") or "poi")[:64],
                        linked_entity_id=_as_uuid(marker.get("linked_entity_id")),
                        style_json=marker.get("style_json") or {},
                        created_by=user.id,
                        version=1,
                    )
                )
            for region in record.get("regions") or []:
                db.add(
                    MapRegion(
                        id=_as_uuid(region.get("id")) or uuid.uuid4(),
                        map_id=map_record.id,
                        universe_id=universe_id,
                        title=str(region.get("title") or "Region")[:150],
                        geometry_json=region.get("geometry_json") or {},
                        linked_entity_id=_as_uuid(region.get("linked_entity_id")),
                        style_json=region.get("style_json") or {},
                        version=1,
                    )
                )

        for action in actions:
            if action.kind != "calendar" or not action.payload or action.action in {SKIP, ERROR, CONFLICT}:
                continue
            record = action.payload
            if dry_run:
                continue
            if action.action == CREATE:
                calendar = Calendar(
                    id=uuid.UUID(action.record_id),
                    universe_id=universe_id,
                    name=str(record.get("name") or "Calendar")[:100],
                    description=record.get("description"),
                    config_json=record.get("config_json") or {},
                    created_by=user.id,
                    version=1,
                )
                db.add(calendar)
                db.flush()
            else:
                calendar = db.get(Calendar, uuid.UUID(action.record_id))
                if calendar is None:
                    continue
                calendar.name = str(record.get("name") or calendar.name)[:100]
                calendar.description = record.get("description")
                calendar.config_json = record.get("config_json") or {}
                calendar.version += 1
                calendar.updated_at = datetime.now(timezone.utc)
                db.execute(Era.__table__.delete().where(Era.calendar_id == calendar.id))
            for era in record.get("eras") or []:
                db.add(
                    Era(
                        id=_as_uuid(era.get("id")) or uuid.uuid4(),
                        calendar_id=calendar.id,
                        name=str(era.get("name") or "Era")[:100],
                        start_day_index=int(era.get("start_day_index") or 0),
                        description=era.get("description"),
                        version=1,
                    )
                )

        for action in actions:
            if action.kind != "timeline_event" or not action.payload or action.action in {SKIP, ERROR, CONFLICT}:
                continue
            record = action.payload
            if dry_run:
                continue
            start_index = int(record.get("start_day_index") or 0)
            if action.action == CREATE:
                db.add(
                    TimelineEvent(
                        id=uuid.UUID(action.record_id),
                        universe_id=universe_id,
                        calendar_id=uuid.UUID(record["calendar_id"]),
                        title=str(record.get("title") or "Event")[:200],
                        description=record.get("description"),
                        start_date_json=record.get("start_date_json") or {},
                        end_date_json=record.get("end_date_json"),
                        start_day_index=start_index,
                        end_day_index=record.get("end_day_index"),
                        date_precision=str(record.get("date_precision") or "day"),
                        uncertainty_json=record.get("uncertainty_json"),
                        linked_entity_id=_as_uuid(record.get("linked_entity_id")),
                        linked_document_id=_as_uuid(record.get("linked_document_id")),
                        created_by=user.id,
                        version=1,
                    )
                )
            else:
                event = db.get(TimelineEvent, uuid.UUID(action.record_id))
                if event is None:
                    continue
                event.calendar_id = uuid.UUID(record["calendar_id"])
                event.title = str(record.get("title") or event.title)[:200]
                event.description = record.get("description")
                event.start_date_json = record.get("start_date_json") or {}
                event.end_date_json = record.get("end_date_json")
                event.start_day_index = start_index
                event.end_day_index = record.get("end_day_index")
                event.date_precision = str(record.get("date_precision") or event.date_precision)
                event.uncertainty_json = record.get("uncertainty_json")
                event.linked_entity_id = _as_uuid(record.get("linked_entity_id"))
                event.linked_document_id = _as_uuid(record.get("linked_document_id"))
                event.version += 1
                event.updated_at = datetime.now(timezone.utc)

        summary = summarise(actions)
        job = ImportJob(
            id=uuid.uuid4(),
            universe_id=universe_id,
            source_universe_id=bundle.source_universe_id,
            schema_version=int(bundle.manifest.get("schema_version") or SCHEMA_VERSION),
            status="dry_run" if dry_run else "completed",
            conflict_policy=conflict_policy,
            dry_run=dry_run,
            archive_checksum_sha256=archive_checksum,
            report_json=summary,
            warnings_json=bundle.warnings,
            created_by=user.id,
        )
        db.add(job)

        if not dry_run:
            record_audit(
                db,
                universe_id,
                user.id,
                Action.IMPORT_EXECUTE,
                "universe",
                universe_id,
                request_id=request_id,
            )
            record_activity(
                db,
                universe_id,
                user.id,
                "universe.imported",
                "universe",
                universe_id,
                {"conflict_policy": conflict_policy, "counts": summary["counts"]},
            )
        db.commit()
        db.refresh(job)
        return job
    except Exception:
        db.rollback()
        for path in written_paths:
            path.unlink(missing_ok=True)
        raise


def _has_conflicts(summary: dict[str, Any]) -> bool:
    return any(counts.get(CONFLICT, 0) for counts in summary["counts"].values())


def validate_import_bundle(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    payload: bytes,
    *,
    max_bytes: int,
) -> tuple[ParsedBundle, list[PlannedAction]]:
    universe, _ = check_universe_access(db, universe_id, user, Action.IMPORT_VALIDATE)
    bundle = parse_bundle(payload, max_bytes=max_bytes)
    bundle = remap_bundle(bundle, universe_id)
    actions = plan_import(db, universe, bundle, "skip")
    return bundle, actions


def run_import(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    payload: bytes,
    *,
    conflict_policy: str,
    dry_run: bool,
    media_root: str,
    max_bytes: int,
    request_id: str | None = None,
) -> ImportJob:
    universe, _ = check_universe_access(db, universe_id, user, Action.IMPORT_EXECUTE)
    if conflict_policy not in CONFLICT_POLICIES:
        raise ApiError(422, "invalid_conflict_policy", "Conflict policy must be skip, overwrite, or fail.")
    bundle = parse_bundle(payload, max_bytes=max_bytes)
    bundle = remap_bundle(bundle, universe_id)
    actions = plan_import(db, universe, bundle, conflict_policy)
    summary = summarise(actions)
    blocking = summary["errors"] > 0 or (
        conflict_policy == "fail" and _has_conflicts(summary)
    )
    if not dry_run and blocking:
        raise ApiError(
            422,
            "import_validation_failed",
            "The import cannot be applied. Resolve the reported issues or choose a different conflict policy.",
            details={"report": summary},
        )
    return execute_import(
        db,
        universe,
        user,
        bundle,
        actions,
        conflict_policy,
        media_root=media_root,
        dry_run=dry_run,
        archive_checksum=sha256_hex(payload),
        request_id=request_id,
    )


def list_import_jobs(db: Session, universe_id: uuid.UUID, user: User, limit: int = 50) -> list[ImportJob]:
    check_universe_access(db, universe_id, user, Action.AUDIT_READ)
    return list(
        db.scalars(
            select(ImportJob)
            .where(ImportJob.universe_id == universe_id)
            .order_by(ImportJob.created_at.desc())
            .limit(min(limit, 100))
        ).all()
    )
