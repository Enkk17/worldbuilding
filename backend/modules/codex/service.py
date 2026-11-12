from __future__ import annotations

import collections
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, aliased

from backend.core.errors import ApiError
from backend.core.models import (
    Entity,
    EntityRelation,
    EntityTag,
    EntityType,
    RelationType,
    Tag,
    User,
)
from backend.core.permissions import Action
from backend.core.visibility import is_visible, visible_clause
from backend.modules.universes.service import (
    check_universe_access,
    record_activity,
    record_audit,
    slugify,
)
from backend.modules.codex.custom_fields import (
    normalize_custom_field_schema,
    validate_custom_field_values,
    validate_entity_reference_types,
)
from backend.modules.codex.schemas import (
    EntityCreate,
    EntityTypeCreate,
    EntityTypeUpdate,
    EntityUpdate,
    RelationTypeCreate,
)

SYSTEM_ENTITY_TYPES = [
    {"key": "character", "name": "Characters", "description": "Fictional personas and figures.", "icon": "user", "color": "#a4523b"},
    {"key": "place", "name": "Places", "description": "Settlements, realms, sites, and geographical landmarks.", "icon": "map-pin", "color": "#253a32"},
    {"key": "people", "name": "Peoples & Species", "description": "Cultures, lineages, ethnicities, and sapient kinds.", "icon": "users", "color": "#b18b4d"},
    {"key": "organization", "name": "Organizations", "description": "Guilds, orders, factions, governments, and secret sects.", "icon": "shield", "color": "#436152"},
    {"key": "creature", "name": "Creatures", "description": "Beasts, monsters, fauna, and supernatural fauna.", "icon": "feather", "color": "#885542"},
    {"key": "item", "name": "Items & Artifacts", "description": "Relics, heirlooms, weapons, and curiosities.", "icon": "gem", "color": "#c4823f"},
    {"key": "religion", "name": "Religions & Deities", "description": "Pantheons, creeds, cosmologies, and sacred rites.", "icon": "sun", "color": "#b89025"},
    {"key": "magic_system", "name": "Magic Systems", "description": "Principles, costs, arcana, and occult traditions.", "icon": "sparkles", "color": "#684577"},
    {"key": "technology", "name": "Technologies", "description": "Inventions, alchemy, crafts, and mechanical marvels.", "icon": "cpu", "color": "#425868"},
    {"key": "concept", "name": "Concepts & Lore", "description": "Philosophies, historical phenomena, languages, and laws.", "icon": "book-open", "color": "#566358"},
]

SYSTEM_RELATION_TYPES = [
    {
        "key": "located_in",
        "label": "Located in",
        "inverse_label": "Houses",
        "allowed_source_types": ["place", "organization", "character"],
        "allowed_target_types": ["place"],
        "is_directional": True,
        "is_symmetric": False,
    },
    {
        "key": "member_of",
        "label": "Member of",
        "inverse_label": "Has member",
        "allowed_source_types": ["character"],
        "allowed_target_types": ["organization", "people"],
        "is_directional": True,
        "is_symmetric": False,
    },
    {
        "key": "allied_with",
        "label": "Allied with",
        "inverse_label": "Allied with",
        "allowed_source_types": ["organization", "character", "people"],
        "allowed_target_types": ["organization", "character", "people"],
        "is_directional": False,
        "is_symmetric": True,
    },
    {
        "key": "parent_of",
        "label": "Parent of",
        "inverse_label": "Child of",
        "allowed_source_types": ["character"],
        "allowed_target_types": ["character"],
        "is_directional": True,
        "is_symmetric": False,
    },
    {
        "key": "possesses",
        "label": "Possesses",
        "inverse_label": "Held by",
        "allowed_source_types": ["character", "organization"],
        "allowed_target_types": ["item"],
        "is_directional": True,
        "is_symmetric": False,
    },
    {
        "key": "creator_of",
        "label": "Creator of",
        "inverse_label": "Created by",
        "allowed_source_types": ["character", "people", "organization"],
        "allowed_target_types": ["item", "technology", "magic_system"],
        "is_directional": True,
        "is_symmetric": False,
    },
]


