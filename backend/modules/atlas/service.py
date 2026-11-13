from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import Asset, Entity, Map, MapMarker, MapRegion, User
from backend.core.permissions import Action
from backend.core.security import state_hash
from backend.core.visibility import is_visible
from backend.modules.atlas.schemas import (
    MapCreate,
    MapMarkerCreate,
    MapMarkerUpdate,
    MapRegionCreate,
    MapRegionUpdate,
    MapUpdate,
)
from backend.modules.universes.service import (
    check_universe_access,
    record_activity,
    record_audit,
)


def _check_asset(db: Session, universe_id: uuid.UUID, asset_id: uuid.UUID | None) -> None:
    if asset_id is None:
        return
    asset = db.get(Asset, asset_id)
    if (
        asset is None
        or asset.universe_id != universe_id
        or asset.deleted_at is not None
    ):
        raise ApiError(404, "asset_not_found", "The requested asset does not exist in this universe.")


def _check_entity(
    db: Session, universe_id: uuid.UUID, user: User, entity_id: uuid.UUID | None
) -> None:
    if entity_id is None:
        return
    _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
    entity = db.get(Entity, entity_id)
    if (
        entity is None
        or entity.universe_id != universe_id
        or entity.deleted_at is not None
        or not is_visible(entity, user.id, membership.role)
    ):
        raise ApiError(404, "entity_not_found", "The linked entity does not exist or is not visible.")


def _get_map(
    db: Session, universe_id: uuid.UUID, map_id: uuid.UUID, user: User, action: str
) -> Map:
    check_universe_access(db, universe_id, user, action)
    map_record = db.scalar(
        select(Map).where(Map.id == map_id, Map.universe_id == universe_id)
    )
    if map_record is None:
        raise ApiError(404, "map_not_found", "The requested map does not exist.")
    return map_record


