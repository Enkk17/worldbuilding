"""Universe export bundle construction (M8).

Produces a ZIP bundle that is both a lossless WORLDWEAVE interchange format and
an Obsidian-openable vault: canonical JSON records carry every field needed for
an exact re-import, while Markdown files with YAML frontmatter and WikiLinks give
humans a portable, editable representation.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.models import (
    Asset,
    Calendar,
    Document,
    DocumentEntityLink,
    Entity,
    EntityRelation,
    EntityTag,
    EntityType,
    Era,
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
from backend.core.visibility import visible_clause
from backend.modules.chronicle.markdown import tiptap_to_markdown
from backend.modules.exports.bundle import (
    CHECKSUMS_NAME,
    FORMAT_NAME,
    MANIFEST_NAME,
    SCHEMA_VERSION,
    UNIVERSE_NAME,
    render_checksums,
    render_frontmatter,
    sha256_hex,
)
from backend.modules.universes.service import check_universe_access, record_activity, record_audit

EXPORTER_VERSION = "1.0.0"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")


def _markdown_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _entity_markdown(entity: Entity, type_key: str, tags: list[str]) -> str:
    metadata = {
        "worldweave_id": str(entity.id),
        "kind": "entity",
        "entity_type": type_key,
        "title": entity.title,
        "slug": entity.slug,
        "status": entity.status,
        "visibility": entity.visibility,
        "tags": tags,
        "schema_version": SCHEMA_VERSION,
        "custom_fields": entity.custom_fields or {},
    }
    return render_frontmatter(metadata, entity.summary or "")


def _document_markdown(
    document: Document, links: list[str]
) -> str:
    metadata = {
        "worldweave_id": str(document.id),
        "kind": "document",
        "document_type": document.document_type,
        "title": document.title,
        "slug": document.slug,
        "parent_id": str(document.parent_id) if document.parent_id else None,
        "status": document.status,
        "visibility": document.visibility,
        "sort_order": document.sort_order,
        "linked_entity_ids": links,
        "schema_version": SCHEMA_VERSION,
    }
    body = tiptap_to_markdown(document.content_json or {"type": "doc", "content": []})
    return render_frontmatter(metadata, body)


def build_export_bundle(
    db: Session,
    universe: Universe,
    user: User,
    role: str,
    *,
    media_root: str,
) -> tuple[bytes, dict[str, Any]]:
    warnings: list[str] = []
    files: dict[str, bytes] = {}

    entity_types = list(
        db.scalars(
            select(EntityType)
            .where(EntityType.universe_id == universe.id)
            .order_by(EntityType.key)
        ).all()
    )
    type_key_by_id = {record.id: record.key for record in entity_types}

    relation_types = list(
        db.scalars(
            select(RelationType)
            .where(RelationType.universe_id == universe.id)
            .order_by(RelationType.key)
        ).all()
    )
    relation_key_by_id = {record.id: record.key for record in relation_types}

    entity_visibility = visible_clause(Entity, user.id, role)
    entity_stmt = select(Entity).where(
        Entity.universe_id == universe.id, Entity.deleted_at.is_(None)
    )
    if entity_visibility is not None:
        entity_stmt = entity_stmt.where(entity_visibility)
    entities = list(db.scalars(entity_stmt.order_by(Entity.title)).all())
    entity_ids = {record.id for record in entities}

    tag_names: dict[uuid.UUID, list[str]] = {}
    if entity_ids:
        tag_rows = db.execute(
            select(EntityTag.entity_id, Tag.name)
            .join(Tag, Tag.id == EntityTag.tag_id)
            .where(EntityTag.entity_id.in_(entity_ids))
            .order_by(Tag.name)
        ).all()
        for entity_id, name in tag_rows:
            tag_names.setdefault(entity_id, []).append(name)

    entity_records: list[dict[str, Any]] = []
    for entity in entities:
        type_key = type_key_by_id.get(entity.entity_type_id)
        if type_key is None:
            warnings.append(f"Entity {entity.id} references a missing entity type and was skipped.")
            continue
        tags = tag_names.get(entity.id, [])
        entity_records.append(
            {
                "id": str(entity.id),
                "entity_type": type_key,
                "title": entity.title,
                "slug": entity.slug,
                "summary": entity.summary,
                "custom_fields": entity.custom_fields or {},
                "status": entity.status,
                "visibility": entity.visibility,
                "tags": tags,
                "version": entity.version,
                "created_at": _iso(entity.created_at),
                "updated_at": _iso(entity.updated_at),
            }
        )
        files[f"entities/{type_key}/{entity.slug}.md"] = _markdown_bytes(
            _entity_markdown(entity, type_key, tags)
        )

    relation_rows = list(
        db.scalars(
            select(EntityRelation).where(
                EntityRelation.universe_id == universe.id,
                EntityRelation.deleted_at.is_(None),
            )
        ).all()
    )
    relation_records: list[dict[str, Any]] = []
    for relation in relation_rows:
        if (
            relation.source_entity_id not in entity_ids
            or relation.target_entity_id not in entity_ids
        ):
            warnings.append(f"Relation {relation.id} references an excluded entity and was skipped.")
            continue
        relation_key = relation_key_by_id.get(relation.relation_type_id)
        if relation_key is None:
            warnings.append(f"Relation {relation.id} references a missing relation type and was skipped.")
            continue
        relation_records.append(
            {
                "id": str(relation.id),
                "source_entity_id": str(relation.source_entity_id),
                "target_entity_id": str(relation.target_entity_id),
                "relation_type": relation_key,
                "attributes_json": relation.attributes_json or {},
            }
        )

    document_visibility = visible_clause(Document, user.id, role)
    document_stmt = select(Document).where(
        Document.universe_id == universe.id, Document.deleted_at.is_(None)
    )
    if document_visibility is not None:
        document_stmt = document_stmt.where(document_visibility)
    documents = list(db.scalars(document_stmt.order_by(Document.sort_order, Document.title)).all())
    document_ids = {record.id for record in documents}

    links_by_document: dict[uuid.UUID, list[str]] = {}
    if document_ids:
        link_rows = db.execute(
            select(DocumentEntityLink.document_id, DocumentEntityLink.entity_id)
            .where(DocumentEntityLink.document_id.in_(document_ids))
            .order_by(DocumentEntityLink.entity_id)
        ).all()
        for document_id, linked_entity_id in link_rows:
            links_by_document.setdefault(document_id, []).append(str(linked_entity_id))

    document_records: list[dict[str, Any]] = []
    for document in documents:
        links = links_by_document.get(document.id, [])
        document_records.append(
            {
                "id": str(document.id),
                "parent_id": str(document.parent_id) if document.parent_id else None,
                "document_type": document.document_type,
                "title": document.title,
                "slug": document.slug,
                "status": document.status,
                "visibility": document.visibility,
                "sort_order": document.sort_order,
                "version": document.version,
                "content_json": document.content_json or {"type": "doc", "content": []},
                "linked_entity_ids": links,
                "created_at": _iso(document.created_at),
                "updated_at": _iso(document.updated_at),
            }
        )
        files[f"documents/{document.document_type}/{document.slug}.md"] = _markdown_bytes(
            _document_markdown(document, links)
        )

    maps = list(
        db.scalars(select(Map).where(Map.universe_id == universe.id).order_by(Map.title)).all()
    )
    map_records: list[dict[str, Any]] = []
    for map_record in maps:
        markers = list(
            db.scalars(
                select(MapMarker)
                .where(MapMarker.map_id == map_record.id)
                .order_by(MapMarker.title)
            ).all()
        )
        regions = list(
            db.scalars(
                select(MapRegion)
                .where(MapRegion.map_id == map_record.id)
                .order_by(MapRegion.title)
            ).all()
        )
        map_records.append(
            {
                "id": str(map_record.id),
                "title": map_record.title,
                "description": map_record.description,
                "image_asset_id": str(map_record.image_asset_id) if map_record.image_asset_id else None,
                "coordinate_system": map_record.coordinate_system,
                "width": map_record.width,
                "height": map_record.height,
                "version": map_record.version,
                "markers": [
                    {
                        "id": str(marker.id),
                        "title": marker.title,
                        "description": marker.description,
                        "x_norm": marker.x_norm,
                        "y_norm": marker.y_norm,
                        "marker_type": marker.marker_type,
                        "linked_entity_id": str(marker.linked_entity_id) if marker.linked_entity_id else None,
                        "style_json": marker.style_json or {},
                        "version": marker.version,
                    }
                    for marker in markers
                ],
                "regions": [
                    {
                        "id": str(region.id),
                        "title": region.title,
                        "geometry_json": region.geometry_json or {},
                        "linked_entity_id": str(region.linked_entity_id) if region.linked_entity_id else None,
                        "style_json": region.style_json or {},
                        "version": region.version,
                    }
                    for region in regions
                ],
            }
        )

    calendars = list(
        db.scalars(
            select(Calendar).where(Calendar.universe_id == universe.id).order_by(Calendar.name)
        ).all()
    )
    calendar_records: list[dict[str, Any]] = []
    for calendar in calendars:
        eras = list(
            db.scalars(
                select(Era).where(Era.calendar_id == calendar.id).order_by(Era.start_day_index)
            ).all()
        )
        calendar_records.append(
            {
                "id": str(calendar.id),
                "name": calendar.name,
                "description": calendar.description,
                "config_json": calendar.config_json or {},
                "version": calendar.version,
                "eras": [
                    {
                        "id": str(era.id),
                        "name": era.name,
                        "start_day_index": era.start_day_index,
                        "description": era.description,
                        "version": era.version,
                    }
                    for era in eras
                ],
            }
        )

    events = list(
        db.scalars(
            select(TimelineEvent)
            .where(TimelineEvent.universe_id == universe.id)
            .order_by(TimelineEvent.start_day_index)
        ).all()
    )
    event_records = [
        {
            "id": str(event.id),
            "calendar_id": str(event.calendar_id),
            "title": event.title,
            "description": event.description,
            "start_date_json": event.start_date_json or {},
            "end_date_json": event.end_date_json,
            "date_precision": event.date_precision,
            "uncertainty_json": event.uncertainty_json,
            "linked_entity_id": str(event.linked_entity_id) if event.linked_entity_id else None,
            "linked_document_id": str(event.linked_document_id) if event.linked_document_id else None,
            "version": event.version,
        }
        for event in events
    ]

    asset_records: list[dict[str, Any]] = []
    referenced_asset_ids = {
        record["image_asset_id"] for record in map_records if record["image_asset_id"]
    }
    if universe.cover_asset_id:
        referenced_asset_ids.add(str(universe.cover_asset_id))
    for asset_id in sorted(referenced_asset_ids):
        asset = db.get(Asset, uuid.UUID(asset_id))
        if asset is None or asset.universe_id != universe.id or asset.deleted_at is not None:
            warnings.append(f"Asset {asset_id} is missing and was omitted from the bundle.")
            continue
        path = Path(media_root).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        source = (path.resolve() / asset.storage_key)
        if not source.is_file():
            warnings.append(f"Asset {asset_id} has no stored file and was omitted from the bundle.")
            continue
        payload = source.read_bytes()
        if sha256_hex(payload) != asset.checksum_sha256:
            warnings.append(f"Asset {asset_id} failed its checksum check and was omitted.")
            continue
        suffix = Path(asset.original_filename).suffix[:16]
        files[f"assets/{asset.id}{suffix}"] = payload
        asset_records.append(
            {
                "id": str(asset.id),
                "path": f"assets/{asset.id}{suffix}",
                "original_filename": asset.original_filename,
                "mime_type": asset.mime_type,
                "byte_size": asset.byte_size,
                "checksum_sha256": asset.checksum_sha256,
                "width": asset.width,
                "height": asset.height,
            }
        )

    files["codex/entity-types.json"] = _json_bytes(
        {
            "items": [
                {
                    "key": record.key,
                    "name": record.name,
                    "description": record.description,
                    "schema_json": record.schema_json or {},
                    "icon": record.icon,
                    "color": record.color,
                    "is_system": record.is_system,
                }
                for record in entity_types
            ]
        }
    )
    files["codex/relation-types.json"] = _json_bytes(
        {
            "items": [
                {
                    "key": record.key,
                    "label": record.label,
                    "inverse_label": record.inverse_label,
                    "description": record.description,
                    "allowed_source_types": record.allowed_source_types or [],
                    "allowed_target_types": record.allowed_target_types or [],
                    "is_directional": record.is_directional,
                    "is_symmetric": record.is_symmetric,
                }
                for record in relation_types
            ]
        }
    )
    files["codex/relations.json"] = _json_bytes({"items": relation_records})
    files["entities/index.json"] = _json_bytes({"items": entity_records})
    files["documents/index.json"] = _json_bytes({"items": document_records})
    files["maps/maps.json"] = _json_bytes({"items": map_records})
    files["timelines/calendars.json"] = _json_bytes({"items": calendar_records})
    files["timelines/events.json"] = _json_bytes({"items": event_records})
    files["assets/assets.json"] = _json_bytes({"items": asset_records})

    universe_payload = {
        "id": str(universe.id),
        "name": universe.name,
        "slug": universe.slug,
        "description": universe.description,
        "settings_json": universe.settings_json or {},
        "status": universe.status,
        "schema_version": SCHEMA_VERSION,
    }
    files[UNIVERSE_NAME] = _json_bytes(universe_payload)

    manifest = {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "exporter_version": EXPORTER_VERSION,
        "universe_id": str(universe.id),
        "universe_name": universe.name,
        "universe_slug": universe.slug,
        "exported_at": _iso(datetime.now(timezone.utc)),
        "counts": {
            "entity_types": len(entity_types),
            "relation_types": len(relation_types),
            "entities": len(entity_records),
            "relations": len(relation_records),
            "documents": len(document_records),
            "maps": len(map_records),
            "calendars": len(calendar_records),
            "timeline_events": len(event_records),
            "assets": len(asset_records),
        },
        "warnings": warnings,
    }
    files[MANIFEST_NAME] = _json_bytes(manifest)
    files[CHECKSUMS_NAME] = _markdown_bytes(render_checksums(files))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])

    filename = f"worldweave-{universe.slug}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip"
    return buffer.getvalue(), manifest


def export_universe(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    *,
    media_root: str,
    request_id: str | None = None,
) -> tuple[bytes, dict[str, Any], str]:
    universe, membership = check_universe_access(db, universe_id, user, Action.EXPORT_CREATE)
    payload, manifest = build_export_bundle(
        db, universe, user, membership.role, media_root=media_root
    )
    record_audit(
        db,
        universe.id,
        user.id,
        Action.EXPORT_CREATE,
        "universe",
        universe.id,
        after_hash=sha256_hex(payload),
        request_id=request_id,
    )
    record_activity(
        db,
        universe.id,
        user.id,
        "universe.exported",
        "universe",
        universe.id,
        {"counts": manifest.get("counts", {})},
    )
    db.commit()
    filename = f"worldweave-{universe.slug}-export.zip"
    return payload, manifest, filename