def ensure_system_types(db: Session, universe_id: uuid.UUID) -> None:
    # Ensure default entity types exist
    existing_types = set(
        db.scalars(
            select(EntityType.key).where(EntityType.universe_id == universe_id)
        ).all()
    )
    for st in SYSTEM_ENTITY_TYPES:
        if st["key"] not in existing_types:
            et = EntityType(
                id=uuid.uuid4(),
                universe_id=universe_id,
                key=st["key"],
                name=st["name"],
                description=st["description"],
                schema_json={},
                icon=st["icon"],
                color=st["color"],
                is_system=True,
            )
            db.add(et)

    # Ensure default relation types exist
    existing_relations = set(
        db.scalars(
            select(RelationType.key).where(RelationType.universe_id == universe_id)
        ).all()
    )
    for rt in SYSTEM_RELATION_TYPES:
        if rt["key"] not in existing_relations:
            rel = RelationType(
                id=uuid.uuid4(),
                universe_id=universe_id,
                key=rt["key"],
                label=rt["label"],
                inverse_label=rt["inverse_label"],
                allowed_source_types=rt["allowed_source_types"],
                allowed_target_types=rt["allowed_target_types"],
                is_directional=rt["is_directional"],
                is_symmetric=rt["is_symmetric"],
            )
            db.add(rel)
    db.commit()


# -----------------------------------------------------------------------------
# Entity Types Service
# -----------------------------------------------------------------------------

def list_entity_types(
    db: Session, universe_id: uuid.UUID, user: User
) -> list[EntityType]:
    check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    ensure_system_types(db, universe_id)
    stmt = (
        select(EntityType)
        .where(EntityType.universe_id == universe_id)
        .order_by(EntityType.is_system.desc(), EntityType.name.asc())
    )
    return list(db.scalars(stmt).all())


def create_entity_type(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    data: EntityTypeCreate,
    request_id: str | None = None,
) -> EntityType:
    check_universe_access(db, universe_id, user, Action.ENTITY_TYPE_MANAGE)
    ensure_system_types(db, universe_id)
    clean_key = slugify(data.key).replace("-", "_")
    existing = db.scalar(
        select(EntityType).where(
            EntityType.universe_id == universe_id, EntityType.key == clean_key
        )
    )
    if existing is not None:
        raise ApiError(409, "entity_type_exists", f"Entity type '{clean_key}' already exists.")

    schema = normalize_custom_field_schema(data.schema_json)
    validate_entity_reference_types(
        db, universe_id, schema, extra_keys={clean_key}
    )

    entity_type = EntityType(
        id=uuid.uuid4(),
        universe_id=universe_id,
        key=clean_key,
        name=data.name.strip(),
        description=data.description.strip() if data.description else None,
        schema_json=schema,
        icon=data.icon,
        color=data.color,
        is_system=False,
    )
    db.add(entity_type)
    record_audit(
        db,
        universe_id,
        user.id,
        "entity_type.create",
        "entity_type",
        entity_type.id,
        request_id=request_id,
    )
    db.commit()
    return entity_type


def update_entity_type(
    db: Session,
    universe_id: uuid.UUID,
    type_id: uuid.UUID,
    user: User,
    data: EntityTypeUpdate,
    request_id: str | None = None,
) -> EntityType:
    check_universe_access(db, universe_id, user, Action.ENTITY_TYPE_MANAGE)
    entity_type = db.get(EntityType, type_id)
    if entity_type is None or entity_type.universe_id != universe_id:
        raise ApiError(404, "entity_type_not_found", "Entity type not found.")

    if data.name is not None:
        entity_type.name = data.name.strip()
    if data.description is not None:
        entity_type.description = data.description.strip()
    if data.schema_json is not None:
        schema = normalize_custom_field_schema(data.schema_json)
        validate_entity_reference_types(
            db, universe_id, schema, extra_keys={entity_type.key}
        )
        entity_type.schema_json = schema
    if data.icon is not None:
        entity_type.icon = data.icon
    if data.color is not None:
        entity_type.color = data.color

    entity_type.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        universe_id,
        user.id,
        "entity_type.update",
        "entity_type",
        entity_type.id,
        request_id=request_id,
    )
    db.commit()
    return entity_type