def list_maps(db: Session, universe_id: uuid.UUID, user: User, limit: int, offset: int):
    check_universe_access(db, universe_id, user, Action.MAP_READ)
    items = list(
        db.scalars(
            select(Map)
            .where(Map.universe_id == universe_id)
            .order_by(Map.updated_at.desc(), Map.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = db.scalar(
        select(func.count()).select_from(Map).where(Map.universe_id == universe_id)
    ) or 0
    return items, total


def get_map(db: Session, universe_id: uuid.UUID, map_id: uuid.UUID, user: User) -> Map:
    return _get_map(db, universe_id, map_id, user, Action.MAP_READ)


def create_map(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    payload: MapCreate,
    request_id: str | None = None,
) -> Map:
    check_universe_access(db, universe_id, user, Action.MAP_CREATE)
    _check_asset(db, universe_id, payload.image_asset_id)
    record = Map(
        id=uuid.uuid4(),
        universe_id=universe_id,
        title=payload.title.strip(),
        description=payload.description,
        image_asset_id=payload.image_asset_id,
        width=payload.width,
        height=payload.height,
        created_by=user.id,
    )
    db.add(record)
    record_audit(
        db, universe_id, user.id, "map.created", "map", record.id,
        after_hash=state_hash({"title": record.title}), request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map.created", "map", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_map(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    user: User,
    payload: MapUpdate,
    request_id: str | None = None,
) -> Map:
    record = _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    if record.version != payload.expected_version:
        raise ApiError(409, "version_conflict", "The map changed; refresh before saving.")
    _check_asset(db, universe_id, payload.image_asset_id)
    before = {
        "title": record.title,
        "description": record.description,
        "image_asset_id": str(record.image_asset_id) if record.image_asset_id else None,
        "width": record.width,
        "height": record.height,
        "version": record.version,
    }
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for name, value in values.items():
        if name == "title" and value is not None:
            value = value.strip()
        setattr(record, name, value)
    record.version += 1
    record_audit(
        db, universe_id, user.id, "map.updated", "map", record.id,
        before_hash=state_hash(before),
        after_hash=state_hash({**before, **values, "version": record.version}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map.updated", "map", record.id)
    db.commit()
    db.refresh(record)
    return record


def delete_map(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    record = _get_map(db, universe_id, map_id, user, Action.MAP_DELETE)
    record_audit(
        db, universe_id, user.id, "map.deleted", "map", record.id,
        before_hash=state_hash({"title": record.title, "version": record.version}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map.deleted", "map", record.id)
    db.delete(record)
    db.commit()


def list_markers(
    db: Session, universe_id: uuid.UUID, map_id: uuid.UUID, user: User
) -> tuple[list[MapMarker], int]:
    _get_map(db, universe_id, map_id, user, Action.MAP_READ)
    items = list(
        db.scalars(
            select(MapMarker)
            .where(MapMarker.universe_id == universe_id, MapMarker.map_id == map_id)
            .order_by(MapMarker.title, MapMarker.id)
        ).all()
    )
    return items, len(items)


def create_marker(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    user: User,
    payload: MapMarkerCreate,
    request_id: str | None = None,
) -> MapMarker:
    _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    _check_entity(db, universe_id, user, payload.linked_entity_id)
    record = MapMarker(
        id=uuid.uuid4(),
        map_id=map_id,
        universe_id=universe_id,
        title=payload.title.strip(),
        description=payload.description,
        x_norm=payload.x_norm,
        y_norm=payload.y_norm,
        marker_type=payload.marker_type,
        linked_entity_id=payload.linked_entity_id,
        style_json=payload.style_json,
        created_by=user.id,
    )
    db.add(record)
    record_audit(
        db, universe_id, user.id, "map_marker.created", "map_marker", record.id,
        after_hash=state_hash({"map_id": str(map_id), "x": record.x_norm, "y": record.y_norm}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map_marker.created", "map_marker", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_marker(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    marker_id: uuid.UUID,
    user: User,
    payload: MapMarkerUpdate,
    request_id: str | None = None,
) -> MapMarker:
    _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    record = db.scalar(
        select(MapMarker).where(
            MapMarker.id == marker_id,
            MapMarker.map_id == map_id,
            MapMarker.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "map_marker_not_found", "The requested marker does not exist.")
    if record.version != payload.expected_version:
        raise ApiError(409, "version_conflict", "The marker changed; refresh before saving.")
    _check_entity(db, universe_id, user, payload.linked_entity_id)
    before = {
        "title": record.title,
        "x": record.x_norm,
        "y": record.y_norm,
        "version": record.version,
    }
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for name, value in values.items():
        if name == "title" and value is not None:
            value = value.strip()
        setattr(record, name, value)
    record.version += 1
    record_audit(
        db, universe_id, user.id, "map_marker.updated", "map_marker", record.id,
        before_hash=state_hash(before),
        after_hash=state_hash({"title": record.title, "x": record.x_norm, "y": record.y_norm, "version": record.version}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map_marker.updated", "map_marker", record.id)
    db.commit()
    db.refresh(record)
    return record


def delete_marker(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    marker_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    record = db.scalar(
        select(MapMarker).where(
            MapMarker.id == marker_id,
            MapMarker.map_id == map_id,
            MapMarker.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "map_marker_not_found", "The requested marker does not exist.")
    record_audit(
        db, universe_id, user.id, "map_marker.deleted", "map_marker", record.id,
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map_marker.deleted", "map_marker", record.id)
    db.delete(record)
    db.commit()


def list_regions(
    db: Session, universe_id: uuid.UUID, map_id: uuid.UUID, user: User
) -> tuple[list[MapRegion], int]:
    _get_map(db, universe_id, map_id, user, Action.MAP_READ)
    items = list(
        db.scalars(
            select(MapRegion)
            .where(MapRegion.universe_id == universe_id, MapRegion.map_id == map_id)
            .order_by(MapRegion.title, MapRegion.id)
        ).all()
    )
    return items, len(items)


def create_region(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    user: User,
    payload: MapRegionCreate,
    request_id: str | None = None,
) -> MapRegion:
    _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    _check_entity(db, universe_id, user, payload.linked_entity_id)
    record = MapRegion(
        id=uuid.uuid4(),
        map_id=map_id,
        universe_id=universe_id,
        title=payload.title.strip(),
        geometry_json=payload.geometry_json.model_dump(),
        linked_entity_id=payload.linked_entity_id,
        style_json=payload.style_json,
    )
    db.add(record)
    record_audit(
        db, universe_id, user.id, "map_region.created", "map_region", record.id,
        after_hash=state_hash(record.geometry_json), request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map_region.created", "map_region", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_region(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    region_id: uuid.UUID,
    user: User,
    payload: MapRegionUpdate,
    request_id: str | None = None,
) -> MapRegion:
    _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    record = db.scalar(
        select(MapRegion).where(
            MapRegion.id == region_id,
            MapRegion.map_id == map_id,
            MapRegion.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "map_region_not_found", "The requested region does not exist.")
    if record.version != payload.expected_version:
        raise ApiError(409, "version_conflict", "The region changed; refresh before saving.")
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "linked_entity_id" in values:
        _check_entity(db, universe_id, user, values["linked_entity_id"])
    before = {
        "title": record.title,
        "geometry_json": record.geometry_json,
        "linked_entity_id": str(record.linked_entity_id) if record.linked_entity_id else None,
        "style_json": record.style_json,
        "version": record.version,
    }
    for name, value in values.items():
        if name == "title" and value is not None:
            value = value.strip()
        elif name == "geometry_json" and value is not None:
            value = value.model_dump()
        setattr(record, name, value)
    record.version += 1
    after = {
        "title": record.title,
        "geometry_json": record.geometry_json,
        "linked_entity_id": str(record.linked_entity_id) if record.linked_entity_id else None,
        "style_json": record.style_json,
        "version": record.version,
    }
    record_audit(
        db, universe_id, user.id, "map_region.updated", "map_region", record.id,
        before_hash=state_hash(before), after_hash=state_hash(after), request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map_region.updated", "map_region", record.id)
    db.commit()
    db.refresh(record)
    return record


def delete_region(
    db: Session,
    universe_id: uuid.UUID,
    map_id: uuid.UUID,
    region_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    _get_map(db, universe_id, map_id, user, Action.MAP_UPDATE)
    record = db.scalar(
        select(MapRegion).where(
            MapRegion.id == region_id,
            MapRegion.map_id == map_id,
            MapRegion.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "map_region_not_found", "The requested region does not exist.")
    record_audit(
        db, universe_id, user.id, "map_region.deleted", "map_region", record.id,
        before_hash=state_hash({"title": record.title, "geometry_json": record.geometry_json}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "map_region.deleted", "map_region", record.id)
    db.delete(record)
    db.commit()


def get_asset(db: Session, universe_id: uuid.UUID, asset_id: uuid.UUID, user: User) -> Asset:
    check_universe_access(db, universe_id, user, Action.MAP_READ)
    asset = db.get(Asset, asset_id)
    if asset is None or asset.universe_id != universe_id or asset.deleted_at is not None:
        raise ApiError(404, "asset_not_found", "The requested asset does not exist.")
    return asset
