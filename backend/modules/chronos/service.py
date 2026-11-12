from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import Calendar, Document, Entity, Era, TimelineEvent, User
from backend.core.permissions import Action
from backend.core.security import state_hash
from backend.core.visibility import is_visible
from backend.modules.chronos.calendar_engine import event_day_window
from backend.modules.chronos.schemas import (
    CalendarConfiguration,
    CalendarCreate,
    CalendarDate,
    CalendarUpdate,
    EraCreate,
    EraUpdate,
    TimelineEventCreate,
    TimelineEventUpdate,
)
from backend.modules.universes.service import (
    check_universe_access,
    record_activity,
    record_audit,
)


def _get_calendar(
    db: Session, universe_id: uuid.UUID, calendar_id: uuid.UUID, user: User, action: str
) -> Calendar:
    check_universe_access(db, universe_id, user, action)
    record = db.scalar(
        select(Calendar).where(
            Calendar.id == calendar_id,
            Calendar.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "calendar_not_found", "The requested calendar does not exist.")
    return record


def _configuration(calendar: Calendar) -> CalendarConfiguration:
    try:
        return CalendarConfiguration.model_validate(calendar.config_json)
    except Exception as exc:
        raise ApiError(
            409,
            "calendar_configuration_invalid",
            "The calendar configuration needs to be repaired before it can be used.",
        ) from exc


def _check_links(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    entity_id: uuid.UUID | None,
    document_id: uuid.UUID | None,
) -> None:
    if entity_id is not None:
        _, membership = check_universe_access(db, universe_id, user, Action.ENTITY_READ)
        entity = db.get(Entity, entity_id)
        if (
            entity is None
            or entity.universe_id != universe_id
            or entity.deleted_at is not None
            or not is_visible(entity, user.id, membership.role)
        ):
            raise ApiError(404, "entity_not_found", "The linked entity does not exist or is not visible.")
    if document_id is not None:
        _, membership = check_universe_access(
            db, universe_id, user, Action.DOCUMENT_READ
        )
        document = db.get(Document, document_id)
        if (
            document is None
            or document.universe_id != universe_id
            or document.deleted_at is not None
            or not is_visible(document, user.id, membership.role)
        ):
            raise ApiError(404, "document_not_found", "The linked document does not exist or is not visible.")


def list_calendars(
    db: Session, universe_id: uuid.UUID, user: User, limit: int, offset: int
) -> tuple[list[Calendar], int]:
    check_universe_access(db, universe_id, user, Action.TIMELINE_READ)
    items = list(
        db.scalars(
            select(Calendar)
            .where(Calendar.universe_id == universe_id)
            .order_by(Calendar.name, Calendar.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = db.scalar(
        select(func.count()).select_from(Calendar).where(Calendar.universe_id == universe_id)
    ) or 0
    return items, total


def get_calendar(
    db: Session, universe_id: uuid.UUID, calendar_id: uuid.UUID, user: User
) -> Calendar:
    return _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_READ)


def create_calendar(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    payload: CalendarCreate,
    request_id: str | None = None,
) -> Calendar:
    check_universe_access(db, universe_id, user, Action.TIMELINE_CREATE)
    record = Calendar(
        id=uuid.uuid4(),
        universe_id=universe_id,
        name=payload.name.strip(),
        description=payload.description,
        config_json=payload.config_json.model_dump(mode="json"),
        created_by=user.id,
    )
    db.add(record)
    record_audit(
        db, universe_id, user.id, "calendar.created", "calendar", record.id,
        after_hash=state_hash({"name": record.name, "config": record.config_json}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "calendar.created", "calendar", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_calendar(
    db: Session,
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    user: User,
    payload: CalendarUpdate,
    request_id: str | None = None,
) -> Calendar:
    record = _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_UPDATE)
    if record.version != payload.expected_version:
        raise ApiError(409, "version_conflict", "The calendar changed; refresh before saving.")

    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "config_json" in values and values["config_json"] is not None:
        new_config = payload.config_json.model_dump(mode="json")
        if new_config != record.config_json:
            event_count = db.scalar(
                select(func.count())
                .select_from(TimelineEvent)
                .where(TimelineEvent.calendar_id == calendar_id)
            ) or 0
            if event_count:
                raise ApiError(
                    409,
                    "calendar_in_use",
                    "Create a new calendar to change its rules after timeline events exist.",
                )
            values["config_json"] = new_config

    before = {
        "name": record.name,
        "description": record.description,
        "config_json": record.config_json,
        "version": record.version,
    }
    for name, value in values.items():
        if name == "name" and value is not None:
            value = value.strip()
        setattr(record, name, value)
    record.version += 1
    record_audit(
        db, universe_id, user.id, "calendar.updated", "calendar", record.id,
        before_hash=state_hash(before),
        after_hash=state_hash(
            {
                "name": record.name,
                "description": record.description,
                "config_json": record.config_json,
                "version": record.version,
            }
        ),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "calendar.updated", "calendar", record.id)
    db.commit()
    db.refresh(record)
    return record


def list_eras(
    db: Session,
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    user: User,
) -> tuple[list[Era], int]:
    _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_READ)
    items = list(
        db.scalars(
            select(Era)
            .where(Era.calendar_id == calendar_id)
            .order_by(Era.start_day_index, Era.name, Era.id)
        ).all()
    )
    return items, len(items)


def create_era(
    db: Session,
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    user: User,
    payload: EraCreate,
    request_id: str | None = None,
) -> Era:
    _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_UPDATE)
    record = Era(
        id=uuid.uuid4(),
        calendar_id=calendar_id,
        name=payload.name.strip(),
        start_day_index=payload.start_day_index,
        description=payload.description,
    )
    db.add(record)
    record_audit(
        db, universe_id, user.id, "era.created", "era", record.id,
        after_hash=state_hash({"name": record.name, "start_day_index": record.start_day_index}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "era.created", "era", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_era(
    db: Session,
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    era_id: uuid.UUID,
    user: User,
    payload: EraUpdate,
    request_id: str | None = None,
) -> Era:
    _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_UPDATE)
    record = db.scalar(
        select(Era).where(Era.id == era_id, Era.calendar_id == calendar_id)
    )
    if record is None:
        raise ApiError(404, "era_not_found", "The requested era does not exist.")
    if record.version != payload.expected_version:
        raise ApiError(409, "version_conflict", "The era changed; refresh before saving.")
    before = {"name": record.name, "start_day_index": record.start_day_index}
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for name, value in values.items():
        if name == "name" and value is not None:
            value = value.strip()
        setattr(record, name, value)
    record.version += 1
    record_audit(
        db, universe_id, user.id, "era.updated", "era", record.id,
        before_hash=state_hash(before),
        after_hash=state_hash({"name": record.name, "start_day_index": record.start_day_index}),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "era.updated", "era", record.id)
    db.commit()
    db.refresh(record)
    return record


def delete_era(
    db: Session,
    universe_id: uuid.UUID,
    calendar_id: uuid.UUID,
    era_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_UPDATE)
    record = db.scalar(
        select(Era).where(Era.id == era_id, Era.calendar_id == calendar_id)
    )
    if record is None:
        raise ApiError(404, "era_not_found", "The requested era does not exist.")
    record_audit(db, universe_id, user.id, "era.deleted", "era", record.id, request_id=request_id)
    record_activity(db, universe_id, user.id, "era.deleted", "era", record.id)
    db.delete(record)
    db.commit()


def list_events(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    *,
    calendar_id: uuid.UUID | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[TimelineEvent], int]:
    check_universe_access(db, universe_id, user, Action.TIMELINE_READ)
    stmt = select(TimelineEvent).where(TimelineEvent.universe_id == universe_id)
    count_stmt = select(func.count()).select_from(TimelineEvent).where(
        TimelineEvent.universe_id == universe_id
    )
    if calendar_id is not None:
        _get_calendar(db, universe_id, calendar_id, user, Action.TIMELINE_READ)
        stmt = stmt.where(TimelineEvent.calendar_id == calendar_id)
        count_stmt = count_stmt.where(TimelineEvent.calendar_id == calendar_id)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(TimelineEvent.title.ilike(pattern))
        count_stmt = count_stmt.where(TimelineEvent.title.ilike(pattern))
    items = list(
        db.scalars(
            stmt.order_by(TimelineEvent.start_day_index, TimelineEvent.title, TimelineEvent.id)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = db.scalar(count_stmt) or 0
    return items, total


def get_event(
    db: Session, universe_id: uuid.UUID, event_id: uuid.UUID, user: User
) -> TimelineEvent:
    check_universe_access(db, universe_id, user, Action.TIMELINE_READ)
    record = db.scalar(
        select(TimelineEvent).where(
            TimelineEvent.id == event_id,
            TimelineEvent.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "timeline_event_not_found", "The requested event does not exist.")
    return record


def create_event(
    db: Session,
    universe_id: uuid.UUID,
    user: User,
    payload: TimelineEventCreate,
    request_id: str | None = None,
) -> TimelineEvent:
    check_universe_access(db, universe_id, user, Action.TIMELINE_CREATE)
    calendar = _get_calendar(
        db, universe_id, payload.calendar_id, user, Action.TIMELINE_CREATE
    )
    _check_links(
        db,
        universe_id,
        user,
        payload.linked_entity_id,
        payload.linked_document_id,
    )
    start_index, end_index = event_day_window(
        _configuration(calendar),
        start_date=payload.start_date_json,
        end_date=payload.end_date_json,
        precision=payload.date_precision,
        uncertainty=payload.uncertainty_json,
    )
    record = TimelineEvent(
        id=uuid.uuid4(),
        universe_id=universe_id,
        calendar_id=calendar.id,
        title=payload.title.strip(),
        description=payload.description,
        start_date_json=payload.start_date_json.model_dump(mode="json"),
        end_date_json=(
            payload.end_date_json.model_dump(mode="json")
            if payload.end_date_json
            else None
        ),
        start_day_index=start_index,
        end_day_index=end_index,
        date_precision=payload.date_precision,
        uncertainty_json=payload.uncertainty_json,
        linked_entity_id=payload.linked_entity_id,
        linked_document_id=payload.linked_document_id,
        created_by=user.id,
    )
    db.add(record)
    record_audit(
        db,
        universe_id,
        user.id,
        "timeline_event.created",
        "timeline_event",
        record.id,
        after_hash=state_hash(
            {"title": record.title, "start_day_index": start_index, "end_day_index": end_index}
        ),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "timeline_event.created", "timeline_event", record.id)
    db.commit()
    db.refresh(record)
    return record


def update_event(
    db: Session,
    universe_id: uuid.UUID,
    event_id: uuid.UUID,
    user: User,
    payload: TimelineEventUpdate,
    request_id: str | None = None,
) -> TimelineEvent:
    check_universe_access(db, universe_id, user, Action.TIMELINE_UPDATE)
    record = db.scalar(
        select(TimelineEvent).where(
            TimelineEvent.id == event_id,
            TimelineEvent.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "timeline_event_not_found", "The requested event does not exist.")
    if record.version != payload.expected_version:
        raise ApiError(409, "version_conflict", "The timeline event changed; refresh before saving.")

    calendar = _get_calendar(
        db, universe_id, record.calendar_id, user, Action.TIMELINE_UPDATE
    )
    supplied = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    start_date = supplied.get(
        "start_date_json", CalendarDate.model_validate(record.start_date_json)
    )
    end_date = supplied.get(
        "end_date_json",
        CalendarDate.model_validate(record.end_date_json)
        if record.end_date_json is not None
        else None,
    )
    precision = supplied.get("date_precision", record.date_precision)
    uncertainty = supplied.get("uncertainty_json", record.uncertainty_json)
    validation_payload = TimelineEventCreate(
        calendar_id=record.calendar_id,
        title=supplied.get("title", record.title),
        description=supplied.get("description", record.description),
        start_date_json=start_date,
        end_date_json=end_date,
        date_precision=precision,
        uncertainty_json=uncertainty,
        linked_entity_id=supplied.get("linked_entity_id", record.linked_entity_id),
        linked_document_id=supplied.get("linked_document_id", record.linked_document_id),
    )
    _check_links(
        db,
        universe_id,
        user,
        validation_payload.linked_entity_id,
        validation_payload.linked_document_id,
    )
    start_index, end_index = event_day_window(
        _configuration(calendar),
        start_date=validation_payload.start_date_json,
        end_date=validation_payload.end_date_json,
        precision=validation_payload.date_precision,
        uncertainty=validation_payload.uncertainty_json,
    )
    before = {
        "title": record.title,
        "start_day_index": record.start_day_index,
        "end_day_index": record.end_day_index,
        "version": record.version,
    }
    record.title = validation_payload.title.strip()
    record.description = validation_payload.description
    record.start_date_json = validation_payload.start_date_json.model_dump(mode="json")
    record.end_date_json = (
        validation_payload.end_date_json.model_dump(mode="json")
        if validation_payload.end_date_json
        else None
    )
    record.start_day_index = start_index
    record.end_day_index = end_index
    record.date_precision = validation_payload.date_precision
    record.uncertainty_json = validation_payload.uncertainty_json
    record.linked_entity_id = validation_payload.linked_entity_id
    record.linked_document_id = validation_payload.linked_document_id
    record.version += 1
    record_audit(
        db,
        universe_id,
        user.id,
        "timeline_event.updated",
        "timeline_event",
        record.id,
        before_hash=state_hash(before),
        after_hash=state_hash(
            {
                "title": record.title,
                "start_day_index": record.start_day_index,
                "end_day_index": record.end_day_index,
                "version": record.version,
            }
        ),
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "timeline_event.updated", "timeline_event", record.id)
    db.commit()
    db.refresh(record)
    return record


def delete_event(
    db: Session,
    universe_id: uuid.UUID,
    event_id: uuid.UUID,
    user: User,
    request_id: str | None = None,
) -> None:
    check_universe_access(db, universe_id, user, Action.TIMELINE_DELETE)
    record = db.scalar(
        select(TimelineEvent).where(
            TimelineEvent.id == event_id,
            TimelineEvent.universe_id == universe_id,
        )
    )
    if record is None:
        raise ApiError(404, "timeline_event_not_found", "The requested event does not exist.")
    record_audit(
        db,
        universe_id,
        user.id,
        "timeline_event.deleted",
        "timeline_event",
        record.id,
        request_id=request_id,
    )
    record_activity(db, universe_id, user.id, "timeline_event.deleted", "timeline_event", record.id)
    db.delete(record)
    db.commit()