# -----------------------------------------------------------------------------
# Relation Types Service
# -----------------------------------------------------------------------------

def list_relation_types(
    db: Session, universe_id: uuid.UUID, user: User
) -> list[RelationType]:
    check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    ensure_system_types(db, universe_id)
    stmt = (
        select(RelationType)
        .where(RelationType.universe_id == universe_id)
        .order_by(RelationType.label.asc())
    )
    return list(db.scalars(stmt).all())


def create_relation_type(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    data: RelationTypeCreate,
    request_id: str | None = None,
) -> RelationType:
    check_universe_access(db, universe_id, user, Action.ENTITY_TYPE_MANAGE)
    ensure_system_types(db, universe_id)
    clean_key = slugify(data.key).replace("-", "_")
    existing = db.scalar(
        select(RelationType).where(
            RelationType.universe_id == universe_id, RelationType.key == clean_key
        )
    )
    if existing is not None:
        raise ApiError(409, "relation_type_exists", f"Relation type '{clean_key}' already exists.")

    allowed_source_types = list(dict.fromkeys(data.allowed_source_types))
    allowed_target_types = list(dict.fromkeys(data.allowed_target_types))
    referenced_keys = set(allowed_source_types) | set(allowed_target_types)
    if referenced_keys:
        existing_keys = set(
            db.scalars(
                select(EntityType.key).where(
                    EntityType.universe_id == universe_id,
                    EntityType.key.in_(referenced_keys),
                )
            ).all()
        )
        missing = sorted(referenced_keys - existing_keys)
        if missing:
            raise ApiError(
                422,
                "validation_error",
                "Relation type references unknown entity types.",
                details={
                    "fields": [
                        {
                            "field": "allowed_source_types/allowed_target_types",
                            "code": "entity_type_not_found",
                            "keys": missing,
                        }
                    ]
                },
            )

    rel_type = RelationType(
        id=uuid.uuid4(),
        universe_id=universe_id,
        key=clean_key,
        label=data.label.strip(),
        inverse_label=data.inverse_label.strip() if data.inverse_label else None,
        description=data.description.strip() if data.description else None,
        allowed_source_types=allowed_source_types,
        allowed_target_types=allowed_target_types,
        is_directional=data.is_directional,
        is_symmetric=data.is_symmetric,
    )
    db.add(rel_type)
    record_audit(
        db,
        universe_id,
        user.id,
        "relation_type.create",
        "relation_type",
        rel_type.id,
        request_id=request_id,
    )
    db.commit()
    return rel_type


# -----------------------------------------------------------------------------
# Entities Service
# -----------------------------------------------------------------------------

def _get_entity_tags(db: Session, entity_id: uuid.UUID) -> list[str]:
    stmt = (
        select(Tag.name)
        .join(EntityTag, EntityTag.tag_id == Tag.id)
        .where(EntityTag.entity_id == entity_id)
        .order_by(Tag.name.asc())
    )
    return list(db.scalars(stmt).all())


def _sync_entity_tags(
    db: Session, universe_id: uuid.UUID, entity_id: uuid.UUID, tag_names: list[str]
) -> None:
    # Clear existing
    db.execute(delete(EntityTag).where(EntityTag.entity_id == entity_id))
    seen_slugs: set[str] = set()
    for name in tag_names:
        clean_name = name.strip()
        if not clean_name:
            continue
        tag_slug = slugify(clean_name)
        if tag_slug in seen_slugs:
            continue
        seen_slugs.add(tag_slug)
        tag = db.scalar(
            select(Tag).where(Tag.universe_id == universe_id, Tag.slug == tag_slug)
        )
        if tag is None:
            tag = Tag(id=uuid.uuid4(), universe_id=universe_id, name=clean_name, slug=tag_slug)
            db.add(tag)
            db.flush()
        db.add(EntityTag(entity_id=entity_id, tag_id=tag.id))


def _entity_to_dict(db: Session, entity: Entity, entity_type: EntityType) -> dict[str, Any]:
    return {
        "id": entity.id,
        "universe_id": entity.universe_id,
        "entity_type_id": entity.entity_type_id,
        "entity_type_key": entity_type.key,
        "entity_type_name": entity_type.name,
        "title": entity.title,
        "slug": entity.slug,
        "summary": entity.summary,
        "custom_fields": entity.custom_fields,
        "status": entity.status,
        "visibility": entity.visibility,
        "created_by": entity.created_by,
        "updated_by": entity.updated_by,
        "version": entity.version,
        "tags": _get_entity_tags(db, entity.id),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


def list_entities(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    type_key: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    ensure_system_types(db, universe_id)

    base = (
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    )
    count_stmt = (
        select(func.count(Entity.id))
        .select_from(Entity)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    )
    visibility = visible_clause(Entity, user.id, membership.role)
    if visibility is not None:
        base = base.where(visibility)
        count_stmt = count_stmt.where(visibility)
    if tag:
        tag_slug = slugify(tag)
        base = base.join(EntityTag, EntityTag.entity_id == Entity.id).join(
            Tag, Tag.id == EntityTag.tag_id
        ).where(Tag.universe_id == universe_id, Tag.slug == tag_slug)
        count_stmt = count_stmt.join(
            EntityTag, EntityTag.entity_id == Entity.id
        ).join(Tag, Tag.id == EntityTag.tag_id).where(
            Tag.universe_id == universe_id, Tag.slug == tag_slug
        )
    if type_key:
        base = base.where(EntityType.key == type_key)
        count_stmt = count_stmt.where(EntityType.key == type_key)
    if status:
        base = base.where(Entity.status == status)
        count_stmt = count_stmt.where(Entity.status == status)
    if search:
        pattern = f"%{search.strip().lower()}%"
        predicate = (Entity.title.ilike(pattern)) | (Entity.summary.ilike(pattern))
        base = base.where(predicate)
        count_stmt = count_stmt.where(predicate)

    total = int(db.scalar(count_stmt) or 0)
    stmt = (
        base.order_by(Entity.title.asc(), Entity.id.asc())
        .limit(min(limit, 500))
        .offset(max(offset, 0))
    )
    results = db.execute(stmt).all()
    return [_entity_to_dict(db, e, et) for e, et in results], total


def create_entity(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    data: EntityCreate,
    request_id: str | None = None,
) -> dict[str, Any]:
    check_universe_access(db, universe_id, user, Action.ENTITY_CREATE)
    ensure_system_types(db, universe_id)

    entity_type = db.scalar(
        select(EntityType).where(
            EntityType.universe_id == universe_id,
            EntityType.key == data.entity_type_key,
        )
    )
    if entity_type is None:
        raise ApiError(404, "entity_type_not_found", f"Entity type '{data.entity_type_key}' not found.")

    schema = normalize_custom_field_schema(entity_type.schema_json)
    custom_fields = validate_custom_field_values(
        db, universe_id, schema, data.custom_fields
    )

    base_slug = slugify(data.slug or data.title)
    slug = base_slug
    counter = 1
    while (
        db.scalar(
            select(Entity.id).where(
                Entity.universe_id == universe_id,
                Entity.entity_type_id == entity_type.id,
                Entity.slug == slug,
            )
        )
        is not None
    ):
        slug = f"{base_slug}-{counter}"
        counter += 1

    entity = Entity(
        id=uuid.uuid4(),
        universe_id=universe_id,
        entity_type_id=entity_type.id,
        title=data.title.strip(),
        slug=slug,
        summary=data.summary.strip() if data.summary else None,
        custom_fields=custom_fields,
        status=data.status,
        visibility=data.visibility,
        created_by=user.id,
        updated_by=user.id,
        version=1,
    )
    db.add(entity)
    db.flush()

    if data.tags:
        _sync_entity_tags(db, universe_id, entity.id, data.tags)

    record_audit(
        db,
        universe_id,
        user.id,
        "entity.create",
        "entity",
        entity.id,
        request_id=request_id,
    )
    record_activity(
        db,
        universe_id,
        user.id,
        "entity.created",
        "entity",
        entity.id,
        {"title": entity.title, "type": entity_type.key},
    )
    db.commit()

    return _entity_to_dict(db, entity, entity_type)


def get_entity_details(
    db: Session, universe_id: uuid.UUID, entity_id: uuid.UUID, user: User
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    result = db.execute(
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            Entity.id == entity_id,
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    ).first()
    if result is None:
        raise ApiError(404, "entity_not_found", "Entity not found or has been deleted.")

    entity, entity_type = result
    if not is_visible(entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Entity not found or has been deleted.")
    return _entity_to_dict(db, entity, entity_type)


def update_entity(
    db: Session,
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    user: User,
    data: EntityUpdate,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_UPDATE)
    result = db.execute(
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            Entity.id == entity_id,
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    ).first()
    if result is None:
        raise ApiError(404, "entity_not_found", "Entity not found.")

    entity, entity_type = result
    if not is_visible(entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Entity not found.")

    # Precondition: Optimistic concurrency check
    if entity.version != data.expected_version:
        raise ApiError(
            409,
            "version_conflict",
            f"Version conflict: expected version {data.expected_version}, but entity has version {entity.version}.",
            details={"current_version": entity.version},
        )

    if data.title is not None:
        entity.title = data.title.strip()
    if data.summary is not None:
        entity.summary = data.summary.strip()
    if data.custom_fields is not None:
        schema = normalize_custom_field_schema(entity_type.schema_json)
        entity.custom_fields = validate_custom_field_values(
            db, universe_id, schema, data.custom_fields
        )
    if data.status is not None:
        entity.status = data.status
    if data.visibility is not None:
        entity.visibility = data.visibility

    if data.tags is not None:
        _sync_entity_tags(db, universe_id, entity.id, data.tags)

    entity.version += 1
    entity.updated_by = user.id
    entity.updated_at = datetime.now(timezone.utc)

    record_audit(
        db,
        universe_id,
        user.id,
        "entity.update",
        "entity",
        entity.id,
        request_id=request_id,
    )
    db.commit()

    return _entity_to_dict(db, entity, entity_type)


def delete_entity(
    db: Session,
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_DELETE)
    entity = db.scalar(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    )
    if entity is None or not is_visible(entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Entity not found.")

    # Soft delete
    entity.deleted_at = datetime.now(timezone.utc)
    record_audit(
        db,
        universe_id,
        user.id,
        "entity.delete",
        "entity",
        entity.id,
        request_id=request_id,
    )
    db.commit()


def restore_entity(
    db: Session,
    universe_id: uuid.UUID,
    entity_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_RESTORE)
    result = db.execute(
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            Entity.id == entity_id,
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_not(None),
        )
    ).first()
    if result is None:
        raise ApiError(404, "entity_not_found", "Deleted entity not found.")

    entity, entity_type = result
    if not is_visible(entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Deleted entity not found.")
    entity.deleted_at = None
    entity.updated_at = datetime.now(timezone.utc)
    record_audit(
        db,
        universe_id,
        user.id,
        "entity.restore",
        "entity",
        entity.id,
        request_id=request_id,
    )
    db.commit()
    return _entity_to_dict(db, entity, entity_type)


# -----------------------------------------------------------------------------
# Relations Service
# -----------------------------------------------------------------------------

def create_relation(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    source_entity_id: uuid.UUID,
    relation_type_key: str,
    target_entity_id: uuid.UUID,
    attributes: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.RELATION_CREATE)

    # 1. Source entity verification
    source_res = db.execute(
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(Entity.id == source_entity_id, Entity.deleted_at.is_(None))
    ).first()
    if source_res is None or source_res[0].universe_id != universe_id:
        raise ApiError(400, "invalid_source_entity", "Source entity does not belong to this universe.")
    source_entity, source_type = source_res
    if not is_visible(source_entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Source entity not found.")

    # 2. Target entity verification (MUST BE SAME UNIVERSE)
    target_res = db.execute(
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(Entity.id == target_entity_id, Entity.deleted_at.is_(None))
    ).first()
    if target_res is None or target_res[0].universe_id != universe_id:
        raise ApiError(400, "invalid_target_entity", "Target entity must belong to the same universe. Cross-universe relations are prohibited.")
    target_entity, target_type = target_res
    if not is_visible(target_entity, user.id, membership.role):
        raise ApiError(404, "entity_not_found", "Target entity not found.")

    # 3. Relation type verification
    rel_type = db.scalar(
        select(RelationType).where(
            RelationType.universe_id == universe_id,
            RelationType.key == relation_type_key,
        )
    )
    if rel_type is None:
        raise ApiError(404, "relation_type_not_found", f"Relation type '{relation_type_key}' not found.")

    if source_entity.id == target_entity.id:
        raise ApiError(
            400,
            "self_relation_not_allowed",
            "An entity cannot be related to itself.",
        )

    duplicate_stmt = select(EntityRelation.id).where(
        EntityRelation.universe_id == universe_id,
        EntityRelation.relation_type_id == rel_type.id,
        EntityRelation.deleted_at.is_(None),
        EntityRelation.source_entity_id == source_entity.id,
        EntityRelation.target_entity_id == target_entity.id,
    )
    if rel_type.is_symmetric:
        duplicate_stmt = select(EntityRelation.id).where(
            EntityRelation.universe_id == universe_id,
            EntityRelation.relation_type_id == rel_type.id,
            EntityRelation.deleted_at.is_(None),
            (
                (
                    (EntityRelation.source_entity_id == source_entity.id)
                    & (EntityRelation.target_entity_id == target_entity.id)
                )
                | (
                    (EntityRelation.source_entity_id == target_entity.id)
                    & (EntityRelation.target_entity_id == source_entity.id)
                )
            ),
        )
    if db.scalar(duplicate_stmt) is not None:
        raise ApiError(
            409,
            "relation_exists",
            "This relation already exists.",
        )

    # 4. Type constraint enforcement
    if rel_type.allowed_source_types and source_type.key not in rel_type.allowed_source_types:
        raise ApiError(
            400,
            "type_constraint_violation",
            f"Entity type '{source_type.key}' is not allowed as source for relation '{relation_type_key}'.",
        )
    if rel_type.allowed_target_types and target_type.key not in rel_type.allowed_target_types:
        raise ApiError(
            400,
            "type_constraint_violation",
            f"Entity type '{target_type.key}' is not allowed as target for relation '{relation_type_key}'.",
        )

    relation = EntityRelation(
        id=uuid.uuid4(),
        universe_id=universe_id,
        source_entity_id=source_entity.id,
        relation_type_id=rel_type.id,
        target_entity_id=target_entity.id,
        attributes_json=attributes or {},
        created_by=user.id,
    )
    db.add(relation)
    record_audit(
        db,
        universe_id,
        user.id,
        "relation.create",
        "relation",
        relation.id,
        request_id=request_id,
    )
    db.commit()

    return {
        "id": relation.id,
        "universe_id": relation.universe_id,
        "source_entity_id": source_entity.id,
        "source_entity_title": source_entity.title,
        "relation_type_id": rel_type.id,
        "relation_type_key": rel_type.key,
        "relation_label": rel_type.label,
        "inverse_label": rel_type.inverse_label,
        "is_symmetric": rel_type.is_symmetric,
        "target_entity_id": target_entity.id,
        "target_entity_title": target_entity.title,
        "attributes_json": relation.attributes_json,
        "created_by": relation.created_by,
        "created_at": relation.created_at,
    }


def list_entity_relations(
    db: Session, universe_id: uuid.UUID, entity_id: uuid.UUID, user: User
) -> list[dict[str, Any]]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    focus_entity = db.scalar(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
    )
    if focus_entity is None or not is_visible(
        focus_entity, user.id, membership.role
    ):
        raise ApiError(404, "entity_not_found", "Entity not found.")
    source = aliased(Entity)
    target = aliased(Entity)
    conditions = [
        EntityRelation.universe_id == universe_id,
        EntityRelation.deleted_at.is_(None),
        source.universe_id == universe_id,
        target.universe_id == universe_id,
        source.deleted_at.is_(None),
        target.deleted_at.is_(None),
        (EntityRelation.source_entity_id == entity_id)
        | (EntityRelation.target_entity_id == entity_id),
    ]
    source_visibility = visible_clause(source, user.id, membership.role)
    if source_visibility is not None:
        conditions.append(source_visibility)
    target_visibility = visible_clause(target, user.id, membership.role)
    if target_visibility is not None:
        conditions.append(target_visibility)
    stmt = (
        select(EntityRelation, RelationType, source, target)
        .join(RelationType, RelationType.id == EntityRelation.relation_type_id)
        .join(source, source.id == EntityRelation.source_entity_id)
        .join(target, target.id == EntityRelation.target_entity_id)
        .where(*conditions)
        .order_by(EntityRelation.created_at.asc())
    )
    results = []
    for rel, rt, src, tgt in db.execute(stmt).all():
        results.append(
            {
                "id": rel.id,
                "universe_id": rel.universe_id,
                "source_entity_id": src.id,
                "source_entity_title": src.title,
                "relation_type_id": rt.id,
                "relation_type_key": rt.key,
                "relation_label": rt.label,
                "inverse_label": rt.inverse_label,
                "is_symmetric": rt.is_symmetric,
                "target_entity_id": tgt.id,
                "target_entity_title": tgt.title,
                "attributes_json": rel.attributes_json,
                "created_by": rel.created_by,
                "created_at": rel.created_at,
            }
        )
    return results


def delete_relation(
    db: Session,
    universe_id: uuid.UUID,
    relation_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    check_universe_access(db, universe_id, user, Action.RELATION_DELETE)
    relation = db.scalar(
        select(EntityRelation).where(
            EntityRelation.id == relation_id,
            EntityRelation.universe_id == universe_id,
        )
    )
    if relation is None:
        raise ApiError(404, "relation_not_found", "Relation not found.")

    db.delete(relation)
    record_audit(
        db,
        universe_id,
        user.id,
        "relation.delete",
        "relation",
        relation.id,
        request_id=request_id,
    )
    db.commit()


# -----------------------------------------------------------------------------
# Nexus Graph Service
# -----------------------------------------------------------------------------

def query_graph(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    focus_entity_id: uuid.UUID | None = None,
    depth: int = 1,
    type_keys: list[str] | None = None,
    entity_type_ids: list[uuid.UUID] | None = None,
    relation_type_ids: list[uuid.UUID] | None = None,
    limit: int = 150,
) -> dict[str, Any]:
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    depth = max(1, min(depth, 3))
    limit = max(10, min(limit, 500))

    # Fetch all active non-deleted entities and types visible to the actor.
    ent_stmt = (
        select(Entity, EntityType)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .where(
            Entity.universe_id == universe_id,
            Entity.deleted_at.is_(None),
        )
        .order_by(Entity.title.asc())
    )
    visibility = visible_clause(Entity, user.id, membership.role)
    if visibility is not None:
        ent_stmt = ent_stmt.where(visibility)
    if type_keys:
        ent_stmt = ent_stmt.where(EntityType.key.in_(type_keys))
    if entity_type_ids:
        ent_stmt = ent_stmt.where(EntityType.id.in_(entity_type_ids))

    all_entities_res = db.execute(ent_stmt).all()
    entity_map = {e.id: (e, et) for e, et in all_entities_res}

    # Fetch active relations
    rel_stmt = (
        select(EntityRelation, RelationType)
        .join(RelationType, RelationType.id == EntityRelation.relation_type_id)
        .where(
            EntityRelation.universe_id == universe_id,
            EntityRelation.deleted_at.is_(None),
        )
        .order_by(EntityRelation.created_at.asc())
    )
    if relation_type_ids:
        rel_stmt = rel_stmt.where(RelationType.id.in_(relation_type_ids))
    all_relations = db.execute(rel_stmt).all()

    if focus_entity_id is not None and focus_entity_id not in entity_map:
        raise ApiError(
            404,
            "entity_not_found",
            "The focus entity does not exist in this universe or graph scope.",
        )

    nodes_included: set[uuid.UUID] = set()
    edges_included: list[tuple[EntityRelation, RelationType]] = []
    seen_edge_ids: set[uuid.UUID] = set()

    def include_edge(relation: EntityRelation, relation_type: RelationType) -> None:
        if relation.id in seen_edge_ids:
            return
        seen_edge_ids.add(relation.id)
        edges_included.append((relation, relation_type))

    if focus_entity_id is not None:
        nodes_included.add(focus_entity_id)
        frontier = {focus_entity_id}
        for _ in range(depth):
            next_frontier: set[uuid.UUID] = set()
            for r, rt in all_relations:
                if (
                    r.source_entity_id in frontier
                    and r.target_entity_id in entity_map
                    and len(nodes_included) < limit
                ):
                    nodes_included.add(r.target_entity_id)
                    next_frontier.add(r.target_entity_id)
                    include_edge(r, rt)
                elif (
                    r.target_entity_id in frontier
                    and r.source_entity_id in entity_map
                    and len(nodes_included) < limit
                ):
                    nodes_included.add(r.source_entity_id)
                    next_frontier.add(r.source_entity_id)
                    include_edge(r, rt)
            frontier = next_frontier
            if not frontier:
                break
    else:
        # Take up to limit entities, then include only fully-scoped edges.
        for entity, _ in all_entities_res[:limit]:
            nodes_included.add(entity.id)
        for r, rt in all_relations:
            if (
                r.source_entity_id in nodes_included
                and r.target_entity_id in nodes_included
            ):
                include_edge(r, rt)

    nodes = sorted(
        (
            {
                "id": str(eid),
                "title": entity_map[eid][0].title,
                "entity_type_key": entity_map[eid][1].key,
                "entity_type_name": entity_map[eid][1].name,
                "summary": entity_map[eid][0].summary,
                "color": entity_map[eid][1].color,
                "icon": entity_map[eid][1].icon,
            }
            for eid in nodes_included
            if eid in entity_map
        ),
        key=lambda node: (node["title"].casefold(), node["id"]),
    )

    edges = []
    for r, rt in edges_included:
        if (
            r.source_entity_id in entity_map
            and r.target_entity_id in entity_map
            and r.source_entity_id in nodes_included
            and r.target_entity_id in nodes_included
        ):
            edges.append(
                {
                    "id": str(r.id),
                    "source": str(r.source_entity_id),
                    "target": str(r.target_entity_id),
                    "relation_type_key": rt.key,
                    "label": rt.label,
                    "inverse_label": rt.inverse_label,
                }
            )

    return {"nodes": nodes, "edges": edges}
